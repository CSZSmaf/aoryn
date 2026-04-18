from pathlib import Path

from desktop_agent.actions import Action, PlanResult
from desktop_agent.capabilities import CapabilityExecutor, build_capability_registry
from desktop_agent.config import AgentConfig
from desktop_agent.drivers import build_driver_registry
from desktop_agent.planner import TaskGraphPlanner
from desktop_agent.workflow import ExecutionState, StepProposal, Subgoal, VerificationResult, WorldModel


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
