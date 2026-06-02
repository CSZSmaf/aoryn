import json
import shutil
import sys
import time
import os
from types import SimpleNamespace
from pathlib import Path
from uuid import uuid4

from desktop_agent.actions import Action, PlanResult
from desktop_agent.config import AgentConfig
import desktop_agent.controller as controller
from desktop_agent.controller import DesktopAgent, _build_history_entry
from desktop_agent.executor import ExecutionCancelled, ExecutionError
from desktop_agent.logger import RunLogger
from desktop_agent.perception import ScreenInfo
from desktop_agent.safety import ActionGuard
from desktop_agent.workflow import (
    ExecutionState,
    PendingDecision,
    StepProposal,
    Subgoal,
    TaskGraph,
    VerificationResult,
    build_execution_plan_summary,
)
from desktop_agent.windows_env import DesktopEnvironment, MonitorSnapshot, Rect


class _PerceptionStub:
    def capture(self, output_path: Path) -> ScreenInfo:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-png")
        return ScreenInfo(
            width=1280,
            height=720,
            environment=DesktopEnvironment(
                platform="windows",
                virtual_bounds=Rect(0, 0, 1280, 720),
                monitors=[
                    MonitorSnapshot(
                        device_name="DISPLAY1",
                        is_primary=True,
                        bounds=Rect(0, 0, 1280, 720),
                        work_area=Rect(0, 0, 1280, 680),
                    )
                ],
            ),
        )


class _ExecutorStub:
    def __init__(self) -> None:
        self.executed_batches = 0

    def execute_many(self, actions, pause_after_action, stop_requested=None):
        self.executed_batches += 1

    def browser_snapshot(self):
        return None


class _RepeatingPlanner:
    def plan(self, task, screenshot_path, history, environment=None):
        return PlanResult(
            status_summary="Open Calculator again.",
            done=False,
            actions=[Action.from_dict({"type": "launch_app", "app": "calculator"})],
        )


class _TwoStepPlanner:
    def plan(self, task, screenshot_path, history, environment=None):
        return PlanResult(
            status_summary="Keep going.",
            done=False,
            actions=[Action.from_dict({"type": "wait", "seconds": 0.1})],
        )


class _RecoveringPlanner:
    def plan(self, task, screenshot_path, history, environment=None):
        if any("Error:" in entry for entry in history):
            return PlanResult(
                status_summary="Recovered and ready to finish.",
                done=True,
                current_focus="finish the recovered step",
                actions=[Action.from_dict({"type": "wait", "seconds": 0.1})],
            )
        return PlanResult(
            status_summary="Focus Calculator first.",
            done=False,
            current_focus="focus calculator",
            actions=[Action.from_dict({"type": "focus_window", "title": "Calculator"})],
        )


def test_desktop_agent_marks_repeated_failed_attempts_as_stuck():
    scratch_root = Path("test_artifacts") / f"controller_repeat_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)

    try:
        config = AgentConfig(dry_run=False, max_steps=6, run_root=run_root)
        executor = _ExecutorStub()
        agent = DesktopAgent(
            config=config,
            planner=_RepeatingPlanner(),
            executor=executor,
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
        )

        result = agent.run("open calculator forever")

        assert result.completed is False
        assert result.cancelled is False
        assert "became stuck" in (result.error or "")
        assert executor.executed_batches >= 2
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_stops_repeated_visible_steps_before_third_retry():
    scratch_root = Path("test_artifacts") / f"controller_visible_loop_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)

    class _VisibleLoopCapabilityExecutor:
        def __init__(self) -> None:
            self.calls = 0

        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            self.calls += 1
            return StepProposal(
                intent="Search the web for openai.",
                actions=[Action.from_dict({"type": "click", "x": 400 + self.calls, "y": 320})],
                capability="browser_gui",
                current_focus="search for openai",
                completes_subgoal=False,
            )

        def verify_step(self, execution_state, step, before, after):
            return VerificationResult(
                success=False,
                status="failed",
                failure_kind="blocked_by_ui",
                message="The page did not advance.",
            )

    try:
        config = AgentConfig(dry_run=False, max_steps=6, run_root=run_root)
        executor = _ExecutorStub()
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=executor,
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            capability_executor=_VisibleLoopCapabilityExecutor(),
        )

        result = agent.run("search the web for openai")

        assert result.completed is False
        assert result.cancelled is False
        assert "execution loop" in (result.error or "")
        assert executor.executed_batches == 2
        assert result.steps == 3
        state_payload = json.loads((result.run_dir / "execution_state.json").read_text(encoding="utf-8"))
        subgoal_payload = state_payload["task_graph"]["subgoals"][0]
        assert result.execution_state is not None
        assert result.execution_state["orchestration_phase"] == "blocked"
        assert result.execution_state["plan_health"]["items"][0]["status"] == "blocked"
        assert state_payload["orchestration_phase"] == "blocked"
        assert state_payload["failure_budget"][subgoal_payload["id"]] == 0
        assert subgoal_payload["status"] == "blocked"
        assert subgoal_payload["attempts"] == 3
        assert state_payload["app_context"]["recovery_reason"] == result.error
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_blocks_when_task_graph_has_no_ready_subgoal():
    scratch_root = Path("test_artifacts") / f"controller_blocked_graph_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)

    class _BlockedTaskGraphPlanner:
        def plan(self, task, history=None, world_model=None):
            return TaskGraph(
                task=task,
                subgoals=[
                    Subgoal(
                        id="subgoal_01",
                        title="Finish a step with an unavailable prerequisite",
                        goal="Finish a step with an unavailable prerequisite",
                        success_condition="The unavailable prerequisite is satisfied first.",
                        prerequisites=["missing_prerequisite"],
                    )
                ],
                dependencies={"subgoal_01": ["missing_prerequisite"]},
                intent={"task_type": "multi_step_workflow", "risk_level": "low", "ambiguity": "low"},
            )

        def replan_remaining(self, execution_state, world_model, failure):
            return execution_state.task_graph

    class _BlockedGraphCapabilityExecutor:
        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            raise AssertionError("Blocked graphs must not propose executable steps.")

    try:
        config = AgentConfig(dry_run=False, max_steps=2, run_root=run_root)
        executor = _ExecutorStub()
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=executor,
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            task_graph_planner=_BlockedTaskGraphPlanner(),
            capability_executor=_BlockedGraphCapabilityExecutor(),
        )

        result = agent.run("complete a graph with missing prerequisites")

        assert result.completed is False
        assert executor.executed_batches == 0
        assert "blocked" in (result.error or "")
        assert "missing_prerequisite" in (result.error or "")
        step_payload = json.loads((result.run_dir / "step_01.json").read_text(encoding="utf-8"))
        assert step_payload["error"] == result.error
        state_payload = json.loads((result.run_dir / "state.json").read_text(encoding="utf-8"))
        assert state_payload["completed"] is False
        assert state_payload["orchestration_phase"] == "blocked"
        assert state_payload["verification_status"] == "failed"
        full_state = json.loads((result.run_dir / "execution_state.json").read_text(encoding="utf-8"))
        assert full_state["completed"] is False
        assert full_state["task_graph"]["subgoals"][0]["status"] == "pending"
        summary_payload = json.loads((result.run_dir / "summary.json").read_text(encoding="utf-8"))
        assert summary_payload["completed"] is False
        assert summary_payload["error"] == result.error
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_uses_initial_task_graph_without_replanning():
    scratch_root = Path("test_artifacts") / f"controller_initial_graph_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)

    class _ForbiddenTaskGraphPlanner:
        def plan(self, task, history=None, world_model=None):
            raise AssertionError("The preview task graph should be used instead of replanning.")

        def replan_remaining(self, execution_state, world_model, failure):
            return execution_state.task_graph

    class _PreviewCapabilityExecutor:
        def __init__(self) -> None:
            self.proposed_subgoals: list[str] = []

        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            subgoal = execution_state.current_subgoal()
            assert subgoal is not None
            self.proposed_subgoals.append(subgoal.id)
            return StepProposal(
                intent="Complete the previewed subgoal.",
                actions=[Action.from_dict({"type": "wait", "seconds": 0.1})],
                capability="desktop_gui",
                completes_subgoal=True,
            )

        def verify_step(self, execution_state, step, before, after):
            return VerificationResult(success=True, status="success", evidence=[{"kind": "state", "value": "preview-done"}])

    try:
        config = AgentConfig(dry_run=False, max_steps=2, run_root=run_root)
        initial_graph = TaskGraph(
            task="complete the previewed plan",
            subgoals=[
                Subgoal(
                    id="preview_01",
                    title="Do the exact previewed work",
                    goal="Do the exact previewed work",
                    success_condition="The previewed work is done.",
                )
            ],
            dependencies={"preview_01": []},
            intent={"task_type": "desktop_app", "risk_level": "low", "ambiguity": "low"},
        )
        capability_executor = _PreviewCapabilityExecutor()
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=_ExecutorStub(),
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            task_graph_planner=_ForbiddenTaskGraphPlanner(),
            capability_executor=capability_executor,
        )

        result = agent.run("complete the previewed plan", initial_task_graph=initial_graph)

        assert result.completed is True
        assert capability_executor.proposed_subgoals == ["preview_01"]
        full_state = json.loads((result.run_dir / "execution_state.json").read_text(encoding="utf-8"))
        assert full_state["app_context"]["plan_source"] == "preview"
        assert full_state["task_graph"]["subgoals"][0]["id"] == "preview_01"
        assert full_state["task_graph"]["subgoals"][0]["status"] == "completed"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_coerce_initial_task_graph_preserves_completion_requirements():
    task_graph = TaskGraph(
        task="complete the previewed plan",
        subgoals=[
            Subgoal(
                id="preview_01",
                title="Do the exact previewed work",
                success_condition="The previewed work is visibly done.",
                status="completed",
                attempts=2,
                notes=["old runtime note"],
                failed_capabilities=["browser_dom"],
                completion_evidence={"kind": "state_change", "detail": "The target state is visible."},
            )
        ],
        dependencies={"preview_01": []},
        completion_summary="The previewed plan is complete when the target state is visible.",
    )

    coerced = controller.coerce_initial_task_graph(
        "complete the previewed plan",
        task_graph,
        max_subgoals=3,
    )

    assert coerced is not None
    assert coerced.subgoals[0].status == "pending"
    assert coerced.subgoals[0].attempts == 0
    assert coerced.subgoals[0].notes == []
    assert coerced.subgoals[0].failed_capabilities == []
    assert coerced.subgoals[0].completion_evidence == {
        "kind": "state_change",
        "detail": "The target state is visible.",
    }
    assert coerced.completion_summary == "The previewed plan is complete when the target state is visible."


def test_desktop_agent_does_not_resume_exhausted_blocked_subgoal():
    scratch_root = Path("test_artifacts") / f"controller_exhausted_blocked_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_dir = run_root / "existing_run"
    run_dir.mkdir(parents=True, exist_ok=True)

    class _NoRetryCapabilityExecutor:
        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            raise AssertionError("Exhausted blocked subgoals must not be proposed again.")

    try:
        config = AgentConfig(dry_run=False, max_steps=2, run_root=run_root)
        subgoal = Subgoal(
            id="subgoal_01",
            title="Complete the exhausted step",
            goal="Complete the exhausted step",
            success_condition="The exhausted step should not be retried.",
            status="blocked",
            attempts=3,
            max_attempts=3,
        )
        state = ExecutionState(
            task="resume an exhausted blocked step",
            run_id=run_dir.name,
            task_graph=TaskGraph(
                task="resume an exhausted blocked step",
                subgoals=[subgoal],
                dependencies={"subgoal_01": []},
            ),
            failure_budget={"subgoal_01": 0},
            stuck_rounds=3,
        )
        executor = _ExecutorStub()
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=executor,
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            capability_executor=_NoRetryCapabilityExecutor(),
        )

        result = agent.run(
            "resume an exhausted blocked step",
            run_dir=run_dir,
            execution_state=state,
            started_at=123.0,
            step_offset=2,
        )

        assert result.completed is False
        assert executor.executed_batches == 0
        assert "exhausted retries" in (result.error or "")
        assert "failure budget 0" in (result.error or "")
        assert (run_dir / "step_03.json").exists()
        full_state = json.loads((run_dir / "execution_state.json").read_text(encoding="utf-8"))
        assert full_state["task_graph"]["subgoals"][0]["status"] == "blocked"
        assert full_state["failure_budget"]["subgoal_01"] == 0
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_skips_exhausted_blocked_subgoal_for_independent_work():
    scratch_root = Path("test_artifacts") / f"controller_skip_exhausted_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_dir = run_root / "existing_run"
    run_dir.mkdir(parents=True, exist_ok=True)

    class _IndependentCapabilityExecutor:
        def __init__(self) -> None:
            self.proposed_subgoals: list[str] = []

        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            subgoal = execution_state.current_subgoal()
            assert subgoal is not None
            self.proposed_subgoals.append(subgoal.id)
            assert subgoal.id == "subgoal_02"
            return StepProposal(
                intent="Complete the independent work.",
                actions=[Action.from_dict({"type": "wait", "seconds": 0.1})],
                capability="desktop_gui",
                completes_subgoal=True,
            )

        def verify_step(self, execution_state, step, before, after):
            return VerificationResult(success=True, status="success", evidence=[{"kind": "state", "value": "done"}])

    try:
        config = AgentConfig(dry_run=False, max_steps=3, run_root=run_root)
        blocked = Subgoal(
            id="subgoal_01",
            title="Exhausted blocked work",
            goal="Exhausted blocked work",
            success_condition="This work is already exhausted.",
            status="blocked",
            attempts=3,
            max_attempts=3,
        )
        independent = Subgoal(
            id="subgoal_02",
            title="Independent pending work",
            goal="Independent pending work",
            success_condition="Independent work completes.",
            status="pending",
        )
        state = ExecutionState(
            task="continue independent work despite one blocked branch",
            run_id=run_dir.name,
            task_graph=TaskGraph(
                task="continue independent work despite one blocked branch",
                subgoals=[blocked, independent],
                dependencies={"subgoal_01": [], "subgoal_02": []},
            ),
            failure_budget={"subgoal_01": 0, "subgoal_02": 2},
            stuck_rounds=3,
        )
        executor = _ExecutorStub()
        capability_executor = _IndependentCapabilityExecutor()
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=executor,
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            capability_executor=capability_executor,
        )

        result = agent.run(
            "continue independent work despite one blocked branch",
            run_dir=run_dir,
            execution_state=state,
            started_at=123.0,
            step_offset=2,
        )

        assert result.completed is False
        assert executor.executed_batches == 1
        assert capability_executor.proposed_subgoals == ["subgoal_02"]
        assert "subgoal_01 exhausted retries" in (result.error or "")
        full_state = json.loads((run_dir / "execution_state.json").read_text(encoding="utf-8"))
        statuses = {item["id"]: item["status"] for item in full_state["task_graph"]["subgoals"]}
        assert statuses == {"subgoal_01": "blocked", "subgoal_02": "completed"}
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_successful_intermediate_progress_does_not_exhaust_retry_budget():
    scratch_root = Path("test_artifacts") / f"controller_success_progress_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)

    class _LongSubgoalPlanner:
        def plan(self, task, history=None, world_model=None):
            return TaskGraph(
                task=task,
                subgoals=[
                    Subgoal(
                        id="subgoal_01",
                        title="Complete a long verified subgoal",
                        goal="Complete a long verified subgoal",
                        success_condition="All verified stages are complete.",
                        max_attempts=2,
                    )
                ],
                dependencies={"subgoal_01": []},
                intent={"task_type": "multi_step_workflow", "risk_level": "low", "ambiguity": "low"},
            )

        def replan_remaining(self, execution_state, world_model, failure):
            return execution_state.task_graph

    class _LongSubgoalCapabilityExecutor:
        def __init__(self) -> None:
            self.proposals = 0

        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            self.proposals += 1
            return StepProposal(
                intent=f"Complete verified stage {self.proposals}.",
                actions=[Action.from_dict({"type": "wait", "seconds": 0.1})],
                capability="desktop_gui",
                completes_subgoal=self.proposals >= 3,
            )

        def verify_step(self, execution_state, step, before, after):
            return VerificationResult(
                success=True,
                status="success",
                evidence=[{"kind": "state", "value": f"stage-{self.proposals}"}],
            )

    try:
        config = AgentConfig(dry_run=False, max_steps=4, run_root=run_root)
        capability_executor = _LongSubgoalCapabilityExecutor()
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=_ExecutorStub(),
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            task_graph_planner=_LongSubgoalPlanner(),
            capability_executor=capability_executor,
        )

        result = agent.run("complete a long verified subgoal")

        assert result.completed is True
        assert result.error is None
        assert result.steps == 3
        assert capability_executor.proposals == 3
        full_state = json.loads((result.run_dir / "execution_state.json").read_text(encoding="utf-8"))
        assert full_state["task_graph"]["subgoals"][0]["attempts"] == 0
        assert full_state["task_graph"]["subgoals"][0]["status"] == "completed"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_does_not_complete_subgoal_without_verification_evidence():
    scratch_root = Path("test_artifacts") / f"controller_unproven_success_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)

    class _SingleSubgoalPlanner:
        def plan(self, task, history=None, world_model=None):
            return TaskGraph(
                task=task,
                subgoals=[
                    Subgoal(
                        id="subgoal_01",
                        title="Complete a task that needs proof",
                        goal="Complete a task that needs proof",
                        success_condition="The task is actually proven complete.",
                    )
                ],
                dependencies={"subgoal_01": []},
                intent={"task_type": "multi_step_workflow", "risk_level": "low", "ambiguity": "low"},
            )

        def replan_remaining(self, execution_state, world_model, failure):
            return execution_state.task_graph

    class _UnprovenThenProvenCapabilityExecutor:
        def __init__(self) -> None:
            self.proposals = 0

        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            self.proposals += 1
            return StepProposal(
                intent=f"Claim completion attempt {self.proposals}.",
                actions=[Action.from_dict({"type": "wait", "seconds": 0.1})],
                capability="desktop_gui",
                completes_subgoal=True,
            )

        def verify_step(self, execution_state, step, before, after):
            if self.proposals == 1:
                return VerificationResult(
                    success=True,
                    status="success",
                    evidence=[
                        {
                            "kind": "state",
                            "scope": "subgoal_completion",
                            "satisfied": "false",
                            "value": "claim-without-proof",
                        }
                    ],
                )
            return VerificationResult(
                success=True,
                status="success",
                evidence=[{"kind": "state", "value": "proved-complete"}],
            )

    try:
        config = AgentConfig(dry_run=False, max_steps=3, run_root=run_root)
        capability_executor = _UnprovenThenProvenCapabilityExecutor()
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=_ExecutorStub(),
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            task_graph_planner=_SingleSubgoalPlanner(),
            capability_executor=capability_executor,
        )

        result = agent.run("complete a task that needs proof")

        assert result.completed is True
        assert result.steps == 2
        assert capability_executor.proposals == 2
        first_step = json.loads((result.run_dir / "step_01.json").read_text(encoding="utf-8"))
        assert first_step["verification"]["status"] == "failed"
        assert first_step["verification"]["evidence"][0]["satisfied"] == "false"
        assert "did not provide evidence" in first_step["verification"]["message"]
        full_state = json.loads((result.run_dir / "execution_state.json").read_text(encoding="utf-8"))
        subgoal = full_state["task_graph"]["subgoals"][0]
        assert subgoal["status"] == "completed"
        assert subgoal["attempts"] == 1
        assert subgoal["completion_evidence"]["evidence"] == [{"kind": "state", "value": "proved-complete"}]
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_verification_completion_helpers_parse_string_satisfied_flags():
    subgoal_false = VerificationResult(
        success=True,
        status="success",
        evidence=[{"scope": "subgoal_completion", "satisfied": "false", "value": "not complete yet"}],
    )
    subgoal_true = VerificationResult(
        success=True,
        status="success",
        evidence=[{"scope": "subgoal_completion", "satisfied": "true", "value": "complete"}],
    )
    task_false = VerificationResult(
        success=True,
        status="success",
        evidence=[{"scope": "task_completion", "satisfied": "false", "value": "not complete yet"}],
    )
    task_true = VerificationResult(
        success=True,
        status="success",
        evidence=[{"scope": "task_completion", "satisfied": "true", "value": "complete"}],
    )

    assert controller._verification_completed_subgoal(subgoal_false) is False
    assert controller._verification_has_completion_proof(subgoal_false) is False
    assert controller._verification_completed_subgoal(subgoal_true) is True
    assert controller._verification_has_completion_proof(subgoal_true) is True
    assert controller._verification_completed_task(task_false) is False
    assert controller._verification_completed_task(task_true) is True


def test_desktop_agent_rejects_placeholder_completion_evidence():
    scratch_root = Path("test_artifacts") / f"controller_placeholder_evidence_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)

    class _SingleSubgoalPlanner:
        def plan(self, task, history=None, world_model=None):
            return TaskGraph(
                task=task,
                subgoals=[
                    Subgoal(
                        id="subgoal_01",
                        title="Complete a task with real proof",
                        goal="Complete a task with real proof",
                        success_condition="Real proof is available.",
                    )
                ],
                dependencies={"subgoal_01": []},
                intent={"task_type": "multi_step_workflow", "risk_level": "low", "ambiguity": "low"},
            )

        def replan_remaining(self, execution_state, world_model, failure):
            return execution_state.task_graph

    class _PlaceholderThenProvenCapabilityExecutor:
        def __init__(self) -> None:
            self.proposals = 0

        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            self.proposals += 1
            return StepProposal(
                intent=f"Claim completion with evidence {self.proposals}.",
                actions=[Action.from_dict({"type": "wait", "seconds": 0.1})],
                capability="desktop_gui",
                completes_subgoal=True,
            )

        def verify_step(self, execution_state, step, before, after):
            if self.proposals == 1:
                return VerificationResult(success=True, status="success", evidence=[{"kind": "state"}])
            return VerificationResult(
                success=True,
                status="success",
                evidence=[{"kind": "state", "value": "real-proof"}],
            )

    try:
        config = AgentConfig(dry_run=False, max_steps=3, run_root=run_root)
        capability_executor = _PlaceholderThenProvenCapabilityExecutor()
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=_ExecutorStub(),
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            task_graph_planner=_SingleSubgoalPlanner(),
            capability_executor=capability_executor,
        )

        result = agent.run("complete a task with real proof")

        assert result.completed is True
        assert result.steps == 2
        first_step = json.loads((result.run_dir / "step_01.json").read_text(encoding="utf-8"))
        assert first_step["verification"]["status"] == "failed"
        assert first_step["verification"]["evidence"] == [{"kind": "state"}]
        full_state = json.loads((result.run_dir / "execution_state.json").read_text(encoding="utf-8"))
        assert full_state["task_graph"]["subgoals"][0]["completion_evidence"]["evidence"] == [
            {"kind": "state", "value": "real-proof"}
        ]
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_does_not_complete_all_subgoals_from_unproven_task_scope():
    scratch_root = Path("test_artifacts") / f"controller_task_scope_evidence_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)

    class _TwoSubgoalPlanner:
        def plan(self, task, history=None, world_model=None):
            return TaskGraph(
                task=task,
                subgoals=[
                    Subgoal(
                        id="subgoal_01",
                        title="Finish the first verified part",
                        goal="Finish the first verified part",
                        success_condition="The first part is verified.",
                    ),
                    Subgoal(
                        id="subgoal_02",
                        title="Finish the second verified part",
                        goal="Finish the second verified part",
                        success_condition="The second part is verified.",
                        prerequisites=["subgoal_01"],
                    ),
                ],
                dependencies={"subgoal_01": [], "subgoal_02": ["subgoal_01"]},
                intent={"task_type": "multi_step_workflow", "risk_level": "low", "ambiguity": "low"},
            )

        def replan_remaining(self, execution_state, world_model, failure):
            return execution_state.task_graph

    class _TaskScopeWithoutTaskProofExecutor:
        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            return StepProposal(
                intent="Claim the entire task is finished while only proving the current part.",
                actions=[Action.from_dict({"type": "wait", "seconds": 0.1})],
                capability="desktop_gui",
                target_scope="task",
                completes_subgoal=True,
            )

        def verify_step(self, execution_state, step, before, after):
            return VerificationResult(
                success=True,
                status="success",
                evidence=[
                    {
                        "scope": "subgoal_completion",
                        "satisfied": True,
                        "value": "first-part-proof",
                    }
                ],
            )

    try:
        config = AgentConfig(dry_run=False, max_steps=1, run_root=run_root)
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=_ExecutorStub(),
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            task_graph_planner=_TwoSubgoalPlanner(),
            capability_executor=_TaskScopeWithoutTaskProofExecutor(),
        )

        result = agent.run("complete two verified parts")

        assert result.completed is False
        assert "Step budget exhausted" in (result.error or "")
        full_state = json.loads((result.run_dir / "execution_state.json").read_text(encoding="utf-8"))
        subgoals = {item["id"]: item for item in full_state["task_graph"]["subgoals"]}
        assert subgoals["subgoal_01"]["status"] == "completed"
        assert subgoals["subgoal_02"]["status"] == "pending"
        assert subgoals["subgoal_02"]["completion_evidence"] is None
        assert full_state["app_context"]["task_scope_completion_downgraded"] is True
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_accepts_task_scope_only_with_task_completion_evidence():
    scratch_root = Path("test_artifacts") / f"controller_task_scope_task_proof_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)

    class _TwoSubgoalPlanner:
        def plan(self, task, history=None, world_model=None):
            return TaskGraph(
                task=task,
                subgoals=[
                    Subgoal(id="subgoal_01", title="Finish part one", goal="Finish part one"),
                    Subgoal(
                        id="subgoal_02",
                        title="Finish part two",
                        goal="Finish part two",
                        prerequisites=["subgoal_01"],
                    ),
                ],
                dependencies={"subgoal_01": [], "subgoal_02": ["subgoal_01"]},
                intent={"task_type": "multi_step_workflow", "risk_level": "low", "ambiguity": "low"},
            )

        def replan_remaining(self, execution_state, world_model, failure):
            return execution_state.task_graph

    class _TaskScopeWithTaskProofExecutor:
        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            return StepProposal(
                intent="Finish and verify the whole task.",
                actions=[Action.from_dict({"type": "wait", "seconds": 0.1})],
                capability="desktop_gui",
                target_scope="task",
                completes_subgoal=True,
            )

        def verify_step(self, execution_state, step, before, after):
            return VerificationResult(
                success=True,
                status="success",
                evidence=[
                    {
                        "scope": "task_completion",
                        "satisfied": True,
                        "value": "all-parts-proof",
                    }
                ],
            )

    try:
        config = AgentConfig(dry_run=False, max_steps=1, run_root=run_root)
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=_ExecutorStub(),
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            task_graph_planner=_TwoSubgoalPlanner(),
            capability_executor=_TaskScopeWithTaskProofExecutor(),
        )

        result = agent.run("complete two verified parts with task proof")

        assert result.completed is True
        full_state = json.loads((result.run_dir / "execution_state.json").read_text(encoding="utf-8"))
        assert [item["status"] for item in full_state["task_graph"]["subgoals"]] == ["completed", "completed"]
        assert "task_scope_completion_downgraded" not in full_state["app_context"]
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_reports_step_budget_exhausted_when_incomplete():
    scratch_root = Path("test_artifacts") / f"controller_step_budget_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)

    class _LongPendingTaskGraphPlanner:
        def plan(self, task, history=None, world_model=None):
            return TaskGraph(
                task=task,
                subgoals=[
                    Subgoal(
                        id="subgoal_01",
                        title="Keep working until proof appears",
                        goal="Keep working until proof appears",
                        success_condition="A final proof appears.",
                    )
                ],
                dependencies={"subgoal_01": []},
                intent={"task_type": "multi_step_workflow", "risk_level": "low", "ambiguity": "low"},
            )

        def replan_remaining(self, execution_state, world_model, failure):
            return execution_state.task_graph

    class _NeverCompletingCapabilityExecutor:
        def __init__(self) -> None:
            self.proposals = 0

        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            self.proposals += 1
            return StepProposal(
                intent=f"Make verified progress {self.proposals}.",
                actions=[Action.from_dict({"type": "wait", "seconds": 0.1})],
                capability="desktop_gui",
                completes_subgoal=False,
            )

        def verify_step(self, execution_state, step, before, after):
            return VerificationResult(
                success=True,
                status="success",
                evidence=[{"kind": "state", "value": f"progress-{self.proposals}"}],
            )

    try:
        config = AgentConfig(
            dry_run=False,
            max_steps=2,
            max_run_seconds=120,
            pause_after_action=0.25,
            task_graph_request_timeout=7.25,
            browser_control_mode="dom",
            browser_dom_backend="playwright",
            browser_dom_timeout=6.5,
            browser_headless=True,
            browser_channel="chrome",
            browser_executable_path="C:\\Tools\\browser.exe",
            cursor_motion_enabled=True,
            cursor_motion_duration=0.4,
            display_override_enabled=True,
            display_override_monitor_device_name="DISPLAY2",
            display_override_dpi_scale=1.25,
            display_override_work_area_left=10,
            display_override_work_area_top=20,
            display_override_work_area_width=1280,
            display_override_work_area_height=720,
            generic_app_launch_enabled=False,
            shell_recipe_policy="strict",
            run_root=run_root,
        )
        capability_executor = _NeverCompletingCapabilityExecutor()
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=_ExecutorStub(),
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            task_graph_planner=_LongPendingTaskGraphPlanner(),
            capability_executor=capability_executor,
        )

        result = agent.run("keep working until proof appears")

        assert result.completed is False
        assert result.steps == 2
        assert "Step budget exhausted" in (result.error or "")
        assert result.execution_budget is not None
        assert result.execution_budget["max_steps"] == 2
        assert result.execution_budget["max_run_seconds"] == 120
        assert result.execution_budget["pause_after_action"] == 0.25
        assert result.execution_budget["task_graph_request_timeout"] == 7.25
        assert result.execution_budget["desktop_autonomy_mode"] == "conservative"
        assert result.execution_budget["recoverable_error_retry_limit"] == 2
        assert result.execution_environment is not None
        assert result.execution_environment["browser_control_mode"] == "dom"
        assert result.execution_environment["browser_dom_timeout"] == 6.5
        assert result.execution_environment["browser_headless"] is True
        assert result.execution_environment["generic_app_launch_enabled"] is False
        assert result.execution_environment["shell_recipe_policy"] == "strict"
        assert capability_executor.proposals == 2
        summary_payload = json.loads((result.run_dir / "summary.json").read_text(encoding="utf-8"))
        assert summary_payload["error"] == result.error
        assert summary_payload["execution_budget"] == result.execution_budget
        assert summary_payload["execution_environment"] == result.execution_environment
        assert summary_payload["task_graph_request_timeout"] == 7.25
        assert summary_payload["max_steps"] == 2
        assert summary_payload["max_run_seconds"] == 120
        assert summary_payload["pause_after_action"] == 0.25
        assert summary_payload["desktop_autonomy_mode"] == "conservative"
        assert summary_payload["complex_task_planning"] == "hybrid"
        assert summary_payload["approval_policy"] == "tiered"
        assert summary_payload["plan_review_policy"] == "low_risk_auto"
        assert summary_payload["stage_review_policy"] == "risk_change"
        assert summary_payload["max_task_subgoals"] == 12
        assert summary_payload["max_subgoal_retries"] == 2
        assert summary_payload["max_replans_per_run"] == 3
        assert summary_payload["max_failures_per_subgoal"] == 3
        assert summary_payload["replan_on_recoverable_error"] is True
        assert summary_payload["recoverable_error_retry_limit"] == 2
        assert summary_payload["browser_control_mode"] == "dom"
        assert summary_payload["browser_dom_backend"] == "playwright"
        assert summary_payload["browser_dom_timeout"] == 6.5
        assert summary_payload["browser_headless"] is True
        assert summary_payload["browser_channel"] == "chrome"
        assert summary_payload["browser_executable_path"] == "C:\\Tools\\browser.exe"
        assert summary_payload["cursor_motion_enabled"] is True
        assert summary_payload["cursor_motion_duration"] == 0.4
        assert summary_payload["display_override_enabled"] is True
        assert summary_payload["display_override_monitor_device_name"] == "DISPLAY2"
        assert summary_payload["display_override_dpi_scale"] == 1.25
        assert summary_payload["display_override_work_area_left"] == 10
        assert summary_payload["display_override_work_area_top"] == 20
        assert summary_payload["display_override_work_area_width"] == 1280
        assert summary_payload["display_override_work_area_height"] == 720
        assert summary_payload["generic_app_launch_enabled"] is False
        assert summary_payload["shell_recipe_policy"] == "strict"
        state_payload = json.loads((result.run_dir / "state.json").read_text(encoding="utf-8"))
        assert state_payload["orchestration_phase"] == "blocked"
        assert state_payload["verification_status"] == "failed"
        full_state = json.loads((result.run_dir / "execution_state.json").read_text(encoding="utf-8"))
        assert full_state["app_context"]["step_budget_exhausted"] is True
        assert full_state["task_graph"]["subgoals"][0]["status"] == "pending"
        assert full_state["last_verification"]["message"] == result.error
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_respects_stop_requested_between_steps():
    scratch_root = Path("test_artifacts") / f"controller_stop_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)

    try:
        config = AgentConfig(dry_run=False, max_steps=6, run_root=run_root)
        executor = _ExecutorStub()
        should_stop = {"value": False}

        def stop_requested():
            return should_stop["value"]

        class _StopAfterFirstBatchExecutor(_ExecutorStub):
            def execute_many(self, actions, pause_after_action, stop_requested=None):
                super().execute_many(actions, pause_after_action, stop_requested=stop_requested)
                should_stop["value"] = True

        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=_StopAfterFirstBatchExecutor(),
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            stop_requested=stop_requested,
        )

        result = agent.run("wait until stopped")

        assert result.completed is False
        assert result.cancelled is True
        assert result.error is None
        assert result.steps == 1
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_stops_when_run_time_limit_is_reached():
    scratch_root = Path("test_artifacts") / f"controller_time_limit_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)

    try:
        config = AgentConfig(dry_run=False, max_steps=6, max_run_seconds=0.5, run_root=run_root)
        executor = _ExecutorStub()
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=executor,
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
        )

        result = agent.run("wait until timeout", started_at=time.time() - 1.0)

        assert result.completed is False
        assert result.cancelled is True
        assert result.cancel_reason == "Run time limit reached."
        assert result.interruption_kind == "time_limit"
        assert executor.executed_batches == 0
        assert result.steps == 0
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_logs_environment_payload():
    scratch_root = Path("test_artifacts") / f"controller_env_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)

    try:
        config = AgentConfig(dry_run=False, max_steps=1, run_root=run_root)
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=_ExecutorStub(),
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
        )

        result = agent.run("wait once")
        step_payload = next(result.run_dir.glob("step_01.json")).read_text(encoding="utf-8")
        step_json = json.loads(step_payload)

        assert '"environment"' in step_payload
        assert '"effective"' in step_payload
        assert '"detected"' in step_payload
        assert '"dpi_scale"' in step_payload
        assert step_json["timings"]["total"] >= 0
        assert "capture_initial" in step_json["timings"]
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_emits_live_pointer_updates_from_executor_progress():
    scratch_root = Path("test_artifacts") / f"controller_live_pointer_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)
    progress_payloads: list[dict] = []

    class _ProgressExecutor(_ExecutorStub):
        def __init__(self) -> None:
            super().__init__()
            self._progress_callback = None

        def set_action_progress_callback(self, callback):
            self._progress_callback = callback

        def execute_many(self, actions, pause_after_action, stop_requested=None):
            super().execute_many(actions, pause_after_action, stop_requested=stop_requested)
            assert self._progress_callback is not None
            self._progress_callback(
                {
                    "event": "cursor_motion",
                    "x": 320,
                    "y": 180,
                    "target_x": 640,
                    "target_y": 360,
                    "phase": "moving",
                    "updated_at": 1711000000.0,
                    "live_action": {
                        "type": "click",
                        "label": "click(640,360)",
                        "status": "running",
                    },
                }
            )
            self._progress_callback({"event": "cursor_motion", "clear": True, "updated_at": 1711000000.1})

    class _LivePointerCapabilityExecutor:
        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            return StepProposal(
                intent="Click the current target.",
                actions=[Action.from_dict({"type": "click", "x": 640, "y": 360})],
                capability="desktop_gui",
                current_focus="click the current target",
                completes_subgoal=True,
            )

        def verify_step(self, execution_state, step, before, after):
            return VerificationResult(success=True, status="success", evidence=[{"kind": "action", "value": "clicked"}])

    try:
        config = AgentConfig(dry_run=False, max_steps=1, run_root=run_root)
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=_ProgressExecutor(),
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            capability_executor=_LivePointerCapabilityExecutor(),
            progress_callback=lambda payload: progress_payloads.append(dict(payload)),
        )

        result = agent.run("click the center target")

        assert result.completed is True
        pointer_payload = next(item for item in progress_payloads if item.get("live_pointer"))
        assert pointer_payload["live_pointer"]["x"] == 320
        assert pointer_payload["live_pointer"]["norm_x"] == 0.25
        assert pointer_payload["live_pointer"]["norm_y"] == 0.25
        assert pointer_payload["live_action"]["label"] == "click(640,360)"
        cleared_payload = next(item for item in reversed(progress_payloads) if item.get("live_pointer") is None)
        assert cleared_payload["live_pointer_trail"] == []
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_requires_plan_review_before_high_risk_task_actions():
    scratch_root = Path("test_artifacts") / f"controller_plan_review_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)
    decisions: list[dict] = []

    try:
        config = AgentConfig(dry_run=False, max_steps=3, run_root=run_root)
        executor = _ExecutorStub()
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=executor,
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            decision_callback=lambda payload: decisions.append(payload) or {"decision": "reject"},
        )

        result = agent.run("visit openai.com and click login")

        assert result.completed is False
        assert "plan was rejected" in (result.error or "")
        assert executor.executed_batches == 0
        assert decisions[0]["pending_decision"]["decision_type"] == "plan_review"
        assert decisions[0]["pending_decision"]["risk_level"] == "high"
        state_payload = json.loads((result.run_dir / "state.json").read_text(encoding="utf-8"))
        assert state_payload["orchestration_phase"] == "blocked"
        assert state_payload["verification_status"] == "failed"
        full_state = json.loads((result.run_dir / "execution_state.json").read_text(encoding="utf-8"))
        assert full_state["last_verification"]["failure_kind"] == "approval_rejected"
        assert full_state["app_context"]["standard_recovery_kind"] == "safety_gate"
        assert full_state["task_graph"]["subgoals"][0]["status"] == "blocked"
        assert full_state["failure_budget"]["subgoal_01"] == 0
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_rejects_unknown_plan_review_decision_for_safety():
    scratch_root = Path("test_artifacts") / f"controller_plan_review_unknown_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)
    decisions: list[dict] = []

    try:
        config = AgentConfig(dry_run=False, max_steps=3, run_root=run_root)
        executor = _ExecutorStub()
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=executor,
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            decision_callback=lambda payload: decisions.append(payload) or {"decision": "later"},
        )

        result = agent.run("visit openai.com and click login")

        assert result.completed is False
        assert "plan was rejected" in (result.error or "")
        assert executor.executed_batches == 0
        assert decisions[0]["pending_decision"]["decision_type"] == "plan_review"
        full_state = json.loads((result.run_dir / "execution_state.json").read_text(encoding="utf-8"))
        assert full_state["app_context"]["plan_review_status"] == "rejected"
        assert full_state["stage_decisions"][-1]["decision_type"] == "plan_review"
        assert full_state["stage_decisions"][-1]["status"] == "rejected"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_resume_after_plan_review_cancel_requests_review_again():
    scratch_root = Path("test_artifacts") / f"controller_plan_review_cancel_resume_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)
    first_decisions: list[dict] = []
    resumed_decisions: list[dict] = []

    class _ReviewedCapabilityExecutor:
        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            return StepProposal(
                intent="Run the reviewed plan.",
                actions=[Action.from_dict({"type": "wait", "seconds": 0.1})],
                capability="desktop_gui",
                completes_subgoal=True,
            )

        def verify_step(self, execution_state, step, before, after):
            return VerificationResult(
                success=True,
                status="success",
                evidence=[{"scope": "subgoal_completion", "satisfied": True, "message": "Reviewed plan ran."}],
            )

    initial_graph = TaskGraph(
        task="run reviewed plan",
        subgoals=[
            Subgoal(
                id="review_01",
                title="Run Reviewed Plan",
                goal="Run the reviewed plan",
                success_condition="The reviewed plan has run.",
                goal_type="open",
                risk_level="low",
            )
        ],
        dependencies={"review_01": []},
    )

    try:
        config = AgentConfig(
            dry_run=False,
            max_steps=1,
            run_root=run_root,
            plan_review_policy="always",
            stage_review_policy="never",
        )
        first_executor = _ExecutorStub()
        first_agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=first_executor,
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            capability_executor=_ReviewedCapabilityExecutor(),
            decision_callback=lambda payload: first_decisions.append(payload)
            or {"decision": " CANCEL ", "note": "Review later."},
        )

        cancelled = first_agent.run("run reviewed plan", initial_task_graph=initial_graph)

        assert cancelled.completed is False
        assert cancelled.cancelled is True
        assert cancelled.cancel_reason == "Review later."
        assert first_executor.executed_batches == 0
        assert len(first_decisions) == 1
        assert first_decisions[0]["pending_decision"]["decision_type"] == "plan_review"
        cancelled_state = json.loads((cancelled.run_dir / "execution_state.json").read_text(encoding="utf-8"))
        assert cancelled_state["pending_decision"] is None
        assert cancelled_state["app_context"]["plan_review_status"] == "pending"
        assert cancelled_state["stage_decisions"][-1]["decision_type"] == "plan_review"
        assert cancelled_state["stage_decisions"][-1]["status"] == "cancelled"

        resume_context = controller._load_resume_context(run_root, cancelled.run_dir.name)
        resume_state = controller._prepare_execution_state_for_resume(resume_context.execution_state)
        resumed_executor = _ExecutorStub()
        resumed_agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=resumed_executor,
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            capability_executor=_ReviewedCapabilityExecutor(),
            decision_callback=lambda payload: resumed_decisions.append(payload)
            or {"decision": " APPROVED ", "note": "Continue now."},
        )

        completed = resumed_agent.run(
            resume_context.task,
            run_dir=resume_context.run_dir,
            execution_state=resume_state,
            started_at=resume_context.started_at,
            step_offset=resume_context.step_offset,
        )

        assert completed.completed is True
        assert completed.error is None
        assert resumed_executor.executed_batches == 1
        assert len(resumed_decisions) == 1
        assert resumed_decisions[0]["pending_decision"]["decision_type"] == "plan_review"
        full_state = json.loads((completed.run_dir / "execution_state.json").read_text(encoding="utf-8"))
        assert full_state["completed"] is True
        assert full_state["pending_decision"] is None
        assert full_state["app_context"]["plan_review_status"] == "approved"
        assert full_state["stage_decisions"][-2]["decision_type"] == "plan_review"
        assert full_state["stage_decisions"][-2]["status"] == "cancelled"
        assert full_state["stage_decisions"][-1]["decision_type"] == "plan_review"
        assert full_state["stage_decisions"][-1]["status"] == "approved"
        assert full_state["task_graph"]["subgoals"][0]["status"] == "completed"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_skips_duplicate_plan_review_for_approved_preview_graph():
    scratch_root = Path("test_artifacts") / f"controller_preview_approved_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)
    decisions: list[dict] = []

    class _PreviewCapabilityExecutor:
        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            return StepProposal(
                intent="Open Calculator from the reviewed preview.",
                actions=[Action.from_dict({"type": "open_app_if_needed", "app": "calculator"})],
                capability="desktop_gui",
                completes_subgoal=True,
            )

        def verify_step(self, execution_state, step, before, after):
            return VerificationResult(success=True, status="success", evidence=[{"kind": "state", "value": "calculator"}])

    initial_graph = TaskGraph(
        task="open calculator from preview",
        subgoals=[
            Subgoal(
                id="preview_01",
                title="Open Calculator",
                goal="Open Calculator",
                success_condition="Calculator is open.",
                goal_type="open",
                risk_level="low",
            )
        ],
        dependencies={"preview_01": []},
    )

    try:
        config = AgentConfig(
            dry_run=False,
            max_steps=1,
            run_root=run_root,
            plan_review_policy="always",
        )
        executor = _ExecutorStub()
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=executor,
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            capability_executor=_PreviewCapabilityExecutor(),
            decision_callback=lambda payload: decisions.append(payload) or {"decision": "reject"},
        )

        result = agent.run(
            "open calculator from preview",
            initial_task_graph=initial_graph,
            initial_plan_review_status="approved",
        )

        assert result.completed is True
        assert decisions == []
        assert executor.executed_batches == 1
        full_state = json.loads((result.run_dir / "execution_state.json").read_text(encoding="utf-8"))
        assert full_state["app_context"]["plan_source"] == "preview"
        assert full_state["app_context"]["plan_review_status"] == "approved"
        assert full_state["stage_decisions"][0]["decision_type"] == "plan_review"
        assert full_state["stage_decisions"][0]["status"] == "approved"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_requests_stage_review_after_replan_risk_increase():
    scratch_root = Path("test_artifacts") / f"controller_stage_review_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)
    decisions: list[dict] = []

    class _RiskIncreasingPlanner:
        def plan(self, task, history=None, world_model=None):
            return TaskGraph(
                task=task,
                subgoals=[
                    Subgoal(
                        id="subgoal_01",
                        title="Read the current page",
                        goal="Read the current page",
                        success_condition="The page content is understood.",
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
            subgoal = graph.subgoals[0]
            subgoal.title = "Submit the recovered form"
            subgoal.goal = "Submit the recovered form"
            subgoal.success_condition = "The recovered form has been submitted."
            subgoal.goal_type = "submit"
            subgoal.capability_preference = "browser_dom"
            subgoal.risk_level = "high"
            graph.intent = {"task_type": "multi_step_workflow", "risk_level": "high", "ambiguity": "low"}
            graph.risk_points = ["Submit the recovered form"]
            return graph

    class _FailingCapabilityExecutor:
        def __init__(self) -> None:
            self.propose_calls = 0
            self.verify_calls = 0

        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            self.propose_calls += 1
            return StepProposal(
                intent=f"Try recovery route {self.propose_calls}.",
                actions=[Action.from_dict({"type": "wait", "seconds": 0.1})],
                capability="browser_dom",
                current_focus=f"recovery route {self.propose_calls}",
                completes_subgoal=True,
            )

        def verify_step(self, execution_state, step, before, after):
            self.verify_calls += 1
            return VerificationResult(
                success=False,
                status="failed",
                failure_kind="blocked_by_ui",
                message=f"Route blocked on attempt {self.verify_calls}.",
            )

    try:
        config = AgentConfig(
            dry_run=False,
            max_steps=6,
            run_root=run_root,
            plan_review_policy="never",
            stage_review_policy="risk_change",
        )
        executor = _ExecutorStub()
        capability_executor = _FailingCapabilityExecutor()
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=executor,
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            task_graph_planner=_RiskIncreasingPlanner(),
            capability_executor=capability_executor,
            decision_callback=lambda payload: decisions.append(payload) or {"decision": "reject", "note": "Too risky."},
        )

        result = agent.run("read a page, recover if blocked, then continue")

        assert result.completed is False
        assert "replanned stage was rejected" in (result.error or "")
        assert executor.executed_batches == 3
        assert capability_executor.verify_calls == 3
        assert len(decisions) == 1
        assert decisions[0]["pending_decision"]["decision_type"] == "stage_review"
        assert decisions[0]["pending_decision"]["risk_level"] == "high"
        full_state = json.loads((result.run_dir / "execution_state.json").read_text(encoding="utf-8"))
        assert full_state["app_context"]["stage_review_status"] == "rejected"
        assert full_state["stage_decisions"][-1]["decision_type"] == "stage_review"
        assert full_state["stage_decisions"][-1]["status"] == "rejected"
        assert full_state["task_graph"]["subgoals"][0]["title"] == "Submit the recovered form"
        assert full_state["task_graph"]["subgoals"][0]["status"] == "blocked"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_resumes_after_approved_stage_review():
    scratch_root = Path("test_artifacts") / f"controller_stage_review_approved_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)
    decisions: list[dict] = []

    class _RiskIncreasingPlanner:
        def plan(self, task, history=None, world_model=None):
            return TaskGraph(
                task=task,
                subgoals=[
                    Subgoal(
                        id="subgoal_01",
                        title="Read the current page",
                        goal="Read the current page",
                        success_condition="The page content is understood.",
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
            subgoal = graph.subgoals[0]
            subgoal.title = "Submit the recovered form"
            subgoal.goal = "Submit the recovered form"
            subgoal.success_condition = "The recovered form has been submitted."
            subgoal.goal_type = "submit"
            subgoal.capability_preference = "browser_dom"
            subgoal.risk_level = "high"
            graph.intent = {"task_type": "multi_step_workflow", "risk_level": "high", "ambiguity": "low"}
            graph.risk_points = ["Submit the recovered form"]
            return graph

    class _FailThenSucceedCapabilityExecutor:
        def __init__(self) -> None:
            self.propose_calls = 0
            self.verify_calls = 0

        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            self.propose_calls += 1
            return StepProposal(
                intent=f"Try recovery route {self.propose_calls}.",
                actions=[Action.from_dict({"type": "wait", "seconds": 0.1})],
                capability="browser_dom",
                current_focus=f"recovery route {self.propose_calls}",
                completes_subgoal=True,
            )

        def verify_step(self, execution_state, step, before, after):
            self.verify_calls += 1
            if self.verify_calls < 4:
                return VerificationResult(
                    success=False,
                    status="failed",
                    failure_kind="blocked_by_ui",
                    message=f"Route blocked on attempt {self.verify_calls}.",
                )
            return VerificationResult(
                success=True,
                status="success",
                evidence=[
                    {
                        "scope": "subgoal_completion",
                        "satisfied": True,
                        "message": "The recovered form was submitted after stage review approval.",
                    }
                ],
            )

    def _approve_stage_review(payload: dict) -> dict:
        decisions.append(payload)
        return {"decision": "approve", "note": "Approved replan."}

    try:
        config = AgentConfig(
            dry_run=False,
            max_steps=6,
            run_root=run_root,
            plan_review_policy="never",
            stage_review_policy="risk_change",
        )
        executor = _ExecutorStub()
        capability_executor = _FailThenSucceedCapabilityExecutor()
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=executor,
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            task_graph_planner=_RiskIncreasingPlanner(),
            capability_executor=capability_executor,
            decision_callback=_approve_stage_review,
        )

        result = agent.run("read a page, recover if blocked, then continue")

        assert result.completed is True
        assert result.error is None
        assert executor.executed_batches == 4
        assert capability_executor.verify_calls == 4
        assert len(decisions) == 1
        assert decisions[0]["pending_decision"]["decision_type"] == "stage_review"
        assert decisions[0]["pending_decision"]["risk_level"] == "high"
        full_state = json.loads((result.run_dir / "execution_state.json").read_text(encoding="utf-8"))
        assert full_state["completed"] is True
        assert full_state["app_context"]["stage_review_status"] == "approved"
        assert full_state["pending_decision"] is None
        assert full_state["stage_decisions"][-1]["decision_type"] == "stage_review"
        assert full_state["stage_decisions"][-1]["status"] == "approved"
        assert full_state["task_graph"]["subgoals"][0]["title"] == "Submit the recovered form"
        assert full_state["task_graph"]["subgoals"][0]["status"] == "completed"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_resume_after_stage_review_cancel_requests_review_again():
    scratch_root = Path("test_artifacts") / f"controller_stage_review_cancel_resume_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)
    first_decisions: list[dict] = []
    resumed_decisions: list[dict] = []

    class _RiskIncreasingPlanner:
        def plan(self, task, history=None, world_model=None):
            return TaskGraph(
                task=task,
                subgoals=[
                    Subgoal(
                        id="subgoal_01",
                        title="Read the current page",
                        goal="Read the current page",
                        success_condition="The page content is understood.",
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
            subgoal = graph.subgoals[0]
            subgoal.title = "Submit the recovered form"
            subgoal.goal = "Submit the recovered form"
            subgoal.success_condition = "The recovered form has been submitted."
            subgoal.goal_type = "submit"
            subgoal.capability_preference = "browser_dom"
            subgoal.risk_level = "high"
            graph.intent = {"task_type": "multi_step_workflow", "risk_level": "high", "ambiguity": "low"}
            graph.risk_points = ["Submit the recovered form"]
            return graph

    class _FailThenSucceedCapabilityExecutor:
        def __init__(self) -> None:
            self.propose_calls = 0
            self.verify_calls = 0

        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            self.propose_calls += 1
            return StepProposal(
                intent=f"Try recovery route {self.propose_calls}.",
                actions=[Action.from_dict({"type": "wait", "seconds": 0.1})],
                capability="browser_dom",
                current_focus=f"recovery route {self.propose_calls}",
                completes_subgoal=True,
            )

        def verify_step(self, execution_state, step, before, after):
            self.verify_calls += 1
            if self.verify_calls < 4:
                return VerificationResult(
                    success=False,
                    status="failed",
                    failure_kind="blocked_by_ui",
                    message=f"Route blocked on attempt {self.verify_calls}.",
                )
            return VerificationResult(
                success=True,
                status="success",
                evidence=[
                    {
                        "scope": "subgoal_completion",
                        "satisfied": True,
                        "message": "The recovered form was submitted after stage review approval.",
                    }
                ],
            )

    try:
        config = AgentConfig(
            dry_run=False,
            max_steps=6,
            run_root=run_root,
            plan_review_policy="never",
            stage_review_policy="risk_change",
        )
        first_executor = _ExecutorStub()
        capability_executor = _FailThenSucceedCapabilityExecutor()
        first_agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=first_executor,
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            task_graph_planner=_RiskIncreasingPlanner(),
            capability_executor=capability_executor,
            decision_callback=lambda payload: first_decisions.append(payload)
            or {"decision": " CANCELED ", "note": "Review replan later."},
        )

        cancelled = first_agent.run("read a page, recover if blocked, then continue")

        assert cancelled.completed is False
        assert cancelled.cancelled is True
        assert cancelled.cancel_reason == "Review replan later."
        assert first_executor.executed_batches == 3
        assert capability_executor.verify_calls == 3
        assert len(first_decisions) == 1
        assert first_decisions[0]["pending_decision"]["decision_type"] == "stage_review"
        assert first_decisions[0]["pending_decision"]["risk_level"] == "high"
        cancelled_state = json.loads((cancelled.run_dir / "execution_state.json").read_text(encoding="utf-8"))
        assert cancelled_state["pending_decision"] is None
        assert cancelled_state["app_context"]["stage_review_status"] == "pending"
        assert cancelled_state["stage_decisions"][-1]["decision_type"] == "stage_review"
        assert cancelled_state["stage_decisions"][-1]["status"] == "cancelled"
        assert cancelled_state["task_graph"]["subgoals"][0]["title"] == "Submit the recovered form"
        assert cancelled_state["task_graph"]["subgoals"][0]["status"] == "pending"

        resume_context = controller._load_resume_context(run_root, cancelled.run_dir.name)
        resume_state = controller._prepare_execution_state_for_resume(resume_context.execution_state)
        resumed_executor = _ExecutorStub()
        resumed_agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=resumed_executor,
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            task_graph_planner=_RiskIncreasingPlanner(),
            capability_executor=capability_executor,
            decision_callback=lambda payload: resumed_decisions.append(payload)
            or {"decision": " APPROVED ", "note": "Continue replan now."},
        )

        completed = resumed_agent.run(
            resume_context.task,
            run_dir=resume_context.run_dir,
            execution_state=resume_state,
            started_at=resume_context.started_at,
            step_offset=resume_context.step_offset,
        )

        assert completed.completed is True
        assert completed.error is None
        assert resumed_executor.executed_batches == 1
        assert capability_executor.verify_calls == 4
        assert len(resumed_decisions) == 1
        assert resumed_decisions[0]["pending_decision"]["decision_type"] == "stage_review"
        full_state = json.loads((completed.run_dir / "execution_state.json").read_text(encoding="utf-8"))
        assert full_state["completed"] is True
        assert full_state["pending_decision"] is None
        assert full_state["app_context"]["stage_review_status"] == "approved"
        assert full_state["stage_decisions"][-2]["decision_type"] == "stage_review"
        assert full_state["stage_decisions"][-2]["status"] == "cancelled"
        assert full_state["stage_decisions"][-1]["decision_type"] == "stage_review"
        assert full_state["stage_decisions"][-1]["status"] == "approved"
        assert full_state["task_graph"]["subgoals"][0]["status"] == "completed"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_blocks_state_after_step_approval_rejection():
    scratch_root = Path("test_artifacts") / f"controller_step_reject_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)
    decisions: list[dict] = []

    class _ApprovalCapabilityExecutor:
        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            return StepProposal(
                intent="Confirm the guarded administrator prompt.",
                actions=[Action.from_dict({"type": "click", "x": 100, "y": 100, "text": "Run as administrator"})],
                capability="desktop_gui",
                risk_level="critical",
                requires_approval=True,
                completes_subgoal=True,
            )

        def verify_step(self, execution_state, step, before, after):
            raise AssertionError("Rejected approval must not execute or verify.")

        def build_pending_decision(self, *, step, subgoal):
            return PendingDecision(
                id="approval-test",
                summary=step.intent,
                reason="High-risk test step.",
                risk_level=step.risk_level,
                decision_type="step_approval",
                actions=list(step.actions),
            )

    try:
        config = AgentConfig(dry_run=False, max_steps=2, run_root=run_root)
        executor = _ExecutorStub()
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=executor,
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            capability_executor=_ApprovalCapabilityExecutor(),
            decision_callback=lambda payload: decisions.append(payload) or {"decision": "reject"},
        )

        result = agent.run("open calculator")

        assert result.completed is False
        assert "high-risk step was rejected" in (result.error or "")
        assert executor.executed_batches == 0
        assert decisions[0]["pending_decision"]["decision_type"] == "step_approval"
        full_state = json.loads((result.run_dir / "execution_state.json").read_text(encoding="utf-8"))
        assert full_state["orchestration_phase"] == "blocked"
        assert full_state["last_verification"]["failure_kind"] == "approval_rejected"
        assert full_state["app_context"]["standard_recovery_kind"] == "safety_gate"
        assert full_state["task_graph"]["subgoals"][0]["status"] == "blocked"
        assert full_state["failure_budget"]["subgoal_01"] == 0
        assert full_state["evidence_ledger"][-1]["status"] == "failed"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_clears_pending_decision_after_step_approval_cancel():
    scratch_root = Path("test_artifacts") / f"controller_step_cancel_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)
    decisions: list[dict] = []

    class _ApprovalCapabilityExecutor:
        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            return StepProposal(
                intent="Click the guarded confirmation.",
                actions=[Action.from_dict({"type": "click", "x": 100, "y": 100})],
                capability="desktop_gui",
                risk_level="high",
                requires_approval=True,
                completes_subgoal=True,
            )

        def verify_step(self, execution_state, step, before, after):
            raise AssertionError("Cancelled approval must not execute or verify.")

        def build_pending_decision(self, *, step, subgoal):
            return PendingDecision(
                id="approval-cancel-test",
                summary=step.intent,
                reason="High-risk test step.",
                risk_level=step.risk_level,
                decision_type="step_approval",
                actions=list(step.actions),
            )

    try:
        config = AgentConfig(dry_run=False, max_steps=2, run_root=run_root)
        executor = _ExecutorStub()
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=executor,
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            capability_executor=_ApprovalCapabilityExecutor(),
            decision_callback=lambda payload: decisions.append(payload) or {"decision": " CANCELLED ", "note": "Stop for now."},
        )

        result = agent.run("open calculator")

        assert result.completed is False
        assert result.cancelled is True
        assert result.cancel_reason == "Stop for now."
        assert executor.executed_batches == 0
        assert decisions[0]["pending_decision"]["decision_type"] == "step_approval"
        full_state = json.loads((result.run_dir / "execution_state.json").read_text(encoding="utf-8"))
        assert full_state["pending_decision"] is None
        assert full_state["orchestration_phase"] == "awaiting_approval"
        assert full_state["stage_decisions"][-1]["decision_type"] == "step_approval"
        assert full_state["stage_decisions"][-1]["status"] == "cancelled"
        summary = build_execution_plan_summary(ExecutionState.from_dict(full_state))
        assert summary["plan_health"]["autonomy"]["status"] == "review_required"
        assert summary["plan_health"]["autonomy"]["requires_review"] is True
        assert summary["plan_health"]["autonomy"]["next_action"] == "approve_step"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_resume_after_step_approval_cancel_requests_approval_again():
    scratch_root = Path("test_artifacts") / f"controller_step_cancel_resume_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)
    first_decisions: list[dict] = []
    resumed_decisions: list[dict] = []

    class _ApprovalCapabilityExecutor:
        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            return StepProposal(
                intent="Click the guarded confirmation.",
                actions=[Action.from_dict({"type": "click", "x": 100, "y": 100})],
                capability="desktop_gui",
                risk_level="high",
                requires_approval=True,
                completes_subgoal=True,
            )

        def verify_step(self, execution_state, step, before, after):
            return VerificationResult(
                success=True,
                status="success",
                evidence=[
                    {
                        "scope": "subgoal_completion",
                        "satisfied": True,
                        "message": "The guarded confirmation was clicked.",
                    }
                ],
            )

        def build_pending_decision(self, *, step, subgoal):
            return PendingDecision(
                id=f"approval-{len(first_decisions) + len(resumed_decisions) + 1}",
                summary=step.intent,
                reason="Critical administrator test step.",
                risk_level=step.risk_level,
                decision_type="step_approval",
                actions=list(step.actions),
                approval_policy="autonomous",
                requires_user_presence=True,
                operator_hint="Keep a person at the screen before approving.",
            )

    try:
        config = AgentConfig(dry_run=False, max_steps=2, run_root=run_root)
        first_executor = _ExecutorStub()
        first_agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=first_executor,
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            capability_executor=_ApprovalCapabilityExecutor(),
            decision_callback=lambda payload: first_decisions.append(payload) or {"decision": " CANCEL ", "note": "Stop for now."},
        )

        cancelled = first_agent.run("open calculator")

        assert cancelled.cancelled is True
        assert first_executor.executed_batches == 0
        assert len(first_decisions) == 1

        resume_context = controller._load_resume_context(run_root, cancelled.run_dir.name)
        resume_state = controller._prepare_execution_state_for_resume(resume_context.execution_state)
        resumed_executor = _ExecutorStub()
        resumed_agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=resumed_executor,
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            capability_executor=_ApprovalCapabilityExecutor(),
            decision_callback=lambda payload: resumed_decisions.append(payload)
            or {
                "decision": " APPROVED ",
                "note": "Operator is present and ready to handle administrator or UAC prompts.",
            },
        )

        completed = resumed_agent.run(
            resume_context.task,
            run_dir=resume_context.run_dir,
            execution_state=resume_state,
            started_at=resume_context.started_at,
            step_offset=resume_context.step_offset,
        )

        assert completed.completed is True
        assert completed.error is None
        assert resumed_executor.executed_batches == 1
        assert len(resumed_decisions) == 1
        assert resumed_decisions[0]["pending_decision"]["decision_type"] == "step_approval"
        assert resumed_decisions[0]["pending_decision"]["approval_policy"] == "autonomous"
        assert resumed_decisions[0]["pending_decision"]["requires_user_presence"] is True
        assert "person at the screen" in resumed_decisions[0]["pending_decision"]["operator_hint"]
        full_state = json.loads((completed.run_dir / "execution_state.json").read_text(encoding="utf-8"))
        assert full_state["completed"] is True
        assert full_state["pending_decision"] is None
        assert full_state["stage_decisions"][-2]["status"] == "cancelled"
        assert full_state["stage_decisions"][-2]["note"] == "Stop for now."
        assert full_state["stage_decisions"][-1]["status"] == "approved"
        assert full_state["stage_decisions"][-1]["note"] == (
            "Operator is present and ready to handle administrator or UAC prompts."
        )
        assert full_state["task_graph"]["subgoals"][0]["status"] == "completed"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_auto_runs_low_risk_plan_without_plan_review():
    scratch_root = Path("test_artifacts") / f"controller_low_risk_auto_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)
    decisions: list[dict] = []

    class _LowRiskCapabilityExecutor:
        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            return StepProposal(
                intent="Open Calculator.",
                actions=[Action.from_dict({"type": "open_app_if_needed", "app": "calculator"})],
                capability="desktop_gui",
                completes_subgoal=True,
            )

        def verify_step(self, execution_state, step, before, after):
            return VerificationResult(success=True, status="success", evidence=[{"kind": "state", "value": "calculator"}])

    try:
        config = AgentConfig(dry_run=False, max_steps=1, run_root=run_root)
        executor = _ExecutorStub()
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=executor,
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            capability_executor=_LowRiskCapabilityExecutor(),
            decision_callback=lambda payload: decisions.append(payload) or {"decision": "reject"},
        )

        result = agent.run("open calculator")

        assert result.completed is True
        assert decisions == []
        assert executor.executed_batches == 1
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_marks_user_stop_with_cancel_reason():
    scratch_root = Path("test_artifacts") / f"controller_cancel_reason_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)

    class _InterruptingExecutor(_ExecutorStub):
        def execute_many(self, actions, pause_after_action, stop_requested=None):
            super().execute_many(actions, pause_after_action, stop_requested=stop_requested)
            raise ExecutionCancelled("Stopped by user.")

    try:
        config = AgentConfig(dry_run=False, max_steps=2, run_root=run_root)
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=_InterruptingExecutor(),
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
        )

        result = agent.run("stop during execution")

        assert result.completed is False
        assert result.cancelled is True
        assert result.cancel_reason == "Stopped by user."
        summary_payload = json.loads((result.run_dir / "summary.json").read_text(encoding="utf-8"))
        assert summary_payload["cancelled"] is True
        assert summary_payload["cancel_reason"] == "Stopped by user."
        step_payload = json.loads((result.run_dir / "step_01.json").read_text(encoding="utf-8"))
        assert step_payload["error"] == "Stopped by user."
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_stops_after_execution_before_post_capture():
    scratch_root = Path("test_artifacts") / f"controller_stop_after_execute_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)
    stop_state = {"requested": False}

    class _CountingPerception(_PerceptionStub):
        def __init__(self) -> None:
            self.captures = 0

        def capture(self, output_path: Path) -> ScreenInfo:
            self.captures += 1
            return super().capture(output_path)

    class _StopAfterExecuteExecutor(_ExecutorStub):
        def execute_many(self, actions, pause_after_action, stop_requested=None):
            super().execute_many(actions, pause_after_action, stop_requested=stop_requested)
            stop_state["requested"] = True

    class _LowRiskCapabilityExecutor:
        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            return StepProposal(
                intent="Open Calculator.",
                actions=[Action.from_dict({"type": "open_app_if_needed", "app": "calculator"})],
                capability="desktop_gui",
                completes_subgoal=True,
            )

        def verify_step(self, execution_state, step, before, after):
            raise AssertionError("verify_step should not run after stop was requested")

    try:
        config = AgentConfig(dry_run=False, max_steps=1, run_root=run_root)
        perception = _CountingPerception()
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=_StopAfterExecuteExecutor(),
            perception=perception,
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            capability_executor=_LowRiskCapabilityExecutor(),
            stop_requested=lambda: stop_state["requested"],
        )

        result = agent.run("open calculator")

        assert result.completed is False
        assert result.cancelled is True
        assert perception.captures == 1
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_replans_after_recoverable_execution_error():
    scratch_root = Path("test_artifacts") / f"controller_recover_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)

    class _FlakyExecutor(_ExecutorStub):
        def execute_many(self, actions, pause_after_action, stop_requested=None):
            super().execute_many(actions, pause_after_action, stop_requested=stop_requested)
            if self.executed_batches == 1:
                raise ExecutionError("Could not focus window: Calculator")

    class _RecoveryCapabilityExecutor:
        def __init__(self) -> None:
            self.proposals = 0

        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            self.proposals += 1
            return StepProposal(
                intent="Focus Calculator and continue.",
                actions=[Action.from_dict({"type": "focus_window", "title": "Calculator"})],
                capability="windows_uia",
                current_focus="Calculator",
                expected_evidence=[],
                progress_signals=["Calculator"],
                repair_strategy=["refocus_window", "retry_with_fresh_observation"],
                completes_subgoal=self.proposals >= 2,
            )

        def verify_step(self, execution_state, step, before, after):
            return VerificationResult(
                success=True,
                status="success",
                evidence=[{"kind": "state", "value": "calculator-focused"}],
            )

    try:
        config = AgentConfig(
            dry_run=False,
            max_steps=4,
            run_root=run_root,
            replan_on_recoverable_error=True,
            recoverable_error_retry_limit=2,
        )
        agent = DesktopAgent(
            config=config,
            planner=_RecoveringPlanner(),
            executor=_FlakyExecutor(),
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            capability_executor=_RecoveryCapabilityExecutor(),
        )

        result = agent.run("recover from a missing calculator window")

        assert result.completed is True
        assert result.error is None
        assert result.steps == 2
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_emits_replanned_state_after_recoverable_execution_error():
    scratch_root = Path("test_artifacts") / f"controller_recover_progress_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)

    class _RepeatedFocusFailureExecutor(_ExecutorStub):
        def execute_many(self, actions, pause_after_action, stop_requested=None):
            super().execute_many(actions, pause_after_action, stop_requested=stop_requested)
            if self.executed_batches <= 3:
                raise ExecutionError("Could not focus window: Calculator")

    class _ReplanningTaskGraphPlanner:
        def __init__(self) -> None:
            self.calls = 0

        def plan(self, task, history=None, world_model=None):
            return TaskGraph(
                task=task,
                subgoals=[
                    Subgoal(
                        id="subgoal_01",
                        title="Focus the original window",
                        goal="Focus the original window",
                        goal_type="confirm",
                        success_condition="The original window is focused.",
                        capability_preference="windows_uia",
                        completion_evidence={"kind": "state"},
                    )
                ],
                dependencies={"subgoal_01": []},
                intent={"task_type": "single_step", "risk_level": "low", "ambiguity": "low"},
            )

        def replan_remaining(self, execution_state, world_model, failure):
            self.calls += 1
            graph = execution_state.task_graph
            graph.subgoals[0].title = "Finish through the replanned route"
            graph.subgoals[0].goal = "Finish through the replanned route"
            graph.subgoals[0].status = "pending"
            graph.subgoals[0].failed_capabilities = []
            return graph

    class _ReplanAwareCapabilityExecutor:
        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            subgoal = execution_state.current_subgoal()
            title = subgoal.title if subgoal is not None else "Finish"
            attempt = int(getattr(execution_state, "stuck_rounds", 0) or 0) + 1
            return StepProposal(
                intent=title,
                actions=[Action.from_dict({"type": "focus_window", "title": f"Calculator {attempt}"})],
                capability="windows_uia",
                current_focus=f"{title} attempt {attempt}",
                completes_subgoal="replanned" in title,
            )

        def verify_step(self, execution_state, step, before, after):
            return VerificationResult(
                success=True,
                status="success",
                evidence=[{"kind": "state", "value": "replanned route finished"}],
            )

    try:
        progress_payloads = []
        config = AgentConfig(
            dry_run=False,
            max_steps=5,
            run_root=run_root,
            replan_on_recoverable_error=True,
            recoverable_error_retry_limit=4,
        )
        graph_planner = _ReplanningTaskGraphPlanner()
        agent = DesktopAgent(
            config=config,
            planner=_RecoveringPlanner(),
            executor=_RepeatedFocusFailureExecutor(),
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            task_graph_planner=graph_planner,
            capability_executor=_ReplanAwareCapabilityExecutor(),
            progress_callback=lambda payload: progress_payloads.append(dict(payload)),
        )

        result = agent.run("recover by replanning a missing calculator window")

        assert result.completed is True
        assert graph_planner.calls == 1
        failure_payloads = [
            payload for payload in progress_payloads if payload.get("error") == "Could not focus window: Calculator"
        ]
        assert len(failure_payloads) == 3
        replanned_failure = failure_payloads[-1]
        assert replanned_failure["last_replan_reason"] == "Could not focus window: Calculator"
        state_payload = replanned_failure["execution_state"]
        assert state_payload["current_goal"] == "Finish through the replanned route"
        assert state_payload["app_context"]["last_replan_reason"] == "Could not focus window: Calculator"
        assert state_payload["plan_health"]["next_subgoal"]["title"] == "Finish through the replanned route"
        assert state_payload["plan_health"]["autonomy"]["status"] == "ready"
        assert state_payload["plan_health"]["autonomy"]["next_action"] == "execute"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_stops_recoverable_execution_error_when_auto_replan_disabled():
    scratch_root = Path("test_artifacts") / f"controller_recover_disabled_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)

    class _FlakyExecutor(_ExecutorStub):
        def execute_many(self, actions, pause_after_action, stop_requested=None):
            super().execute_many(actions, pause_after_action, stop_requested=stop_requested)
            raise ExecutionError("Could not focus window: Calculator")

    class _RecoveryCapabilityExecutor:
        def __init__(self) -> None:
            self.proposals = 0

        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            self.proposals += 1
            return StepProposal(
                intent="Focus Calculator and continue.",
                actions=[Action.from_dict({"type": "focus_window", "title": "Calculator"})],
                capability="windows_uia",
                current_focus="Calculator",
                repair_strategy=["refocus_window", "retry_with_fresh_observation"],
                completes_subgoal=False,
            )

    try:
        config = AgentConfig(
            dry_run=False,
            max_steps=4,
            run_root=run_root,
            replan_on_recoverable_error=False,
            recoverable_error_retry_limit=2,
        )
        executor = _FlakyExecutor()
        capability_executor = _RecoveryCapabilityExecutor()
        agent = DesktopAgent(
            config=config,
            planner=_RecoveringPlanner(),
            executor=executor,
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            capability_executor=capability_executor,
        )

        result = agent.run("recover from a missing calculator window")

        assert result.completed is False
        assert result.error == "Could not focus window: Calculator"
        assert result.steps == 1
        assert executor.executed_batches == 1
        assert capability_executor.proposals == 1
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_replans_remaining_work_after_repeated_verification_failure():
    scratch_root = Path("test_artifacts") / f"controller_replan_remaining_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)

    class _ReplanTaskGraphPlanner:
        def __init__(self) -> None:
            self.calls = 0

        def plan(self, task, history=None, world_model=None):
            return TaskGraph(
                task=task,
                subgoals=[
                    Subgoal(
                        id="subgoal_01",
                        title="Complete the brittle step",
                        goal="Complete the brittle step",
                        goal_type="confirm",
                        success_condition="The brittle step completes.",
                        fallback_goal="Complete the repaired step",
                        capability_preference="desktop_gui",
                        completion_evidence={"kind": "state_change"},
                    )
                ],
                dependencies={"subgoal_01": []},
                intent={"task_type": "multi_step_workflow", "risk_level": "low", "ambiguity": "low"},
            )

        def replan_remaining(self, execution_state, world_model, failure):
            self.calls += 1
            graph = execution_state.task_graph
            graph.subgoals[0].title = "Complete the repaired step"
            graph.subgoals[0].goal = "Complete the repaired step"
            graph.subgoals[0].status = "pending"
            graph.subgoals[0].failed_capabilities = []
            return graph

    class _ReplanningCapabilityExecutor:
        def __init__(self) -> None:
            self.proposals = 0

        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            self.proposals += 1
            return StepProposal(
                intent=f"Try visible route {self.proposals}.",
                actions=[Action.from_dict({"type": "click", "x": 100 + self.proposals, "y": 220})],
                capability="desktop_gui",
                current_focus=f"attempt {self.proposals}",
                completes_subgoal=self.proposals >= 4,
            )

        def verify_step(self, execution_state, step, before, after):
            if self.proposals >= 4:
                return VerificationResult(success=True, status="success", evidence=[{"kind": "state", "value": "repaired"}])
            return VerificationResult(
                success=False,
                status="failed",
                failure_kind="blocked_by_ui",
                message="The route did not move the task forward.",
            )

    try:
        config = AgentConfig(dry_run=False, max_steps=5, run_root=run_root)
        graph_planner = _ReplanTaskGraphPlanner()
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=_ExecutorStub(),
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            task_graph_planner=graph_planner,
            capability_executor=_ReplanningCapabilityExecutor(),
        )

        result = agent.run("complete a brittle low risk workflow")

        assert result.completed is True
        assert graph_planner.calls == 1
        plan_payload = json.loads((result.run_dir / "plan.json").read_text(encoding="utf-8"))
        assert plan_payload["subgoals"][0]["title"] == "Complete the repaired step"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_repairs_after_repeated_partial_progress():
    scratch_root = Path("test_artifacts") / f"controller_partial_repair_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)

    class _PartialTaskGraphPlanner:
        def plan(self, task, history=None, world_model=None):
            return TaskGraph(
                task=task,
                subgoals=[
                    Subgoal(
                        id="subgoal_01",
                        title="Complete the partially advancing step",
                        goal="Complete the partially advancing step",
                        goal_type="confirm",
                        success_condition="The step reaches a verified final state.",
                    )
                ],
                dependencies={"subgoal_01": []},
                intent={"task_type": "multi_step_workflow", "risk_level": "low", "ambiguity": "low"},
            )

        def replan_remaining(self, execution_state, world_model, failure):
            return execution_state.task_graph

    class _PartialProgressCapabilityExecutor:
        def __init__(self) -> None:
            self.proposals = 0
            self.repairs = 0

        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            pending_repair = execution_state.app_context.get("pending_repair")
            if isinstance(pending_repair, dict):
                self.repairs += 1
                return StepProposal(
                    intent="Repair after repeated partial progress.",
                    actions=[Action.from_dict({"type": "wait", "seconds": 0.1})],
                    capability="browser_dom",
                    current_focus="repair route",
                    completes_subgoal=True,
                )
            self.proposals += 1
            return StepProposal(
                intent=f"Advance route {self.proposals}.",
                actions=[Action.from_dict({"type": "press", "key": "enter"})],
                capability="browser_dom",
                current_focus="partial route",
                completes_subgoal=False,
            )

        def verify_step(self, execution_state, step, before, after):
            if step.completes_subgoal:
                return VerificationResult(
                    success=True,
                    status="success",
                    evidence=[{"kind": "state", "value": "repaired"}],
                )
            return VerificationResult(
                success=False,
                status="partial_progress",
                failure_kind="verification_failed",
                message="The route moved forward but did not prove completion.",
            )

    try:
        config = AgentConfig(dry_run=False, max_steps=4, run_root=run_root)
        capability_executor = _PartialProgressCapabilityExecutor()
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=_ExecutorStub(),
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            task_graph_planner=_PartialTaskGraphPlanner(),
            capability_executor=capability_executor,
        )

        result = agent.run("complete a step that keeps making partial progress")

        assert result.completed is True
        assert result.error is None
        assert result.steps == 3
        assert capability_executor.proposals == 2
        assert capability_executor.repairs == 1
        state_payload = json.loads((result.run_dir / "state.json").read_text(encoding="utf-8"))
        assert state_payload["capability_failures"]["subgoal_01:browser_dom"][:2] == [
            "partial_progress",
            "partial_progress",
        ]
        assert any(item["mode"] == "repair" for item in state_payload["repair_history"])
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_blocks_when_partial_progress_recovery_is_exhausted():
    scratch_root = Path("test_artifacts") / f"controller_partial_exhausted_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)

    class _PartialExhaustionTaskGraphPlanner:
        def __init__(self) -> None:
            self.replans = 0

        def plan(self, task, history=None, world_model=None):
            return TaskGraph(
                task=task,
                subgoals=[
                    Subgoal(
                        id="subgoal_01",
                        title="Complete a step that only partly advances",
                        goal="Complete a step that only partly advances",
                        goal_type="confirm",
                        success_condition="The final state is verified.",
                    )
                ],
                dependencies={"subgoal_01": []},
                intent={"task_type": "multi_step_workflow", "risk_level": "low", "ambiguity": "low"},
            )

        def replan_remaining(self, execution_state, world_model, failure):
            self.replans += 1
            graph = execution_state.task_graph
            graph.subgoals[0].status = "pending"
            graph.subgoals[0].failed_capabilities = []
            return graph

    class _AlwaysPartialCapabilityExecutor:
        def __init__(self) -> None:
            self.proposals = 0
            self.repairs = 0

        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            if isinstance(execution_state.app_context.get("pending_repair"), dict):
                self.repairs += 1
            self.proposals += 1
            return StepProposal(
                intent=f"Try partial route {self.proposals}.",
                actions=[Action.from_dict({"type": "wait", "seconds": 0.1})],
                capability="browser_dom",
                current_focus="partial route",
                completes_subgoal=False,
            )

        def verify_step(self, execution_state, step, before, after):
            return VerificationResult(
                success=False,
                status="partial_progress",
                failure_kind="verification_failed",
                message="Screen changed but completion is missing.",
            )

    try:
        config = AgentConfig(dry_run=False, max_steps=8, run_root=run_root)
        graph_planner = _PartialExhaustionTaskGraphPlanner()
        capability_executor = _AlwaysPartialCapabilityExecutor()
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=_ExecutorStub(),
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            task_graph_planner=graph_planner,
            capability_executor=capability_executor,
        )

        result = agent.run("complete a step that only partly advances")

        assert result.completed is False
        assert result.steps < config.max_steps
        assert "Repeated partial progress" in (result.error or "")
        assert graph_planner.replans == 1
        assert capability_executor.repairs == 2
        state_payload = json.loads((result.run_dir / "state.json").read_text(encoding="utf-8"))
        assert state_payload["verification_status"] == "failed"
        assert state_payload["current_subgoal"]["status"] == "blocked"
        assert [item["mode"] for item in state_payload["repair_history"]] == ["repair", "repair", "replan"]
        full_state = json.loads((result.run_dir / "execution_state.json").read_text(encoding="utf-8"))
        assert full_state["failure_budget"]["subgoal_01"] == 0
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_desktop_agent_resume_reuses_existing_run_dir_and_state():
    scratch_root = Path("test_artifacts") / f"controller_resume_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_dir = run_root / "existing_run"
    run_dir.mkdir(parents=True, exist_ok=True)

    class _ResumeCapabilityExecutor:
        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            return StepProposal(
                intent="Finish the resumed subgoal.",
                actions=[Action.from_dict({"type": "wait", "seconds": 0.1})],
                capability="desktop_gui",
                completes_subgoal=True,
            )

        def verify_step(self, execution_state, step, before, after):
            return VerificationResult(success=True, evidence=[{"kind": "state", "value": "resumed"}])

    try:
        config = AgentConfig(dry_run=False, max_steps=3, run_root=run_root)
        task_graph = TaskGraph(
            task="resume the interrupted task",
            subgoals=[
                Subgoal(
                    id="subgoal_01",
                    title="Finish the interrupted step",
                    success_condition="The resumed step completes successfully.",
                )
            ],
        )
        state = ExecutionState(
            task="resume the interrupted task",
            run_id=run_dir.name,
            task_graph=task_graph,
            memory=["Paused for manual verification."],
        )
        agent = DesktopAgent(
            config=config,
            planner=_TwoStepPlanner(),
            executor=_ExecutorStub(),
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
            capability_executor=_ResumeCapabilityExecutor(),
        )

        result = agent.run(
            "resume the interrupted task",
            run_dir=run_dir,
            execution_state=state,
            started_at=123.0,
            step_offset=3,
            history=list(state.memory),
        )

        assert result.completed is True
        assert result.run_dir == run_dir
        assert result.steps == 4
        assert (run_dir / "step_04.json").exists()
        summary_payload = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        assert summary_payload["completed"] is True
        assert summary_payload["steps"] == 4
        display_state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
        full_state = json.loads((run_dir / "execution_state.json").read_text(encoding="utf-8"))
        assert "task_graph" not in display_state
        assert full_state["run_id"] == run_dir.name
        assert full_state["task_graph"]["subgoals"][0]["status"] == "completed"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_load_resume_context_prefers_full_execution_state_file():
    scratch_root = Path("test_artifacts") / f"controller_resume_full_state_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_dir = run_root / "existing_run"
    run_dir.mkdir(parents=True, exist_ok=True)

    try:
        (run_dir / "summary.json").write_text(
            json.dumps(
                {
                    "task": "resume the saved graph",
                    "completed": False,
                    "steps": 2,
                    "started_at": 123.0,
                }
            ),
            encoding="utf-8",
        )
        display_summary = {
            "task": "resume the saved graph",
            "subgoals": [
                {
                    "id": "display_only",
                    "title": "Display-only summary",
                    "success_condition": "This should not drive resume.",
                }
            ],
            "repair_history": [{"mode": "summary"}],
        }
        (run_dir / "state.json").write_text(json.dumps(display_summary), encoding="utf-8")

        task_graph = TaskGraph(
            task="resume the saved graph",
            subgoals=[
                Subgoal(
                    id="subgoal_01",
                    title="Continue from the durable state",
                    success_condition="The durable state is loaded.",
                    status="in_progress",
                )
            ],
            dependencies={"subgoal_01": []},
        )
        state = ExecutionState(
            task="resume the saved graph",
            run_id=run_dir.name,
            task_graph=task_graph,
            memory=["Paused with a full execution state."],
            repair_history=[{"mode": "repair", "subgoal_id": "subgoal_01"}],
            app_context={"pending_repair": {"subgoal_id": "subgoal_01"}},
        )
        (run_dir / "execution_state.json").write_text(json.dumps(state.to_dict()), encoding="utf-8")

        context = controller._load_resume_context(run_root, run_dir.name)

        assert context.execution_state is not None
        assert context.execution_state.task_graph.subgoals[0].id == "subgoal_01"
        assert context.execution_state.task_graph.subgoals[0].status == "in_progress"
        assert context.execution_state.memory == ["Paused with a full execution state."]
        assert context.execution_state.repair_history[0]["mode"] == "repair"
        assert context.execution_state.app_context["pending_repair"]["subgoal_id"] == "subgoal_01"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_load_resume_context_reconstructs_legacy_summary_state():
    scratch_root = Path("test_artifacts") / f"controller_resume_legacy_state_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_dir = run_root / "legacy_run"
    run_dir.mkdir(parents=True, exist_ok=True)

    try:
        (run_dir / "summary.json").write_text(
            json.dumps(
                {
                    "task": "resume a legacy paused run",
                    "completed": False,
                    "steps": 2,
                    "started_at": 456.0,
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "step_05.json").write_text(json.dumps({"step": 5}), encoding="utf-8")
        task_graph = TaskGraph(
            task="resume a legacy paused run",
            subgoals=[
                Subgoal(
                    id="subgoal_01",
                    title="Finish legacy subgoal",
                    success_condition="The legacy subgoal is resumed.",
                    status="in_progress",
                )
            ],
            dependencies={"subgoal_01": []},
        )
        (run_dir / "plan.json").write_text(json.dumps(task_graph.to_dict()), encoding="utf-8")
        (run_dir / "state.json").write_text(
            json.dumps(
                {
                    "task": "resume a legacy paused run",
                    "orchestration_phase": "executing",
                    "workspace_summary": {"notes": ["legacy note"], "evidence": [{"status": "partial"}]},
                    "last_step": StepProposal(
                        intent="Continue the legacy action.",
                        actions=[Action.from_dict({"type": "wait", "seconds": 0.1})],
                        capability="desktop_gui",
                    ).to_dict(),
                    "last_verification": VerificationResult(
                        success=False,
                        status="partial_progress",
                        evidence=[{"kind": "state_change", "satisfied": False}],
                    ).to_dict(),
                    "evidence_ledger": [{"subgoal_id": "subgoal_01", "status": "partial_progress"}],
                    "repair_history": [{"mode": "repair", "subgoal_id": "subgoal_01"}],
                    "app_context": {"pending_repair": {"subgoal_id": "subgoal_01"}},
                    "current_surface_kind": "managed_aoryn_browser",
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "facts.json").write_text(
            json.dumps({"items": [{"source": "world_model", "key": "active_app", "value": "browser"}]}),
            encoding="utf-8",
        )

        context = controller._load_resume_context(run_root, run_dir.name)

        assert context.step_offset == 5
        assert context.execution_state is not None
        assert context.execution_state.task_graph.subgoals[0].title == "Finish legacy subgoal"
        assert context.execution_state.orchestration_phase == "executing"
        assert context.execution_state.workspace.notes == ["legacy note"]
        assert context.execution_state.last_step is not None
        assert context.execution_state.last_verification is not None
        assert context.execution_state.last_verification.status == "partial_progress"
        assert context.execution_state.facts[0].key == "active_app"
        assert context.execution_state.repair_history[0]["mode"] == "repair"
        assert context.execution_state.current_surface_kind == "managed_aoryn_browser"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_prepare_resume_execution_state_clears_manual_handoff_blocker():
    task_graph = TaskGraph(
        task="resume after login",
        subgoals=[
            Subgoal(
                id="subgoal_01",
                title="Continue after login",
                success_condition="The signed-in page is ready.",
            )
        ],
        dependencies={"subgoal_01": []},
    )
    state = ExecutionState(
        task="resume after login",
        run_id="manual-run",
        task_graph=task_graph,
        orchestration_phase="awaiting_user",
        last_verification=VerificationResult(
            success=False,
            status="failed",
            failure_kind="requires_human",
            message="Complete the login prompt.",
        ),
        app_context={
            "human_handoff_kind": "login",
            "human_handoff_summary": "Login required.",
            "human_handoff_reason": "Complete the login prompt.",
            "recovery_reason": "Complete the login prompt.",
            "standard_recovery_kind": "requires_user",
        },
    )

    before = build_execution_plan_summary(state)
    assert before["plan_health"]["autonomy"]["status"] == "waiting_user"

    prepared = controller._prepare_execution_state_for_resume(state)

    assert prepared is state
    summary = build_execution_plan_summary(prepared)
    assert summary["orchestration_phase"] == "stage_ready"
    assert summary["plan_health"]["autonomy"]["status"] == "ready"
    assert summary["plan_health"]["autonomy"]["can_continue"] is True
    assert summary["recovery_reason"] is None
    assert summary["verification_status"] is None
    assert summary["last_verification"] is None
    assert "human_handoff_reason" not in summary["app_context"]
    assert summary["app_context"]["manual_resume_status"] == "resumed"
    assert prepared.repair_history[-1]["kind"] == "manual_resume"
    assert prepared.memory[-1].startswith("Resumed after user completed manual step")


def test_prepare_resume_execution_state_clears_saved_step_approval_checkpoint():
    task_graph = TaskGraph(
        task="resume after step approval",
        subgoals=[
            Subgoal(
                id="subgoal_01",
                title="Click guarded confirm",
                success_condition="The guarded confirmation is accepted.",
            )
        ],
        dependencies={"subgoal_01": []},
    )
    state = ExecutionState(
        task="resume after step approval",
        run_id="step-approval-run",
        task_graph=task_graph,
        orchestration_phase="awaiting_approval",
    )

    before = build_execution_plan_summary(state)
    assert before["plan_health"]["autonomy"]["status"] == "review_required"
    assert before["plan_health"]["autonomy"]["next_action"] == "approve_step"

    prepared = controller._prepare_execution_state_for_resume(state)

    assert prepared is state
    summary = build_execution_plan_summary(prepared)
    assert summary["orchestration_phase"] == "stage_ready"
    assert summary["pending_decision"] is None
    assert summary["plan_health"]["autonomy"]["status"] == "ready"
    assert summary["plan_health"]["autonomy"]["can_continue"] is True
    assert summary["plan_health"]["autonomy"]["requires_review"] is False
    assert summary["app_context"]["manual_resume_status"] == "resumed"
    assert prepared.repair_history[-1]["kind"] == "manual_resume"


def test_prepare_resume_execution_state_hides_stale_failure_recovery_reason():
    task_graph = TaskGraph(
        task="resume after auth",
        subgoals=[
            Subgoal(
                id="subgoal_01",
                title="Continue after auth",
                success_condition="The signed-in page is visible.",
            )
        ],
        dependencies={"subgoal_01": []},
    )
    state = ExecutionState(
        task="resume after auth",
        run_id="manual-run-top-level-recovery",
        task_graph=task_graph,
        orchestration_phase="awaiting_user",
        last_verification=VerificationResult(
            success=False,
            status="failed",
            failure_kind="requires_auth",
            message="Complete the sign-in challenge.",
        ),
        failures=[
            {
                "failure_kind": "requires_auth",
                "message": "Complete the sign-in challenge.",
            }
        ],
        app_context={"standard_recovery_kind": "requires_user"},
    )

    prepared = controller._prepare_execution_state_for_resume(state)
    summary = build_execution_plan_summary(prepared)

    assert prepared is state
    assert summary["orchestration_phase"] == "stage_ready"
    assert summary["recovery_reason"] is None
    assert summary["verification_status"] is None
    assert summary["last_verification"] is None
    assert summary["plan_health"]["autonomy"]["can_continue"] is True
    assert summary["app_context"]["manual_resume_status"] == "resumed"
    assert summary["app_context"]["manual_resume_reason"] == "Complete the sign-in challenge."


def test_prepare_resume_execution_state_keeps_clarification_waiting_for_user():
    task_graph = TaskGraph(
        task="clarify destination",
        subgoals=[
            Subgoal(
                id="subgoal_01",
                title="Ask which folder to use",
                goal_type="clarify",
                success_condition="The user provides a destination folder.",
            )
        ],
        dependencies={"subgoal_01": []},
    )
    state = ExecutionState(
        task="clarify destination",
        run_id="clarify-run",
        task_graph=task_graph,
        orchestration_phase="awaiting_user",
        last_verification=VerificationResult(
            success=False,
            status="failed",
            failure_kind="requires_clarification",
            message="Choose the destination folder.",
        ),
        app_context={
            "human_handoff_kind": "requires_clarification",
            "human_handoff_reason": "Choose the destination folder.",
            "standard_recovery_kind": "requires_user",
        },
    )

    prepared = controller._prepare_execution_state_for_resume(state)
    summary = build_execution_plan_summary(prepared)

    assert summary["orchestration_phase"] == "awaiting_user"
    assert summary["plan_health"]["autonomy"]["status"] == "waiting_user"
    assert summary["plan_health"]["autonomy"]["requires_user"] is True
    assert summary["app_context"]["human_handoff_kind"] == "requires_clarification"


def test_prepare_resume_execution_state_preserves_pending_review_decision():
    task_graph = TaskGraph(
        task="review generated task plan",
        subgoals=[
            Subgoal(
                id="subgoal_01",
                title="Review generated task plan",
                success_condition="The plan is approved before execution.",
            )
        ],
        dependencies={"subgoal_01": []},
    )
    state = ExecutionState(
        task="review generated task plan",
        run_id="review-run",
        task_graph=task_graph,
        orchestration_phase="plan_review",
        pending_decision=PendingDecision(
            id="plan-review-1",
            summary="Review the generated task plan.",
            reason="The plan touches an external account.",
            risk_level="high",
            decision_type="plan_review",
        ),
        app_context={
            "plan_review_status": "pending",
            "human_handoff_reason": "Review the generated task plan.",
            "standard_recovery_kind": "requires_user",
        },
    )

    prepared = controller._prepare_execution_state_for_resume(state)
    summary = build_execution_plan_summary(prepared)

    assert prepared is state
    assert prepared.pending_decision is not None
    assert prepared.pending_decision.decision_type == "plan_review"
    assert summary["orchestration_phase"] == "plan_review"
    assert summary["pending_decision"]["decision_type"] == "plan_review"
    assert summary["plan_health"]["autonomy"]["status"] == "review_required"
    assert "human_handoff_reason" not in summary["app_context"]
    assert "standard_recovery_kind" not in summary["app_context"]
    assert "manual_resume_status" not in summary["app_context"]


def test_build_history_entry_keeps_decomposition_context():
    plan = PlanResult(
        status_summary="Open openai.com, then continue with login.",
        done=False,
        actions=[Action.from_dict({"type": "browser_open", "text": "https://openai.com"})],
        current_focus="open openai.com",
        reasoning="The website must load before the login button is available.",
        remaining_steps=["click login", "enter credentials"],
    )

    history_entry = _build_history_entry(
        plan,
        [Action.from_dict({"type": "browser_open", "text": "https://openai.com"})],
    )

    assert "Current focus: open openai.com" in history_entry
    assert "Reasoning: The website must load before the login button is available." in history_entry
    assert "Remaining steps: click login -> enter credentials" in history_entry
    assert "Executed actions: browser_open(https://openai.com)" in history_entry


def test_launch_dashboard_cli_prefers_desktop_shell_on_windows(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr("desktop_agent.desktop_shell.sys.platform", "win32")
    monkeypatch.setitem(
        sys.modules,
        "desktop_agent.desktop_shell",
        SimpleNamespace(
            DesktopShellUnavailable=RuntimeError,
            launch_desktop_shell=lambda **kwargs: calls.append(("shell", kwargs)) or 7,
        ),
    )

    result = controller._launch_dashboard_cli([])

    assert result == 7
    assert calls == [
        (
            "shell",
            {
                "host": controller.DEFAULT_DASHBOARD_HOST,
                "port": controller.DEFAULT_DASHBOARD_PORT,
                "config_path": None,
            },
        )
    ]


def test_launch_dashboard_cli_browser_flag_keeps_browser_dashboard(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(controller.sys, "platform", "win32")
    monkeypatch.setitem(
        sys.modules,
        "desktop_agent.dashboard",
        SimpleNamespace(
            launch_dashboard=lambda **kwargs: calls.append(("browser", kwargs)) or 9,
        ),
    )

    result = controller._launch_dashboard_cli(["--browser", "--no-browser"])

    assert result == 9
    assert calls == [
        (
            "browser",
            {
                "host": controller.DEFAULT_DASHBOARD_HOST,
                "port": controller.DEFAULT_DASHBOARD_PORT,
                "config_path": None,
                "open_browser": False,
            },
        )
    ]


def test_build_floating_view_state_idle_and_expanded_input():
    from desktop_agent.desktop_shell import build_floating_view_state

    idle = build_floating_view_state()
    expanded = build_floating_view_state(input_expanded=True)

    assert idle.mode == "idle"
    assert (idle.width, idle.height) == (300, 52)
    assert idle.show_open is True
    assert idle.show_add is True
    assert idle.show_input is False

    assert expanded.mode == "idle_input"
    assert (expanded.width, expanded.height) == (620, 60)
    assert expanded.show_input is True
    assert expanded.show_submit is True
    assert expanded.show_cancel is True
    assert expanded.submit_label == "开始"


def test_build_floating_view_state_running_stopping_and_queued_input():
    from desktop_agent.desktop_shell import build_floating_view_state

    active_job = {
        "id": "job-1",
        "status": "running",
        "task": "点击浏览器里的继续按钮然后等待页面刷新",
    }
    handoff_job = {
        **active_job,
        "result": {
            "execution_state": {
                "current_goal": "继续登录后的页面",
                "app_context": {
                    "human_handoff_kind": "login",
                    "human_handoff_reason": "需要完成登录提示。",
                },
            }
        },
    }
    result_only_handoff_job = {
        **active_job,
        "result": {
            "requires_human": True,
            "interruption_kind": "requires_auth",
            "interruption_reason": "需要完成登录提示。",
        },
    }

    running = build_floating_view_state(active_job=active_job)
    handoff = build_floating_view_state(active_job=handoff_job)
    result_only_handoff = build_floating_view_state(active_job=result_only_handoff_job)
    queued = build_floating_view_state(active_job=active_job, follow_up_draft="下一步搜索文档")
    expanded = build_floating_view_state(
        active_job=active_job,
        follow_up_draft="下一步搜索文档",
        input_expanded=True,
    )
    stopping = build_floating_view_state(active_job={**active_job, "status": "stopping", "cancel_requested": True})
    failed = build_floating_view_state(
        active_job={**active_job, "result": {"error": "规划失败", "pending_decision": {"summary": "过期确认"}}},
        follow_up_draft="下一步搜索文档",
        input_expanded=True,
    )
    cancelled = build_floating_view_state(active_job={**active_job, "result": {"cancelled": True, "cancel_reason": "用户停止"}})
    completed = build_floating_view_state(active_job={**active_job, "result": {"completed": True, "latest_summary": "已整理结果"}})

    assert running.mode == "running"
    assert (running.width, running.height) == (480, 52)
    assert running.show_timer is True
    assert running.show_stop is True
    assert running.show_open is True
    assert running.show_add is True
    assert handoff.mode == "running"
    assert handoff.title == "等待人工处理: 需要完成登录提示。"
    assert result_only_handoff.mode == "running"
    assert result_only_handoff.title == "等待人工处理: 需要完成登录提示。"

    assert queued.mode == "running_queued"
    assert queued.add_label == "编辑"

    assert expanded.mode == "running_input"
    assert (expanded.width, expanded.height) == (620, 60)
    assert expanded.show_input is True
    assert expanded.submit_label == "排队"
    assert expanded.input_text == "下一步搜索文档"

    assert stopping.mode == "stopping"
    assert (stopping.width, stopping.height) == (300, 52)
    assert stopping.title == "正在停止"
    assert stopping.show_add is False
    assert stopping.show_stop is False
    assert stopping.show_open is True

    assert failed.mode == "running"
    assert failed.title == "需要处理: 规划失败"
    assert (failed.width, failed.height) == (300, 52)
    assert failed.show_timer is False
    assert failed.show_add is False
    assert failed.show_stop is False
    assert failed.show_open is True

    assert cancelled.mode == "stopping"
    assert cancelled.title == "任务已停止"
    assert cancelled.show_timer is False
    assert cancelled.show_stop is False
    assert cancelled.show_open is True

    assert completed.mode == "running"
    assert completed.title == "任务完成"
    assert completed.show_timer is False
    assert completed.show_stop is False
    assert completed.show_open is True


def test_build_floating_view_state_parses_string_boolean_flags():
    from desktop_agent.desktop_shell import build_floating_view_state

    active_job = {
        "id": "job-string-bools",
        "status": "running",
        "task": "continue the current task",
        "cancel_requested": "false",
        "cancelled": "false",
        "completed": "false",
        "requires_human": "false",
        "result": {
            "cancelled": "false",
            "completed": "false",
            "requires_human": "false",
        },
    }

    running = build_floating_view_state(active_job=active_job)
    stopping = build_floating_view_state(active_job={**active_job, "cancel_requested": "true"})
    cancelled = build_floating_view_state(active_job={**active_job, "result": {"cancelled": "true"}})
    completed = build_floating_view_state(active_job={**active_job, "result": {"completed": "true"}})

    assert running.mode == "running"
    assert running.show_stop is True
    assert running.show_add is True

    assert stopping.mode == "stopping"
    assert stopping.show_stop is False
    assert stopping.show_add is False

    assert cancelled.mode == "stopping"
    assert cancelled.show_open is True

    assert completed.mode == "running"
    assert completed.show_open is True
    assert completed.show_stop is False


def test_build_floating_view_state_approval_resume_and_waiting_follow_up():
    from desktop_agent.desktop_shell import build_floating_view_state

    approval = build_floating_view_state(
        active_job={
            "id": "job-approve",
            "status": "approval",
            "result": {"pending_decision": {"summary": "确认是否点击付款按钮"}},
        }
    )
    nested_approval = build_floating_view_state(
        active_job={
            "id": "job-nested-approve",
            "status": "running",
            "result": {
                "execution_state": {
                    "pending_decision": {
                        "summary": "确认是否执行生成的计划",
                        "reason": "当前计划需要复核",
                    }
                }
            },
        }
    )
    resume = build_floating_view_state(
        resume_run_id="run-human",
        resume_task="完成验证码后继续",
        resume_reason="等待人工处理",
    )
    waiting = build_floating_view_state(follow_up_draft="继续整理结果")
    editing = build_floating_view_state(follow_up_draft="继续整理结果", input_expanded=True)

    assert approval.mode == "approval"
    assert (approval.width, approval.height) == (520, 56)
    assert approval.show_continue is True
    assert approval.continue_label == "批准"
    assert approval.show_stop is True
    assert approval.stop_label == "驳回"
    assert nested_approval.mode == "approval"
    assert nested_approval.title == "确认是否执行生成的计划"
    assert nested_approval.show_continue is True

    assert resume.mode == "resume"
    assert (resume.width, resume.height) == (520, 56)
    assert resume.show_continue is True
    assert resume.continue_label == "恢复"
    assert resume.show_open is True

    assert waiting.mode == "followup"
    assert waiting.show_continue is True
    assert waiting.add_label == "编辑"

    assert editing.mode == "followup_input"
    assert editing.show_input is True
    assert editing.submit_label == "更新"
    assert editing.input_text == "继续整理结果"


def test_build_floating_view_state_saved_step_approval_phase_without_pending_decision():
    from desktop_agent.desktop_shell import build_floating_view_state

    approval = build_floating_view_state(
        active_job={
            "id": "job-saved-step-approval",
            "status": "running",
            "task": "Confirm guarded step",
            "result": {
                "execution_state": {
                    "orchestration_phase": "awaiting_approval",
                    "current_goal": "Click guarded confirm",
                }
            },
        }
    )

    assert approval.mode == "approval"
    assert (approval.width, approval.height) == (520, 56)
    assert approval.show_continue is True
    assert approval.show_stop is True


def test_desktop_shell_job_decision_helper_handles_nested_pending_decision():
    from desktop_agent.desktop_shell import _job_waits_for_decision, _pending_decision_from_job

    top_level_job = {
        "id": "job-top-level-approval",
        "status": "running",
        "pending_decision": {
            "decision_type": "plan_review",
            "summary": "Review the top-level task plan.",
        },
        "result": {},
    }
    nested_job = {
        "id": "job-nested-approval",
        "status": "running",
        "result": {
            "execution_state": {
                "pending_decision": {
                    "decision_type": "plan_review",
                    "summary": "Review the generated plan.",
                }
            }
        },
    }
    state_only_job = {
        "id": "job-state-approval",
        "status": "running",
        "result": {
            "state": {
                "pending_decision": {
                    "decision_type": "stage_review",
                    "summary": "Review the summarized stage.",
                }
            }
        },
    }
    terminal_failed_job = {
        "id": "job-failed-stale-approval",
        "status": "failed",
        "pending_decision": {
            "decision_type": "plan_review",
            "summary": "Stale approval should not keep the shell waiting.",
        },
        "result": {"error": "Planner crashed after approval cleanup."},
    }

    assert _pending_decision_from_job(top_level_job)["summary"] == "Review the top-level task plan."
    assert _job_waits_for_decision(top_level_job) is True
    assert _pending_decision_from_job(nested_job)["summary"] == "Review the generated plan."
    assert _job_waits_for_decision(nested_job) is True
    assert _pending_decision_from_job(state_only_job)["summary"] == "Review the summarized stage."
    assert _job_waits_for_decision(state_only_job) is True
    assert _job_waits_for_decision({"status": "approval", "result": {}}) is True
    assert _job_waits_for_decision(terminal_failed_job) is False
    assert _job_waits_for_decision({"status": "running", "result": {}}) is False


def test_desktop_shell_controller_stages_follow_up_while_running_without_submitting():
    from desktop_agent.desktop_shell import DesktopShellController

    floating_updates: list[tuple[dict[str, object], str]] = []
    controller_stub = SimpleNamespace(
        current_active_job_id="job-1",
        current_active_job={"id": "job-1", "status": "running"},
        follow_up_draft="",
        main_window=SimpleNamespace(isVisible=lambda: False),
        floating=SimpleNamespace(
            update_active_job=lambda job, draft: floating_updates.append((job, draft)),
            show_waiting_follow_up=lambda draft: floating_updates.append(({}, draft)),
        ),
    )

    result = DesktopShellController._submit_or_stage_follow_up(controller_stub, "  下一步打开设置  ")

    assert result is True
    assert controller_stub.follow_up_draft == "下一步打开设置"
    assert floating_updates == [({"id": "job-1", "status": "running"}, "下一步打开设置")]


def test_desktop_shell_controller_updates_waiting_follow_up_without_submitting():
    from desktop_agent.desktop_shell import DesktopShellController

    shown: list[str] = []
    controller_stub = SimpleNamespace(
        current_active_job_id=None,
        current_active_job=None,
        follow_up_draft="旧任务",
        main_window=SimpleNamespace(isVisible=lambda: False),
        floating=SimpleNamespace(
            update_active_job=lambda *_: None,
            show_waiting_follow_up=lambda draft: shown.append(draft),
        ),
    )

    result = DesktopShellController._submit_or_stage_follow_up(controller_stub, "  新任务  ")

    assert result is True
    assert controller_stub.follow_up_draft == "新任务"
    assert shown == ["新任务"]


def test_desktop_shell_controller_continue_follow_up_clears_only_after_success():
    from desktop_agent.desktop_shell import DesktopShellController

    hidden: list[str] = []
    controller_stub = SimpleNamespace(
        follow_up_draft="继续完成任务",
        success_feedback_deadline=123.0,
        _submit_task=lambda task: True,
        _hide_main_window_for_floating=lambda: hidden.append("hide"),
    )

    result = DesktopShellController._continue_follow_up(controller_stub)

    assert result is True
    assert controller_stub.follow_up_draft == ""
    assert controller_stub.success_feedback_deadline == 0
    assert hidden == ["hide"]

    failing_stub = SimpleNamespace(
        follow_up_draft="不要丢掉",
        success_feedback_deadline=123.0,
        _submit_task=lambda task: False,
        _hide_main_window_for_floating=lambda: hidden.append("unexpected"),
    )

    result = DesktopShellController._continue_follow_up(failing_stub)

    assert result is False
    assert failing_stub.follow_up_draft == "不要丢掉"


def test_desktop_shell_controller_stop_task_updates_state_only_after_success(monkeypatch):
    from desktop_agent.desktop_shell import DesktopShellController

    updates: list[tuple[dict[str, object], str]] = []

    class _Response:
        ok = True
        content = b"{}"

        def json(self):
            return {"status": "stopping"}

    monkeypatch.setattr("desktop_agent.desktop_shell.requests.post", lambda *_, **__: _Response())

    controller_stub = SimpleNamespace(
        base_url="http://127.0.0.1:8765",
        current_active_job={"id": "job-1", "status": "running"},
        follow_up_draft="保留草稿",
        main_window=SimpleNamespace(isVisible=lambda: False),
        floating=SimpleNamespace(update_active_job=lambda job, draft: updates.append((job, draft))),
    )

    result = DesktopShellController._stop_active_task(controller_stub)

    assert result is True
    assert controller_stub.current_active_job["status"] == "stopping"
    assert controller_stub.current_active_job["cancel_requested"] is True
    assert updates == [(controller_stub.current_active_job, "保留草稿")]

    def _raise(*_, **__):
        raise RuntimeError("offline")

    monkeypatch.setattr("desktop_agent.desktop_shell.requests.post", _raise)
    failing_stub = SimpleNamespace(
        base_url="http://127.0.0.1:8765",
        current_active_job={"id": "job-2", "status": "running"},
        follow_up_draft="不要清空",
        main_window=SimpleNamespace(isVisible=lambda: False),
        floating=SimpleNamespace(update_active_job=lambda *_: None),
    )

    result = DesktopShellController._stop_active_task(failing_stub)

    assert result is False
    assert failing_stub.current_active_job == {"id": "job-2", "status": "running"}
    assert failing_stub.follow_up_draft == "不要清空"


def test_desktop_shell_source_keeps_single_current_floating_implementation():
    source = Path("desktop_agent/desktop_shell.py").read_text(encoding="utf-8")

    assert "class _LegacyFloatingExecutionWindow" not in source
    assert "class _LegacyDesktopShellController" not in source
    assert source.count("class FloatingExecutionWindow") == 1
    assert source.count("class DesktopShellController") == 1


def test_desktop_shell_controller_ignores_tray_activation_while_menu_open():
    from desktop_agent.desktop_shell import DesktopShellController

    calls: list[str] = []
    controller_stub = SimpleNamespace(
        tray_menu_open=True,
        quitting=False,
        ignore_tray_activation_until=0.0,
        _toggle_main_window=lambda: calls.append("toggle"),
    )

    DesktopShellController._handle_tray_activated(
        controller_stub,
        SimpleNamespace(Trigger="trigger").Trigger,
    )

    assert calls == []


def test_desktop_shell_controller_allows_normal_tray_trigger():
    from desktop_agent.desktop_shell import DesktopShellController, QSystemTrayIcon

    calls: list[str] = []
    controller_stub = SimpleNamespace(
        tray_menu_open=False,
        quitting=False,
        ignore_tray_activation_until=0.0,
        _toggle_main_window=lambda: calls.append("toggle"),
    )

    DesktopShellController._handle_tray_activated(
        controller_stub,
        QSystemTrayIcon.ActivationReason.Trigger,
    )

    assert calls == ["toggle"]


def test_floating_taskbar_activation_opens_main_when_cursor_is_outside():
    from desktop_agent.desktop_shell import FloatingExecutionWindow

    opened: list[str] = []
    controller_stub = SimpleNamespace(
        _suppress_taskbar_activation_until=0.0,
        _cursor_is_over_window=lambda: False,
        _on_open_main=lambda: opened.append("open"),
    )
    controller_stub._remember_programmatic_activation = lambda duration=0.5: setattr(
        controller_stub,
        "_suppress_taskbar_activation_until",
        time.time() + duration,
    )

    FloatingExecutionWindow._open_main_from_taskbar(controller_stub, force=False)

    assert opened == ["open"]
    assert controller_stub._suppress_taskbar_activation_until > time.time()


def test_floating_direct_mouse_activation_does_not_open_main():
    from desktop_agent.desktop_shell import FloatingExecutionWindow

    opened: list[str] = []
    controller_stub = SimpleNamespace(
        _suppress_taskbar_activation_until=0.0,
        _cursor_is_over_window=lambda: True,
        _remember_programmatic_activation=lambda duration=0.5: None,
        _on_open_main=lambda: opened.append("open"),
    )

    FloatingExecutionWindow._open_main_from_taskbar(controller_stub, force=False)

    assert opened == []


def test_floating_taskbar_restore_ignores_cursor_position():
    from desktop_agent.desktop_shell import FloatingExecutionWindow

    opened: list[str] = []
    controller_stub = SimpleNamespace(
        _suppress_taskbar_activation_until=0.0,
        _cursor_is_over_window=lambda: True,
        _on_open_main=lambda: opened.append("open"),
    )
    controller_stub._remember_programmatic_activation = lambda duration=0.5: setattr(
        controller_stub,
        "_suppress_taskbar_activation_until",
        time.time() + duration,
    )

    FloatingExecutionWindow._open_main_from_taskbar(controller_stub, force=True)

    assert opened == ["open"]


def test_desktop_shell_controller_quit_path_blocks_tray_reopen():
    from desktop_agent.desktop_shell import DesktopShellController

    disconnected: list[str] = []
    hidden: list[str] = []
    allow_close: list[str] = []
    quit_calls: list[str] = []

    controller_stub = SimpleNamespace(
        quitting=False,
        tray_menu_open=True,
        ignore_tray_activation_until=0.0,
        _handle_tray_activated=object(),
        tray_icon=SimpleNamespace(
            activated=SimpleNamespace(disconnect=lambda handler: disconnected.append("disconnect")),
            hide=lambda: hidden.append("tray"),
        ),
        floating=SimpleNamespace(hide_floating=lambda: hidden.append("floating")),
        main_window=SimpleNamespace(allow_close=lambda: allow_close.append("allow")),
        qt_app=SimpleNamespace(quit=lambda: quit_calls.append("quit")),
    )

    DesktopShellController._quit_application(controller_stub)

    assert controller_stub.quitting is True
    assert controller_stub.tray_menu_open is False
    assert controller_stub.ignore_tray_activation_until > time.time()
    assert disconnected == ["disconnect"]
    assert hidden == ["floating", "tray"]
    assert allow_close == ["allow"]
    assert quit_calls == ["quit"]


def test_desktop_shell_controller_keeps_human_verification_in_floating_prompt():
    from desktop_agent.desktop_shell import DesktopShellController

    prompted: list[str] = []
    opened: list[str | None] = []
    controller_stub = SimpleNamespace(
        last_finished_run_id=None,
        paused_run_id=None,
        paused_task="",
        paused_reason="",
        main_window=SimpleNamespace(isVisible=lambda: False),
        _show_paused_run_prompt=lambda: prompted.append("prompt"),
        show_main_window=lambda run_id=None: opened.append(run_id),
    )

    DesktopShellController._handle_finished_job(
        controller_stub,
        {
            "task": "continue the browser task",
            "requires_human": True,
            "interruption_reason": "Complete the CAPTCHA in the browser.",
            "result": {
                "run_id": "run-human-1",
                "interruption_reason": "Complete the CAPTCHA in the browser.",
            },
        },
    )

    assert controller_stub.last_finished_run_id == "run-human-1"
    assert controller_stub.paused_run_id == "run-human-1"
    assert controller_stub.paused_task == "continue the browser task"
    assert "CAPTCHA" in controller_stub.paused_reason
    assert prompted == ["prompt"]
    assert opened == []


def test_desktop_shell_controller_keeps_result_only_handoff_in_floating_prompt():
    from desktop_agent.desktop_shell import DesktopShellController

    prompted: list[str] = []
    controller_stub = SimpleNamespace(
        last_finished_run_id=None,
        paused_run_id=None,
        paused_task="",
        paused_reason="",
        main_window=SimpleNamespace(isVisible=lambda: False),
        _show_paused_run_prompt=lambda: prompted.append("prompt"),
    )

    DesktopShellController._handle_finished_job(
        controller_stub,
        {
            "task": "continue the browser task",
            "status": "attention",
            "requires_human": False,
            "result": {
                "run_id": "run-result-human-1",
                "requires_human": True,
                "interruption_reason": "Complete sign-in before continuing.",
            },
        },
    )

    assert controller_stub.last_finished_run_id == "run-result-human-1"
    assert controller_stub.paused_run_id == "run-result-human-1"
    assert controller_stub.paused_task == "continue the browser task"
    assert controller_stub.paused_reason == "Complete sign-in before continuing."
    assert prompted == ["prompt"]


def test_desktop_shell_controller_summarizes_result_only_handoff_job():
    import desktop_agent.desktop_shell as desktop_shell

    summary = desktop_shell.DesktopShellController._summarize_job(
        {
            "id": "job-result-handoff",
            "status": "running",
            "task": "resume after sign-in",
            "requires_human": False,
            "result": {
                "run_id": "run-result-handoff",
                "requires_human": True,
                "interruption_kind": "requires_auth",
                "interruption_reason": "Complete sign-in before continuing.",
            },
        }
    )

    assert summary["requires_human"] is True
    assert summary["interruption_kind"] == "requires_auth"
    assert summary["interruption_reason"] == "Complete sign-in before continuing."


def test_desktop_shell_controller_keeps_failed_run_in_floating_prompt():
    from desktop_agent.desktop_shell import DesktopShellController

    prompted: list[str] = []
    opened: list[str | None] = []
    controller_stub = SimpleNamespace(
        last_finished_run_id=None,
        paused_run_id=None,
        paused_task="",
        paused_reason="",
        main_window=SimpleNamespace(isVisible=lambda: False),
        floating=SimpleNamespace(show_idle=lambda **kwargs: prompted.append(kwargs.get("status", ""))),
        _clear_paused_run=lambda: None,
        _hide_main_window_for_floating=lambda: opened.append("hide"),
        follow_up_draft="",
        success_feedback_deadline=0.0,
    )

    DesktopShellController._handle_finished_job(
        controller_stub,
        {
            "task": "continue the browser task",
            "status": "failed",
            "result": {
                "run_id": "run-failed-1",
            },
        },
    )

    assert controller_stub.last_finished_run_id == "run-failed-1"
    assert prompted == ["需要处理"]
    assert opened == []


def test_desktop_shell_controller_ignores_stale_terminal_pending_decision_in_finished_job():
    from desktop_agent.desktop_shell import DesktopShellController

    prompts: list[str] = []
    idle_statuses: list[str] = []
    controller_stub = SimpleNamespace(
        last_finished_run_id=None,
        paused_run_id="old-paused-run",
        paused_task="old task",
        paused_reason="old reason",
        main_window=SimpleNamespace(isVisible=lambda: False),
        floating=SimpleNamespace(show_idle=lambda **kwargs: idle_statuses.append(kwargs.get("status", ""))),
        _show_paused_run_prompt=lambda: prompts.append("prompt"),
        _clear_paused_run=lambda: (
            setattr(controller_stub, "paused_run_id", None),
            setattr(controller_stub, "paused_task", ""),
            setattr(controller_stub, "paused_reason", ""),
        ),
        _hide_main_window_for_floating=lambda: None,
        follow_up_draft="",
        success_feedback_deadline=0.0,
    )

    DesktopShellController._handle_finished_job(
        controller_stub,
        {
            "task": "review generated plan",
            "status": "failed",
            "requires_human": True,
            "pending_decision": {
                "decision_type": "plan_review",
                "summary": "Stale approval",
            },
            "result": {
                "run_id": "run-failed-stale",
                "error": "Planner crashed after approval cleanup.",
                "pending_decision": {
                    "decision_type": "plan_review",
                    "summary": "Nested stale approval",
                },
            },
        },
    )

    assert prompts == []
    assert controller_stub.paused_run_id is None
    assert controller_stub.paused_task == ""
    assert controller_stub.paused_reason == ""
    assert controller_stub.last_finished_run_id == "run-failed-stale"
    assert len(idle_statuses) == 1


def test_desktop_shell_controller_finished_terminal_resumable_job_prompts_resume():
    from desktop_agent.desktop_shell import DesktopShellController

    prompts: list[str] = []
    idle_statuses: list[str] = []
    controller_stub = SimpleNamespace(
        last_finished_run_id=None,
        paused_run_id=None,
        paused_task="",
        paused_reason="",
        main_window=SimpleNamespace(isVisible=lambda: False),
        floating=SimpleNamespace(show_idle=lambda **kwargs: idle_statuses.append(kwargs.get("status", ""))),
        _show_paused_run_prompt=lambda: prompts.append("prompt"),
        _clear_paused_run=lambda: None,
        _hide_main_window_for_floating=lambda: None,
        follow_up_draft="",
        success_feedback_deadline=0.0,
    )

    DesktopShellController._handle_finished_job(
        controller_stub,
        {
            "task": "continue the reviewed task",
            "status": "cancelled",
            "result": {
                "run_id": "run-cancelled-resumable",
                "cancelled": True,
                "resume_mode": "execution_state",
                "can_resume": True,
                "cancel_reason": "Review later.",
            },
        },
    )

    assert controller_stub.last_finished_run_id == "run-cancelled-resumable"
    assert controller_stub.paused_run_id == "run-cancelled-resumable"
    assert controller_stub.paused_task == "continue the reviewed task"
    assert controller_stub.paused_reason == "Review later."
    assert prompts == ["prompt"]
    assert idle_statuses == []


def test_desktop_shell_controller_resume_interrupted_run_posts_resume_request(monkeypatch):
    from desktop_agent.desktop_shell import DesktopShellController

    captured: dict[str, object] = {}

    class _Response:
        ok = True
        content = b"{}"

        def json(self):
            return {"id": "job-resume-1", "task": "resume the paused run"}

    def _post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("desktop_agent.desktop_shell.requests.post", _post)

    cleared: list[str] = []
    hidden: list[str] = []
    controller_stub = SimpleNamespace(
        base_url="http://127.0.0.1:8765",
        paused_run_id="run-human-1",
        current_active_job=None,
        current_active_job_id=None,
        success_feedback_deadline=1.0,
        _read_runtime_preferences=lambda: {"model_provider": "openai_compatible"},
        _clear_paused_run=lambda: cleared.append("paused"),
        _hide_main_window_for_floating=lambda: hidden.append("floating"),
    )

    result = DesktopShellController._resume_interrupted_run(controller_stub)

    assert result is True
    assert captured["url"] == "http://127.0.0.1:8765/api/runs/run-human-1/resume"
    assert captured["json"] == {"config_overrides": {"model_provider": "openai_compatible"}}
    assert captured["timeout"] == 2.0
    assert controller_stub.current_active_job == {"id": "job-resume-1", "task": "resume the paused run"}
    assert controller_stub.current_active_job_id == "job-resume-1"
    assert controller_stub.success_feedback_deadline == 0
    assert cleared == ["paused"]
    assert hidden == ["floating"]


def test_desktop_shell_controller_decide_active_job_posts_decision(monkeypatch):
    from desktop_agent.desktop_shell import DesktopShellController

    captured: dict[str, object] = {}

    class _Response:
        ok = True
        content = b"{}"

        def json(self):
            return {"status": "approval", "id": "job-approve-1"}

    def _post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("desktop_agent.desktop_shell.requests.post", _post)

    hidden: list[str] = []
    controller_stub = SimpleNamespace(
        base_url="http://127.0.0.1:8765",
        current_active_job_id="job-approve-1",
        current_active_job={"id": "job-approve-1", "status": "approval"},
        _hide_main_window_for_floating=lambda: hidden.append("floating"),
    )

    result = DesktopShellController._decide_active_job(controller_stub, "approve")

    assert result is True
    assert captured["url"] == "http://127.0.0.1:8765/api/jobs/job-approve-1/decision"
    assert captured["json"] == {"decision": "approve"}
    assert captured["timeout"] == 2.0
    assert controller_stub.current_active_job["status"] == "approval"
    assert hidden == ["floating"]


def test_desktop_shell_controller_loads_versioned_dashboard_url(monkeypatch):
    import desktop_agent.desktop_shell as desktop_shell

    captured: dict[str, object] = {}

    class _WindowStub:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def show(self):
            return None

    monkeypatch.setattr(desktop_shell, "DesktopMainWindow", _WindowStub)
    monkeypatch.setattr(desktop_shell, "FloatingExecutionWindow", lambda **kwargs: SimpleNamespace(move=lambda *_: None))
    monkeypatch.setattr(desktop_shell.DesktopShellController, "_build_tray", lambda self: SimpleNamespace(show=lambda: None))

    desktop_shell.DesktopShellController(
        qt_app=SimpleNamespace(),
        dashboard_app=SimpleNamespace(
            ui_root=Path("desktop_agent/dashboard_assets"),
            config=SimpleNamespace(window_display_mode="workarea_maximized"),
        ),
        server=SimpleNamespace(),
        base_url="http://127.0.0.1:8765/",
    )

    assert captured["url"] == f"http://127.0.0.1:8765/index.html?v={desktop_shell.APP_ASSET_VERSION}"


def test_desktop_shell_controller_starts_with_main_shell_by_default(monkeypatch):
    import desktop_agent.desktop_shell as desktop_shell

    main_shows: list[str] = []
    floating_states: list[str] = []

    class _WindowStub:
        def __init__(self, **kwargs):
            pass

        def show(self):
            main_shows.append("main")

        def isVisible(self):
            return False

    floating = SimpleNamespace(
        move=lambda *_: None,
        update_active_job=lambda *_: floating_states.append("active"),
        show_waiting_follow_up=lambda *_: floating_states.append("followup"),
        show_idle=lambda **__: floating_states.append("idle"),
    )

    monkeypatch.setattr(desktop_shell, "DesktopMainWindow", _WindowStub)
    monkeypatch.setattr(desktop_shell, "FloatingExecutionWindow", lambda **kwargs: floating)
    monkeypatch.setattr(desktop_shell.DesktopShellController, "_build_tray", lambda self: SimpleNamespace(show=lambda: None))

    desktop_shell.DesktopShellController(
        qt_app=SimpleNamespace(),
        dashboard_app=SimpleNamespace(
            ui_root=Path("desktop_agent/dashboard_assets"),
            config=SimpleNamespace(window_display_mode="workarea_maximized"),
        ),
        server=SimpleNamespace(),
        base_url="http://127.0.0.1:8765/",
    )

    assert main_shows == ["main"]
    assert floating_states == []


def test_desktop_shell_controller_can_start_with_floating_shell_when_configured(monkeypatch):
    import desktop_agent.desktop_shell as desktop_shell

    main_shows: list[str] = []
    floating_states: list[str] = []

    class _WindowStub:
        def __init__(self, **kwargs):
            pass

        def show(self):
            main_shows.append("main")

        def isVisible(self):
            return False

    floating = SimpleNamespace(
        move=lambda *_: None,
        update_active_job=lambda *_: floating_states.append("active"),
        show_waiting_follow_up=lambda *_: floating_states.append("followup"),
        show_idle=lambda **__: floating_states.append("idle"),
    )

    monkeypatch.setattr(desktop_shell, "DesktopMainWindow", _WindowStub)
    monkeypatch.setattr(desktop_shell, "FloatingExecutionWindow", lambda **kwargs: floating)
    monkeypatch.setattr(desktop_shell.DesktopShellController, "_build_tray", lambda self: SimpleNamespace(show=lambda: None))

    desktop_shell.DesktopShellController(
        qt_app=SimpleNamespace(),
        dashboard_app=SimpleNamespace(
            ui_root=Path("desktop_agent/dashboard_assets"),
            config=SimpleNamespace(window_display_mode="workarea_maximized", shell_start_mode="floating"),
        ),
        server=SimpleNamespace(),
        base_url="http://127.0.0.1:8765/",
    )

    assert main_shows == []
    assert floating_states == ["idle"]


def test_desktop_shell_controller_request_overview_refresh_skips_reentrant_calls(monkeypatch):
    import desktop_agent.desktop_shell as desktop_shell

    started: list[str] = []

    class _ThreadStub:
        def __init__(self, *, target=None, name=None, daemon=None):
            self.target = target
            self.name = name
            self.daemon = daemon

        def start(self):
            started.append(self.name or "thread")

    monkeypatch.setattr(desktop_shell.threading, "Thread", _ThreadStub)

    controller_stub = SimpleNamespace(
        _overview_request_in_flight=False,
        _fetch_overview_payload=lambda: None,
    )

    first = desktop_shell.DesktopShellController._request_overview_refresh(controller_stub)
    second = desktop_shell.DesktopShellController._request_overview_refresh(controller_stub)

    assert first is True
    assert second is False
    assert controller_stub._overview_request_in_flight is True
    assert started == ["desktop-agent-overview-refresh"]


def test_desktop_shell_controller_handle_overview_payload_skips_unchanged_snapshots():
    import desktop_agent.desktop_shell as desktop_shell

    applied: list[dict[str, object]] = []
    payload = {
        "active_job": {"id": "job-1", "status": "running", "task": "demo", "result": {"run_id": "run-1"}},
        "jobs": [{"id": "job-1", "status": "running", "task": "demo", "result": {"run_id": "run-1"}}],
        "runs": [{"id": "run-1", "steps": 1, "completed": False}],
        "runtime_preferences": {"updated_at": 12.0},
    }
    controller_stub = SimpleNamespace(
        _overview_request_in_flight=True,
        _last_overview_signature="",
        success_feedback_deadline=0.0,
        _apply_overview_payload=lambda incoming: applied.append(incoming),
    )

    first = desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload)
    second = desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload)

    assert first is True
    assert second is False
    assert controller_stub._overview_request_in_flight is False
    assert len(applied) == 1


def test_desktop_shell_controller_handle_overview_payload_applies_changed_snapshots():
    import desktop_agent.desktop_shell as desktop_shell

    applied: list[dict[str, object]] = []
    controller_stub = SimpleNamespace(
        _overview_request_in_flight=True,
        _last_overview_signature="",
        success_feedback_deadline=0.0,
        _apply_overview_payload=lambda incoming: applied.append(incoming),
    )

    payload_one = {
        "active_job": {"id": "job-1", "status": "running", "task": "demo", "result": {"run_id": "run-1"}},
        "jobs": [{"id": "job-1", "status": "running", "task": "demo", "result": {"run_id": "run-1"}}],
        "runs": [{"id": "run-1", "steps": 1, "completed": False}],
        "runtime_preferences": {"updated_at": 12.0},
    }
    payload_two = {
        "active_job": None,
        "jobs": [{"id": "job-1", "status": "completed", "task": "demo", "result": {"run_id": "run-1"}}],
        "runs": [{"id": "run-1", "steps": 2, "completed": True}],
        "runtime_preferences": {"updated_at": 12.0},
    }

    desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_one)
    changed = desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_two)

    assert changed is True
    assert len(applied) == 2


def test_desktop_shell_controller_active_job_switches_main_to_floating():
    import desktop_agent.desktop_shell as desktop_shell

    hidden: list[str] = []
    controller_stub = SimpleNamespace(
        current_active_job_id=None,
        current_active_job=None,
        paused_run_id=None,
        paused_task="",
        paused_reason="",
        follow_up_draft="",
        success_feedback_deadline=0.0,
        auto_collapsed_for_current_job=False,
        main_window=SimpleNamespace(isVisible=lambda: True),
        floating=SimpleNamespace(update_active_job=lambda *_: None),
        _clear_paused_run=lambda: None,
        _hide_main_window_for_floating=lambda: hidden.append("floating"),
    )

    desktop_shell.DesktopShellController._apply_overview_payload(
        controller_stub,
        {
            "active_job": {"id": "job-running", "status": "running", "task": "click continue"},
            "jobs": [],
            "runs": [],
        },
    )

    assert controller_stub.current_active_job_id == "job-running"
    assert controller_stub.current_active_job["task"] == "click continue"
    assert controller_stub.auto_collapsed_for_current_job is True
    assert hidden == ["floating"]


def test_desktop_shell_controller_overview_signature_tracks_terminal_job_result_reason():
    import desktop_agent.desktop_shell as desktop_shell

    base_job = {
        "id": "job-terminal-reason",
        "status": "failed",
        "task": "surface terminal reason",
        "updated_at": 1711000001,
        "error": "Stale top-level failure.",
        "cancel_reason": "Stale top-level cancellation.",
        "result": {
            "run_id": "run-terminal-reason",
            "completed": False,
            "error": "Planner failed before execution.",
            "cancel_reason": "Stopped while checking the first step.",
        },
    }
    changed_job = {
        **base_job,
        "result": {
            **base_job["result"],
            "error": "Executor failed after retry.",
            "cancel_reason": "Stopped after recovery retry.",
        },
    }
    payload_one = {
        "active_job": None,
        "jobs": [base_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }
    payload_two = {
        "active_job": None,
        "jobs": [changed_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }

    signature_one = desktop_shell.DesktopShellController._build_overview_signature(
        payload_one,
        success_feedback_active=False,
    )
    signature_two = desktop_shell.DesktopShellController._build_overview_signature(
        payload_two,
        success_feedback_active=False,
    )
    summary = desktop_shell.DesktopShellController._summarize_job(changed_job)

    assert signature_one != signature_two
    assert summary["completed"] is False
    assert summary["error"] == "Executor failed after retry."
    assert summary["cancel_reason"] == "Stopped after recovery retry."


def test_desktop_shell_controller_handle_overview_payload_tracks_run_state_summary():
    import desktop_agent.desktop_shell as desktop_shell

    applied: list[dict[str, object]] = []
    controller_stub = SimpleNamespace(
        _overview_request_in_flight=True,
        _last_overview_signature="",
        success_feedback_deadline=0.0,
        _apply_overview_payload=lambda incoming: applied.append(incoming),
    )
    base_run = {
        "id": "run-state-summary",
        "steps": 2,
        "completed": False,
        "state": {
            "current_goal": "Recover blocked page",
            "plan_health": {
                "counts": {"total": 2, "completed": 0, "ready": 1, "blocked": 0},
                "next_subgoal_id": "subgoal_01",
                "autonomy": {"status": "recovering", "can_continue": True, "next_action": "repair"},
                "items": [
                    {"id": "subgoal_01", "title": "Recover blocked page", "status": "pending", "ready": True},
                    {"id": "subgoal_02", "title": "Continue local notes", "status": "pending"},
                ],
            },
        },
    }
    payload_one = {
        "active_job": None,
        "jobs": [],
        "runs": [base_run],
        "runtime_preferences": {"updated_at": 12.0},
    }
    changed_run = {
        **base_run,
        "state": {
            "current_goal": "Continue local notes",
            "plan_health": {
                "counts": {"total": 2, "completed": 1, "ready": 1, "blocked": 0},
                "next_subgoal_id": "subgoal_02",
                "autonomy": {"status": "ready", "can_continue": True, "next_action": "execute"},
                "items": [
                    {"id": "subgoal_01", "title": "Recover blocked page", "status": "completed"},
                    {"id": "subgoal_02", "title": "Continue local notes", "status": "pending", "ready": True, "is_next": True},
                ],
            },
        },
    }
    payload_two = {
        "active_job": None,
        "jobs": [],
        "runs": [changed_run],
        "runtime_preferences": {"updated_at": 12.0},
    }

    desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_one)
    changed = desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_two)

    assert changed is True
    assert len(applied) == 2


def test_desktop_shell_controller_apply_overview_payload_surfaces_paused_history_run():
    import desktop_agent.desktop_shell as desktop_shell

    prompts: list[dict[str, str]] = []
    hidden: list[str] = []
    controller_stub = SimpleNamespace(
        current_active_job_id=None,
        current_active_job=None,
        paused_run_id=None,
        paused_task="",
        paused_reason="",
        follow_up_draft="",
        success_feedback_deadline=0.0,
        main_window=SimpleNamespace(isVisible=lambda: False),
        floating=SimpleNamespace(show_idle=lambda **_kwargs: None, hide_floating=lambda: None),
        _hide_main_window_for_floating=lambda: hidden.append("hidden"),
    )

    def _show_paused_run_prompt():
        prompts.append(
            {
                "run_id": controller_stub.paused_run_id,
                "task": controller_stub.paused_task,
                "reason": controller_stub.paused_reason,
            }
        )

    controller_stub._show_paused_run_prompt = _show_paused_run_prompt

    desktop_shell.DesktopShellController._apply_overview_payload(
        controller_stub,
        {
            "active_job": None,
            "jobs": [],
            "runs": [
                {
                    "id": "run-human-history",
                    "task": "Finish the login flow",
                    "completed": False,
                    "cancelled": False,
                    "requires_human": True,
                    "can_resume": True,
                    "interruption_reason": "A login prompt is waiting.",
                }
            ],
        },
    )

    assert controller_stub.paused_run_id == "run-human-history"
    assert controller_stub.paused_task == "Finish the login flow"
    assert controller_stub.paused_reason == "A login prompt is waiting."
    assert prompts == [
        {
            "run_id": "run-human-history",
            "task": "Finish the login flow",
            "reason": "A login prompt is waiting.",
        }
    ]
    assert hidden == []


def test_desktop_shell_controller_apply_overview_payload_surfaces_historical_pending_decision():
    import desktop_agent.desktop_shell as desktop_shell

    prompts: list[dict[str, str]] = []
    controller_stub = SimpleNamespace(
        current_active_job_id=None,
        current_active_job=None,
        paused_run_id=None,
        paused_task="",
        paused_reason="",
        follow_up_draft="",
        success_feedback_deadline=0.0,
        main_window=SimpleNamespace(isVisible=lambda: False),
        floating=SimpleNamespace(show_idle=lambda **_kwargs: None, hide_floating=lambda: None),
        _hide_main_window_for_floating=lambda: None,
    )

    def _show_paused_run_prompt():
        prompts.append(
            {
                "run_id": controller_stub.paused_run_id,
                "task": controller_stub.paused_task,
                "reason": controller_stub.paused_reason,
            }
        )

    controller_stub._show_paused_run_prompt = _show_paused_run_prompt

    desktop_shell.DesktopShellController._apply_overview_payload(
        controller_stub,
        {
            "active_job": None,
            "jobs": [],
            "runs": [
                {
                    "id": "run-review-history",
                    "task": "Review the generated plan",
                    "completed": False,
                    "cancelled": False,
                    "requires_human": False,
                    "can_resume": True,
                    "resume_mode": "execution_state",
                    "state": {
                        "pending_decision": {
                            "decision_type": "plan_review",
                            "summary": "Review the generated task plan.",
                            "reason": "Plan review is configured before execution.",
                        }
                    },
                }
            ],
        },
    )

    assert controller_stub.paused_run_id == "run-review-history"
    assert controller_stub.paused_task == "Review the generated plan"
    assert controller_stub.paused_reason == "Review the generated task plan."
    assert prompts == [
        {
            "run_id": "run-review-history",
            "task": "Review the generated plan",
            "reason": "Review the generated task plan.",
        }
    ]


def test_desktop_shell_controller_apply_overview_payload_surfaces_cancelled_resumable_run():
    import desktop_agent.desktop_shell as desktop_shell

    prompts: list[dict[str, str]] = []
    controller_stub = SimpleNamespace(
        current_active_job_id=None,
        current_active_job=None,
        paused_run_id=None,
        paused_task="",
        paused_reason="",
        follow_up_draft="",
        success_feedback_deadline=0.0,
        main_window=SimpleNamespace(isVisible=lambda: False),
        floating=SimpleNamespace(show_idle=lambda **_kwargs: None, hide_floating=lambda: None),
        _hide_main_window_for_floating=lambda: None,
    )

    def _show_paused_run_prompt():
        prompts.append(
            {
                "run_id": controller_stub.paused_run_id,
                "task": controller_stub.paused_task,
                "reason": controller_stub.paused_reason,
            }
        )

    controller_stub._show_paused_run_prompt = _show_paused_run_prompt

    desktop_shell.DesktopShellController._apply_overview_payload(
        controller_stub,
        {
            "active_job": None,
            "jobs": [],
            "runs": [
                {
                    "id": "run-cancelled-review-history",
                    "task": "Continue a cancelled review",
                    "completed": False,
                    "cancelled": True,
                    "requires_human": False,
                    "can_resume": True,
                    "resume_mode": "execution_state",
                    "cancel_reason": "Review later.",
                    "execution_state": {
                        "task_graph": {
                            "subgoals": [
                                {"id": "subgoal_01", "title": "Continue reviewed task", "status": "pending"}
                            ],
                        }
                    },
                }
            ],
        },
    )

    assert controller_stub.paused_run_id == "run-cancelled-review-history"
    assert controller_stub.paused_task == "Continue a cancelled review"
    assert controller_stub.paused_reason == "Review later."
    assert prompts == [
        {
            "run_id": "run-cancelled-review-history",
            "task": "Continue a cancelled review",
            "reason": "Review later.",
        }
    ]


def test_desktop_shell_controller_handle_overview_payload_tracks_nested_pending_decision():
    import desktop_agent.desktop_shell as desktop_shell

    applied: list[dict[str, object]] = []
    controller_stub = SimpleNamespace(
        _overview_request_in_flight=True,
        _last_overview_signature="",
        success_feedback_deadline=0.0,
        _apply_overview_payload=lambda incoming: applied.append(incoming),
    )
    base_job = {
        "id": "job-nested-approval",
        "status": "approval",
        "task": "review generated plan",
        "result": {
            "execution_state": {
                "pending_decision": {
                    "summary": "确认生成的计划",
                    "reason": "计划需要复核",
                }
            }
        },
    }
    payload_one = {
        "active_job": base_job,
        "jobs": [base_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }
    changed_job = {
        **base_job,
        "result": {
            "execution_state": {
                "pending_decision": {
                    "summary": "确认更新后的计划",
                    "reason": "计划变更后仍需复核",
                }
            }
        },
    }
    payload_two = {
        "active_job": changed_job,
        "jobs": [changed_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }

    desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_one)
    changed = desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_two)

    assert changed is True
    assert len(applied) == 2


def test_desktop_shell_controller_handle_overview_payload_tracks_pending_decision_actions():
    import desktop_agent.desktop_shell as desktop_shell

    applied: list[dict[str, object]] = []
    controller_stub = SimpleNamespace(
        _overview_request_in_flight=True,
        _last_overview_signature="",
        success_feedback_deadline=0.0,
        _apply_overview_payload=lambda incoming: applied.append(incoming),
    )
    base_job = {
        "id": "job-step-approval-action",
        "status": "approval",
        "task": "review critical step",
        "result": {
            "execution_state": {
                "pending_decision": {
                    "id": "approval-1",
                    "decision_type": "step_approval",
                    "summary": "Review the next action.",
                    "reason": "The action is critical.",
                    "risk_level": "critical",
                    "actions": [{"type": "browser_dom_click", "selector": "#checkout"}],
                }
            }
        },
    }
    payload_one = {
        "active_job": base_job,
        "jobs": [base_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }
    changed_job = {
        **base_job,
        "result": {
            "execution_state": {
                "pending_decision": {
                    **base_job["result"]["execution_state"]["pending_decision"],
                    "actions": [{"type": "browser_dom_click", "selector": "#confirm-checkout"}],
                }
            }
        },
    }
    payload_two = {
        "active_job": changed_job,
        "jobs": [changed_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }

    desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_one)
    changed = desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_two)

    assert changed is True
    assert len(applied) == 2


def test_desktop_shell_controller_handle_overview_payload_tracks_replan_health():
    import desktop_agent.desktop_shell as desktop_shell

    applied: list[dict[str, object]] = []
    controller_stub = SimpleNamespace(
        _overview_request_in_flight=True,
        _last_overview_signature="",
        success_feedback_deadline=0.0,
        _apply_overview_payload=lambda incoming: applied.append(incoming),
    )
    base_job = {
        "id": "job-replan-health",
        "status": "running",
        "task": "recover and continue",
        "result": {
            "latest_summary": "Recovering route.",
            "execution_state": {
                "orchestration_phase": "recovering",
                "stage_review_status": "pending",
                "last_replan_reason": "Original route failed.",
                "plan_health": {
                    "next_subgoal_id": "subgoal_01",
                    "remaining": 2,
                    "counts": {"completed": 0, "ready": 1, "blocked": 0, "exhausted": 0},
                    "autonomy": {
                        "status": "recovering",
                        "can_continue": True,
                        "next_action": "repair",
                    },
                },
            },
        },
    }
    payload_one = {
        "active_job": base_job,
        "jobs": [base_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }
    changed_job = {
        **base_job,
        "result": {
            "latest_summary": "Recovering route.",
            "execution_state": {
                "orchestration_phase": "stage_ready",
                "stage_review_status": "approved",
                "last_replan_reason": "Replanned route is ready.",
                "plan_health": {
                    "next_subgoal_id": "subgoal_02",
                    "remaining": 1,
                    "counts": {"completed": 1, "ready": 1, "blocked": 0, "exhausted": 0},
                    "autonomy": {
                        "status": "ready",
                        "can_continue": True,
                        "next_action": "execute",
                    },
                },
            },
        },
    }
    payload_two = {
        "active_job": changed_job,
        "jobs": [changed_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }

    desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_one)
    changed = desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_two)

    assert changed is True
    assert len(applied) == 2


def test_desktop_shell_controller_handle_overview_payload_tracks_plan_review_status():
    import desktop_agent.desktop_shell as desktop_shell

    applied: list[dict[str, object]] = []
    controller_stub = SimpleNamespace(
        _overview_request_in_flight=True,
        _last_overview_signature="",
        success_feedback_deadline=0.0,
        _apply_overview_payload=lambda incoming: applied.append(incoming),
    )
    base_job = {
        "id": "job-plan-review",
        "status": "running",
        "task": "review generated plan",
        "result": {
            "latest_summary": "Waiting for plan review.",
            "execution_state": {
                "current_goal": "Review generated task plan",
                "orchestration_phase": "plan_review",
                "plan_review_status": "pending",
            },
        },
    }
    payload_one = {
        "active_job": base_job,
        "jobs": [base_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }
    changed_job = {
        **base_job,
        "result": {
            "latest_summary": "Waiting for plan review.",
            "execution_state": {
                "current_goal": "Review generated task plan",
                "orchestration_phase": "plan_review",
                "plan_review_status": "approved",
            },
        },
    }
    payload_two = {
        "active_job": changed_job,
        "jobs": [changed_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }

    desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_one)
    changed = desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_two)

    assert changed is True
    assert len(applied) == 2


def test_desktop_shell_controller_handle_overview_payload_tracks_workspace_summary():
    import desktop_agent.desktop_shell as desktop_shell

    applied: list[dict[str, object]] = []
    controller_stub = SimpleNamespace(
        _overview_request_in_flight=True,
        _last_overview_signature="",
        success_feedback_deadline=0.0,
        _apply_overview_payload=lambda incoming: applied.append(incoming),
    )
    base_job = {
        "id": "job-workspace-summary",
        "status": "running",
        "task": "collect source notes",
        "result": {
            "latest_summary": "Collecting source notes.",
            "workspace_summary": {
                "facts": [{"key": "source-status", "value": "Searching for source candidates."}],
                "sources": [{"title": "Local notes", "url": "file:///notes.md"}],
            },
            "execution_state": {
                "current_goal": "Collect source notes",
            },
        },
    }
    payload_one = {
        "active_job": base_job,
        "jobs": [base_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }
    changed_job = {
        **base_job,
        "result": {
            "latest_summary": "Collecting source notes.",
            "workspace_summary": {
                "facts": [{"key": "source-status", "value": "Source candidates collected."}],
                "sources": [{"title": "Local notes", "url": "file:///notes.md"}],
            },
            "execution_state": {
                "current_goal": "Collect source notes",
            },
        },
    }
    payload_two = {
        "active_job": changed_job,
        "jobs": [changed_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }

    desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_one)
    changed = desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_two)

    assert changed is True
    assert len(applied) == 2


def test_desktop_shell_controller_handle_overview_payload_tracks_step_proposal():
    import desktop_agent.desktop_shell as desktop_shell

    applied: list[dict[str, object]] = []
    controller_stub = SimpleNamespace(
        _overview_request_in_flight=True,
        _last_overview_signature="",
        success_feedback_deadline=0.0,
        _apply_overview_payload=lambda incoming: applied.append(incoming),
    )
    base_job = {
        "id": "job-step-proposal",
        "status": "running",
        "task": "continue autonomous run",
        "result": {
            "latest_summary": "Choosing the next action.",
            "step_proposal": {
                "capability": "desktop_gui",
                "intent": "Click the stale desktop target.",
                "risk_level": "low",
                "target_scope": "subgoal",
                "surface_kind": "current_user_desktop",
                "requires_approval": False,
                "actions": [{"type": "click", "x": 320, "y": 240, "button": "left"}],
            },
            "execution_state": {
                "current_goal": "Continue autonomous run",
            },
        },
    }
    payload_one = {
        "active_job": base_job,
        "jobs": [base_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }
    changed_job = {
        **base_job,
        "result": {
            "latest_summary": "Choosing the next action.",
            "step_proposal": {
                "capability": "browser_dom",
                "intent": "Use DOM automation after the desktop target became stale.",
                "risk_level": "medium",
                "target_scope": "subgoal",
                "surface_kind": "managed_aoryn_browser",
                "requires_approval": False,
                "actions": [{"type": "click", "selector": "#continue", "button": "left"}],
            },
            "execution_state": {
                "current_goal": "Continue autonomous run",
            },
        },
    }
    payload_two = {
        "active_job": changed_job,
        "jobs": [changed_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }

    desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_one)
    changed = desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_two)

    assert changed is True
    assert len(applied) == 2


def test_desktop_shell_controller_handle_overview_payload_tracks_last_step_proposal():
    import desktop_agent.desktop_shell as desktop_shell

    applied: list[dict[str, object]] = []
    controller_stub = SimpleNamespace(
        _overview_request_in_flight=True,
        _last_overview_signature="",
        success_feedback_deadline=0.0,
        _apply_overview_payload=lambda incoming: applied.append(incoming),
    )
    base_job = {
        "id": "job-last-step-proposal",
        "status": "running",
        "task": "continue saved last step",
        "result": {
            "latest_summary": "Continuing from saved state.",
            "execution_state": {
                "current_goal": "Continue saved last step",
                "last_step": {
                    "capability": "desktop_gui",
                    "intent": "Click the saved desktop target.",
                    "risk_level": "low",
                    "surface_kind": "current_user_desktop",
                    "actions": [{"type": "click", "x": 320, "y": 240, "button": "left"}],
                },
            },
        },
    }
    payload_one = {
        "active_job": base_job,
        "jobs": [base_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }
    changed_job = {
        **base_job,
        "result": {
            "latest_summary": "Continuing from saved state.",
            "execution_state": {
                "current_goal": "Continue saved last step",
                "last_step": {
                    "capability": "browser_dom",
                    "intent": "Use DOM automation for the saved step.",
                    "risk_level": "medium",
                    "surface_kind": "managed_aoryn_browser",
                    "actions": [{"type": "click", "selector": "#continue", "button": "left"}],
                },
            },
        },
    }
    payload_two = {
        "active_job": changed_job,
        "jobs": [changed_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }

    desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_one)
    changed = desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_two)

    assert changed is True
    assert len(applied) == 2


def test_desktop_shell_controller_handle_overview_payload_tracks_active_progress_counters():
    import desktop_agent.desktop_shell as desktop_shell

    applied: list[dict[str, object]] = []
    controller_stub = SimpleNamespace(
        _overview_request_in_flight=True,
        _last_overview_signature="",
        success_feedback_deadline=0.0,
        _apply_overview_payload=lambda incoming: applied.append(incoming),
    )
    base_job = {
        "id": "job-progress-counters",
        "status": "running",
        "task": "track execution progress",
        "started_at": 1711000000,
        "updated_at": 1711000001,
        "result": {
            "run_id": "run-progress-counters",
            "started_at": 1711000000,
            "latest_summary": "Executing the current plan.",
            "steps": 1,
            "dry_run": True,
            "execution_state": {
                "current_goal": "Track execution progress",
            },
        },
    }
    payload_one = {
        "active_job": base_job,
        "jobs": [base_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }
    changed_job = {
        **base_job,
        "result": {
            "run_id": "run-progress-counters",
            "started_at": 1711000000,
            "latest_summary": "Executing the current plan.",
            "steps": 2,
            "dry_run": False,
            "execution_state": {
                "current_goal": "Track execution progress",
            },
        },
    }
    payload_two = {
        "active_job": changed_job,
        "jobs": [changed_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }

    desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_one)
    changed = desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_two)

    assert changed is True
    assert len(applied) == 2


def test_desktop_shell_controller_handle_overview_payload_tracks_live_telemetry():
    import desktop_agent.desktop_shell as desktop_shell

    applied: list[dict[str, object]] = []
    controller_stub = SimpleNamespace(
        _overview_request_in_flight=True,
        _last_overview_signature="",
        success_feedback_deadline=0.0,
        _apply_overview_payload=lambda incoming: applied.append(incoming),
    )
    base_job = {
        "id": "job-live-telemetry",
        "status": "running",
        "task": "track live desktop motion",
        "started_at": 1711000000,
        "updated_at": 1711000001,
        "result": {
            "run_id": "run-live-telemetry",
            "latest_summary": "Moving toward the target.",
            "latest_screenshot": "live-shot.png",
            "latest_timings": {"total": 1.2, "capture_initial": 0.2, "plan": 0.4, "execute": 0.6},
            "latest_actions": [{"type": "launch_app", "app": "calculator"}],
            "live_pointer": {"norm_x": 0.25, "norm_y": 0.3, "phase": "moving", "updated_at": 1711000001},
            "live_pointer_trail": [{"norm_x": 0.2, "norm_y": 0.25, "updated_at": 1711000000}],
            "live_action": {"type": "click", "x": 320, "y": 240, "button": "left", "status": "running"},
            "execution_state": {
                "current_goal": "Track live desktop motion",
            },
        },
    }
    payload_one = {
        "active_job": base_job,
        "jobs": [base_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }
    changed_job = {
        **base_job,
        "result": {
            **base_job["result"],
            "latest_timings": {"total": 1.8, "capture_initial": 0.2, "plan": 0.5, "execute": 1.1},
            "latest_actions": [{"type": "launch_app", "app": "notepad"}],
            "live_pointer": {"norm_x": 0.62, "norm_y": 0.56, "phase": "arrived", "updated_at": 1711000002},
            "live_pointer_trail": [
                {"norm_x": 0.2, "norm_y": 0.25, "updated_at": 1711000000},
                {"norm_x": 0.62, "norm_y": 0.56, "updated_at": 1711000002},
            ],
            "live_action": {"type": "click", "x": 640, "y": 360, "button": "left", "status": "running"},
        },
    }
    payload_two = {
        "active_job": changed_job,
        "jobs": [changed_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }

    desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_one)
    changed = desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_two)

    assert changed is True
    assert len(applied) == 2


def test_desktop_shell_controller_handle_overview_payload_tracks_active_verification_trace():
    import desktop_agent.desktop_shell as desktop_shell

    applied: list[dict[str, object]] = []
    controller_stub = SimpleNamespace(
        _overview_request_in_flight=True,
        _last_overview_signature="",
        success_feedback_deadline=0.0,
        _apply_overview_payload=lambda incoming: applied.append(incoming),
    )
    base_job = {
        "id": "job-verification-trace",
        "status": "running",
        "task": "verify the active step",
        "result": {
            "latest_summary": "Checking the current step.",
            "execution_state": {
                "current_goal": "Verify the active step",
                "verification_status": "partial_progress",
                "last_verification": {
                    "status": "partial_progress",
                    "failure_kind": "needs_more_evidence",
                    "message": "The page changed but final evidence is incomplete.",
                    "evidence": [{"kind": "selector", "selector": "#continue"}],
                },
                "evidence_ledger": [
                    {
                        "subgoal_id": "subgoal_01",
                        "capability": "browser_dom",
                        "status": "partial_progress",
                        "evidence": [{"kind": "selector", "selector": "#continue"}],
                    }
                ],
            },
        },
    }
    payload_one = {
        "active_job": base_job,
        "jobs": [base_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }
    changed_job = {
        **base_job,
        "result": {
            **base_job["result"],
            "execution_state": {
                **base_job["result"]["execution_state"],
                "verification_status": "failed",
                "last_verification": {
                    "status": "failed",
                    "failure_kind": "verification_failed",
                    "message": "The final evidence did not match.",
                    "evidence": [{"kind": "screenshot", "title": "Mismatch"}],
                },
                "evidence_ledger": [
                    *base_job["result"]["execution_state"]["evidence_ledger"],
                    {
                        "subgoal_id": "subgoal_01",
                        "capability": "browser_dom",
                        "status": "failed",
                        "evidence": [{"kind": "screenshot", "title": "Mismatch"}],
                    },
                ],
            },
        },
    }
    payload_two = {
        "active_job": changed_job,
        "jobs": [changed_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }

    desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_one)
    changed = desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_two)

    assert changed is True
    assert len(applied) == 2


def test_desktop_shell_controller_handle_overview_payload_tracks_active_handoff_state():
    import desktop_agent.desktop_shell as desktop_shell

    applied: list[dict[str, object]] = []
    controller_stub = SimpleNamespace(
        _overview_request_in_flight=True,
        _last_overview_signature="",
        success_feedback_deadline=0.0,
        _apply_overview_payload=lambda incoming: applied.append(incoming),
    )
    base_job = {
        "id": "job-handoff-state",
        "status": "running",
        "task": "resume after sign-in",
        "result": {
            "latest_summary": "Waiting for sign-in.",
            "execution_state": {
                "current_goal": "Resume after sign-in",
                "app_context": {
                    "human_handoff_kind": "login",
                    "human_handoff_reason": "Complete sign-in before continuing.",
                },
            },
        },
    }
    payload_one = {
        "active_job": base_job,
        "jobs": [base_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }
    changed_job = {
        **base_job,
        "result": {
            **base_job["result"],
            "execution_state": {
                **base_job["result"]["execution_state"],
                "app_context": {
                    "manual_resume_status": "resumed",
                    "manual_resume_reason": "Sign-in completed by the user.",
                },
            },
        },
    }
    payload_two = {
        "active_job": changed_job,
        "jobs": [changed_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }

    desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_one)
    changed = desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_two)

    assert changed is True
    assert len(applied) == 2


def test_desktop_shell_controller_handle_overview_payload_tracks_run_policy_chips():
    import desktop_agent.desktop_shell as desktop_shell

    applied: list[dict[str, object]] = []
    controller_stub = SimpleNamespace(
        _overview_request_in_flight=True,
        _last_overview_signature="",
        success_feedback_deadline=0.0,
        _apply_overview_payload=lambda incoming: applied.append(incoming),
    )
    base_job = {
        "id": "job-run-policies",
        "status": "running",
        "task": "track run policy chips",
        "max_steps": 4,
        "max_run_seconds": 120,
        "pause_after_action": 0.25,
        "desktop_autonomy_mode": "conservative",
        "approval_policy": "tiered",
        "result": {
            "latest_summary": "Executing with policy chips.",
            "execution_state": {
                "current_goal": "Track run policy chips",
            },
        },
    }
    payload_one = {
        "active_job": base_job,
        "jobs": [base_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }
    changed_job = {
        **base_job,
        "max_run_seconds": 240,
        "desktop_autonomy_mode": "autonomous",
        "approval_policy": "autonomous",
    }
    payload_two = {
        "active_job": changed_job,
        "jobs": [changed_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }

    desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_one)
    changed = desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_two)

    assert changed is True
    assert len(applied) == 2


def test_desktop_shell_controller_handle_overview_payload_tracks_historical_run_metadata():
    import desktop_agent.desktop_shell as desktop_shell

    applied: list[dict[str, object]] = []
    controller_stub = SimpleNamespace(
        _overview_request_in_flight=True,
        _last_overview_signature="",
        success_feedback_deadline=0.0,
        _apply_overview_payload=lambda incoming: applied.append(incoming),
    )
    base_run = {
        "id": "run-metadata",
        "steps": 1,
        "dry_run": True,
        "max_steps": 4,
        "max_run_seconds": 120,
        "pause_after_action": 0.25,
        "completed": False,
        "state": {
            "current_goal": "Track run metadata",
        },
    }
    payload_one = {
        "active_job": None,
        "jobs": [],
        "runs": [base_run],
        "runtime_preferences": {"updated_at": 12.0},
    }
    changed_run = {
        **base_run,
        "dry_run": False,
        "max_steps": 6,
        "max_run_seconds": 240,
        "pause_after_action": 0.5,
    }
    payload_two = {
        "active_job": None,
        "jobs": [],
        "runs": [changed_run],
        "runtime_preferences": {"updated_at": 12.0},
    }

    desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_one)
    changed = desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_two)

    assert changed is True
    assert len(applied) == 2


def test_desktop_shell_controller_handle_overview_payload_tracks_autonomy_blockers():
    import desktop_agent.desktop_shell as desktop_shell

    applied: list[dict[str, object]] = []
    controller_stub = SimpleNamespace(
        _overview_request_in_flight=True,
        _last_overview_signature="",
        success_feedback_deadline=0.0,
        _apply_overview_payload=lambda incoming: applied.append(incoming),
    )
    base_job = {
        "id": "job-autonomy-blockers",
        "status": "running",
        "task": "track autonomy blockers",
        "result": {
            "latest_summary": "Checking whether autonomy can continue.",
            "execution_state": {
                "current_goal": "Track autonomy blockers",
                "plan_health": {
                    "blocked_reason": "Waiting for the current view.",
                    "autonomy": {
                        "status": "waiting_user",
                        "can_continue": False,
                        "requires_user": False,
                        "requires_review": False,
                        "next_action": "resume_after_user",
                        "blockers": ["Waiting for the current view."],
                        "warnings": [],
                    },
                },
            },
        },
    }
    payload_one = {
        "active_job": base_job,
        "jobs": [base_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }
    changed_job = {
        **base_job,
        "result": {
            "latest_summary": "Checking whether autonomy can continue.",
            "execution_state": {
                "current_goal": "Track autonomy blockers",
                "plan_health": {
                    "blocked_reason": "Login is required before continuing.",
                    "autonomy": {
                        "status": "waiting_user",
                        "can_continue": False,
                        "requires_user": True,
                        "requires_review": False,
                        "next_action": "resume_after_user",
                        "blockers": ["Login is required before continuing."],
                        "warnings": ["Manual handoff is active."],
                    },
                },
            },
        },
    }
    payload_two = {
        "active_job": changed_job,
        "jobs": [changed_job],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }

    desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_one)
    changed = desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_two)

    assert changed is True
    assert len(applied) == 2


def test_desktop_shell_controller_summarizes_job_state_payload():
    import desktop_agent.desktop_shell as desktop_shell

    summary = desktop_shell.DesktopShellController._summarize_job(
        {
            "id": "job-state-summary",
            "status": "running",
            "task": "track summarized active state",
            "result": {
                "latest_summary": "Checking summarized state.",
                "state": {
                    "current_goal": "Review summarized stage",
                    "orchestration_phase": "stage_review",
                    "stage_review_status": "pending",
                    "pending_decision": {
                        "decision_type": "stage_review",
                        "summary": "Review summarized stage.",
                        "risk_level": "high",
                    },
                    "plan_health": {
                        "counts": {"total": 1, "completed": 0, "ready": 1},
                        "next_subgoal_id": "subgoal_01",
                        "autonomy": {
                            "status": "review_required",
                            "can_continue": False,
                            "requires_review": True,
                            "next_action": "approve_stage",
                            "blockers": ["The replanned stage is waiting for approval."],
                        },
                        "items": [
                            {
                                "id": "subgoal_01",
                                "title": "Review summarized stage",
                                "status": "pending",
                                "ready": True,
                                "is_next": True,
                            }
                        ],
                    },
                    "last_step": {
                        "capability": "browser_dom",
                        "intent": "Use summarized state next step.",
                        "risk_level": "medium",
                        "actions": [{"type": "click", "selector": "#continue"}],
                    },
                },
            },
        }
    )

    assert summary["current_goal"] == "Review summarized stage"
    assert summary["stage_review_status"] == "pending"
    assert summary["pending_decision"]["decision_type"] == "stage_review"
    assert summary["plan_health"]["next_subgoal_id"] == "subgoal_01"
    assert summary["plan_health"]["autonomy"]["status"] == "review_required"
    assert summary["step_proposal"]["capability"] == "browser_dom"
    assert summary["step_proposal"]["actions"][0]["selector"] == "#continue"


def test_desktop_shell_controller_summarizes_string_boolean_flags():
    import desktop_agent.desktop_shell as desktop_shell

    job_summary = desktop_shell.DesktopShellController._summarize_job(
        {
            "id": "job-string-bools",
            "status": "running",
            "task": "track string booleans",
            "cancel_requested": "false",
            "cancelled": "false",
            "completed": "false",
            "requires_human": "false",
            "config_overrides": {
                "browser_control_mode": "hybrid",
                "browser_dom_backend": "playwright",
                "browser_headless": "true",
                "cursor_motion_enabled": "false",
                "generic_app_launch_enabled": "false",
                "shell_recipe_policy": "approval_required",
            },
            "result": {
                "dry_run": "false",
                "cancelled": "false",
                "completed": "false",
                "requires_human": "false",
                "execution_budget": {
                    "max_steps": 9,
                    "max_run_seconds": 240,
                    "desktop_autonomy_mode": "autonomous",
                    "replan_on_recoverable_error": "true",
                    "recoverable_error_retry_limit": 4,
                },
                "execution_environment": {
                    "browser_dom_timeout": 7,
                    "browser_channel": "msedge",
                },
                "state": {
                    "plan_health": {
                        "autonomy": {
                            "can_continue": "false",
                            "requires_review": "true",
                            "requires_user": "false",
                        },
                        "items": [
                            {
                                "id": "subgoal_01",
                                "ready": "true",
                                "is_next": "false",
                                "exhausted": "false",
                            }
                        ],
                    },
                    "last_step": {
                        "requires_approval": "false",
                        "completes_subgoal": "true",
                    },
                    "last_verification": {
                        "success": "false",
                        "evidence": [{"kind": "state", "satisfied": "false"}],
                    },
                    "evidence_ledger": [{"kind": "state", "satisfied": "false"}],
                },
            },
        }
    )

    assert job_summary["dry_run"] is False
    assert job_summary["cancel_requested"] is False
    assert job_summary["cancelled"] is False
    assert job_summary["completed"] is False
    assert job_summary["requires_human"] is False
    assert job_summary["max_steps"] == 9
    assert job_summary["max_run_seconds"] == 240
    assert job_summary["desktop_autonomy_mode"] == "autonomous"
    assert job_summary["replan_on_recoverable_error"] is True
    assert job_summary["recoverable_error_retry_limit"] == 4
    assert job_summary["execution_budget"]["max_steps"] == 9
    assert job_summary["execution_budget"]["replan_on_recoverable_error"] is True
    assert job_summary["browser_control_mode"] == "hybrid"
    assert job_summary["browser_dom_backend"] == "playwright"
    assert job_summary["browser_dom_timeout"] == 7
    assert job_summary["browser_headless"] is True
    assert job_summary["browser_channel"] == "msedge"
    assert job_summary["cursor_motion_enabled"] is False
    assert job_summary["generic_app_launch_enabled"] is False
    assert job_summary["shell_recipe_policy"] == "approval_required"
    assert job_summary["execution_environment"]["browser_headless"] is True
    assert job_summary["execution_environment"]["generic_app_launch_enabled"] is False
    assert job_summary["plan_health"]["autonomy"]["can_continue"] is False
    assert job_summary["plan_health"]["autonomy"]["requires_review"] is True
    assert job_summary["plan_health"]["items"][0]["ready"] is True
    assert job_summary["plan_health"]["items"][0]["is_next"] is False
    assert job_summary["step_proposal"]["requires_approval"] is False
    assert job_summary["step_proposal"]["completes_subgoal"] is True
    assert job_summary["last_verification"]["success"] is False
    assert job_summary["evidence_ledger"][0]["satisfied"] is False

    run_summary = desktop_shell.DesktopShellController._summarize_run(
        {
            "id": "run-string-bools",
            "dry_run": "true",
            "completed": "false",
            "cancelled": "false",
            "requires_human": "false",
            "can_resume": "true",
            "execution_budget": {
                "max_steps": 4,
                "replan_on_recoverable_error": "false",
                "recoverable_error_retry_limit": 2,
            },
            "browser_control_mode": "dom",
            "browser_dom_backend": "uia",
            "browser_headless": "false",
            "cursor_motion_enabled": "true",
            "generic_app_launch_enabled": "false",
            "shell_recipe_policy": "approval_required",
            "state": {
                "plan_health": {
                    "autonomy": {
                        "can_continue": "true",
                        "requires_review": "false",
                        "requires_user": "false",
                    },
                    "items": [{"id": "subgoal_01", "ready": "true", "is_next": "true", "exhausted": "false"}],
                },
                "last_step": {
                    "requires_approval": "false",
                    "completes_subgoal": "true",
                },
            },
            "task_graph": {
                "subgoals": [{"id": "subgoal_01", "ready": "true", "is_next": "true"}],
            },
        }
    )

    assert run_summary["dry_run"] is True
    assert run_summary["completed"] is False
    assert run_summary["cancelled"] is False
    assert run_summary["requires_human"] is False
    assert run_summary["can_resume"] is True
    assert run_summary["max_steps"] == 4
    assert run_summary["replan_on_recoverable_error"] is False
    assert run_summary["execution_budget"]["replan_on_recoverable_error"] is False
    assert run_summary["browser_control_mode"] == "dom"
    assert run_summary["browser_dom_backend"] == "uia"
    assert run_summary["browser_headless"] is False
    assert run_summary["cursor_motion_enabled"] is True
    assert run_summary["generic_app_launch_enabled"] is False
    assert run_summary["shell_recipe_policy"] == "approval_required"
    assert run_summary["execution_environment"]["browser_headless"] is False
    assert run_summary["execution_environment"]["generic_app_launch_enabled"] is False
    assert run_summary["plan_health"]["autonomy"]["can_continue"] is True
    assert run_summary["plan_health"]["autonomy"]["requires_review"] is False
    assert run_summary["plan_health"]["items"][0]["exhausted"] is False
    assert run_summary["task_graph"]["subgoals"][0]["ready"] is True
    assert run_summary["step_proposal"]["requires_approval"] is False


def test_desktop_shell_controller_omits_empty_plan_health_summary():
    import desktop_agent.desktop_shell as desktop_shell

    job_summary = desktop_shell.DesktopShellController._summarize_job(
        {
            "id": "job-empty-plan-health",
            "status": "running",
            "result": {
                "state": {
                    "plan_health": {
                        "counts": {"total": None, "completed": None, "ready": None},
                        "autonomy": {},
                        "items": [{}],
                    },
                },
            },
        }
    )
    run_summary = desktop_shell.DesktopShellController._summarize_run(
        {
            "id": "run-empty-plan-health",
            "state": {
                "plan_health": {
                    "counts": {},
                    "autonomy": {},
                    "items": [{}],
                },
            },
        }
    )

    assert job_summary["plan_health"] is None
    assert run_summary["plan_health"] is None

    payload_without_noise = {
        "active_job": {"id": "job-empty-plan-health", "status": "running", "result": {}},
        "jobs": [],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }
    payload_with_noise = {
        "active_job": {
            "id": "job-empty-plan-health",
            "status": "running",
            "result": {"state": {"plan_health": {"counts": {}, "autonomy": {}}}},
        },
        "jobs": [],
        "runs": [],
        "runtime_preferences": {"updated_at": 12.0},
    }

    assert desktop_shell.DesktopShellController._build_overview_signature(
        payload_without_noise,
        success_feedback_active=False,
    ) == desktop_shell.DesktopShellController._build_overview_signature(
        payload_with_noise,
        success_feedback_active=False,
    )


def test_desktop_shell_controller_preserves_minimal_plan_health_signals():
    import desktop_agent.desktop_shell as desktop_shell

    blocked_summary = desktop_shell.DesktopShellController._summarize_job(
        {
            "id": "job-blocked-reason",
            "status": "running",
            "result": {
                "state": {
                    "plan_health": {
                        "blocked_reason": "Waiting for sign-in.",
                        "counts": {},
                        "autonomy": {},
                    },
                },
            },
        }
    )
    autonomy_summary = desktop_shell.DesktopShellController._summarize_run(
        {
            "id": "run-autonomy-only",
            "state": {
                "plan_health": {
                    "autonomy": {
                        "can_continue": "true",
                        "requires_review": "false",
                        "next_action": "execute",
                    },
                },
            },
        }
    )

    assert blocked_summary["plan_health"]["blocked_reason"] == "Waiting for sign-in."
    assert "counts" not in blocked_summary["plan_health"]
    assert "autonomy" not in blocked_summary["plan_health"]
    assert autonomy_summary["plan_health"]["autonomy"]["can_continue"] is True
    assert autonomy_summary["plan_health"]["autonomy"]["requires_review"] is False
    assert autonomy_summary["plan_health"]["autonomy"]["next_action"] == "execute"
    assert "counts" not in autonomy_summary["plan_health"]


def test_desktop_shell_controller_handle_overview_payload_tracks_surface_progress():
    import desktop_agent.desktop_shell as desktop_shell

    applied: list[dict[str, object]] = []
    controller_stub = SimpleNamespace(
        _overview_request_in_flight=True,
        _last_overview_signature="",
        success_feedback_deadline=0.0,
        _apply_overview_payload=lambda incoming: applied.append(incoming),
    )
    base_run = {
        "id": "run-surface-progress",
        "steps": 2,
        "completed": False,
        "state": {
            "current_goal": "Continue visible desktop work",
            "current_surface_kind": "current_user_desktop",
            "last_progress_at": 1711000001,
        },
    }
    payload_one = {
        "active_job": None,
        "jobs": [],
        "runs": [base_run],
        "runtime_preferences": {"updated_at": 12.0},
    }
    changed_run = {
        **base_run,
        "state": {
            "current_goal": "Continue visible desktop work",
            "current_surface_kind": "managed_aoryn_browser",
            "last_progress_at": 1711000002,
        },
    }
    payload_two = {
        "active_job": None,
        "jobs": [],
        "runs": [changed_run],
        "runtime_preferences": {"updated_at": 12.0},
    }

    desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_one)
    changed = desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_two)

    assert changed is True
    assert len(applied) == 2


def test_desktop_shell_controller_handle_overview_payload_tracks_historical_execution_state_changes():
    import desktop_agent.desktop_shell as desktop_shell

    applied: list[dict[str, object]] = []
    controller_stub = SimpleNamespace(
        _overview_request_in_flight=True,
        _last_overview_signature="",
        success_feedback_deadline=0.0,
        _apply_overview_payload=lambda incoming: applied.append(incoming),
    )
    base_run = {
        "id": "run-execution-state-progress",
        "steps": 2,
        "completed": False,
        "execution_state": {
            "current_goal": "Recover blocked page",
            "plan_health": {
                "counts": {"total": 2, "completed": 0, "ready": 1},
                "next_subgoal_id": "subgoal_01",
                "items": [
                    {"id": "subgoal_01", "title": "Recover blocked page", "status": "pending", "ready": True},
                    {"id": "subgoal_02", "title": "Continue local notes", "status": "pending"},
                ],
            },
        },
    }
    payload_one = {
        "active_job": None,
        "jobs": [],
        "runs": [base_run],
        "runtime_preferences": {"updated_at": 12.0},
    }
    changed_run = {
        **base_run,
        "execution_state": {
            **base_run["execution_state"],
            "current_goal": "Continue local notes",
            "plan_health": {
                "counts": {"total": 2, "completed": 1, "ready": 1},
                "next_subgoal_id": "subgoal_02",
                "items": [
                    {"id": "subgoal_01", "title": "Recover blocked page", "status": "completed"},
                    {"id": "subgoal_02", "title": "Continue local notes", "status": "pending", "ready": True},
                ],
            },
        },
    }
    payload_two = {
        "active_job": None,
        "jobs": [],
        "runs": [changed_run],
        "runtime_preferences": {"updated_at": 12.0},
    }

    desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_one)
    changed = desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_two)

    assert changed is True
    assert len(applied) == 2


def test_desktop_shell_controller_handle_overview_payload_tracks_recovery_trace():
    import desktop_agent.desktop_shell as desktop_shell

    applied: list[dict[str, object]] = []
    controller_stub = SimpleNamespace(
        _overview_request_in_flight=True,
        _last_overview_signature="",
        success_feedback_deadline=0.0,
        _apply_overview_payload=lambda incoming: applied.append(incoming),
    )
    base_run = {
        "id": "run-recovery-trace",
        "steps": 2,
        "completed": False,
        "state": {
            "current_goal": "Repair stale target",
            "repair_history": [{"mode": "repair", "subgoal_id": "subgoal_01", "failure_kind": "stale_target", "step": 1}],
            "capability_failures": {"subgoal_01:desktop_gui": ["stale_target"]},
        },
    }
    payload_one = {
        "active_job": None,
        "jobs": [],
        "runs": [base_run],
        "runtime_preferences": {"updated_at": 12.0},
    }
    changed_run = {
        **base_run,
        "state": {
            "current_goal": "Repair stale target",
            "repair_history": [
                {"mode": "repair", "subgoal_id": "subgoal_01", "failure_kind": "stale_target", "step": 1},
                {"mode": "replan", "subgoal_id": "subgoal_01", "failure_kind": "stale_target", "step": 2},
            ],
            "capability_failures": {"subgoal_01:desktop_gui": ["stale_target", "partial_progress"]},
        },
    }
    payload_two = {
        "active_job": None,
        "jobs": [],
        "runs": [changed_run],
        "runtime_preferences": {"updated_at": 12.0},
    }

    desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_one)
    changed = desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_two)

    assert changed is True
    assert len(applied) == 2


def test_desktop_shell_controller_handle_overview_payload_tracks_historical_verification_trace():
    import desktop_agent.desktop_shell as desktop_shell

    applied: list[dict[str, object]] = []
    controller_stub = SimpleNamespace(
        _overview_request_in_flight=True,
        _last_overview_signature="",
        success_feedback_deadline=0.0,
        _apply_overview_payload=lambda incoming: applied.append(incoming),
    )
    base_run = {
        "id": "run-verification-trace",
        "steps": 2,
        "completed": False,
        "state": {
            "current_goal": "Verify historical step",
            "verification_status": "partial_progress",
            "last_verification": {
                "status": "partial_progress",
                "failure_kind": "needs_more_evidence",
                "message": "Selector was found but completion is not proven.",
                "evidence": [{"kind": "selector", "selector": "#continue"}],
            },
            "evidence_ledger": [
                {
                    "subgoal_id": "subgoal_01",
                    "capability": "browser_dom",
                    "status": "partial_progress",
                    "evidence": [{"kind": "selector", "selector": "#continue"}],
                }
            ],
        },
    }
    payload_one = {
        "active_job": None,
        "jobs": [],
        "runs": [base_run],
        "runtime_preferences": {"updated_at": 12.0},
    }
    changed_run = {
        **base_run,
        "state": {
            **base_run["state"],
            "verification_status": "failed",
            "last_verification": {
                "status": "failed",
                "failure_kind": "verification_failed",
                "message": "The screenshot contradicted completion.",
                "evidence": [{"kind": "screenshot", "title": "Mismatch"}],
            },
            "evidence_ledger": [
                *base_run["state"]["evidence_ledger"],
                {
                    "subgoal_id": "subgoal_01",
                    "capability": "browser_dom",
                    "status": "failed",
                    "evidence": [{"kind": "screenshot", "title": "Mismatch"}],
                },
            ],
        },
    }
    payload_two = {
        "active_job": None,
        "jobs": [],
        "runs": [changed_run],
        "runtime_preferences": {"updated_at": 12.0},
    }

    desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_one)
    changed = desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_two)

    assert changed is True
    assert len(applied) == 2


def test_desktop_shell_controller_handle_overview_payload_tracks_historical_handoff_state():
    import desktop_agent.desktop_shell as desktop_shell

    applied: list[dict[str, object]] = []
    controller_stub = SimpleNamespace(
        _overview_request_in_flight=True,
        _last_overview_signature="",
        success_feedback_deadline=0.0,
        _apply_overview_payload=lambda incoming: applied.append(incoming),
    )
    base_run = {
        "id": "run-handoff-state",
        "steps": 2,
        "completed": False,
        "state": {
            "current_goal": "Resume historical run",
            "app_context": {
                "human_handoff_kind": "login",
                "human_handoff_reason": "Complete sign-in before continuing.",
            },
        },
    }
    payload_one = {
        "active_job": None,
        "jobs": [],
        "runs": [base_run],
        "runtime_preferences": {"updated_at": 12.0},
    }
    changed_run = {
        **base_run,
        "state": {
            **base_run["state"],
            "app_context": {
                "manual_resume_status": "resumed",
                "manual_resume_reason": "Sign-in completed by the user.",
            },
        },
    }
    payload_two = {
        "active_job": None,
        "jobs": [],
        "runs": [changed_run],
        "runtime_preferences": {"updated_at": 12.0},
    }

    desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_one)
    changed = desktop_shell.DesktopShellController._handle_overview_payload(controller_stub, payload_two)

    assert changed is True
    assert len(applied) == 2


def test_desktop_shell_controller_finds_manual_resume_mode_run():
    import desktop_agent.desktop_shell as desktop_shell

    run = {
        "id": "manual-run",
        "completed": False,
        "can_resume": True,
        "requires_human": False,
        "resume_mode": "manual",
    }

    paused_run = desktop_shell.DesktopShellController._find_paused_resume_run([run])

    assert paused_run is run


def test_desktop_shell_controller_finds_pending_decision_run():
    import desktop_agent.desktop_shell as desktop_shell

    run = {
        "id": "review-run",
        "completed": False,
        "can_resume": True,
        "requires_human": False,
        "resume_mode": "execution_state",
        "state": {
            "pending_decision": {
                "decision_type": "plan_review",
                "summary": "Review the generated task plan.",
            }
        },
    }

    paused_run = desktop_shell.DesktopShellController._find_paused_resume_run([run])

    assert paused_run is run


def test_desktop_shell_controller_finds_saved_step_approval_phase_run():
    import desktop_agent.desktop_shell as desktop_shell

    run = {
        "id": "step-approval-run",
        "completed": False,
        "requires_human": False,
        "execution_state": {
            "orchestration_phase": "awaiting_approval",
            "task_graph": {
                "subgoals": [
                    {
                        "id": "subgoal_01",
                        "title": "Confirm guarded step",
                        "status": "pending",
                    }
                ],
            },
        },
    }

    paused_run = desktop_shell.DesktopShellController._find_paused_resume_run([run])

    assert paused_run is run


def test_desktop_shell_controller_finds_resume_run_with_string_boolean_flags():
    import desktop_agent.desktop_shell as desktop_shell

    blocked_by_can_resume = {
        "id": "blocked-run",
        "completed": "false",
        "cancelled": "false",
        "can_resume": "false",
        "requires_human": "true",
    }
    false_handoff = {
        "id": "not-paused",
        "completed": "false",
        "cancelled": "false",
        "can_resume": "true",
        "requires_human": "false",
    }
    paused = {
        "id": "paused-run",
        "completed": "false",
        "cancelled": "false",
        "can_resume": "true",
        "requires_human": "true",
    }
    failed_with_stale_handoff = {
        "id": "failed-run",
        "completed": "false",
        "cancelled": "false",
        "can_resume": "true",
        "requires_human": "true",
        "error": "planner stopped",
        "state": {
            "pending_decision": {
                "decision_type": "plan_review",
                "summary": "Stale review request.",
            },
        },
    }
    cancelled_with_saved_state = {
        "id": "cancelled-review-run",
        "completed": "false",
        "cancelled": "true",
        "can_resume": "true",
        "requires_human": "false",
        "resume_mode": "execution_state",
        "cancel_reason": "Review later.",
        "execution_state": {
            "task_graph": {
                "subgoals": [{"id": "subgoal_01", "title": "Continue reviewed task", "status": "pending"}],
            }
        },
    }

    assert desktop_shell.DesktopShellController._find_paused_resume_run([blocked_by_can_resume]) is None
    assert desktop_shell.DesktopShellController._find_paused_resume_run([false_handoff]) is None
    assert desktop_shell.DesktopShellController._find_paused_resume_run([failed_with_stale_handoff]) is None
    assert desktop_shell.DesktopShellController._find_paused_resume_run([false_handoff, paused]) is paused
    assert desktop_shell.DesktopShellController._find_paused_resume_run([cancelled_with_saved_state]) is cancelled_with_saved_state


def test_desktop_shell_controller_summarizes_run_execution_state_pending_decision():
    import desktop_agent.desktop_shell as desktop_shell

    summary = desktop_shell.DesktopShellController._summarize_run(
        {
            "id": "review-run",
            "completed": False,
            "execution_state": {
                "current_goal": "Review generated plan",
                "plan_health": {
                    "counts": {"total": 1, "completed": 0, "ready": 1},
                    "next_subgoal_id": "subgoal_01",
                    "items": [{"id": "subgoal_01", "title": "Review generated plan", "status": "pending"}],
                },
                "pending_decision": {
                    "decision_type": "plan_review",
                    "summary": "Review the generated task plan.",
                    "reason": "The plan touches an external account.",
                    "risk_level": "high",
                }
            },
        }
    )

    assert summary["pending_decision"]["decision_type"] == "plan_review"
    assert summary["pending_decision"]["summary"] == "Review the generated task plan."
    assert summary["pending_decision"]["risk_level"] == "high"
    assert summary["current_goal"] == "Review generated plan"
    assert summary["plan_health"]["next_subgoal_id"] == "subgoal_01"

    terminal_summary = desktop_shell.DesktopShellController._summarize_run(
        {
            "id": "failed-review-run",
            "completed": "false",
            "cancelled": "false",
            "requires_human": "true",
            "error": "planner stopped",
            "state": {
                "pending_decision": {
                    "decision_type": "plan_review",
                    "summary": "Stale review request.",
                    "risk_level": "high",
                }
            },
        }
    )

    assert terminal_summary["requires_human"] is False
    assert terminal_summary["pending_decision"] is None


def test_desktop_shell_controller_handle_overview_error_resets_idle_feedback_after_deadline():
    import desktop_agent.desktop_shell as desktop_shell

    hidden: list[str] = []
    shown: list[str] = []
    controller_stub = SimpleNamespace(
        _overview_request_in_flight=True,
        success_feedback_deadline=time.time() - 0.1,
        main_window=SimpleNamespace(isVisible=lambda: False),
        floating=SimpleNamespace(
            hide_floating=lambda: hidden.append("hide"),
            show_idle=lambda **kwargs: shown.append(kwargs.get("status", "")),
        ),
    )

    result = desktop_shell.DesktopShellController._handle_overview_error(controller_stub, "offline")

    assert result is False
    assert controller_stub._overview_request_in_flight is False
    assert controller_stub.success_feedback_deadline == 0
    assert hidden == []
    assert shown == [""]


def test_desktop_main_window_show_policy_uses_work_area_on_windows(monkeypatch):
    from desktop_agent.desktop_shell import DesktopMainWindow

    calls: list[tuple[str, object]] = []
    window_stub = SimpleNamespace(
        _environment_provider=None,
        _display_mode="workarea_maximized",
        minimumWidth=lambda: 1180,
        minimumHeight=lambda: 760,
        setGeometry=lambda x, y, w, h: calls.append(("geometry", (x, y, w, h))),
        showNormal=lambda: calls.append(("showNormal", None)),
        show=lambda: calls.append(("show", None)),
        showMaximized=lambda: calls.append(("showMaximized", None)),
        showFullScreen=lambda: calls.append(("showFullScreen", None)),
    )

    monkeypatch.setattr(controller.sys, "platform", "win32")
    monkeypatch.setattr(
        "desktop_agent.desktop_shell.capture_effective_desktop_environment",
        lambda: DesktopEnvironment(
            platform="windows",
            virtual_bounds=Rect(0, 0, 1920, 1080),
            monitors=[
                MonitorSnapshot(
                    device_name="DISPLAY1",
                    is_primary=True,
                    bounds=Rect(0, 0, 1920, 1080),
                    work_area=Rect(0, 0, 1920, 1040),
                )
            ],
            current_monitor=MonitorSnapshot(
                device_name="DISPLAY1",
                is_primary=True,
                bounds=Rect(0, 0, 1920, 1080),
                work_area=Rect(0, 0, 1920, 1040),
            ),
        ),
    )

    DesktopMainWindow._show_with_display_policy(window_stub)

    assert ("geometry", (0, 0, 1920, 1040)) in calls
    assert ("showMaximized", None) in calls


def test_desktop_main_window_show_policy_supports_fullscreen():
    from desktop_agent.desktop_shell import DesktopMainWindow

    calls: list[tuple[str, object]] = []
    window_stub = SimpleNamespace(
        _environment_provider=None,
        _display_mode="fullscreen",
        minimumWidth=lambda: 1180,
        minimumHeight=lambda: 760,
        setGeometry=lambda x, y, w, h: calls.append(("geometry", (x, y, w, h))),
        showNormal=lambda: calls.append(("showNormal", None)),
        show=lambda: calls.append(("show", None)),
        showMaximized=lambda: calls.append(("showMaximized", None)),
        showFullScreen=lambda: calls.append(("showFullScreen", None)),
    )

    DesktopMainWindow._show_with_display_policy(window_stub)

    assert ("showFullScreen", None) in calls
    assert ("showMaximized", None) not in calls


def test_qtwebengine_storage_root_falls_back_when_local_root_is_not_writable(monkeypatch):
    import desktop_agent.desktop_shell as desktop_shell

    scratch_root = Path("test_artifacts") / f"qtwebengine_root_{uuid4().hex}"
    primary_root = scratch_root / "primary"
    fallback_root = scratch_root / "fallback"

    try:
        monkeypatch.setattr(
            desktop_shell,
            "_qtwebengine_storage_candidates",
            lambda: [primary_root, fallback_root],
        )
        monkeypatch.setattr(
            desktop_shell,
            "_is_writable_directory",
            lambda path: str(path).startswith(str(fallback_root)),
        )

        assert desktop_shell._resolve_qtwebengine_storage_root() == fallback_root / "qtwebengine"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_configure_qtwebengine_profile_storage_uses_resolved_root(monkeypatch):
    import desktop_agent.desktop_shell as desktop_shell

    calls: list[tuple[str, str]] = []

    class FakeProfile:
        def setPersistentStoragePath(self, path: str) -> None:
            calls.append(("profile", path))

        def setCachePath(self, path: str) -> None:
            calls.append(("cache", path))

    scratch_root = Path("test_artifacts") / f"qtwebengine_profile_{uuid4().hex}"
    qt_root = scratch_root / "qtwebengine"

    try:
        monkeypatch.setattr(desktop_shell, "_resolve_qtwebengine_storage_root", lambda: qt_root)
        monkeypatch.setattr(
            desktop_shell,
            "QWebEngineProfile",
            SimpleNamespace(defaultProfile=lambda: FakeProfile()),
        )

        desktop_shell._configure_qtwebengine_profile_storage()

        assert ("profile", str(qt_root / "profile")) in calls
        assert ("cache", str(qt_root / "cache")) in calls
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_configure_qtwebengine_environment_omits_single_process_by_default_on_windows(monkeypatch):
    import desktop_agent.desktop_shell as desktop_shell

    monkeypatch.delenv("QTWEBENGINE_CHROMIUM_FLAGS", raising=False)
    monkeypatch.delenv("QTWEBENGINE_DISABLE_SANDBOX", raising=False)
    monkeypatch.delenv("AORYN_QTWEBENGINE_SINGLE_PROCESS", raising=False)
    monkeypatch.setattr(desktop_shell.sys, "platform", "win32")

    desktop_shell._configure_qtwebengine_environment()

    flags = set((os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS") or "").split())
    assert "--no-sandbox" in flags
    assert "--single-process" not in flags
    assert os.environ.get("QTWEBENGINE_DISABLE_SANDBOX") == "1"


def test_configure_qtwebengine_environment_honors_single_process_escape_hatch(monkeypatch):
    import desktop_agent.desktop_shell as desktop_shell

    monkeypatch.delenv("QTWEBENGINE_CHROMIUM_FLAGS", raising=False)
    monkeypatch.delenv("QTWEBENGINE_DISABLE_SANDBOX", raising=False)
    monkeypatch.setenv("AORYN_QTWEBENGINE_SINGLE_PROCESS", "1")
    monkeypatch.setattr(desktop_shell.sys, "platform", "win32")

    desktop_shell._configure_qtwebengine_environment()

    flags = set((os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS") or "").split())
    assert "--no-sandbox" in flags
    assert "--single-process" in flags
    assert os.environ.get("QTWEBENGINE_DISABLE_SANDBOX") == "1"
