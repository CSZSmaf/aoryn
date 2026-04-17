from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from desktop_agent.actions import PlanResult
from desktop_agent.config import AgentConfig
from desktop_agent.executor import (
    BaseExecutor,
    ExecutionCancelled,
    ExecutionError,
    MockExecutor,
    RealDesktopExecutor,
)
from desktop_agent.human_verification import HumanVerificationSignal, detect_human_verification
from desktop_agent.logger import RunLogger
from desktop_agent.perception import MockCapture, PerceptionError, ScreenCapture
from desktop_agent.planner import BasePlanner, PlannerError, build_planner
from desktop_agent.runtime_paths import discover_default_config_path
from desktop_agent.safety import ActionGuard, SafetyError
from desktop_agent.version import APP_NAME


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
    ) -> None:
        self.config = config
        self.planner = planner
        self.executor = executor
        self.perception = perception
        self.logger = logger
        self.guard = guard
        self.stop_requested = stop_requested
        self.progress_callback = progress_callback

    def run(self, task: str) -> AgentRunResult:
        run_dir = self.logger.create_run_dir(task)
        started_at = time.time()
        self._emit_progress(
            {
                "task": task,
                "run_dir": str(run_dir),
                "run_id": run_dir.name,
                "steps": 0,
                "latest_screenshot": None,
                "latest_summary": None,
                "latest_actions": [],
                "started_at": started_at,
            }
        )
        history: list[str] = []
        completed = False
        error_message: str | None = None
        cancelled = False
        cancel_reason: str | None = None
        step_count = 0
        challenge_signal: HumanVerificationSignal | None = None
        last_plan_signature: str | None = None
        repeated_plan_count = 0
        recoverable_error_count = 0

        for step_index in range(1, self.config.max_steps + 1):
            if self._stop_requested():
                cancelled = True
                cancel_reason = "Stopped by user."
                break
            step_count = step_index
            screenshot_path = run_dir / f"step_{step_index:02d}.{self.config.screenshot_format}"
            plan: PlanResult | None = None
            safe_actions: list[Action] = []
            try:
                screen_info = self.perception.capture(screenshot_path)
                captured_at = time.time()
                environment_payload = _build_environment_payload(screen_info)
                if hasattr(self.executor, "update_environment"):
                    self.executor.update_environment(getattr(screen_info, "environment", None))
                challenge_signal = detect_human_verification(self.executor.browser_snapshot())
                if challenge_signal is not None:
                    self.logger.log_step(
                        run_dir=run_dir,
                        step_index=step_index,
                        task=task,
                        screenshot_path=screenshot_path,
                        plan=_build_human_handoff_plan(challenge_signal),
                        executed_actions=[],
                        error=None,
                        challenge=challenge_signal.to_dict(),
                        captured_at=captured_at,
                        environment=environment_payload,
                    )
                    self._emit_progress(
                        self._build_progress_payload(
                            task=task,
                            run_dir=run_dir,
                            step_index=step_index,
                            screenshot_path=screenshot_path,
                            captured_at=captured_at,
                            plan=_build_human_handoff_plan(challenge_signal),
                            executed_actions=[],
                            error=None,
                            challenge=challenge_signal.to_dict(),
                            started_at=started_at,
                            environment=environment_payload,
                        )
                    )
                    history.append(challenge_signal.summary)
                    break
                plan = self.planner.plan(
                    task=task,
                    screenshot_path=screenshot_path,
                    history=history,
                    environment=getattr(screen_info, "environment", None),
                )
                safe_actions = self.guard.validate_many(
                    plan.actions,
                    screen_width=screen_info.width,
                    screen_height=screen_info.height,
                )
                plan_signature = _build_plan_signature(plan, safe_actions)
                if plan_signature == last_plan_signature:
                    repeated_plan_count += 1
                else:
                    repeated_plan_count = 1
                    last_plan_signature = plan_signature
                if repeated_plan_count >= 3:
                    error_message = "Detected the same plan repeatedly. Task stopped to avoid an execution loop."
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
                        )
                    )
                    break
                if self._stop_requested():
                    cancelled = True
                    cancel_reason = "Stopped by user."
                    break
                self.executor.execute_many(
                    safe_actions,
                    pause_after_action=self.config.pause_after_action,
                    stop_requested=self._stop_requested,
                )
                recoverable_error_count = 0
                challenge_signal = detect_human_verification(self.executor.browser_snapshot())
                if challenge_signal is not None:
                    captured_at = self._refresh_step_screenshot(screenshot_path) or captured_at
                    self.logger.log_step(
                        run_dir=run_dir,
                        step_index=step_index,
                        task=task,
                        screenshot_path=screenshot_path,
                        plan=_build_human_handoff_plan(challenge_signal),
                        executed_actions=safe_actions,
                        error=None,
                        challenge=challenge_signal.to_dict(),
                        captured_at=captured_at,
                        environment=environment_payload,
                    )
                    self._emit_progress(
                        self._build_progress_payload(
                            task=task,
                            run_dir=run_dir,
                            step_index=step_index,
                            screenshot_path=screenshot_path,
                            captured_at=captured_at,
                            plan=_build_human_handoff_plan(challenge_signal),
                            executed_actions=safe_actions,
                            error=None,
                            challenge=challenge_signal.to_dict(),
                            started_at=started_at,
                            environment=environment_payload,
                        )
                    )
                    history.append(challenge_signal.summary)
                    break
                self.logger.log_step(
                    run_dir=run_dir,
                    step_index=step_index,
                    task=task,
                    screenshot_path=screenshot_path,
                    plan=plan,
                    executed_actions=safe_actions,
                    error=None,
                    challenge=None,
                    captured_at=captured_at,
                    environment=environment_payload,
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
                        challenge=None,
                        started_at=started_at,
                        environment=environment_payload,
                    )
                )
                history.append(_build_history_entry(plan, safe_actions))
                if self._stop_requested():
                    cancelled = True
                    cancel_reason = "Stopped by user."
                    break
                if plan.done:
                    completed = True
                    break
                if not plan.actions:
                    error_message = "Planner returned no actions before completion."
                    break
            except ExecutionCancelled as exc:
                cancelled = True
                cancel_reason = str(exc) or "Stopped by user."
                cancelled_at = time.time()
                cancel_plan = _build_cancelled_plan(plan)
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
                    )
                )
                break
            except (PlannerError, SafetyError, ExecutionError, PerceptionError) as exc:
                step_error = str(exc)
                recoverable = self._is_recoverable_error(exc)
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
                    )
                )
                history.append(
                    _build_error_history_entry(
                        error=step_error,
                        previous_plan=plan,
                        attempted_actions=safe_actions,
                    )
                )
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
        return AgentRunResult(
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

    def _refresh_step_screenshot(self, screenshot_path: Path) -> float | None:
        try:
            self.perception.capture(screenshot_path)
            return time.time()
        except PerceptionError:
            return None

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
    ) -> dict[str, Any]:
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
        }

    def _emit_progress(self, payload: dict[str, Any]) -> None:
        if self.progress_callback is None:
            return
        try:
            self.progress_callback(payload)
        except Exception:
            return

    def _stop_requested(self) -> bool:
        if self.stop_requested is None:
            return False
        try:
            return bool(self.stop_requested())
        except Exception:
            return False

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


def _build_environment_payload(screen_info) -> dict[str, Any] | None:
    effective = getattr(screen_info, "effective_environment", None) or getattr(screen_info, "environment", None)
    detected = getattr(screen_info, "detected_environment", None)
    if effective is None and detected is None:
        return None
    return {
        "effective": effective.to_dict() if effective is not None else None,
        "detected": detected.to_dict() if detected is not None else None,
    }


def build_agent(
    config: AgentConfig,
    *,
    stop_requested: Callable[[], bool] | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> DesktopAgent:
    planner = build_planner(config)
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
    return config


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
    )
    return agent.run(task)


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
