import json

import desktop_agent.planner as planner_module
from desktop_agent.config import AgentConfig
from desktop_agent.controller import build_agent
from desktop_agent.executor import MockExecutor
from desktop_agent.planner import (
    TaskGraphPlanner,
    _extract_deliverable_plan,
    classify_task_intent,
)
from desktop_agent.workflow import ExecutionState, StepProposal, Subgoal, TaskGraph, WorldModel


def _heuristic_planner() -> TaskGraphPlanner:
    return TaskGraphPlanner(AgentConfig(complex_task_planning="heuristic"))


def test_extract_deliverable_plan_expands_chinese_report():
    plan = _extract_deliverable_plan("写一份关于电动汽车的报告")
    assert plan is not None
    assert len(plan) == 2
    assert "电动汽车" in plan[0]  # research step
    assert plan[1].startswith("撰写")  # author step


def test_extract_deliverable_plan_expands_trip_with_cjk_numeral():
    plan = _extract_deliverable_plan("规划一个北京三日游")
    assert plan is not None
    assert "北京三日游" in plan[0]
    assert plan[1].startswith("撰写")


def test_extract_deliverable_plan_expands_english_deliverable():
    plan = _extract_deliverable_plan("create a study plan for calculus")
    assert plan is not None
    assert plan[0] == "search for calculus"
    assert plan[1] == "write the calculus plan"


def test_extract_deliverable_plan_skips_non_deliverables():
    assert _extract_deliverable_plan("calculate 2+2") is None
    assert _extract_deliverable_plan("open notepad") is None
    # multi-step tasks with connectors are handled by the normal splitter
    assert _extract_deliverable_plan("打开记事本并输入demo") is None
    # explicit browser/search tasks are owned by the web agent, not the deliverable planner
    from desktop_agent.web_agent import WebAgent

    bc = WebAgent().parse("search for OpenAI desktop agent")
    assert _extract_deliverable_plan("search for OpenAI desktop agent", bc) is None


def test_task_graph_autoplans_deliverable_into_research_then_author():
    for task in [
        "写一份关于电动汽车的报告",
        "规划一个北京三日游",
        "做一个Python学习计划",
        "create a study plan for calculus",
        "整理一份机器学习入门指南",
    ]:
        graph = _heuristic_planner().plan(task)
        assert len(graph.subgoals) == 2, task
        assert graph.subgoals[0].capability_preference == "browser_dom", task
        assert graph.subgoals[1].capability_preference == "document_authoring", task
        # the author subgoal depends on the research subgoal
        assert graph.subgoals[0].id in graph.subgoals[1].prerequisites, task


def test_task_graph_leaves_plain_app_tasks_unchanged():
    graph = _heuristic_planner().plan("calculate 2+2")
    assert all(
        subgoal.capability_preference != "document_authoring" for subgoal in graph.subgoals
    )


def test_classify_intent_marks_deliverable_as_research_summary():
    intent = classify_task_intent("写一份关于新能源汽车的报告")
    assert intent.task_type == "research_summary"
    assert "document_authoring" in intent.preferred_capabilities
    assert "browser_dom" in intent.preferred_capabilities
    assert intent.planning_strategy == "model_assisted"
    assert not intent.requires_clarification


def test_agent_autonomously_researches_then_authors_a_document():
    # composition_enabled=False forces the deterministic composer (no network),
    # and heuristic planning keeps decomposition deterministic.
    config = AgentConfig(
        dry_run=True,
        complex_task_planning="heuristic",
        composition_enabled=False,
        plan_reflection_enabled=False,  # keep this test deterministic (no model call)
    )
    agent = build_agent(config)

    result = agent.run("写一份关于电动汽车的报告")

    assert result.completed is True, result.error
    executor = agent.executor
    assert isinstance(executor, MockExecutor)
    # the agent autonomously opened the browser to research...
    assert "browser" in executor.state.open_apps
    # ...and wrote a real, structured document into whichever editor it chose.
    document = next(
        (
            executor.state.text_buffers[app]
            for app in ("word", "notepad", "wps")
            if executor.state.text_buffers.get(app)
        ),
        "",
    )
    assert len(document) > 80
    assert "概述" in document or "Overview" in document


# ----- model-driven adaptive re-planning (reflection) -----

_INSERTED = "搜索电动汽车充电桩分布"


def _research_then_author_state() -> ExecutionState:
    research = Subgoal(
        id="subgoal_01", title="搜索电动汽车", goal_type="navigate",
        status="completed", capability_preference="browser_dom",
    )
    author = Subgoal(
        id="subgoal_02", title="撰写电动汽车报告", goal_type="fill",
        status="pending", capability_preference="document_authoring", prerequisites=["subgoal_01"],
    )
    graph = TaskGraph(
        task="写一份关于电动汽车的报告",
        subgoals=[research, author],
        dependencies={"subgoal_01": [], "subgoal_02": ["subgoal_01"]},
        intent={"task_type": "research_summary"},
    )
    state = ExecutionState(task=graph.task, run_id="r", task_graph=graph)
    state.workspace.add_note("[web] 电动汽车 续航 充电 政策")
    return state


def _stub_model(monkeypatch, subgoals):
    monkeypatch.setattr(planner_module, "_task_graph_model_endpoint_available", lambda config: True)
    monkeypatch.setattr(planner_module, "_request_task_graph_text", lambda **kwargs: json.dumps({"subgoals": subgoals}))


def test_reflect_on_plan_inserts_model_suggested_step(monkeypatch):
    _stub_model(monkeypatch, [
        {"title": _INSERTED, "goal_type": "navigate", "success_condition": "found", "capability_preference": "browser_dom", "risk_level": "low"},
        {"title": "撰写电动汽车报告", "goal_type": "fill", "success_condition": "written", "capability_preference": "document_authoring", "risk_level": "low"},
    ])
    planner = TaskGraphPlanner(AgentConfig(model_name="test-model"))
    new_graph = planner.reflect_on_plan(_research_then_author_state(), WorldModel())
    assert new_graph is not None
    titles = [s.title for s in new_graph.subgoals]
    assert titles[0] == "搜索电动汽车"  # completed step preserved
    assert _INSERTED in titles  # model inserted an extra research step
    assert titles[-1] == "撰写电动汽车报告"
    assert new_graph.subgoals[0].status == "completed"


def test_reflect_on_plan_returns_none_when_unchanged(monkeypatch):
    _stub_model(monkeypatch, [
        {"title": "撰写电动汽车报告", "goal_type": "fill", "success_condition": "written", "capability_preference": "document_authoring", "risk_level": "low"},
    ])
    planner = TaskGraphPlanner(AgentConfig(model_name="test-model"))
    assert planner.reflect_on_plan(_research_then_author_state(), WorldModel()) is None


def test_reflect_on_plan_offline_returns_none(monkeypatch):
    monkeypatch.setattr(planner_module, "_task_graph_model_endpoint_available", lambda config: False)
    planner = TaskGraphPlanner(AgentConfig(model_name="test-model"))
    assert planner.reflect_on_plan(_research_then_author_state(), WorldModel()) is None


def test_orchestrator_reflection_respects_budget_and_disabled(monkeypatch):
    _stub_model(monkeypatch, [
        {"title": _INSERTED, "goal_type": "navigate", "success_condition": "found", "capability_preference": "browser_dom", "risk_level": "low"},
        {"title": "撰写电动汽车报告", "goal_type": "fill", "success_condition": "written", "capability_preference": "document_authoring", "risk_level": "low"},
    ])
    disabled = build_agent(AgentConfig(model_name="test-model", plan_reflection_enabled=False))
    assert disabled.orchestrator.reflect_on_plan(state=_research_then_author_state(), world_model=WorldModel()) is False

    agent = build_agent(AgentConfig(model_name="test-model", plan_reflection_enabled=True, max_plan_reflections=1))
    state = _research_then_author_state()
    assert agent.orchestrator.reflect_on_plan(state=state, world_model=WorldModel()) is True
    assert state.app_context.get("reflection_count") == 1
    assert any(s.title == _INSERTED for s in state.task_graph.subgoals)
    # budget of 1 is now exhausted
    assert agent.orchestrator.reflect_on_plan(state=state, world_model=WorldModel()) is False


def test_controller_reflection_trigger_gating():
    agent = build_agent(AgentConfig(model_name="test-model"))
    state = _research_then_author_state()
    research = state.task_graph.subgoals[0]
    browser_step = StepProposal(intent="searched", capability="browser_dom")
    assert agent._should_reflect_after_subgoal(execution_state=state, subgoal=research, step_proposal=browser_step) is True
    # not a research_summary goal -> no reflection
    state.task_graph.intent = {"task_type": "information_search"}
    assert agent._should_reflect_after_subgoal(execution_state=state, subgoal=research, step_proposal=browser_step) is False


# ----- model-first initial planning routing -----

from desktop_agent.planner import _should_use_structured_task_graph  # noqa: E402
from desktop_agent.web_agent import WebAgent  # noqa: E402


def _routes_to_model(task, config):
    bc = WebAgent().parse(task)
    intent = classify_task_intent(task, browser_command=bc)
    return _should_use_structured_task_graph(config=config, task=task, intent=intent, browser_command=bc)


def test_model_first_routes_nontrivial_tasks_to_model(monkeypatch):
    monkeypatch.setattr(planner_module, "_task_graph_model_endpoint_available", lambda config: True)
    config = AgentConfig()  # hybrid
    # trivial, deterministic single actions stay on the fast heuristic path
    for task in ["open notepad", "calculate 2+2", "search for OpenAI", "visit openai.com", "shop for pants on amazon"]:
        assert _routes_to_model(task, config) is False, task
    # non-trivial tasks go to the model — including novel ones with no keyword match
    for task in [
        "open notepad and type demo",
        "search openai.com and click login",
        "写一份关于电动汽车的报告",
        "帮我对比三款笔记软件并给出建议",
        "总结今天的科技新闻",
    ]:
        assert _routes_to_model(task, config) is True, task


def test_model_first_routing_falls_back_to_heuristic_offline(monkeypatch):
    monkeypatch.setattr(planner_module, "_task_graph_model_endpoint_available", lambda config: False)
    assert _routes_to_model("帮我对比三款笔记软件并给出建议", AgentConfig()) is False


def test_heuristic_mode_never_uses_model(monkeypatch):
    monkeypatch.setattr(planner_module, "_task_graph_model_endpoint_available", lambda config: True)
    assert _routes_to_model("帮我对比三款笔记软件并给出建议", AgentConfig(complex_task_planning="heuristic")) is False


# ----- deeper research: search -> extract page content -> grounded notes -----

from desktop_agent.capabilities import BrowserDOMCapability  # noqa: E402
from desktop_agent.orchestrator import _accumulate_research_notes  # noqa: E402


def _deliverable_research_state():
    research = Subgoal(id="subgoal_01", title="搜索电动汽车", goal_type="navigate", status="in_progress", capability_preference="browser_dom")
    author = Subgoal(id="subgoal_02", title="撰写电动汽车报告", goal_type="fill", status="pending", capability_preference="document_authoring", prerequisites=["subgoal_01"])
    graph = TaskGraph(task="写一份关于电动汽车的报告", subgoals=[research, author], dependencies={"subgoal_01": [], "subgoal_02": ["subgoal_01"]})
    return ExecutionState(task=graph.task, run_id="r", task_graph=graph), research


_RESULTS_WM = WorldModel(browser_snapshot={"url": "https://www.google.com/search?q=ev", "text": "电动汽车 结果"})


def test_browser_research_searches_then_extracts_when_feeding_author():
    cap = BrowserDOMCapability()
    config = AgentConfig()
    state, research = _deliverable_research_state()
    # no results yet -> search, but DON'T complete the subgoal (we still want to read)
    step1 = cap.propose_step(subgoal=research, world_model=WorldModel(), execution_state=state, config=config, planner=None)
    assert step1 is not None and step1.actions[0].type == "browser_search"
    assert step1.completes_subgoal is False
    # results visible -> read the page content, completing the research
    step2 = cap.propose_step(subgoal=research, world_model=_RESULTS_WM, execution_state=state, config=config, planner=None)
    assert step2 is not None and step2.actions[0].type == "browser_dom_extract"
    assert step2.completes_subgoal is True


def test_browser_research_skips_deep_extract_for_standalone_search():
    cap = BrowserDOMCapability()
    config = AgentConfig()
    research = Subgoal(id="subgoal_01", title="搜索电动汽车", goal_type="navigate", status="in_progress", capability_preference="browser_dom")
    state = ExecutionState(task="搜索电动汽车", run_id="r", task_graph=TaskGraph(task="搜索电动汽车", subgoals=[research]))
    step = cap.propose_step(subgoal=research, world_model=_RESULTS_WM, execution_state=state, config=config, planner=None)
    # no downstream consumer -> normal web flow, never a deep extract
    assert step is None or step.actions[0].type != "browser_dom_extract"


def test_research_extract_disabled_skips_extraction():
    cap = BrowserDOMCapability()
    config = AgentConfig(research_extract_enabled=False)
    state, research = _deliverable_research_state()
    step = cap.propose_step(subgoal=research, world_model=_RESULTS_WM, execution_state=state, config=config, planner=None)
    assert step is None or step.actions[0].type != "browser_dom_extract"


def test_accumulate_research_notes_captures_extracted_page_text():
    state = ExecutionState(task="t", run_id="r", task_graph=TaskGraph(task="t", subgoals=[Subgoal(id="s", title="t")]))
    wm = WorldModel(browser_snapshot={"url": "https://x.test", "text": "snippet", "extracted_text": "full article body about electric vehicles"})
    _accumulate_research_notes(state, wm)
    assert any(n.startswith("[extract]") and "full article body" in n for n in state.workspace.notes)


def test_deliverable_topic_strips_descriptive_words():
    # adjectives describing the deliverable ("简短/详细/简单") and the noun must not
    # leak into the research query.
    assert _extract_deliverable_plan("帮我写一份关于电动汽车未来发展趋势的简短报告")[0] == "搜索电动汽车未来发展趋势"
    assert _extract_deliverable_plan("写一份详细的人工智能行业报告")[0] == "搜索人工智能行业"
    assert _extract_deliverable_plan("write a detailed AI industry report")[0] == "search for AI industry"


def test_model_capability_preference_list_is_normalized():
    from desktop_agent.planner import _coerce_model_capability_preference
    # models sometimes return a list; take the first concrete capability name
    assert _coerce_model_capability_preference(["browser_dom", "clipboard"]) == "browser_dom"
    assert _coerce_model_capability_preference("document_authoring") == "document_authoring"
    assert _coerce_model_capability_preference([]) is None
    assert _coerce_model_capability_preference(None) is None
