from pathlib import Path

from desktop_agent.actions import Action, PlanResult
from desktop_agent.capabilities import CapabilityExecutor, build_capability_registry
from desktop_agent.config import AgentConfig
from desktop_agent.drivers import build_driver_registry
from desktop_agent.planner import TaskGraphPlanner
from desktop_agent.workflow import ExecutionState, StepProposal, WorldModel


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
    assert step.actions
    assert step.expected_evidence


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
