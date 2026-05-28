from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from desktop_agent.actions import Action, PlanResult
from desktop_agent.capabilities import CapabilityExecutor, build_capability_registry
from desktop_agent.config import AgentConfig
from desktop_agent.drivers import DriverRegistry, build_driver_registry
from desktop_agent.executor import (
    BaseExecutor,
    CapabilityExecutor as CapabilityExecutorExport,
    ExecutionCancelled,
    ExecutionError,
    MockExecutor,
    RealDesktopExecutor,
)
from desktop_agent.human_verification import HumanVerificationSignal, detect_human_verification
from desktop_agent.logger import RunLogger
from desktop_agent.orchestrator import TaskOrchestrator, standardize_failure_kind, task_graph_is_ambiguous, task_graph_risk_level
from desktop_agent.perception import MockCapture, PerceptionError, ScreenCapture
from desktop_agent.planner import (
    BasePlanner,
    PlannerError,
    SubgoalPlanner,
    TaskGraphPlanner,
    build_planner,
)
from desktop_agent.recipes import TaskRecipeMemory
from desktop_agent.runtime_paths import discover_default_config_path
from desktop_agent.safety import ActionGuard, SafetyError
from desktop_agent.surfaces import (
    capture_user_desktop_session,
    choose_surface_kind,
    detect_user_input_preemption,
)
from desktop_agent.version import APP_NAME
from desktop_agent.workflow import (
    ExecutionState,
    PendingDecision,
    StepProposal,
    Subgoal,
    VerificationResult,
    WorldModel,
    build_execution_plan_summary,
)


DEFAULT_DASHBOARD_HOST = "127.0.0.1"
DEFAULT_DASHBOARD_PORT = 8765


@dataclass(slots=True)
class AgentRunResult:
    task: str
    completed: bool
    steps: int
    run_dir: Path
    started_at: float
    finished_at: float
    error: str | None = None
    cancelled: bool = False
    cancel_reason: str | None = None
    requires_human: bool = False
    interruption_kind: str | None = None
    interruption_reason: str | None = None


@dataclass(slots=True)
class ResumeRunContext:
    task: str
    run_dir: Path
    started_at: float
    step_offset: int
    execution_state: ExecutionState | None = None


class DesktopAgent:
    def __init__(
        self,
        config: AgentConfig,
        planner: BasePlanner,
        executor: BaseExecutor,
        perception: ScreenCapture,
        logger: RunLogger,
        guard: ActionGuard,
        stop_requested: Callable[[], bool] | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        decision_callback: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
        task_graph_planner: TaskGraphPlanner | None = None,
        capability_executor: CapabilityExecutor | None = None,
        driver_registry: DriverRegistry | None = None,
        recipe_memory: TaskRecipeMemory | None = None,
    ) -> None:
        self.config = config
        self.planner = planner
        self.executor = executor
        self.perception = perception
        self.logger = logger
        self.guard = guard
        self.stop_requested = stop_requested
        self.progress_callback = progress_callback
        self.decision_callback = decision_callback
        self.driver_registry = driver_registry or build_driver_registry()
        self.task_graph_planner = task_graph_planner or TaskGraphPlanner(config)
        self.capability_executor = capability_executor or CapabilityExecutor(
            config=config,
            planner=planner,
            registry=build_capability_registry(),
            driver_registry=self.driver_registry,
        )
        self.recipe_memory = recipe_memory or TaskRecipeMemory()
        self.orchestrator = TaskOrchestrator(
            config=config,
            task_graph_planner=self.task_graph_planner,
            capability_executor=self.capability_executor,
            recipe_memory=self.recipe_memory,
        )
        self._live_progress_context: dict[str, Any] | None = None
        self._live_pointer_trail: list[dict[str, Any]] = []
        self._active_run_deadline: float | None = None
        self._active_stop_reason: str | None = None
        if hasattr(self.executor, "set_action_progress_callback"):
            self.executor.set_action_progress_callback(self._handle_action_progress)

    def run(
        self,
        task: str,
        *,
        run_dir: Path | None = None,
        execution_state: ExecutionState | None = None,
        started_at: float | None = None,
        step_offset: int = 0,
        history: list[str] | None = None,
    ) -> AgentRunResult:
        run_dir = run_dir or self.logger.create_run_dir(task)
        started_at = float(started_at) if isinstance(started_at, (int, float)) else time.time()
        self._emit_progress(
            {
                "task": task,
                "run_dir": str(run_dir),
                "run_id": run_dir.name,
                "steps": max(0, int(step_offset)),
                "latest_screenshot": None,
                "latest_summary": None,
                "latest_actions": [],
                "live_pointer": None,
                "live_pointer_trail": [],
                "live_action": None,
                "started_at": started_at,
            }
        )
        history = list(history or (execution_state.memory if execution_state is not None else []))
        completed = False
        error_message: str | None = None
        cancelled = False
        cancel_reason: str | None = None
        step_count = max(0, int(step_offset))
        challenge_signal: HumanVerificationSignal | None = None
        previous_deadline = self._active_run_deadline
        previous_stop_reason = self._active_stop_reason
        previous_executor_stop_requested = getattr(self.executor, "_run_stop_requested", None)
        self._active_run_deadline = _resolve_run_deadline(started_at, self.config.max_run_seconds)
        self._active_stop_reason = None
        if hasattr(self.executor, "set_run_stop_requested"):
            self.executor.set_run_stop_requested(self._stop_requested)
        last_step_signature: str | None = None
        repeated_plan_count = 0
        last_visible_step_signature: str | None = None
        repeated_visible_step_count = 0
        recoverable_error_count = 0
        execution_loop_error = "Detected the same step repeatedly. Task stopped to avoid an execution loop."

        for relative_step_index in range(1, self.config.max_steps + 1):
            if self._stop_requested():
                cancelled = True
                cancel_reason = self._stop_cancel_reason()
                challenge_signal = self._build_stop_signal()
                break

            step_index = step_offset + relative_step_index
            step_count = step_index
            screenshot_path = run_dir / f"step_{step_index:02d}.{self.config.screenshot_format}"
            plan: PlanResult | None = None
            step_proposal: StepProposal | None = None
            safe_actions: list[Action] = []
            verification: VerificationResult | None = None
            world_model: WorldModel | None = None
            recovery_mode: str | None = None
            step_started_at = time.perf_counter()
            step_timings: dict[str, float] = {}

            try:
                phase_started = time.perf_counter()
                screen_info = self.perception.capture(screenshot_path)
                _record_step_timing(step_timings, "capture_initial", phase_started)
                captured_at = time.time()
                environment_payload = _build_environment_payload(screen_info)
                if hasattr(self.executor, "update_environment"):
                    self.executor.update_environment(getattr(screen_info, "environment", None))
                self._raise_if_stop_requested()

                phase_started = time.perf_counter()
                world_model = self._build_world_model(
                    screenshot_path=screenshot_path,
                    screen_info=screen_info,
                    step_index=step_index,
                    captured_at=captured_at,
                )
                _record_step_timing(step_timings, "world_model", phase_started)
                self._raise_if_stop_requested()
                challenge_signal = detect_human_verification(world_model.browser_snapshot)
                if challenge_signal is not None:
                    plan = _build_human_handoff_plan(challenge_signal)
                    timings_payload = _finalize_step_timings(step_timings, step_started_at)
                    self.logger.log_step(
                        run_dir=run_dir,
                        step_index=step_index,
                        task=task,
                        screenshot_path=screenshot_path,
                        plan=plan,
                        executed_actions=[],
                        error=None,
                        challenge=challenge_signal.to_dict(),
                        captured_at=captured_at,
                        environment=environment_payload,
                        world_model=world_model.to_dict(),
                        timings=timings_payload,
                    )
                    self._emit_progress(
                        self._build_progress_payload(
                            task=task,
                            run_dir=run_dir,
                            step_index=step_index,
                            screenshot_path=screenshot_path,
                            captured_at=captured_at,
                            plan=plan,
                            executed_actions=[],
                            error=None,
                            challenge=challenge_signal.to_dict(),
                            started_at=started_at,
                            environment=environment_payload,
                            execution_state=None,
                            step_proposal=None,
                            verification=None,
                            timings=timings_payload,
                        )
                    )
                    history.append(challenge_signal.summary)
                    break

                phase_started = time.perf_counter()
                if execution_state is None:
                    execution_state = self._initialize_execution_state(task=task, run_dir=run_dir, world_model=world_model)
                else:
                    execution_state.world_model = world_model
                    execution_state.updated_at = time.time()
                    self.orchestrator.prime_state(execution_state, world_model=world_model)

                if detect_user_input_preemption(
                    config=self.config,
                    execution_context=execution_state.app_context,
                    session=world_model.user_desktop_session,
                ):
                    challenge_signal = HumanVerificationSignal(
                        kind="user_preempted",
                        summary="User activity detected. Pause automation and resume when ready.",
                        detail=(
                            "Aoryn noticed fresh user mouse or keyboard activity on the shared desktop. "
                            "Automation paused so it does not fight for control."
                        ),
                        title=world_model.active_window_title,
                    )
                    plan = _build_human_handoff_plan(challenge_signal)
                    self._log_execution_state(run_dir=run_dir, execution_state=execution_state)
                    self.logger.log_step(
                        run_dir=run_dir,
                        step_index=step_index,
                        task=task,
                        screenshot_path=screenshot_path,
                        plan=plan,
                        executed_actions=[],
                        error=None,
                        challenge=challenge_signal.to_dict(),
                        captured_at=captured_at,
                        environment=environment_payload,
                        state=build_execution_plan_summary(execution_state),
                        world_model=world_model.to_dict(),
                        step_proposal=None,
                        verification=None,
                    )
                    self._emit_progress(
                        self._build_progress_payload(
                            task=task,
                            run_dir=run_dir,
                            step_index=step_index,
                            screenshot_path=screenshot_path,
                            captured_at=captured_at,
                            plan=plan,
                            executed_actions=[],
                            error=None,
                            challenge=challenge_signal.to_dict(),
                            started_at=started_at,
                            environment=environment_payload,
                            execution_state=execution_state,
                            step_proposal=None,
                            verification=None,
                        )
                    )
                    history.append(challenge_signal.summary)
                    break

                observed_facts = self.orchestrator.observe_world(state=execution_state, world_model=world_model)
                world_model.facts = observed_facts
                execution_state.facts = _merge_facts(execution_state.facts, observed_facts)

                current_subgoal = self.orchestrator.prepare_stage(state=execution_state, world_model=world_model)
                _record_step_timing(step_timings, "observe_prepare", phase_started)
                self._raise_if_stop_requested()
                if current_subgoal is None:
                    completed = True
                    execution_state.completed = True
                    self.orchestrator.mark_complete(execution_state)
                    break
                review_type = self.orchestrator.pending_review_type(execution_state)
                if review_type is not None:
                    decision_response = self._request_plan_review(
                        execution_state=execution_state,
                        run_dir=run_dir,
                        step_index=step_index,
                        screenshot_path=screenshot_path,
                        captured_at=captured_at,
                        environment_payload=environment_payload,
                        world_model=world_model,
                        decision_type=review_type,
                    )
                    if decision_response.get("decision") == "reject":
                        error_message = (
                            "The replanned stage was rejected by the user."
                            if review_type == "stage_review"
                            else "The task plan was rejected by the user."
                        )
                        execution_state.pending_decision = None
                        execution_state.app_context[
                            "stage_review_status" if review_type == "stage_review" else "plan_review_status"
                        ] = "rejected"
                        self.orchestrator.record_decision(
                            state=execution_state,
                            decision_type=review_type,
                            status="rejected",
                            risk_level=_task_graph_risk_level(execution_state),
                            summary=error_message,
                            note=str(decision_response.get("note") or ""),
                        )
                        self._log_execution_state(run_dir=run_dir, execution_state=execution_state)
                        break
                    if decision_response.get("decision") == "cancel":
                        cancelled = True
                        cancel_reason = str(decision_response.get("note") or "Stopped by user.")
                        execution_state.pending_decision = None
                        self._log_execution_state(run_dir=run_dir, execution_state=execution_state)
                        break
                    execution_state.pending_decision = None
                    execution_state.app_context[
                        "stage_review_status" if review_type == "stage_review" else "plan_review_status"
                    ] = "approved"
                    self.orchestrator.record_decision(
                        state=execution_state,
                        decision_type=review_type,
                        status="approved",
                        risk_level=_task_graph_risk_level(execution_state),
                        summary=f"{review_type} approved.",
                        note=str(decision_response.get("note") or ""),
                    )
                    self._log_execution_state(run_dir=run_dir, execution_state=execution_state)
                if current_subgoal.goal_type == "clarify":
                    challenge_signal = HumanVerificationSignal(
                        kind="requires_clarification",
                        summary=current_subgoal.title,
                        detail=current_subgoal.success_condition,
                        title=world_model.active_window_title,
                    )
                    plan = _build_human_handoff_plan(challenge_signal)
                    self._log_execution_state(run_dir=run_dir, execution_state=execution_state)
                    self.logger.log_step(
                        run_dir=run_dir,
                        step_index=step_index,
                        task=task,
                        screenshot_path=screenshot_path,
                        plan=plan,
                        executed_actions=[],
                        error=None,
                        challenge=challenge_signal.to_dict(),
                        captured_at=captured_at,
                        environment=environment_payload,
                        state=build_execution_plan_summary(execution_state),
                        world_model=world_model.to_dict(),
                        step_proposal=None,
                        verification=None,
                    )
                    self._emit_progress(
                        self._build_progress_payload(
                            task=task,
                            run_dir=run_dir,
                            step_index=step_index,
                            screenshot_path=screenshot_path,
                            captured_at=captured_at,
                            plan=plan,
                            executed_actions=[],
                            error=None,
                            challenge=challenge_signal.to_dict(),
                            started_at=started_at,
                            environment=environment_payload,
                            execution_state=execution_state,
                            step_proposal=None,
                            verification=None,
                        )
                    )
                    history.append(challenge_signal.summary)
                    break
                execution_state.task_graph.mark_in_progress(current_subgoal.id)

                phase_started = time.perf_counter()
                step_proposal = self.orchestrator.propose_step(
                    state=execution_state,
                    world_model=world_model,
                )
                execution_state.last_step = step_proposal
                plan = step_proposal.to_plan_result(done=step_proposal.completes_subgoal)
                safe_actions = self.guard.validate_many(
                    step_proposal.actions,
                    screen_width=screen_info.width,
                    screen_height=screen_info.height,
                )
                _record_step_timing(step_timings, "plan", phase_started)
                self._raise_if_stop_requested()
                plan_signature = _build_step_signature(current_subgoal.id, step_proposal, safe_actions)
                visible_step_signature = _build_visible_step_signature(current_subgoal.id, step_proposal, safe_actions)
                if plan_signature == last_step_signature:
                    repeated_plan_count += 1
                else:
                    repeated_plan_count = 1
                    last_step_signature = plan_signature
                if visible_step_signature == last_visible_step_signature:
                    repeated_visible_step_count += 1
                else:
                    repeated_visible_step_count = 1
                    last_visible_step_signature = visible_step_signature
                if (
                    (repeated_plan_count >= 3 and execution_state.stuck_rounds >= 2)
                    or (repeated_visible_step_count >= 3 and execution_state.stuck_rounds >= 1)
                ):
                    plan_loop_detected = repeated_plan_count >= 3 and execution_state.stuck_rounds >= 2
                    visible_loop_detected = repeated_visible_step_count >= 3 and execution_state.stuck_rounds >= 1
                    error_message = (
                        f"Subgoal became stuck after repeated failed attempts: {current_subgoal.title}"
                        if plan_loop_detected
                        else execution_loop_error
                    )
                    verification = VerificationResult(
                        success=False,
                        status="failed",
                        evidence=[],
                        failure_kind="goal_ambiguous",
                        message=error_message,
                    )
                    execution_state.last_verification = verification
                    self._log_execution_state(run_dir=run_dir, execution_state=execution_state)
                    self.logger.log_step(
                        run_dir=run_dir,
                        step_index=step_index,
                        task=task,
                        screenshot_path=screenshot_path,
                        plan=plan,
                        executed_actions=[],
                        error=error_message,
                        challenge=None,
                        captured_at=captured_at,
                        environment=environment_payload,
                        state=build_execution_plan_summary(execution_state),
                        world_model=world_model.to_dict(),
                        step_proposal=step_proposal.to_dict(),
                        verification=verification.to_dict(),
                    )
                    self._emit_progress(
                        self._build_progress_payload(
                            task=task,
                            run_dir=run_dir,
                            step_index=step_index,
                            screenshot_path=screenshot_path,
                            captured_at=captured_at,
                            plan=plan,
                            executed_actions=[],
                            error=error_message,
                            challenge=None,
                            started_at=started_at,
                            environment=environment_payload,
                            execution_state=execution_state,
                            step_proposal=step_proposal,
                            verification=verification,
                        )
                    )
                    break

                if step_proposal.requires_approval and safe_actions:
                    decision_response = self._request_decision(
                        execution_state=execution_state,
                        step_proposal=step_proposal,
                        plan=plan,
                        run_dir=run_dir,
                        step_index=step_index,
                        screenshot_path=screenshot_path,
                        captured_at=captured_at,
                        environment_payload=environment_payload,
                        world_model=world_model,
                    )
                    if decision_response.get("decision") == "reject":
                        error_message = "The requested high-risk step was rejected by the user."
                        verification = VerificationResult(
                            success=False,
                            status="failed",
                            evidence=[],
                            failure_kind="approval_rejected",
                            message=error_message,
                        )
                        execution_state.last_verification = verification
                        execution_state.pending_decision = None
                        self.orchestrator.record_decision(
                            state=execution_state,
                            decision_type="step_approval",
                            status="rejected",
                            risk_level=step_proposal.risk_level,
                            summary=step_proposal.intent,
                            note=str(decision_response.get("note") or ""),
                        )
                        self._log_execution_state(run_dir=run_dir, execution_state=execution_state)
                        self.logger.log_step(
                            run_dir=run_dir,
                            step_index=step_index,
                            task=task,
                            screenshot_path=screenshot_path,
                            plan=plan,
                            executed_actions=[],
                            error=error_message,
                            challenge=None,
                            captured_at=time.time(),
                            environment=environment_payload,
                            state=build_execution_plan_summary(execution_state),
                            world_model=world_model.to_dict(),
                            step_proposal=step_proposal.to_dict(),
                            verification=verification.to_dict(),
                        )
                        self._emit_progress(
                            self._build_progress_payload(
                                task=task,
                                run_dir=run_dir,
                                step_index=step_index,
                                screenshot_path=screenshot_path,
                                captured_at=time.time(),
                                plan=plan,
                                executed_actions=[],
                                error=error_message,
                                challenge=None,
                                started_at=started_at,
                                environment=environment_payload,
                                execution_state=execution_state,
                                step_proposal=step_proposal,
                                verification=verification,
                            )
                        )
                        break
                    if decision_response.get("decision") == "cancel":
                        cancelled = True
                        cancel_reason = str(decision_response.get("note") or "Stopped by user.")
                        self.orchestrator.record_decision(
                            state=execution_state,
                            decision_type="step_approval",
                            status="cancelled",
                            risk_level=step_proposal.risk_level,
                            summary=step_proposal.intent,
                            note=cancel_reason,
                        )
                        break
                    execution_state.pending_decision = None
                    self.orchestrator.record_decision(
                        state=execution_state,
                        decision_type="step_approval",
                        status="approved",
                        risk_level=step_proposal.risk_level,
                        summary=step_proposal.intent,
                        note=str(decision_response.get("note") or ""),
                    )

                if self._stop_requested():
                    cancelled = True
                    cancel_reason = self._stop_cancel_reason()
                    challenge_signal = self._build_stop_signal()
                    break

                for action in safe_actions:
                    action.target_scope = action.target_scope or step_proposal.surface_kind
                self._set_live_progress_context(
                    task=task,
                    run_dir=run_dir,
                    step_index=step_index,
                    screenshot_path=screenshot_path,
                    captured_at=captured_at,
                    plan=plan,
                    started_at=started_at,
                    environment=environment_payload,
                    execution_state=execution_state,
                    step_proposal=step_proposal,
                    screen_width=screen_info.width,
                    screen_height=screen_info.height,
                )
                try:
                    phase_started = time.perf_counter()
                    self.executor.execute_many(
                        safe_actions,
                        pause_after_action=self.config.pause_after_action,
                        stop_requested=self._stop_requested,
                    )
                    _record_step_timing(step_timings, "execute", phase_started)
                finally:
                    self._clear_live_progress_context()
                self._raise_if_stop_requested(executed_actions=safe_actions)
                execution_state.app_context["last_agent_action_at"] = time.time()
                execution_state.current_surface_kind = step_proposal.surface_kind
                recoverable_error_count = 0
                phase_started = time.perf_counter()
                captured_at = self._refresh_step_screenshot(screenshot_path) or captured_at
                self._raise_if_stop_requested(executed_actions=safe_actions)
                refreshed_screen_info = getattr(self.perception, "last_screen_info", None) or screen_info
                post_world_model = self._build_world_model(
                    screenshot_path=screenshot_path,
                    screen_info=refreshed_screen_info,
                    step_index=step_index,
                    captured_at=captured_at,
                )
                post_world_model.state_delta = _describe_world_model_delta(world_model, post_world_model)
                post_facts = self.capability_executor.observe(post_world_model)
                post_world_model.facts = post_facts
                execution_state.facts = _merge_facts(execution_state.facts, post_facts)
                _record_step_timing(step_timings, "capture_after", phase_started)
                self._raise_if_stop_requested(executed_actions=safe_actions)
                challenge_signal = detect_human_verification(post_world_model.browser_snapshot)
                if challenge_signal is not None:
                    execution_state.world_model = post_world_model
                    plan = _build_human_handoff_plan(challenge_signal)
                    self._log_execution_state(run_dir=run_dir, execution_state=execution_state)
                    timings_payload = _finalize_step_timings(step_timings, step_started_at)
                    self.logger.log_step(
                        run_dir=run_dir,
                        step_index=step_index,
                        task=task,
                        screenshot_path=screenshot_path,
                        plan=plan,
                        executed_actions=safe_actions,
                        error=None,
                        challenge=challenge_signal.to_dict(),
                        captured_at=captured_at,
                        environment=_build_environment_payload(refreshed_screen_info),
                        state=build_execution_plan_summary(execution_state),
                        world_model=post_world_model.to_dict(),
                        step_proposal=step_proposal.to_dict(),
                        timings=timings_payload,
                    )
                    self._emit_progress(
                        self._build_progress_payload(
                            task=task,
                            run_dir=run_dir,
                            step_index=step_index,
                            screenshot_path=screenshot_path,
                            captured_at=captured_at,
                            plan=plan,
                                executed_actions=safe_actions,
                                error=None,
                                challenge=challenge_signal.to_dict(),
                                started_at=started_at,
                                environment=_build_environment_payload(refreshed_screen_info),
                                execution_state=execution_state,
                                step_proposal=step_proposal,
                                verification=None,
                                timings=timings_payload,
                        )
                    )
                    history.append(challenge_signal.summary)
                    break

                phase_started = time.perf_counter()
                verification = self.capability_executor.verify_step(
                    execution_state=execution_state,
                    step=step_proposal,
                    before=world_model,
                    after=post_world_model,
                )
                self._raise_if_stop_requested(executed_actions=safe_actions)
                execution_state.world_model = post_world_model
                execution_state.last_verification = verification
                execution_state.updated_at = time.time()
                self.orchestrator.record_step_result(
                    state=execution_state,
                    step=step_proposal,
                    verification=verification,
                    world_model=post_world_model,
                )
                _record_step_timing(step_timings, "verify", phase_started)
                current_subgoal.attempts += 1
                subgoal_completed_now = step_proposal.completes_subgoal or _verification_completed_subgoal(verification)

                if verification.status == "success" and subgoal_completed_now:
                    execution_state.last_progress_at = time.time()
                    execution_state.stuck_rounds = 0
                    execution_state.app_context.pop("pending_repair", None)
                    execution_state.app_context.pop("recovery_reason", None)
                    last_step_signature = None
                    repeated_plan_count = 0
                    last_visible_step_signature = None
                    repeated_visible_step_count = 0
                    if step_proposal.target_scope == "task":
                        for subgoal in execution_state.task_graph.subgoals:
                            if subgoal.status != "completed":
                                execution_state.task_graph.mark_completed(
                                    subgoal.id,
                                    evidence=verification.to_dict(),
                                )
                        completed = True
                        execution_state.completed = True
                    else:
                        execution_state.task_graph.mark_completed(current_subgoal.id, evidence=verification.to_dict())
                elif verification.status == "success":
                    execution_state.last_progress_at = time.time()
                    execution_state.stuck_rounds = 0
                    execution_state.app_context.pop("pending_repair", None)
                    execution_state.app_context.pop("recovery_reason", None)
                    last_step_signature = None
                    repeated_plan_count = 0
                    last_visible_step_signature = None
                    repeated_visible_step_count = 0
                    current_subgoal.notes.append("Progress verified, but the subgoal is not complete yet.")
                    current_subgoal.status = "pending"
                elif verification.status == "partial_progress":
                    execution_state.last_progress_at = time.time()
                    execution_state.stuck_rounds = 0
                    execution_state.app_context.pop("pending_repair", None)
                    execution_state.app_context.pop("recovery_reason", None)
                    last_step_signature = None
                    repeated_plan_count = 0
                    last_visible_step_signature = None
                    repeated_visible_step_count = 0
                    current_subgoal.notes.append(verification.message or "Partial progress observed.")
                    current_subgoal.status = "pending"
                else:
                    if step_proposal.capability and step_proposal.capability not in current_subgoal.failed_capabilities:
                        current_subgoal.failed_capabilities.append(step_proposal.capability)
                    current_subgoal.status = "blocked"
                    execution_state.stuck_rounds += 1
                    execution_state.failures.append(
                        {
                            "subgoal_id": current_subgoal.id,
                            "failure_kind": verification.failure_kind,
                            "standard_failure_kind": standardize_failure_kind(verification.failure_kind),
                            "message": verification.message,
                            "step": step_index,
                        }
                    )
                    recovery_mode = _schedule_recovery(
                        execution_state=execution_state,
                        subgoal=current_subgoal,
                        step_proposal=step_proposal,
                        verification=verification,
                        step_index=step_index,
                        repeated_step_signature=(repeated_visible_step_count >= 2 or repeated_plan_count >= 2),
                    )
                    if recovery_mode == "repair":
                        current_subgoal.status = "pending"
                    elif recovery_mode == "replan":
                        current_subgoal.status = "pending"
                        last_step_signature = None
                        repeated_plan_count = 0
                        last_visible_step_signature = None
                        repeated_visible_step_count = 0
                        self._replan_remaining(
                            run_dir=run_dir,
                            execution_state=execution_state,
                            world_model=post_world_model,
                            failure=verification,
                        )

                if execution_state.task_graph.is_complete():
                    completed = True
                    execution_state.completed = True
                    self.orchestrator.mark_complete(execution_state)

                history_entry = _build_step_history_entry(step_proposal, verification, safe_actions)
                history.append(history_entry)
                execution_state.memory = history[-8:]
                phase_started = time.perf_counter()
                self._log_execution_state(run_dir=run_dir, execution_state=execution_state)
                _record_step_timing(step_timings, "persist", phase_started)
                timings_payload = _finalize_step_timings(step_timings, step_started_at)
                self.logger.log_step(
                    run_dir=run_dir,
                    step_index=step_index,
                    task=task,
                    screenshot_path=screenshot_path,
                    plan=plan,
                    executed_actions=safe_actions,
                    error=None if verification.status in {"success", "partial_progress"} else verification.message,
                    challenge=None,
                    captured_at=captured_at,
                    environment=_build_environment_payload(refreshed_screen_info),
                    state=build_execution_plan_summary(execution_state),
                    world_model=post_world_model.to_dict(),
                    step_proposal=step_proposal.to_dict(),
                    verification=verification.to_dict(),
                    timings=timings_payload,
                )
                self._emit_progress(
                    self._build_progress_payload(
                        task=task,
                        run_dir=run_dir,
                        step_index=step_index,
                        screenshot_path=screenshot_path,
                        captured_at=captured_at,
                        plan=plan,
                        executed_actions=safe_actions,
                        error=None if verification.status in {"success", "partial_progress"} else verification.message,
                        challenge=None,
                        started_at=started_at,
                        environment=_build_environment_payload(refreshed_screen_info),
                        execution_state=execution_state,
                        step_proposal=step_proposal,
                        verification=verification,
                        timings=timings_payload,
                    )
                )

                if self._stop_requested():
                    cancelled = True
                    cancel_reason = self._stop_cancel_reason()
                    challenge_signal = self._build_stop_signal()
                    break

                if completed:
                    break
                if not step_proposal.actions and verification.status == "failed":
                    error_message = "Planner returned no executable actions before the task could finish."
                    break
                if verification.status == "failed":
                    if (
                        (repeated_plan_count >= 3 and execution_state.stuck_rounds >= 2)
                        or (repeated_visible_step_count >= 3 and execution_state.stuck_rounds >= 1)
                    ):
                        plan_loop_detected = repeated_plan_count >= 3 and execution_state.stuck_rounds >= 2
                        visible_loop_detected = repeated_visible_step_count >= 3 and execution_state.stuck_rounds >= 1
                        error_message = (
                            f"Subgoal became stuck after repeated failed attempts: {current_subgoal.title}"
                            if plan_loop_detected
                            else execution_loop_error
                        )
                        break
                    if recovery_mode in {"repair", "replan"}:
                        recoverable_error_count += 1
                        continue
                    if self.orchestrator.can_retry_subgoal(state=execution_state, subgoal=current_subgoal):
                        recoverable_error_count += 1
                        current_subgoal.status = "pending"
                        continue
                    if execution_state.stuck_rounds >= 3:
                        error_message = f"Subgoal became stuck after repeated failed attempts: {current_subgoal.title}"
                        break
                    error_message = verification.message or f"Subgoal failed: {current_subgoal.title}"
                    break
                current_subgoal.status = "pending" if not subgoal_completed_now else current_subgoal.status
            except ExecutionCancelled as exc:
                cancelled = True
                cancel_reason = self._stop_cancel_reason(str(exc) or "Stopped by user.")
                challenge_signal = self._build_stop_signal()
                cancelled_at = time.time()
                cancel_plan = _build_cancelled_plan(plan)
                if execution_state is not None:
                    self._log_execution_state(run_dir=run_dir, execution_state=execution_state)
                self.logger.log_step(
                    run_dir=run_dir,
                    step_index=step_index,
                    task=task,
                    screenshot_path=screenshot_path,
                    plan=cancel_plan,
                    executed_actions=list(exc.executed_actions),
                    error=cancel_reason,
                    challenge=None,
                    captured_at=cancelled_at,
                    environment=None,
                    state=build_execution_plan_summary(execution_state) if execution_state is not None else None,
                    world_model=world_model.to_dict() if world_model is not None else None,
                    step_proposal=step_proposal.to_dict() if step_proposal is not None else None,
                    verification=verification.to_dict() if verification is not None else None,
                )
                self._emit_progress(
                    self._build_progress_payload(
                        task=task,
                        run_dir=run_dir,
                        step_index=step_index,
                        screenshot_path=screenshot_path,
                        captured_at=cancelled_at,
                        plan=cancel_plan,
                        executed_actions=list(exc.executed_actions),
                        error=cancel_reason,
                        challenge=None,
                        started_at=started_at,
                        environment=None,
                        execution_state=execution_state,
                        step_proposal=step_proposal,
                        verification=verification,
                    )
                )
                break
            except (PlannerError, SafetyError, ExecutionError, PerceptionError) as exc:
                step_error = str(exc)
                recoverable = self._is_recoverable_error(exc)
                verification = VerificationResult(
                    success=False,
                    status="failed",
                    evidence=[],
                    failure_kind="transient_failure" if recoverable else "blocked_by_ui",
                    message=step_error,
                )
                if execution_state is not None and execution_state.current_subgoal() is not None:
                    current_subgoal = execution_state.current_subgoal()
                    current_subgoal.attempts += 1
                    if step_proposal is not None and step_proposal.capability not in current_subgoal.failed_capabilities:
                        current_subgoal.failed_capabilities.append(step_proposal.capability)
                    current_subgoal.status = "pending"
                    execution_state.last_verification = verification
                    execution_state.stuck_rounds += 1
                    execution_state.failures.append(
                        {
                            "subgoal_id": current_subgoal.id,
                            "failure_kind": verification.failure_kind,
                            "standard_failure_kind": standardize_failure_kind(verification.failure_kind),
                            "message": step_error,
                            "step": step_index,
                        }
                    )
                    recovery_mode = _schedule_recovery(
                        execution_state=execution_state,
                        subgoal=current_subgoal,
                        step_proposal=step_proposal,
                        verification=verification,
                        step_index=step_index,
                        recoverable=recoverable,
                        repeated_step_signature=(repeated_visible_step_count >= 2 or repeated_plan_count >= 2),
                    )
                fallback_plan = PlanResult(
                    status_summary="Execution failed for this step.",
                    done=False,
                    actions=[],
                    current_focus=plan.current_focus if plan else None,
                    reasoning=(
                        "The last attempt failed and the agent should re-evaluate the current UI."
                        if recoverable
                        else None
                    ),
                    remaining_steps=list(plan.remaining_steps) if plan else [],
                    raw_response=None,
                )
                failure_captured_at = time.time()
                if execution_state is not None:
                    self._log_execution_state(run_dir=run_dir, execution_state=execution_state)
                self.logger.log_step(
                    run_dir=run_dir,
                    step_index=step_index,
                    task=task,
                    screenshot_path=screenshot_path,
                    plan=fallback_plan,
                    executed_actions=safe_actions,
                    error=step_error,
                    challenge=None,
                    captured_at=failure_captured_at,
                    environment=None,
                    state=build_execution_plan_summary(execution_state) if execution_state is not None else None,
                    world_model=world_model.to_dict() if world_model is not None else None,
                    step_proposal=step_proposal.to_dict() if step_proposal is not None else None,
                    verification=verification.to_dict(),
                )
                self._emit_progress(
                    self._build_progress_payload(
                        task=task,
                        run_dir=run_dir,
                        step_index=step_index,
                        screenshot_path=screenshot_path,
                        captured_at=failure_captured_at,
                        plan=fallback_plan,
                        executed_actions=safe_actions,
                        error=step_error,
                        challenge=None,
                        started_at=started_at,
                        environment=None,
                        execution_state=execution_state,
                        step_proposal=step_proposal,
                        verification=verification,
                    )
                )
                history.append(
                    _build_error_history_entry(
                        error=step_error,
                        previous_plan=plan,
                        attempted_actions=safe_actions,
                    )
                )
                if execution_state is not None:
                    execution_state.memory = history[-8:]
                if recovery_mode in {"repair", "replan"}:
                    if recovery_mode == "replan" and execution_state is not None and world_model is not None:
                        self._replan_remaining(
                            run_dir=run_dir,
                            execution_state=execution_state,
                            world_model=world_model,
                            failure=verification,
                        )
                    recoverable_error_count += 1
                    continue
                if (
                    recoverable
                    and self.config.replan_on_recoverable_error
                    and recoverable_error_count < max(0, int(self.config.recoverable_error_retry_limit))
                ):
                    recoverable_error_count += 1
                    continue
                error_message = step_error
                break

        finished_at = time.time()
        if execution_state is not None:
            execution_state.completed = completed
            execution_state.updated_at = finished_at
            if completed:
                self.orchestrator.mark_complete(execution_state)
                try:
                    recipe = self.recipe_memory.record_success(execution_state)
                    if recipe is not None:
                        execution_state.app_context["learned_recipe"] = recipe.to_dict()
                except Exception:
                    pass
            self._log_execution_state(run_dir=run_dir, execution_state=execution_state)
        self.logger.log_summary(
            run_dir=run_dir,
            task=task,
            completed=completed,
            steps=step_count,
            dry_run=self.config.dry_run,
            planner_mode=self.config.planner_mode,
            error=error_message,
            cancelled=cancelled,
            cancel_reason=cancel_reason,
            requires_human=challenge_signal is not None,
            interruption_kind=challenge_signal.kind if challenge_signal else None,
            interruption_reason=challenge_signal.detail if challenge_signal else None,
            started_at=started_at,
            finished_at=finished_at,
        )
        result = AgentRunResult(
            task=task,
            completed=completed,
            steps=step_count,
            run_dir=run_dir,
            started_at=started_at,
            finished_at=finished_at,
            error=error_message,
            cancelled=cancelled,
            cancel_reason=cancel_reason,
            requires_human=challenge_signal is not None,
            interruption_kind=challenge_signal.kind if challenge_signal else None,
            interruption_reason=challenge_signal.detail if challenge_signal else None,
        )
        self._active_run_deadline = previous_deadline
        self._active_stop_reason = previous_stop_reason
        if hasattr(self.executor, "set_run_stop_requested"):
            self.executor.set_run_stop_requested(previous_executor_stop_requested)
        return result

    def _refresh_step_screenshot(self, screenshot_path: Path) -> float | None:
        try:
            self.perception.capture(screenshot_path)
            return time.time()
        except PerceptionError:
            return None

    def _build_world_model(
        self,
        *,
        screenshot_path: Path,
        screen_info,
        step_index: int,
        captured_at: float,
    ) -> WorldModel:
        environment = getattr(screen_info, "effective_environment", None) or getattr(screen_info, "environment", None)
        foreground = getattr(environment, "foreground_window", None) if environment is not None else None
        active_window_title = getattr(foreground, "title", None)
        foreground_window_handle = getattr(foreground, "handle", None)
        browser_snapshot = self.executor.browser_snapshot()
        browser_observation = dict(browser_snapshot) if isinstance(browser_snapshot, dict) else None
        mock_state = getattr(self.executor, "state", None)
        active_app = _infer_active_app(
            active_window_title=active_window_title,
            browser_snapshot=browser_snapshot,
        )
        clipboard_text = None
        selection_text = None
        current_buffer_text = None
        last_interaction_text = None
        if mock_state is not None and (self.config.dry_run or isinstance(self.executor, MockExecutor)):
            active_app = getattr(mock_state, "active_app", None) or active_app
            active_window_title = _mock_window_title(mock_state) or active_window_title
            clipboard_text = getattr(mock_state, "clipboard_text", None)
            selection_text = getattr(mock_state, "last_extracted_text", None)
            if active_app:
                current_buffer_text = getattr(mock_state, "text_buffers", {}).get(active_app)
            browser_clicks = list(getattr(mock_state, "browser_dom_clicks", []) or [])
            if browser_clicks:
                last_interaction_text = str(browser_clicks[-1]).strip() or None
        else:
            if not active_window_title and mock_state is not None:
                active_window_title = _mock_window_title(mock_state)
            if active_app is None and mock_state is not None:
                active_app = getattr(mock_state, "active_app", None)
            if mock_state is not None:
                selection_text = getattr(mock_state, "last_extracted_text", None)
                if active_app:
                    current_buffer_text = getattr(mock_state, "text_buffers", {}).get(active_app)
                browser_clicks = list(getattr(mock_state, "browser_dom_clicks", []) or [])
                if browser_clicks:
                    last_interaction_text = str(browser_clicks[-1]).strip() or None
        if not selection_text and current_buffer_text:
            selection_text = current_buffer_text
        visible_windows = [item.to_dict() for item in getattr(environment, "visible_windows", [])] if environment else []
        downloads = []
        if isinstance(browser_snapshot, dict) and isinstance(browser_snapshot.get("downloads"), list):
            downloads = [dict(item) for item in browser_snapshot.get("downloads", []) if isinstance(item, dict)]
        structured_sources: list[str] = []
        if browser_snapshot:
            structured_sources.append("browser_dom")
        if environment is not None:
            structured_sources.append("windows_env")
        if clipboard_text:
            structured_sources.append("clipboard")
        fact_sources = list(structured_sources)
        fact_sources.append("screenshot")
        dom_available = bool(browser_snapshot and any(str(browser_snapshot.get(key) or "").strip() for key in ("url", "title", "text")))
        uia_available = bool(active_window_title and active_app not in {"browser"})
        user_session = capture_user_desktop_session(environment=environment, focused_control=None)
        surface_kind = choose_surface_kind(
            config=self.config,
            active_app=active_app,
            browser_snapshot=browser_snapshot,
            goal_type=None,
        )
        anchor_candidates = _collect_anchor_candidates(
            active_window_title=active_window_title,
            browser_snapshot=browser_snapshot,
            visible_windows=visible_windows,
            selection_text=selection_text or current_buffer_text or last_interaction_text,
        )
        if last_interaction_text:
            cleaned_interaction = " ".join(str(last_interaction_text).split()).strip()
            if cleaned_interaction and cleaned_interaction not in anchor_candidates:
                anchor_candidates.append(cleaned_interaction)
        world_model = WorldModel(
            screenshot_path=screenshot_path,
            environment=environment,
            browser_snapshot=browser_snapshot,
            downloads=downloads,
            visible_windows=visible_windows,
            fact_sources=fact_sources,
            active_app=active_app,
            active_window_title=active_window_title,
            target_window_title=active_window_title,
            foreground_window_handle=foreground_window_handle,
            clipboard_text=clipboard_text,
            focused_control=None,
            surface_kind=surface_kind,
            surface_id=user_session.session_id if surface_kind == "current_user_desktop" else surface_kind,
            session_id=user_session.session_id,
            dom_available=dom_available,
            uia_available=uia_available,
            structured_sources=structured_sources,
            visual_sources=["screenshot"],
            anchor_candidates=anchor_candidates,
            selection_text=selection_text,
            file_observations=_infer_file_observations(mock_state, browser_snapshot),
            browser_observation=browser_observation,
            user_desktop_session=user_session,
            step_index=step_index,
            captured_at=captured_at,
        )
        driver = self.driver_registry.detect(world_model)
        world_model.active_driver = driver.name if driver is not None else None
        if world_model.active_driver:
            world_model.structured_sources.append(f"driver:{world_model.active_driver}")
        return world_model

    def _initialize_execution_state(self, *, task: str, run_dir: Path, world_model: WorldModel) -> ExecutionState:
        return self.orchestrator.initialize_state(task=task, run_id=run_dir.name, world_model=world_model)

    def _log_execution_state(self, *, run_dir: Path, execution_state: ExecutionState) -> None:
        summary = build_execution_plan_summary(execution_state)
        self.logger.log_execution_state(
            run_dir=run_dir,
            task_graph=execution_state.task_graph.to_dict(),
            state=summary,
            facts=[item.to_dict() for item in execution_state.facts],
        )

    def _request_plan_review(
        self,
        *,
        execution_state: ExecutionState,
        run_dir: Path,
        step_index: int,
        screenshot_path: Path,
        captured_at: float,
        environment_payload: dict[str, Any] | None,
        world_model: WorldModel,
        decision_type: str = "plan_review",
    ) -> dict[str, Any]:
        risk_level = _task_graph_risk_level(execution_state)
        is_stage_review = decision_type == "stage_review"
        pending = PendingDecision(
            id=f"{decision_type}-{run_dir.name}",
            summary=(
                f"Review the replanned stage before execution: {execution_state.task}"
                if is_stage_review
                else f"Review the task plan before execution: {execution_state.task}"
            ),
            reason=_build_plan_review_reason(execution_state, decision_type=decision_type),
            risk_level=risk_level,
            decision_type=decision_type,
            actions=[],
        )
        execution_state.pending_decision = pending
        execution_state.app_context["stage_review_status" if is_stage_review else "plan_review_status"] = "pending"
        execution_state.orchestration_phase = "stage_review" if is_stage_review else "plan_review"
        execution_state.updated_at = time.time()
        plan = PlanResult(
            status_summary=(
                "Review the replanned stage before execution."
                if is_stage_review
                else "Review the generated task plan before execution."
            ),
            done=False,
            actions=[],
            current_focus=execution_state.current_subgoal().title if execution_state.current_subgoal() else None,
            reasoning=pending.reason,
            remaining_steps=[item.title for item in execution_state.task_graph.subgoals if item.status != "completed"],
        )
        self._log_execution_state(run_dir=run_dir, execution_state=execution_state)
        self._emit_progress(
            self._build_progress_payload(
                task=execution_state.task,
                run_dir=run_dir,
                step_index=step_index,
                screenshot_path=screenshot_path,
                captured_at=captured_at,
                plan=plan,
                executed_actions=[],
                error=None,
                challenge=None,
                started_at=execution_state.started_at,
                environment=environment_payload,
                execution_state=execution_state,
                step_proposal=None,
                verification=None,
            )
        )
        if self.decision_callback is None:
            if self.config.dry_run:
                return {"decision": "approve", "note": "Auto-approved in dry-run mode."}
            return {"decision": "reject", "note": "Plan review required but no decision handler is configured."}
        response = self.decision_callback(
            {
                "run_id": run_dir.name,
                "task": execution_state.task,
                "step": step_index,
                "pending_decision": pending.to_dict(),
                "state": build_execution_plan_summary(execution_state),
                "world_model": world_model.to_dict(),
            }
        )
        return dict(response or {"decision": "reject"})

    def _request_decision(
        self,
        *,
        execution_state: ExecutionState,
        step_proposal: StepProposal,
        plan: PlanResult,
        run_dir: Path,
        step_index: int,
        screenshot_path: Path,
        captured_at: float,
        environment_payload: dict[str, Any] | None,
        world_model: WorldModel,
    ) -> dict[str, Any]:
        current_subgoal = execution_state.current_subgoal()
        if current_subgoal is None:
            return {"decision": "approve"}
        pending = self.capability_executor.build_pending_decision(step=step_proposal, subgoal=current_subgoal)
        execution_state.pending_decision = pending
        execution_state.updated_at = time.time()
        self._log_execution_state(run_dir=run_dir, execution_state=execution_state)
        self._emit_progress(
            self._build_progress_payload(
                task=execution_state.task,
                run_dir=run_dir,
                step_index=step_index,
                screenshot_path=screenshot_path,
                captured_at=captured_at,
                plan=plan,
                executed_actions=[],
                error=None,
                challenge=None,
                started_at=execution_state.started_at,
                environment=environment_payload,
                execution_state=execution_state,
                step_proposal=step_proposal,
                verification=None,
            )
        )
        if self.decision_callback is None:
            if self.config.dry_run:
                return {"decision": "approve", "note": "Auto-approved in dry-run mode."}
            return {"decision": "reject", "note": "Approval required but no decision handler is configured."}
        response = self.decision_callback(
            {
                "run_id": run_dir.name,
                "task": execution_state.task,
                "step": step_index,
                "pending_decision": pending.to_dict(),
                "step_proposal": step_proposal.to_dict(),
                "state": build_execution_plan_summary(execution_state),
                "world_model": world_model.to_dict(),
            }
        )
        return dict(response or {"decision": "reject"})

    def _replan_remaining(
        self,
        *,
        run_dir: Path,
        execution_state: ExecutionState,
        world_model: WorldModel,
        failure: VerificationResult,
    ) -> None:
        try:
            if self.orchestrator.replan_remaining(
                state=execution_state,
                world_model=world_model,
                failure=failure,
            ):
                self._log_execution_state(run_dir=run_dir, execution_state=execution_state)
        except Exception:
            return

    def _build_progress_payload(
        self,
        *,
        task: str,
        run_dir: Path,
        step_index: int,
        screenshot_path: Path,
        captured_at: float,
        plan: PlanResult,
        executed_actions,
        error: str | None,
        challenge: dict[str, Any] | None,
        started_at: float,
        environment: dict[str, Any] | None,
        execution_state: ExecutionState | None,
        step_proposal: StepProposal | None,
        verification: VerificationResult | None,
        live_pointer: dict[str, Any] | None = None,
        live_pointer_trail: list[dict[str, Any]] | None = None,
        live_action: dict[str, Any] | None = None,
        timings: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        state_summary = build_execution_plan_summary(execution_state) if execution_state is not None else None
        return {
            "task": task,
            "run_dir": str(run_dir),
            "run_id": run_dir.name,
            "steps": step_index,
            "latest_screenshot": screenshot_path.name,
            "latest_summary": plan.status_summary,
            "latest_actions": [item.to_dict() for item in executed_actions],
            "captured_at": captured_at,
            "environment": environment,
            "error": error,
            "challenge": challenge,
            "started_at": started_at,
            "execution_state": state_summary,
            "intent": state_summary.get("intent") if isinstance(state_summary, dict) else None,
            "orchestration_phase": state_summary.get("orchestration_phase") if isinstance(state_summary, dict) else None,
            "active_specialist": state_summary.get("active_specialist") if isinstance(state_summary, dict) else None,
            "workspace_summary": state_summary.get("workspace_summary") if isinstance(state_summary, dict) else None,
            "stage_review_status": state_summary.get("stage_review_status") if isinstance(state_summary, dict) else None,
            "last_replan_reason": state_summary.get("last_replan_reason") if isinstance(state_summary, dict) else None,
            "current_goal": state_summary.get("current_goal") if isinstance(state_summary, dict) else None,
            "chosen_capability": state_summary.get("chosen_capability") if isinstance(state_summary, dict) else None,
            "verification_status": state_summary.get("verification_status") if isinstance(state_summary, dict) else None,
            "recovery_reason": state_summary.get("recovery_reason") if isinstance(state_summary, dict) else None,
            "step_proposal": step_proposal.to_dict() if step_proposal is not None else None,
            "verification": verification.to_dict() if verification is not None else None,
            "live_pointer": dict(live_pointer) if isinstance(live_pointer, dict) else None,
            "live_pointer_trail": [dict(item) for item in (live_pointer_trail or []) if isinstance(item, dict)],
            "live_action": dict(live_action) if isinstance(live_action, dict) else None,
            "latest_timings": dict(timings) if isinstance(timings, dict) else None,
        }

    def _emit_progress(self, payload: dict[str, Any]) -> None:
        if self.progress_callback is None:
            return
        try:
            self.progress_callback(payload)
        except Exception:
            return

    def _set_live_progress_context(
        self,
        *,
        task: str,
        run_dir: Path,
        step_index: int,
        screenshot_path: Path,
        captured_at: float,
        plan: PlanResult,
        started_at: float,
        environment: dict[str, Any] | None,
        execution_state: ExecutionState | None,
        step_proposal: StepProposal | None,
        screen_width: int,
        screen_height: int,
    ) -> None:
        self._live_progress_context = {
            "task": task,
            "run_dir": run_dir,
            "step_index": step_index,
            "screenshot_path": screenshot_path,
            "captured_at": captured_at,
            "plan": plan,
            "started_at": started_at,
            "environment": environment,
            "execution_state": execution_state,
            "step_proposal": step_proposal,
            "screen_width": max(1, int(screen_width or 1)),
            "screen_height": max(1, int(screen_height or 1)),
        }
        self._live_pointer_trail = []

    def _clear_live_progress_context(self) -> None:
        self._live_progress_context = None
        self._live_pointer_trail = []

    def _handle_action_progress(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict) or payload.get("event") != "cursor_motion":
            return
        context = self._live_progress_context
        if context is None:
            return
        if payload.get("clear"):
            self._live_pointer_trail = []
            self._emit_progress(
                self._build_progress_payload(
                    task=str(context["task"]),
                    run_dir=context["run_dir"],
                    step_index=int(context["step_index"]),
                    screenshot_path=context["screenshot_path"],
                    captured_at=float(context["captured_at"]),
                    plan=context["plan"],
                    executed_actions=[],
                    error=None,
                    challenge=None,
                    started_at=float(context["started_at"]),
                    environment=context["environment"],
                    execution_state=context["execution_state"],
                    step_proposal=context["step_proposal"],
                    verification=None,
                    live_pointer=None,
                    live_pointer_trail=[],
                    live_action=None,
                )
            )
            return

        pointer = _build_live_pointer_payload(
            payload=payload,
            screen_width=int(context["screen_width"]),
            screen_height=int(context["screen_height"]),
        )
        if pointer is None:
            return
        trail_point = {
            "norm_x": pointer["norm_x"],
            "norm_y": pointer["norm_y"],
            "updated_at": pointer["updated_at"],
        }
        last_point = self._live_pointer_trail[-1] if self._live_pointer_trail else None
        if last_point != trail_point:
            self._live_pointer_trail.append(trail_point)
        self._live_pointer_trail = self._live_pointer_trail[-10:]
        live_action = payload.get("live_action") if isinstance(payload.get("live_action"), dict) else None
        self._emit_progress(
            self._build_progress_payload(
                task=str(context["task"]),
                run_dir=context["run_dir"],
                step_index=int(context["step_index"]),
                screenshot_path=context["screenshot_path"],
                captured_at=float(context["captured_at"]),
                plan=context["plan"],
                executed_actions=[],
                error=None,
                challenge=None,
                started_at=float(context["started_at"]),
                environment=context["environment"],
                execution_state=context["execution_state"],
                step_proposal=context["step_proposal"],
                verification=None,
                live_pointer=pointer,
                live_pointer_trail=self._live_pointer_trail,
                live_action=live_action,
            )
        )

    def _stop_requested(self) -> bool:
        if self._active_run_deadline is not None and time.time() >= self._active_run_deadline:
            self._active_stop_reason = "time_limit"
            return True
        if self.stop_requested is None:
            return False
        try:
            requested = bool(self.stop_requested())
        except Exception:
            return False
        if requested:
            self._active_stop_reason = "user"
        return requested

    def _raise_if_stop_requested(self, *, executed_actions: list[Action] | None = None) -> None:
        if self._stop_requested():
            raise ExecutionCancelled(executed_actions=list(executed_actions or []))

    def _stop_cancel_reason(self, fallback: str = "Stopped by user.") -> str:
        if self._active_stop_reason == "time_limit":
            return "Run time limit reached."
        return fallback

    def _build_stop_signal(self) -> HumanVerificationSignal | None:
        if self._active_stop_reason != "time_limit":
            return None
        return HumanVerificationSignal(
            kind="time_limit",
            summary="Run time limit reached. Pause automation and resume when ready.",
            detail=(
                "The configured maximum run duration elapsed, so Aoryn stopped before starting more desktop "
                "automation. Reopen this run from history to resume from the saved state."
            ),
            title=None,
        )

    @staticmethod
    def _is_recoverable_error(exc: Exception) -> bool:
        if isinstance(exc, ExecutionError):
            lowered = str(exc).lower()
            recoverable_fragments = (
                "could not focus window",
                "could not minimize window",
                "could not find target window",
                "could not close window",
                "could not move or resize window",
                "timed out waiting for window",
                "failed to open browser target",
            )
            return any(fragment in lowered for fragment in recoverable_fragments)
        return False


def _build_human_handoff_plan(signal: HumanVerificationSignal) -> PlanResult:
    return PlanResult(
        status_summary=signal.summary,
        done=False,
        actions=[],
        raw_response=None,
    )


def _build_cancelled_plan(previous_plan: PlanResult | None) -> PlanResult:
    return PlanResult(
        status_summary="Task stopped by user.",
        done=False,
        actions=[],
        current_focus=previous_plan.current_focus if previous_plan else None,
        reasoning="Execution stopped after the user pressed Stop.",
        remaining_steps=list(previous_plan.remaining_steps) if previous_plan else [],
        raw_response=None,
    )


def _build_plan_signature(plan: PlanResult, actions) -> str:
    payload = {
        "actions": [action.to_dict() for action in actions],
        "current_focus": plan.current_focus or plan.status_summary,
        "done": plan.done,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _build_step_signature(subgoal_id: str, step: StepProposal, actions: list[Action]) -> str:
    payload = {
        "subgoal_id": subgoal_id,
        "actions": [action.to_dict() for action in actions],
        "intent": step.intent,
        "completes_subgoal": step.completes_subgoal,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _build_visible_step_signature(subgoal_id: str, step: StepProposal, actions: list[Action]) -> str:
    payload = {
        "subgoal_id": subgoal_id,
        "capability": step.capability,
        "focus": (step.current_focus or step.intent).strip().lower(),
        "actions": [_build_visible_action_signature(action) for action in actions],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _build_visible_action_signature(action: Action) -> dict[str, str]:
    target = (
        getattr(action, "selector", None)
        or getattr(action, "text", None)
        or getattr(action, "url", None)
        or getattr(action, "title", None)
        or getattr(action, "app", None)
        or getattr(action, "key", None)
        or "+".join(getattr(action, "keys", []) or [])
        or getattr(action, "recipe", None)
        or getattr(action, "target_scope", None)
        or ""
    )
    normalized_target = str(target or "").strip().lower()
    if len(normalized_target) > 120:
        normalized_target = normalized_target[:120]
    return {
        "type": action.type,
        "target": normalized_target,
    }


def _build_step_history_entry(step: StepProposal, verification: VerificationResult, executed_actions: list[Action]) -> str:
    plan = step.to_plan_result(done=step.completes_subgoal)
    lines = [f"Summary: {plan.status_summary}"]
    lines.append(f"Capability: {step.capability}")
    if plan.current_focus:
        lines.append(f"Current focus: {plan.current_focus}")
    if plan.reasoning:
        lines.append(f"Reasoning: {plan.reasoning}")
    if executed_actions:
        action_notes = ", ".join(_summarize_action(action) for action in executed_actions)
        lines.append(f"Executed actions: {action_notes}")
    lines.append(f"Verification: {verification.status}")
    if verification.message:
        lines.append(f"Verification detail: {verification.message}")
    lines.append(f"Task complete in this round: {'yes' if step.completes_subgoal and verification.status == 'success' else 'no'}")
    return "\n".join(lines)


def _build_history_entry(plan: PlanResult, executed_actions) -> str:
    lines = [f"Summary: {plan.status_summary}"]
    if plan.current_focus:
        lines.append(f"Current focus: {plan.current_focus}")
    if plan.reasoning:
        lines.append(f"Reasoning: {plan.reasoning}")
    if plan.remaining_steps:
        lines.append(f"Remaining steps: {' -> '.join(plan.remaining_steps)}")
    if executed_actions:
        action_notes = ", ".join(_summarize_action(action) for action in executed_actions)
        lines.append(f"Executed actions: {action_notes}")
    lines.append(f"Task complete in this round: {'yes' if plan.done else 'no'}")
    return "\n".join(lines)


def _summarize_action(action) -> str:
    if action.type == "launch_app":
        return f"launch_app({action.app})"
    if action.type == "open_app_if_needed":
        return f"open_app_if_needed({action.app})"
    if action.type == "browser_open":
        return f"browser_open({action.text})"
    if action.type == "browser_search":
        return f"browser_search({action.text})"
    if action.type == "browser_dom_click":
        target = action.selector or action.text
        return f"browser_dom_click({target})"
    if action.type == "browser_dom_fill":
        target = action.selector or action.target_scope or "field"
        return f"browser_dom_fill({target})"
    if action.type == "browser_dom_select":
        target = action.selector or action.target_scope or "field"
        return f"browser_dom_select({target})"
    if action.type == "browser_dom_wait":
        target = action.selector or action.text
        return f"browser_dom_wait({target})"
    if action.type == "browser_dom_extract":
        target = action.selector or action.text
        return f"browser_dom_extract({target})"
    if action.type == "clipboard_copy":
        return "clipboard_copy()"
    if action.type == "clipboard_paste":
        return "clipboard_paste()"
    if action.type == "drag":
        return f"drag({action.x},{action.y}->{action.end_x},{action.end_y})"
    if action.type in {"uia_invoke", "uia_set_value", "uia_select", "uia_expand"}:
        target = action.selector or action.text or action.title
        return f"{action.type}({target})"
    if action.type == "shell_recipe_request":
        return f"shell_recipe_request({action.recipe})"
    if action.type == "type":
        text = (action.text or "").strip()
        if len(text) > 40:
            text = text[:37] + "..."
        return f"type({text})"
    if action.type == "hotkey":
        return f"hotkey({'+'.join(action.keys)})"
    if action.type == "press":
        return f"press({action.key})"
    if action.type == "wait":
        return f"wait({action.seconds}s)"
    if action.type == "scroll":
        return f"scroll({action.amount})"
    if action.type == "click":
        return f"click({action.x},{action.y})"
    if action.type == "relative_click":
        target = action.title or action.text
        return f"relative_click({target}@{action.relative_x:.3f},{action.relative_y:.3f})"
    if action.type in {"focus_window", "minimize_window", "close_window", "dismiss_popup", "maximize_window", "wait_for_window"}:
        target = action.title or action.text
        return f"{action.type}({target})"
    if action.type == "move_resize_window":
        target = action.title or action.text
        return f"move_resize_window({target}@{action.x},{action.y},{action.width}x{action.height})"
    return action.type


def _build_error_history_entry(
    *,
    error: str,
    previous_plan: PlanResult | None,
    attempted_actions,
) -> str:
    lines = ["Summary: The previous step failed and needs recovery."]
    if previous_plan and previous_plan.current_focus:
        lines.append(f"Current focus: {previous_plan.current_focus}")
    if attempted_actions:
        action_notes = ", ".join(_summarize_action(action) for action in attempted_actions)
        lines.append(f"Attempted actions: {action_notes}")
    lines.append(f"Error: {error}")
    lines.append("Task complete in this round: no")
    return "\n".join(lines)


def _plan_review_required(config: AgentConfig, execution_state: ExecutionState) -> bool:
    if execution_state.pending_decision is not None:
        pending_type = str(getattr(execution_state.pending_decision, "decision_type", "") or "").strip().lower()
        if pending_type != "plan_review":
            return False
    status = str(execution_state.app_context.get("plan_review_status") or "").strip().lower()
    if status in {"approved", "rejected"}:
        return False
    policy = str(getattr(config, "plan_review_policy", "low_risk_auto") or "low_risk_auto").strip().lower()
    if policy == "never":
        return False
    current_subgoal = execution_state.current_subgoal()
    if current_subgoal is not None and current_subgoal.goal_type == "clarify":
        return False
    if policy == "always":
        return True
    return _task_graph_risk_level(execution_state) != "low" or _task_graph_is_ambiguous(execution_state)


def _task_graph_risk_level(execution_state: ExecutionState) -> str:
    return task_graph_risk_level(execution_state.task_graph)


def _task_graph_is_ambiguous(execution_state: ExecutionState) -> bool:
    return task_graph_is_ambiguous(execution_state.task_graph)


def _build_plan_review_reason(execution_state: ExecutionState, *, decision_type: str = "plan_review") -> str:
    if decision_type == "stage_review":
        configured_reason = str(execution_state.app_context.get("stage_review_reason") or "").strip()
        if configured_reason:
            return configured_reason
        return "The remaining task plan changed and needs approval before Aoryn continues."
    risk_level = _task_graph_risk_level(execution_state)
    if _task_graph_is_ambiguous(execution_state):
        return "The generated plan needs review because the task has ambiguous or model-assisted planning assumptions."
    if risk_level != "low":
        return f"The generated plan includes {risk_level}-risk work and needs approval before Aoryn acts."
    return "The generated plan is configured to require approval before execution."


def _count_subgoal_recovery(execution_state: ExecutionState, subgoal_id: str, mode: str) -> int:
    count = 0
    for item in execution_state.repair_history:
        if str(item.get("subgoal_id")) == subgoal_id and str(item.get("mode")) == mode:
            count += 1
    return count


def _schedule_recovery(
    *,
    execution_state: ExecutionState,
    subgoal: Subgoal,
    step_proposal: StepProposal | None,
    verification: VerificationResult,
    step_index: int,
    recoverable: bool = False,
    repeated_step_signature: bool = False,
) -> str | None:
    standard_kind = standardize_failure_kind(verification.failure_kind)
    if verification.failure_kind in {"requires_auth", "requires_human", "approval_rejected"}:
        execution_state.app_context.pop("pending_repair", None)
        execution_state.app_context["recovery_reason"] = verification.message or verification.failure_kind
        execution_state.app_context["standard_recovery_kind"] = standard_kind
        return None

    repair_attempts = _count_subgoal_recovery(execution_state, subgoal.id, "repair")
    replan_attempts = _count_subgoal_recovery(execution_state, subgoal.id, "replan")
    capability_name = step_proposal.capability if step_proposal is not None else None

    # When the planner keeps proposing the same action and it keeps failing
    # despite repair attempts, give the next repair round a chance to try a
    # different capability — repairing with an unchanged blocked-capability
    # list will just produce the same plan again.
    if repeated_step_signature and repair_attempts >= 1 and subgoal.failed_capabilities:
        subgoal.failed_capabilities.clear()
        execution_state.app_context["recovery_escalation"] = "repeated_step_capability_reset"

    if repair_attempts < 2:
        execution_state.app_context["pending_repair"] = {
            "subgoal_id": subgoal.id,
            "failure_kind": verification.failure_kind,
            "standard_failure_kind": standard_kind,
            "capability": capability_name,
            "recoverable": recoverable,
            "step_index": step_index,
            "message": verification.message,
        }
        execution_state.app_context["recovery_reason"] = verification.message or verification.failure_kind
        execution_state.app_context["standard_recovery_kind"] = standard_kind
        execution_state.repair_history.append(
            {
                "subgoal_id": subgoal.id,
                "mode": "repair",
                "failure_kind": verification.failure_kind,
                "standard_failure_kind": standard_kind,
                "capability": capability_name,
                "message": verification.message,
                "step": step_index,
                "created_at": time.time(),
            }
        )
        return "repair"

    if replan_attempts < 1:
        execution_state.app_context.pop("pending_repair", None)
        execution_state.app_context["recovery_reason"] = verification.message or verification.failure_kind
        execution_state.app_context["standard_recovery_kind"] = standard_kind
        subgoal.failed_capabilities.clear()
        execution_state.repair_history.append(
            {
                "subgoal_id": subgoal.id,
                "mode": "replan",
                "failure_kind": verification.failure_kind,
                "standard_failure_kind": standard_kind,
                "capability": capability_name,
                "message": verification.message,
                "step": step_index,
                "created_at": time.time(),
            }
        )
        return "replan"

    execution_state.app_context.pop("pending_repair", None)
    execution_state.app_context["recovery_reason"] = verification.message or verification.failure_kind
    execution_state.app_context["standard_recovery_kind"] = standard_kind
    return None


def _verification_completed_subgoal(verification: VerificationResult | None) -> bool:
    if verification is None or verification.status != "success":
        return False
    for item in verification.evidence:
        if str(item.get("scope")) == "subgoal_completion" and bool(item.get("satisfied")):
            return True
    return False


def _collect_anchor_candidates(
    *,
    active_window_title: str | None,
    browser_snapshot: dict[str, Any] | None,
    visible_windows: list[dict[str, Any]],
    selection_text: str | None,
) -> list[str]:
    anchors: list[str] = []
    if active_window_title:
        anchors.append(str(active_window_title))
    if browser_snapshot:
        for key in ("title", "url", "text"):
            value = str(browser_snapshot.get(key) or "").strip()
            if value:
                anchors.append(value[:200])
    for item in visible_windows[:6]:
        title = str(item.get("title") or "").strip()
        if title:
            anchors.append(title)
    if selection_text:
        anchors.append(str(selection_text)[:200])
    deduped: list[str] = []
    seen: set[str] = set()
    for item in anchors:
        cleaned = " ".join(str(item).split()).strip()
        lowered = cleaned.lower()
        if not cleaned or lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(cleaned)
    return deduped[:10]


def _describe_world_model_delta(before: WorldModel, after: WorldModel) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    field_pairs = (
        ("active_app", before.active_app, after.active_app),
        ("active_window_title", before.active_window_title, after.active_window_title),
        ("clipboard_text", before.clipboard_text, after.clipboard_text),
        ("selection_text", before.selection_text, after.selection_text),
    )
    for key, old_value, new_value in field_pairs:
        old_text = _compact_text(old_value)
        new_text = _compact_text(new_value)
        if old_text != new_text:
            changes[key] = {"before": old_text, "after": new_text}

    before_browser = before.browser_snapshot or {}
    after_browser = after.browser_snapshot or {}
    for key in ("url", "title", "text"):
        old_text = _compact_text(before_browser.get(key))
        new_text = _compact_text(after_browser.get(key))
        if old_text != new_text:
            changes[f"browser_{key}"] = {
                "before": old_text[:240],
                "after": new_text[:240],
            }
    if len(before.file_observations) != len(after.file_observations):
        changes["file_observations"] = {
            "before": len(before.file_observations),
            "after": len(after.file_observations),
        }
    if len(before.downloads) != len(after.downloads):
        changes["downloads"] = {"before": len(before.downloads), "after": len(after.downloads)}
    return changes


def _compact_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _infer_file_observations(mock_state, browser_snapshot: dict[str, Any] | None) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    if isinstance(browser_snapshot, dict):
        for item in browser_snapshot.get("downloads", []) or []:
            if isinstance(item, dict):
                observations.append(dict(item))
    for attr_name in ("saved_paths", "downloaded_files"):
        values = getattr(mock_state, attr_name, None) if mock_state is not None else None
        if isinstance(values, list):
            for item in values:
                text = str(item).strip()
                if text:
                    observations.append({"path": text})
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in observations:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _merge_facts(existing, observed):
    merged = list(existing or [])
    seen = {(item.source, item.key, item.value) for item in merged}
    for fact in observed or []:
        key = (fact.source, fact.key, fact.value)
        if key in seen:
            continue
        seen.add(key)
        merged.append(fact)
    return merged


def _infer_active_app(*, active_window_title: str | None, browser_snapshot: dict[str, Any] | None) -> str | None:
    title = " ".join(str(active_window_title or "").strip().lower().split())
    if browser_snapshot and str(browser_snapshot.get("url") or "").strip():
        return "browser"
    if not title:
        return None
    if "visual studio code" in title or "cursor" in title or "vscode" in title:
        return "vscode"
    if "excel" in title:
        return "excel"
    if "powerpoint" in title:
        return "powerpoint"
    if "word" in title:
        return "word"
    if "notepad" in title or "记事本" in title:
        return "notepad"
    if "calculator" in title or "计算器" in title:
        return "calculator"
    if "explorer" in title or "file explorer" in title or "资源管理器" in title:
        return "explorer"
    return title.split(" - ")[-1] if title else None


def _mock_window_title(mock_state) -> str | None:
    active_app = getattr(mock_state, "active_app", None)
    if not active_app:
        return None
    mapping = {
        "browser": "Microsoft Edge",
        "notepad": "Notepad",
        "calculator": "Calculator",
        "explorer": "File Explorer",
        "vscode": "Visual Studio Code",
    }
    return mapping.get(str(active_app).lower(), str(active_app))


def _build_environment_payload(screen_info) -> dict[str, Any] | None:
    effective = getattr(screen_info, "effective_environment", None) or getattr(screen_info, "environment", None)
    detected = getattr(screen_info, "detected_environment", None)
    if effective is None and detected is None:
        return None
    return {
        "effective": effective.to_dict() if effective is not None else None,
        "detected": detected.to_dict() if detected is not None else None,
    }


def _record_step_timing(timings: dict[str, float], key: str, started_at: float) -> None:
    timings[key] = round(max(0.0, time.perf_counter() - started_at), 4)


def _resolve_run_deadline(started_at: float, max_run_seconds: float | None) -> float | None:
    if max_run_seconds is None:
        return None
    try:
        seconds = float(max_run_seconds)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return float(started_at) + seconds


def _finalize_step_timings(timings: dict[str, float], step_started_at: float) -> dict[str, float]:
    payload = dict(timings)
    payload["total"] = round(max(0.0, time.perf_counter() - step_started_at), 4)
    return payload


def build_agent(
    config: AgentConfig,
    *,
    stop_requested: Callable[[], bool] | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    decision_callback: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
) -> DesktopAgent:
    planner = build_planner(config)
    subgoal_planner = SubgoalPlanner(config, base_planner=planner)
    driver_registry = build_driver_registry()
    if config.dry_run:
        executor: BaseExecutor = MockExecutor(config)
        perception = MockCapture(config=config)
    else:
        executor = RealDesktopExecutor(config)
        perception = ScreenCapture(config=config)
    logger = RunLogger(config.run_root)
    guard = ActionGuard(config)
    return DesktopAgent(
        config=config,
        planner=planner,
        executor=executor,
        perception=perception,
        logger=logger,
        guard=guard,
        stop_requested=stop_requested,
        progress_callback=progress_callback,
        decision_callback=decision_callback,
        task_graph_planner=TaskGraphPlanner(config),
        capability_executor=CapabilityExecutor(
            config=config,
            planner=subgoal_planner,
            registry=build_capability_registry(),
            driver_registry=driver_registry,
        ),
        driver_registry=driver_registry,
    )


def discover_config_path(config_path: str | Path | None) -> Path | None:
    if config_path:
        return Path(config_path)
    return discover_default_config_path()


def load_agent_config(
    config_path: str | Path | None = None,
    *,
    planner_mode: str | None = None,
    dry_run: bool | None = None,
    real_mode: bool = False,
    max_steps: int | None = None,
    pause_after_action: float | None = None,
    config_overrides: dict[str, Any] | None = None,
) -> AgentConfig:
    resolved_config_path = discover_config_path(config_path)
    config = AgentConfig.from_yaml(resolved_config_path)
    if planner_mode:
        config.planner_mode = planner_mode
    if dry_run is not None:
        config.dry_run = bool(dry_run)
    if real_mode:
        config.dry_run = False
    if max_steps is not None:
        config.max_steps = max_steps
    if pause_after_action is not None:
        config.pause_after_action = pause_after_action
    if config_overrides:
        for key, value in config_overrides.items():
            if value is None or not hasattr(config, key):
                continue
            setattr(config, key, value)
    config.normalize()
    return config


def _build_live_pointer_payload(
    *,
    payload: dict[str, Any],
    screen_width: int,
    screen_height: int,
) -> dict[str, Any] | None:
    try:
        x = int(payload.get("x"))
        y = int(payload.get("y"))
    except (TypeError, ValueError):
        return None
    try:
        target_x = int(payload.get("target_x", x))
        target_y = int(payload.get("target_y", y))
    except (TypeError, ValueError):
        target_x = x
        target_y = y
    width = max(1, int(screen_width or 1))
    height = max(1, int(screen_height or 1))
    return {
        "x": x,
        "y": y,
        "norm_x": round(min(max(x / width, 0.0), 1.0), 6),
        "norm_y": round(min(max(y / height, 0.0), 1.0), 6),
        "target_x": target_x,
        "target_y": target_y,
        "phase": str(payload.get("phase", "moving")).strip() or "moving",
        "updated_at": float(payload.get("updated_at", time.time()) or time.time()),
    }


def _resolve_resume_run_dir(run_root: Path, run_id: str) -> Path:
    normalized_run_id = str(run_id or "").strip()
    if not normalized_run_id or "/" in normalized_run_id or "\\" in normalized_run_id:
        raise RuntimeError("Run not found.")
    run_dir = (run_root / normalized_run_id).resolve()
    try:
        run_dir.relative_to(run_root.resolve())
    except ValueError as exc:
        raise RuntimeError("Run not found.") from exc
    if not run_dir.exists() or not run_dir.is_dir():
        raise RuntimeError("Run not found.")
    return run_dir


def _load_resume_context(run_root: Path, run_id: str) -> ResumeRunContext:
    run_dir = _resolve_resume_run_dir(run_root, run_id)
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        raise RuntimeError("Run summary is missing.")
    try:
        summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Run summary could not be read.") from exc

    task = str(summary_payload.get("task", "")).strip() or run_dir.name
    started_at_value = summary_payload.get("started_at")
    started_at = float(started_at_value) if isinstance(started_at_value, (int, float)) else time.time()

    latest_step = 0
    for step_path in run_dir.glob("step_*.json"):
        stem = step_path.stem
        try:
            latest_step = max(latest_step, int(stem.split("_", 1)[1]))
        except (IndexError, ValueError):
            continue
    summary_steps = int(summary_payload.get("steps", 0) or 0)
    step_offset = max(summary_steps, latest_step)

    execution_state: ExecutionState | None = None
    state_path = run_dir / "state.json"
    if state_path.exists():
        try:
            state_payload = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("Saved execution state could not be read.") from exc
        if isinstance(state_payload, dict) and state_payload:
            execution_state = ExecutionState.from_dict(state_payload)

    return ResumeRunContext(
        task=task,
        run_dir=run_dir,
        started_at=started_at,
        step_offset=step_offset,
        execution_state=execution_state,
    )


def run_task(
    task: str,
    *,
    config_path: str | Path | None = None,
    planner_mode: str | None = None,
    dry_run: bool | None = None,
    real_mode: bool = False,
    max_steps: int | None = None,
    pause_after_action: float | None = None,
    config_overrides: dict[str, Any] | None = None,
    stop_requested: Callable[[], bool] | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    decision_callback: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
) -> AgentRunResult:
    config = load_agent_config(
        config_path=config_path,
        planner_mode=planner_mode,
        dry_run=dry_run,
        real_mode=real_mode,
        max_steps=max_steps,
        pause_after_action=pause_after_action,
        config_overrides=config_overrides,
    )
    agent = build_agent(
        config,
        stop_requested=stop_requested,
        progress_callback=progress_callback,
        decision_callback=decision_callback,
    )
    return agent.run(task)


def resume_task(
    run_id: str,
    *,
    config_path: str | Path | None = None,
    planner_mode: str | None = None,
    dry_run: bool | None = None,
    real_mode: bool = False,
    max_steps: int | None = None,
    pause_after_action: float | None = None,
    config_overrides: dict[str, Any] | None = None,
    stop_requested: Callable[[], bool] | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    decision_callback: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
) -> AgentRunResult:
    config = load_agent_config(
        config_path=config_path,
        planner_mode=planner_mode,
        dry_run=dry_run,
        real_mode=real_mode,
        max_steps=max_steps,
        pause_after_action=pause_after_action,
        config_overrides=config_overrides,
    )
    resume_context = _load_resume_context(config.run_root, run_id)
    agent = build_agent(
        config,
        stop_requested=stop_requested,
        progress_callback=progress_callback,
        decision_callback=decision_callback,
    )
    return agent.run(
        resume_context.task,
        run_dir=resume_context.run_dir,
        execution_state=resume_context.execution_state,
        started_at=resume_context.started_at,
        step_offset=resume_context.step_offset,
        history=list(resume_context.execution_state.memory) if resume_context.execution_state is not None else None,
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if not args:
        return _launch_dashboard_cli([])

    command = args[0]
    if command in {"ui", "serve"}:
        return _launch_dashboard_cli(args[1:])
    if command == "run":
        return _run_cli(args[1:])
    return _run_cli(args)


def _run_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} task runner")
    parser.add_argument("task_positional", nargs="?", help="Natural-language task")
    parser.add_argument("--task", help="Natural-language task")
    parser.add_argument("--config", help="Path to YAML config")
    parser.add_argument("--planner", choices=["auto", "rule", "vlm"], help="Override planner mode")
    parser.add_argument("--dry-run", action="store_true", help="Run in mock mode")
    parser.add_argument("--real", action="store_true", help="Force real desktop mode")
    parser.add_argument("--max-steps", type=int, help="Override max steps")
    parser.add_argument("--pause", type=float, help="Pause after each action")
    parsed = parser.parse_args(argv)

    task = (parsed.task or parsed.task_positional or "").strip()
    if not task:
        parser.error("Task is required.")

    result = run_task(
        task,
        config_path=parsed.config,
        planner_mode=parsed.planner,
        dry_run=True if parsed.dry_run else None,
        real_mode=parsed.real,
        max_steps=parsed.max_steps,
        pause_after_action=parsed.pause,
    )
    print(
        json.dumps(
            {
                "task": result.task,
                "completed": result.completed,
                "steps": result.steps,
                "run_dir": str(result.run_dir),
                "started_at": result.started_at,
                "finished_at": result.finished_at,
                "error": result.error,
                "cancelled": result.cancelled,
                "requires_human": result.requires_human,
                "interruption_kind": result.interruption_kind,
                "interruption_reason": result.interruption_reason,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result.completed else 1


def _launch_dashboard_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} dashboard")
    parser.add_argument("--host", default=DEFAULT_DASHBOARD_HOST, help="Dashboard host")
    parser.add_argument("--port", default=DEFAULT_DASHBOARD_PORT, type=int, help="Dashboard port")
    parser.add_argument("--config", help="Path to YAML config")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")
    parser.add_argument("--browser", action="store_true", help="Use the browser-based dashboard instead of the desktop shell")
    parsed = parser.parse_args(argv)

    if not parsed.browser and sys.platform.startswith("win"):
        from desktop_agent.desktop_shell import DesktopShellUnavailable, launch_desktop_shell

        try:
            return launch_desktop_shell(
                host=parsed.host,
                port=parsed.port,
                config_path=parsed.config,
            )
        except DesktopShellUnavailable as exc:
            print(
                f"Desktop shell is unavailable ({exc}). Falling back to the browser dashboard.",
                file=sys.stderr,
            )

    from desktop_agent.dashboard import launch_dashboard

    return launch_dashboard(
        host=parsed.host,
        port=parsed.port,
        config_path=parsed.config,
        open_browser=not parsed.no_browser,
    )
