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
from desktop_agent.workflow import ExecutionState, StepProposal, Subgoal, TaskGraph, VerificationResult
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
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


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
    assert (idle.width, idle.height) == (220, 46)
    assert idle.show_open is True
    assert idle.show_add is True
    assert idle.show_input is False

    assert expanded.mode == "idle_input"
    assert (expanded.width, expanded.height) == (440, 54)
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

    running = build_floating_view_state(active_job=active_job)
    queued = build_floating_view_state(active_job=active_job, follow_up_draft="下一步搜索文档")
    expanded = build_floating_view_state(
        active_job=active_job,
        follow_up_draft="下一步搜索文档",
        input_expanded=True,
    )
    stopping = build_floating_view_state(active_job={**active_job, "status": "stopping", "cancel_requested": True})

    assert running.mode == "running"
    assert (running.width, running.height) == (360, 46)
    assert running.show_timer is True
    assert running.show_stop is True
    assert running.show_open is True
    assert running.show_add is True

    assert queued.mode == "running_queued"
    assert queued.add_label == "编辑"

    assert expanded.mode == "running_input"
    assert (expanded.width, expanded.height) == (440, 54)
    assert expanded.show_input is True
    assert expanded.submit_label == "排队"
    assert expanded.input_text == "下一步搜索文档"

    assert stopping.mode == "stopping"
    assert (stopping.width, stopping.height) == (220, 46)
    assert stopping.title == "正在停止"
    assert stopping.show_add is False
    assert stopping.show_stop is False
    assert stopping.show_open is True


def test_build_floating_view_state_approval_resume_and_waiting_follow_up():
    from desktop_agent.desktop_shell import build_floating_view_state

    approval = build_floating_view_state(
        active_job={
            "id": "job-approve",
            "status": "approval",
            "result": {"pending_decision": {"summary": "确认是否点击付款按钮"}},
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
    assert (approval.width, approval.height) == (420, 54)
    assert approval.show_continue is True
    assert approval.continue_label == "批准"
    assert approval.show_stop is True
    assert approval.stop_label == "驳回"

    assert resume.mode == "resume"
    assert (resume.width, resume.height) == (420, 54)
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
