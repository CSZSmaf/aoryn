from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from desktop_agent.actions import Action, PlanResult


@dataclass(slots=True)
class RunLogger:
    run_root: Path

    def create_run_dir(self, task: str) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = _slugify(task)[:36]
        run_dir = self.run_root / f"{timestamp}_{slug}"
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def log_step(
        self,
        run_dir: Path,
        step_index: int,
        task: str,
        screenshot_path: Path,
        plan: PlanResult,
        executed_actions: list[Action],
        error: str | None = None,
        challenge: dict | None = None,
        captured_at: float | None = None,
        environment: dict | None = None,
        state: dict[str, Any] | None = None,
        world_model: dict[str, Any] | None = None,
        step_proposal: dict[str, Any] | None = None,
        verification: dict[str, Any] | None = None,
        timings: dict[str, float] | None = None,
    ) -> Path:
        payload = {
            "step": step_index,
            "task": task,
            "screenshot": screenshot_path.name,
            "captured_at": captured_at if captured_at is not None else time.time(),
            "environment": environment,
            "plan": plan.to_dict(),
            "executed_actions": [item.to_dict() for item in executed_actions],
            "error": error,
            "challenge": challenge,
            "state": state,
            "world_model": world_model,
            "step_proposal": step_proposal,
            "verification": verification,
            "timings": timings,
        }
        output = run_dir / f"step_{step_index:02d}.json"
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output

    def log_execution_state(
        self,
        *,
        run_dir: Path,
        task_graph: dict[str, Any] | None,
        state: dict[str, Any] | None,
        facts: list[dict[str, Any]] | None,
        execution_state: dict[str, Any] | None = None,
    ) -> None:
        self._write_json(run_dir / "plan.json", task_graph or {})
        self._write_json(run_dir / "state.json", state or {})
        self._write_json(run_dir / "facts.json", {"items": list(facts or [])})
        if execution_state is not None:
            self._write_json(run_dir / "execution_state.json", execution_state)

    def log_summary(
        self,
        run_dir: Path,
        task: str,
        completed: bool,
        steps: int,
        dry_run: bool,
        planner_mode: str,
        task_graph_request_timeout: float | None = None,
        max_steps: int | None = None,
        max_run_seconds: float | None = None,
        pause_after_action: float | None = None,
        desktop_autonomy_mode: str | None = None,
        complex_task_planning: str | None = None,
        approval_policy: str | None = None,
        plan_review_policy: str | None = None,
        stage_review_policy: str | None = None,
        max_task_subgoals: int | None = None,
        max_subgoal_retries: int | None = None,
        max_replans_per_run: int | None = None,
        max_failures_per_subgoal: int | None = None,
        replan_on_recoverable_error: bool | None = None,
        recoverable_error_retry_limit: int | None = None,
        browser_control_mode: str | None = None,
        browser_dom_backend: str | None = None,
        browser_dom_timeout: float | None = None,
        browser_headless: bool | None = None,
        browser_channel: str | None = None,
        browser_executable_path: str | None = None,
        cursor_motion_enabled: bool | None = None,
        cursor_motion_duration: float | None = None,
        display_override_enabled: bool | None = None,
        display_override_monitor_device_name: str | None = None,
        display_override_dpi_scale: float | None = None,
        display_override_work_area_left: int | None = None,
        display_override_work_area_top: int | None = None,
        display_override_work_area_width: int | None = None,
        display_override_work_area_height: int | None = None,
        generic_app_launch_enabled: bool | None = None,
        shell_recipe_policy: str | None = None,
        error: str | None = None,
        cancelled: bool = False,
        cancel_reason: str | None = None,
        requires_human: bool = False,
        interruption_kind: str | None = None,
        interruption_reason: str | None = None,
        started_at: float | None = None,
        finished_at: float | None = None,
        architecture: str = "generic_agent_v1",
    ) -> Path:
        payload = {
            "task": task,
            "completed": completed,
            "steps": steps,
            "dry_run": dry_run,
            "planner_mode": planner_mode,
            "task_graph_request_timeout": task_graph_request_timeout,
            "max_steps": max_steps,
            "max_run_seconds": max_run_seconds,
            "pause_after_action": pause_after_action,
            "desktop_autonomy_mode": desktop_autonomy_mode,
            "complex_task_planning": complex_task_planning,
            "approval_policy": approval_policy,
            "plan_review_policy": plan_review_policy,
            "stage_review_policy": stage_review_policy,
            "max_task_subgoals": max_task_subgoals,
            "max_subgoal_retries": max_subgoal_retries,
            "max_replans_per_run": max_replans_per_run,
            "max_failures_per_subgoal": max_failures_per_subgoal,
            "replan_on_recoverable_error": replan_on_recoverable_error,
            "recoverable_error_retry_limit": recoverable_error_retry_limit,
            "browser_control_mode": browser_control_mode,
            "browser_dom_backend": browser_dom_backend,
            "browser_dom_timeout": browser_dom_timeout,
            "browser_headless": browser_headless,
            "browser_channel": browser_channel,
            "browser_executable_path": browser_executable_path,
            "cursor_motion_enabled": cursor_motion_enabled,
            "cursor_motion_duration": cursor_motion_duration,
            "display_override_enabled": display_override_enabled,
            "display_override_monitor_device_name": display_override_monitor_device_name,
            "display_override_dpi_scale": display_override_dpi_scale,
            "display_override_work_area_left": display_override_work_area_left,
            "display_override_work_area_top": display_override_work_area_top,
            "display_override_work_area_width": display_override_work_area_width,
            "display_override_work_area_height": display_override_work_area_height,
            "generic_app_launch_enabled": generic_app_launch_enabled,
            "shell_recipe_policy": shell_recipe_policy,
            "execution_budget": {
                "task_graph_request_timeout": task_graph_request_timeout,
                "max_steps": max_steps,
                "max_run_seconds": max_run_seconds,
                "pause_after_action": pause_after_action,
                "desktop_autonomy_mode": desktop_autonomy_mode,
                "approval_policy": approval_policy,
                "complex_task_planning": complex_task_planning,
                "plan_review_policy": plan_review_policy,
                "max_task_subgoals": max_task_subgoals,
                "max_subgoal_retries": max_subgoal_retries,
                "stage_review_policy": stage_review_policy,
                "max_replans_per_run": max_replans_per_run,
                "max_failures_per_subgoal": max_failures_per_subgoal,
                "replan_on_recoverable_error": replan_on_recoverable_error,
                "recoverable_error_retry_limit": recoverable_error_retry_limit,
            },
            "execution_environment": {
                "browser_control_mode": browser_control_mode,
                "browser_dom_backend": browser_dom_backend,
                "browser_dom_timeout": browser_dom_timeout,
                "browser_headless": browser_headless,
                "browser_channel": browser_channel,
                "browser_executable_path": browser_executable_path,
                "cursor_motion_enabled": cursor_motion_enabled,
                "cursor_motion_duration": cursor_motion_duration,
                "display_override_enabled": display_override_enabled,
                "display_override_monitor_device_name": display_override_monitor_device_name,
                "display_override_dpi_scale": display_override_dpi_scale,
                "display_override_work_area_left": display_override_work_area_left,
                "display_override_work_area_top": display_override_work_area_top,
                "display_override_work_area_width": display_override_work_area_width,
                "display_override_work_area_height": display_override_work_area_height,
                "generic_app_launch_enabled": generic_app_launch_enabled,
                "shell_recipe_policy": shell_recipe_policy,
            },
            "error": error,
            "cancelled": cancelled,
            "cancel_reason": cancel_reason,
            "requires_human": requires_human,
            "interruption_kind": interruption_kind,
            "interruption_reason": interruption_reason,
            "started_at": started_at,
            "finished_at": finished_at if finished_at is not None else time.time(),
            "architecture": architecture,
        }
        output = run_dir / "summary.json"
        self._write_json(output, payload)
        return output

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _slugify(text: str) -> str:
    text = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", text.strip(), flags=re.U)
    return text.strip("_") or "task"
