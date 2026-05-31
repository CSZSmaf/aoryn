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
