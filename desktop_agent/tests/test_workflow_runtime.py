from pathlib import Path

from desktop_agent.actions import Action, PlanResult
from desktop_agent.capabilities import CapabilityExecutor, build_capability_registry
from desktop_agent.config import AgentConfig
from desktop_agent.drivers import build_driver_registry
from desktop_agent.orchestrator import TaskOrchestrator
from desktop_agent.planner import TaskGraphPlanner, classify_task_intent
from desktop_agent.recipes import TaskRecipeMemory, build_recipe_from_state
from desktop_agent.workflow import (
    ExecutionState,
    PendingDecision,
    StepProposal,
    Subgoal,
    TaskGraph,
    VerificationResult,
    WorldModel,
    build_execution_plan_summary,
)


class _PlannerStub:
    def plan(self, task, screenshot_path, history, environment=None):
        if "login" in task.lower():
            return PlanResult(
                status_summary="Click the login button.",
                done=True,
                actions=[Action.from_dict({"type": "browser_dom_click", "text": "Login"})],
            )
        return PlanResult(
            status_summary="Open the browser.",
            done=True,
            actions=[Action.from_dict({"type": "browser_open", "text": "https://openai.com"})],
        )


def test_task_graph_planner_splits_generic_multi_step_task():
    planner = TaskGraphPlanner(AgentConfig())

    graph = planner.plan("open browser and search for python packaging guide and bookmark the best page")

    assert graph.task == "open browser and search for python packaging guide and bookmark the best page"
    assert len(graph.subgoals) >= 2
    assert graph.subgoals[0].id == "subgoal_01"
    assert graph.subgoals[0].success_condition
    assert graph.dependencies.get("subgoal_01") == []
    assert graph.dependencies.get("subgoal_02") == ["subgoal_01"]
    assert graph.completion_summary


def test_task_graph_planner_keeps_plain_chinese_search_as_search_goal():
    planner = TaskGraphPlanner(AgentConfig())

    graph = planner.plan("搜索体育方面新闻")

    assert len(graph.subgoals) == 1
    assert graph.subgoals[0].title == "search for 体育方面新闻"
    assert "shopping" not in graph.subgoals[0].title.lower()


def test_task_intent_classifies_plain_chinese_search_as_information_search():
    intent = classify_task_intent("\u641c\u7d22\u4f53\u80b2\u65b9\u9762\u65b0\u95fb")

    assert intent.task_type == "information_search"
    assert intent.domain == "web"
    assert "browser_dom" in intent.preferred_capabilities
    assert intent.requires_clarification is False


def test_task_intent_classifies_explicit_chinese_shopping():
    intent = classify_task_intent(
        "\u5728\u8d2d\u7269\u7f51\u7ad9\u641c\u7d22\u9ad8\u6027\u4ef7\u6bd4\u7537\u6027\u88e4\u5b50"
    )

    assert intent.task_type == "shopping"
    assert intent.domain == "web"
    assert intent.risk_level == "medium"


def test_task_graph_planner_splits_research_summary_goal():
    planner = TaskGraphPlanner(AgentConfig())

    graph = planner.plan("\u641c\u7d22\u4f53\u80b2\u65b9\u9762\u65b0\u95fb\u5e76\u603b\u7ed3\u4e09\u6761")

    assert graph.intent["task_type"] == "research_summary"
    assert len(graph.subgoals) == 2
    assert graph.subgoals[0].title == "search for \u4f53\u80b2\u65b9\u9762\u65b0\u95fb"
    assert "\u603b\u7ed3" in graph.subgoals[1].title
    assert graph.subgoals[1].prerequisites == ["subgoal_01"]


def test_task_graph_planner_marks_ambiguous_task_for_clarification():
    planner = TaskGraphPlanner(AgentConfig())

    graph = planner.plan("\u5904\u7406\u4e00\u4e0b")

    assert graph.intent["requires_clarification"] is True
    assert graph.subgoals[0].goal_type == "clarify"
    assert graph.subgoals[0].retry_budget == 0


def test_task_graph_planner_limits_long_workflows_to_stage_goals():
    planner = TaskGraphPlanner(AgentConfig(complex_task_planning="heuristic", max_task_subgoals=4))

    graph = planner.plan(
        "open browser then search for release notes then copy the result then open notepad "
        "then paste the summary then save the note then close the window"
    )

    assert len(graph.subgoals) == 4
    assert graph.subgoals[-1].title.startswith("Complete remaining requested work:")
    assert all(subgoal.capability_preference for subgoal in graph.subgoals)
    assert all(subgoal.completion_evidence for subgoal in graph.subgoals)


def test_task_graph_planner_handles_cross_app_research_write_workflow():
    planner = TaskGraphPlanner(AgentConfig(complex_task_planning="heuristic"))

    graph = planner.plan("\u641c\u7d22\u4f53\u80b2\u65b9\u9762\u65b0\u95fb\u5e76\u603b\u7ed3\u4e09\u6761\u7136\u540e\u5199\u5165\u8bb0\u4e8b\u672c")

    assert graph.intent["task_type"] in {"research_summary", "multi_step_workflow"}
    assert len(graph.subgoals) >= 2
    assert graph.subgoals[0].capability_preference == "browser_dom"
    assert any("\u603b\u7ed3" in subgoal.title or "write" in subgoal.title.lower() for subgoal in graph.subgoals)


def test_pending_decision_round_trips_decision_type():
    from desktop_agent.workflow import PendingDecision

    decision = PendingDecision.from_dict(
        {
            "id": "plan-1",
            "summary": "Review plan",
            "reason": "The plan is medium risk.",
            "risk_level": "medium",
            "decision_type": "plan_review",
        }
    )

    assert decision.decision_type == "plan_review"
    assert decision.to_dict()["decision_type"] == "plan_review"


def test_pending_decision_accepts_stage_review_type():
    decision = PendingDecision.from_dict(
        {
            "id": "stage-1",
            "summary": "Review replanned stage",
            "reason": "Risk increased after recovery.",
            "risk_level": "high",
            "decision_type": "stage_review",
        }
    )

    assert decision.decision_type == "stage_review"
    assert decision.to_dict()["decision_type"] == "stage_review"


def test_execution_state_round_trips_workspace_and_orchestration_fields():
    graph = TaskGraphPlanner(AgentConfig()).plan("search documentation and summarize it")
    state = ExecutionState(task=graph.task, run_id="demo", task_graph=graph)
    state.orchestration_phase = "stage_ready"
    state.active_specialist = "browser_research"
    state.failure_budget = {"subgoal_01": 2}
    state.last_replan_reason = "selector became stale"
    state.workspace.add_note("Collected source candidates.")
    state.workspace.add_evidence({"subgoal_id": "subgoal_01", "status": "success", "specialist": "browser_research"})

    restored = ExecutionState.from_dict(state.to_dict())
    summary = build_execution_plan_summary(restored)

    assert restored.orchestration_phase == "stage_ready"
    assert restored.active_specialist == "browser_research"
    assert restored.failure_budget["subgoal_01"] == 2
    assert restored.workspace.notes == ["Collected source candidates."]
    assert summary["workspace_summary"]["evidence"][0]["specialist"] == "browser_research"
    assert summary["last_replan_reason"] == "selector became stale"


def test_capability_executor_prefers_browser_capability_for_web_subgoal():
    config = AgentConfig()
    graph = TaskGraphPlanner(config).plan("visit openai.com and click login")
    state = ExecutionState(task=graph.task, run_id="demo", task_graph=graph)
    world_model = WorldModel(
        screenshot_path=Path("demo.png"),
        browser_snapshot={"url": "https://openai.com", "title": "OpenAI", "text": "Login"},
        active_app="browser",
        active_window_title="Microsoft Edge",
    )
    state.world_model = world_model
    executor = CapabilityExecutor(
        config=config,
        planner=_PlannerStub(),
        registry=build_capability_registry(),
        driver_registry=build_driver_registry(),
    )

    step = executor.propose_step(execution_state=state, world_model=world_model)

    assert step.capability == "browser_dom"
    assert step.surface_kind == "managed_aoryn_browser"
    assert step.actions
    assert step.expected_evidence
    assert step.progress_signals
    assert step.repair_strategy
    assert step.primary_anchor is not None
    assert step.fallback_anchors
    assert step.rationale
    assert "desktop_gui" in step.fallbacks
    assert state.app_context["capability_ranking"][0]["name"] == "browser_dom"


def test_step_proposal_tracks_subgoal_completion_from_plan_result():
    plan = PlanResult(
        status_summary="Open the browser.",
        done=True,
        actions=[Action.from_dict({"type": "open_app_if_needed", "app": "browser"})],
    )

    proposal = StepProposal.from_plan_result(plan, capability="desktop_gui")

    assert proposal.completes_subgoal is True
    assert proposal.to_plan_result(done=proposal.completes_subgoal).done is True


def test_capability_executor_marks_guarded_shell_recipe_as_approval_required():
    config = AgentConfig()
    graph = TaskGraphPlanner(config).plan("configure a python environment")
    state = ExecutionState(task=graph.task, run_id="demo", task_graph=graph)
    world_model = WorldModel(screenshot_path=Path("demo.png"), active_window_title="Visual Studio Code")
    state.world_model = world_model
    executor = CapabilityExecutor(
        config=config,
        planner=_PlannerStub(),
        registry=build_capability_registry(),
        driver_registry=build_driver_registry(),
    )

    step = executor.propose_step(execution_state=state, world_model=world_model)

    assert step.requires_approval is True
    assert any(action.type == "shell_recipe_request" for action in step.actions)


def test_verification_without_completion_evidence_does_not_auto_succeed():
    config = AgentConfig()
    executor = CapabilityExecutor(
        config=config,
        planner=_PlannerStub(),
        registry=build_capability_registry(),
        driver_registry=build_driver_registry(),
    )
    subgoal = Subgoal(
        id="subgoal_01",
        title="confirm the page changed",
        goal="confirm the page changed",
        goal_type="confirm",
        success_condition="The page visibly changes.",
        completion_evidence={"kind": "state_change", "detail": "A visible state change confirms the subgoal."},
    )
    state = ExecutionState(task="confirm the page changed", run_id="demo", task_graph=TaskGraphPlanner(config).plan("confirm the page changed"))
    state.task_graph.subgoals = [subgoal]
    before = WorldModel(screenshot_path=Path("before.png"), active_window_title="Browser", active_app="browser")
    after = WorldModel(screenshot_path=Path("after.png"), active_window_title="Browser", active_app="browser")
    step = StepProposal(
        intent="Wait for confirmation.",
        actions=[Action.from_dict({"type": "wait", "seconds": 0.1})],
        capability="desktop_gui",
        completes_subgoal=True,
    )

    result = executor.verify_step(execution_state=state, step=step, before=before, after=after)

    assert result.status == "failed"
    assert result.success is False


def test_capability_ranking_penalizes_recent_failures():
    config = AgentConfig()
    graph = TaskGraphPlanner(config).plan("visit openai.com and click login")
    state = ExecutionState(task=graph.task, run_id="demo", task_graph=graph)
    world_model = WorldModel(
        screenshot_path=Path("demo.png"),
        browser_snapshot={"url": "https://openai.com", "title": "OpenAI", "text": "Login"},
        active_app="browser",
        active_window_title="Microsoft Edge",
        structured_sources=["browser_dom"],
    )
    state.capability_failures["subgoal_01:browser_dom"] = ["failed", "partial_progress"]
    executor = CapabilityExecutor(
        config=config,
        planner=_PlannerStub(),
        registry=build_capability_registry(),
        driver_registry=build_driver_registry(),
    )

    ranked = executor.rank_capabilities(
        subgoal=graph.subgoals[0],
        world_model=world_model,
        execution_state=state,
    )
    scores = {cap.name: score for cap, score in ranked}

    assert scores["browser_dom"] < 1.05


def test_orchestrator_routes_specialist_and_requests_stage_review_after_risk_increase():
    config = AgentConfig(stage_review_policy="risk_change")

    class _GraphPlanner:
        def plan(self, task, history=None, world_model=None):
            return TaskGraph(
                task=task,
                subgoals=[
                    Subgoal(
                        id="subgoal_01",
                        title="Search product details",
                        goal_type="read",
                        capability_preference="browser_dom",
                        risk_level="low",
                    )
                ],
                dependencies={"subgoal_01": []},
                intent={"task_type": "information_search", "risk_level": "low", "ambiguity": "low"},
            )

        def replan_remaining(self, execution_state, world_model, failure):
            graph = execution_state.task_graph
            graph.subgoals[0].title = "Submit the recovered form"
            graph.subgoals[0].goal = "Submit the recovered form"
            graph.subgoals[0].risk_level = "high"
            graph.risk_points = ["Submit the recovered form"]
            graph.intent = {"task_type": "multi_step_workflow", "risk_level": "high", "ambiguity": "low"}
            return graph

    class _CapabilityExecutor:
        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            return StepProposal(intent="Search the page.", capability="browser_dom")

    orchestrator = TaskOrchestrator(
        config=config,
        task_graph_planner=_GraphPlanner(),
        capability_executor=_CapabilityExecutor(),
        recipe_memory=TaskRecipeMemory(path=Path("test_artifacts") / "unused-recipes.json"),
    )
    world_model = WorldModel(browser_snapshot={"url": "https://example.com", "title": "Example"})
    state = orchestrator.initialize_state(task="search product details", run_id="demo", world_model=world_model)

    assert state.active_specialist == "browser_research"

    changed = orchestrator.replan_remaining(
        state=state,
        world_model=world_model,
        failure=VerificationResult(success=False, status="failed", failure_kind="blocked_by_ui", message="popup"),
    )

    assert changed is True
    assert state.app_context["stage_review_status"] == "pending"
    assert orchestrator.pending_review_type(state) == "stage_review"
    assert state.last_replan_reason == "popup"


def test_recipe_records_specialist_sequence_and_sanitizes_summary():
    graph = TaskGraphPlanner(AgentConfig()).plan("search docs and summarize them")
    state = ExecutionState(task=graph.task, run_id="demo", task_graph=graph)
    state.completed = True
    for subgoal in state.task_graph.subgoals:
        subgoal.status = "completed"
    state.task_graph.completion_summary = "Saved summary from https://secret.example/token abcdefghijklmnopqrstuvwxyz123456"
    state.evidence_ledger.append(
        {
            "subgoal_id": "subgoal_01",
            "capability": "browser_dom",
            "status": "success",
            "evidence": [{"kind": "browser_text_contains"}],
        }
    )
    state.workspace.add_evidence(
        {
            "subgoal_id": "subgoal_01",
            "specialist": "browser_research",
            "capability": "browser_dom",
            "status": "success",
        }
    )

    recipe = build_recipe_from_state(state)

    assert recipe is not None
    assert recipe.specialist_sequence == ["browser_research"]
    assert recipe.verified_evidence_kinds == ["browser_text_contains"]
    assert "<url>" in (recipe.summary or "")
    assert "abcdefghijklmnopqrstuvwxyz123456" not in (recipe.summary or "")
