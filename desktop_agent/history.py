from __future__ import annotations

import json
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_EXECUTION_BUDGET_SUMMARY_FIELDS = (
    "task_graph_request_timeout",
    "max_steps",
    "max_run_seconds",
    "pause_after_action",
    "desktop_autonomy_mode",
    "approval_policy",
    "complex_task_planning",
    "plan_review_policy",
    "max_task_subgoals",
    "max_subgoal_retries",
    "stage_review_policy",
    "max_replans_per_run",
    "max_failures_per_subgoal",
    "replan_on_recoverable_error",
    "recoverable_error_retry_limit",
)

_EXECUTION_BUDGET_BOOLEAN_FIELDS = {"replan_on_recoverable_error"}

_EXECUTION_ENVIRONMENT_SUMMARY_FIELDS = (
    "browser_control_mode",
    "browser_dom_backend",
    "browser_dom_timeout",
    "browser_headless",
    "browser_channel",
    "browser_executable_path",
    "cursor_motion_enabled",
    "cursor_motion_duration",
    "display_override_enabled",
    "display_override_monitor_device_name",
    "display_override_dpi_scale",
    "display_override_work_area_left",
    "display_override_work_area_top",
    "display_override_work_area_width",
    "display_override_work_area_height",
    "generic_app_launch_enabled",
    "shell_recipe_policy",
)

_EXECUTION_ENVIRONMENT_BOOLEAN_FIELDS = {
    "browser_headless",
    "cursor_motion_enabled",
    "display_override_enabled",
    "generic_app_launch_enabled",
}


@dataclass(slots=True)
class RunRecord:
    run_id: str
    task: str
    completed: bool
    steps: int
    error: str | None
    created_at: float
    summary_payload: dict[str, Any]
    summary_path: Path
    run_dir: Path

    def to_dict(self) -> dict[str, Any]:
        latest_step_image = _find_latest_step_image(self.run_dir)
        details_updated_at = _find_details_updated_at(self.run_dir, self.summary_path)
        resume_mode = _resume_mode_for_run(self.summary_payload, self.run_dir)
        state_summary = _load_history_state_summary(self.run_dir)
        execution_budget = _summary_execution_budget(self.summary_payload)
        execution_environment = _summary_execution_environment(self.summary_payload)
        requires_manual = False if _summary_has_terminal_result(self.summary_payload) else (
            _requires_manual_continuation(self.summary_payload)
            or resume_mode == "manual"
            or _requires_manual_continuation(state_summary)
        )
        return {
            "id": self.run_id,
            "task": self.task,
            "completed": self.completed,
            "steps": self.steps,
            "dry_run": _summary_bool(self.summary_payload.get("dry_run")),
            "planner_mode": self.summary_payload.get("planner_mode"),
            "max_steps": execution_budget.get("max_steps"),
            "max_run_seconds": execution_budget.get("max_run_seconds"),
            "pause_after_action": execution_budget.get("pause_after_action"),
            "desktop_autonomy_mode": execution_budget.get("desktop_autonomy_mode"),
            "complex_task_planning": execution_budget.get("complex_task_planning"),
            "approval_policy": execution_budget.get("approval_policy"),
            "plan_review_policy": execution_budget.get("plan_review_policy"),
            "stage_review_policy": execution_budget.get("stage_review_policy"),
            "max_task_subgoals": execution_budget.get("max_task_subgoals"),
            "max_subgoal_retries": execution_budget.get("max_subgoal_retries"),
            "max_replans_per_run": execution_budget.get("max_replans_per_run"),
            "max_failures_per_subgoal": execution_budget.get("max_failures_per_subgoal"),
            "replan_on_recoverable_error": execution_budget.get("replan_on_recoverable_error"),
            "recoverable_error_retry_limit": execution_budget.get("recoverable_error_retry_limit"),
            "execution_budget": execution_budget,
            "execution_environment": execution_environment,
            **execution_environment,
            "cancelled": _bool_value(self.summary_payload.get("cancelled")),
            "cancel_reason": self.summary_payload.get("cancel_reason"),
            "requires_human": requires_manual,
            "can_resume": bool(resume_mode),
            "resume_mode": resume_mode,
            "interruption_kind": self.summary_payload.get("interruption_kind"),
            "interruption_reason": self.summary_payload.get("interruption_reason"),
            "error": self.error,
            "current_goal": state_summary.get("current_goal") if isinstance(state_summary, dict) else None,
            "orchestration_phase": state_summary.get("orchestration_phase") if isinstance(state_summary, dict) else None,
            "active_specialist": state_summary.get("active_specialist") if isinstance(state_summary, dict) else None,
            "workspace_summary": state_summary.get("workspace_summary") if isinstance(state_summary, dict) else None,
            "plan_review_status": state_summary.get("plan_review_status") if isinstance(state_summary, dict) else None,
            "stage_review_status": state_summary.get("stage_review_status") if isinstance(state_summary, dict) else None,
            "last_replan_reason": state_summary.get("last_replan_reason") if isinstance(state_summary, dict) else None,
            "verification_status": state_summary.get("verification_status") if isinstance(state_summary, dict) else None,
            "recovery_reason": state_summary.get("recovery_reason") if isinstance(state_summary, dict) else None,
            "last_progress_at": state_summary.get("last_progress_at") if isinstance(state_summary, dict) else None,
            "current_surface_kind": state_summary.get("current_surface_kind") if isinstance(state_summary, dict) else None,
            "state": state_summary,
            "created_at": self.created_at,
            "started_at": self.summary_payload.get("started_at", self.created_at),
            "finished_at": self.summary_payload.get("finished_at", self.created_at),
            "details_updated_at": details_updated_at,
            "preview_image": latest_step_image.name if latest_step_image else None,
        }


@dataclass(slots=True)
class _CachedRunSummary:
    record: RunRecord
    summary_mtime_ns: int
    summary_size: int


class RunHistoryIndex:
    """Incrementally caches run summaries for overview-style queries."""

    def __init__(self, run_root: Path) -> None:
        self.run_root = run_root.resolve()
        self._entries: dict[str, _CachedRunSummary] = {}
        self._lock = threading.Lock()

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            records = self._refresh_records_locked()
            selected = records[: max(0, int(limit))]
            return [record.to_dict() for record in selected]

    def _refresh_records_locked(self) -> list[RunRecord]:
        if not self.run_root.exists():
            self._entries.clear()
            return []

        seen_run_ids: set[str] = set()
        for summary_path in self.run_root.glob("*/summary.json"):
            run_dir = summary_path.parent
            run_id = run_dir.name
            seen_run_ids.add(run_id)
            try:
                stat = summary_path.stat()
            except OSError:
                self._entries.pop(run_id, None)
                continue

            cached = self._entries.get(run_id)
            if (
                cached is not None
                and cached.summary_mtime_ns == stat.st_mtime_ns
                and cached.summary_size == stat.st_size
            ):
                continue

            payload = _load_summary_payload(summary_path)
            if payload is None:
                self._entries.pop(run_id, None)
                continue

            self._entries[run_id] = _CachedRunSummary(
                record=_build_run_record(
                    run_dir=run_dir,
                    summary_path=summary_path,
                    summary_payload=payload,
                    summary_stat=stat,
                ),
                summary_mtime_ns=stat.st_mtime_ns,
                summary_size=stat.st_size,
            )

        stale_run_ids = [run_id for run_id in self._entries if run_id not in seen_run_ids]
        for run_id in stale_run_ids:
            self._entries.pop(run_id, None)

        records = [entry.record for entry in self._entries.values()]
        records.sort(key=lambda item: item.created_at, reverse=True)
        return records


_RUN_HISTORY_INDEXES: dict[str, RunHistoryIndex] = {}
_RUN_HISTORY_INDEXES_LOCK = threading.Lock()


def list_runs(run_root: Path, limit: int = 20) -> list[dict[str, Any]]:
    return _history_index_for(run_root).list_runs(limit=limit)


def load_run_details(run_root: Path, run_id: str) -> dict[str, Any] | None:
    run_dir = _resolve_run_dir(run_root, run_id)
    if run_dir is None:
        return None

    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        return None

    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    summary_stat = summary_path.stat()
    details_updated_at = _find_details_updated_at(run_dir, summary_path)

    steps: list[dict[str, Any]] = []
    for step_path in sorted(run_dir.glob("step_*.json")):
        try:
            step_payload = json.loads(step_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        screenshot_name = step_payload.get("screenshot")
        step_stat = step_path.stat()
        steps.append(
            {
                "step": int(step_payload.get("step", 0) or 0),
                "task": step_payload.get("task"),
                "error": step_payload.get("error"),
                "screenshot": screenshot_name,
                "captured_at": step_payload.get("captured_at", step_stat.st_mtime),
                "plan": step_payload.get("plan", {}),
                "executed_actions": step_payload.get("executed_actions", []),
                "challenge": step_payload.get("challenge"),
                "state": step_payload.get("state"),
                "world_model": step_payload.get("world_model"),
                "step_proposal": step_payload.get("step_proposal"),
                "verification": step_payload.get("verification"),
                "timings": step_payload.get("timings"),
            }
        )

    plan_payload = _load_optional_json(run_dir / "plan.json")
    state_payload = _load_optional_json(run_dir / "state.json")
    execution_state_payload = _load_optional_json(run_dir / "execution_state.json")
    facts_payload = _load_optional_json(run_dir / "facts.json")
    resume_mode = _resume_mode_from_payloads(
        summary,
        execution_state_payload=execution_state_payload,
        state_payload=state_payload,
        plan_payload=plan_payload,
    )
    requires_manual = False if _summary_has_terminal_result(summary) else (
        _requires_manual_continuation(summary)
        or resume_mode == "manual"
        or _requires_manual_continuation(execution_state_payload)
        or _requires_manual_continuation(state_payload)
    )
    execution_budget = _summary_execution_budget(summary)
    execution_environment = _summary_execution_environment(summary)

    return {
        "id": run_id,
        "task": summary.get("task"),
        "completed": _bool_value(summary.get("completed")),
        "steps": int(summary.get("steps", 0) or 0),
        "dry_run": _summary_bool(summary.get("dry_run")),
        "planner_mode": summary.get("planner_mode"),
        "max_steps": execution_budget.get("max_steps"),
        "max_run_seconds": execution_budget.get("max_run_seconds"),
        "pause_after_action": execution_budget.get("pause_after_action"),
        "desktop_autonomy_mode": execution_budget.get("desktop_autonomy_mode"),
        "complex_task_planning": execution_budget.get("complex_task_planning"),
        "approval_policy": execution_budget.get("approval_policy"),
        "plan_review_policy": execution_budget.get("plan_review_policy"),
        "stage_review_policy": execution_budget.get("stage_review_policy"),
        "max_task_subgoals": execution_budget.get("max_task_subgoals"),
        "max_subgoal_retries": execution_budget.get("max_subgoal_retries"),
        "max_replans_per_run": execution_budget.get("max_replans_per_run"),
        "max_failures_per_subgoal": execution_budget.get("max_failures_per_subgoal"),
        "replan_on_recoverable_error": execution_budget.get("replan_on_recoverable_error"),
        "recoverable_error_retry_limit": execution_budget.get("recoverable_error_retry_limit"),
        "execution_budget": execution_budget,
        "execution_environment": execution_environment,
        **execution_environment,
        "cancelled": _bool_value(summary.get("cancelled")),
        "cancel_reason": summary.get("cancel_reason"),
        "requires_human": requires_manual,
        "can_resume": bool(resume_mode),
        "resume_mode": resume_mode,
        "interruption_kind": summary.get("interruption_kind"),
        "interruption_reason": summary.get("interruption_reason"),
        "started_at": summary.get("started_at", summary_stat.st_mtime),
        "finished_at": summary.get("finished_at", summary_stat.st_mtime),
        "details_updated_at": details_updated_at,
        "error": summary.get("error"),
        "architecture": summary.get("architecture"),
        "artifacts": [item.name for item in sorted(run_dir.iterdir()) if item.is_file()],
        "timeline": steps,
        "plan": plan_payload,
        "state": state_payload,
        "execution_state": execution_state_payload,
        "facts": facts_payload.get("items") if isinstance(facts_payload, dict) else facts_payload,
    }


def resolve_artifact_path(run_root: Path, run_id: str, artifact_name: str) -> Path | None:
    if not artifact_name or "/" in artifact_name or "\\" in artifact_name:
        return None
    run_dir = _resolve_run_dir(run_root, run_id)
    if run_dir is None:
        return None

    artifact_path = (run_dir / artifact_name).resolve()
    try:
        artifact_path.relative_to(run_dir.resolve())
    except ValueError:
        return None
    if not artifact_path.exists() or not artifact_path.is_file():
        return None
    return artifact_path


def clear_runs(run_root: Path) -> int:
    resolved_root = run_root.resolve()
    if not resolved_root.exists() or not resolved_root.is_dir():
        return 0
    run_dirs = []
    for summary_path in resolved_root.glob("*/summary.json"):
        if not summary_path.is_file():
            continue
        run_dir = summary_path.parent.resolve()
        try:
            run_dir.relative_to(resolved_root)
        except ValueError:
            continue
        if run_dir == resolved_root:
            continue
        run_dirs.append(run_dir)

    cleared = 0
    for run_dir in sorted(set(run_dirs)):
        try:
            shutil.rmtree(run_dir)
        except OSError:
            continue
        cleared += 1
    return cleared


def _resolve_run_dir(run_root: Path, run_id: str) -> Path | None:
    if not run_id or "/" in run_id or "\\" in run_id:
        return None
    run_dir = (run_root / run_id).resolve()
    try:
        run_dir.relative_to(run_root.resolve())
    except ValueError:
        return None
    if not run_dir.exists() or not run_dir.is_dir():
        return None
    return run_dir


_STEP_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def _find_latest_step_image(run_dir: Path) -> Path | None:
    images = sorted(
        item
        for item in run_dir.glob("step_*.*")
        if item.is_file() and item.suffix.lower() in _STEP_IMAGE_SUFFIXES
    )
    if images:
        return images[-1]
    return None


def _find_details_updated_at(run_dir: Path, summary_path: Path) -> float:
    candidates = [
        summary_path,
        run_dir / "execution_state.json",
        run_dir / "state.json",
        run_dir / "plan.json",
        run_dir / "facts.json",
    ]
    candidates.extend(run_dir.glob("step_*.json"))

    latest = 0.0
    for path in candidates:
        try:
            if path.is_file():
                latest = max(latest, path.stat().st_mtime)
        except OSError:
            continue
    return latest


_HISTORY_STATE_SUMMARY_KEYS = {
    "task",
    "completed",
    "intent",
    "orchestration_phase",
    "active_specialist",
    "plan_health",
    "workspace_summary",
    "plan_review_status",
    "stage_review_status",
    "last_replan_reason",
    "current_goal",
    "chosen_capability",
    "verification_status",
    "recovery_reason",
    "current_subgoal",
    "completion_summary",
    "subgoals",
    "dependencies",
    "pending_decision",
    "last_step",
    "last_verification",
    "evidence_ledger",
    "app_context",
    "last_progress_at",
    "repair_history",
    "current_surface_kind",
    "task_graph",
    "updated_at",
}


_HISTORY_EMPTY_STATE_SHELL_KEYS = {
    "workspace_summary",
    "task_graph",
    "last_verification",
    "evidence_ledger",
    "repair_history",
    "capability_failures",
}


def _load_history_state_summary(run_dir: Path) -> dict[str, Any] | None:
    full_state = _load_optional_json(run_dir / "execution_state.json")
    display_state = _load_optional_json(run_dir / "state.json")
    merged: dict[str, Any] = {}

    if isinstance(full_state, dict):
        merged.update(_compact_history_state_payload(full_state))
    if isinstance(display_state, dict):
        merged.update(_compact_history_state_payload(display_state))
    if (
        isinstance(full_state, dict)
        and isinstance(full_state.get("task_graph"), dict)
        and not isinstance(merged.get("task_graph"), dict)
    ):
        merged["task_graph"] = full_state["task_graph"]

    return {key: value for key, value in merged.items() if value is not None} or None


def _compact_history_state_payload(payload: dict[str, Any]) -> dict[str, Any]:
    compact = {
        key: payload.get(key)
        for key in _HISTORY_STATE_SUMMARY_KEYS
        if key in payload and payload.get(key) is not None
    }
    if isinstance(payload.get("plan_health"), dict):
        plan_health = _compact_history_plan_health(payload.get("plan_health"))
        if plan_health is None:
            compact.pop("plan_health", None)
        else:
            compact["plan_health"] = plan_health
    if isinstance(payload.get("pending_decision"), dict) and not _has_pending_decision_payload(payload.get("pending_decision")):
        compact.pop("pending_decision", None)
    for key in _HISTORY_EMPTY_STATE_SHELL_KEYS:
        if key in compact and not _history_summary_has_value(compact[key]):
            compact.pop(key, None)
    if isinstance(payload.get("last_step"), dict):
        last_step = _compact_history_step(payload.get("last_step"))
        if last_step is None:
            compact.pop("last_step", None)
        else:
            compact["last_step"] = last_step
    if isinstance(payload.get("last_verification"), dict):
        last_verification = _compact_history_verification(payload.get("last_verification"))
        if last_verification is None:
            compact.pop("last_verification", None)
        else:
            compact["last_verification"] = last_verification
    if isinstance(payload.get("evidence_ledger"), list):
        evidence_ledger = [
            item
            for item in (_compact_history_evidence_item(entry) for entry in payload.get("evidence_ledger", [])[-6:])
            if item is not None
        ]
        if evidence_ledger:
            compact["evidence_ledger"] = evidence_ledger
        else:
            compact.pop("evidence_ledger", None)
    return compact


def _history_summary_has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_history_summary_has_value(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_history_summary_has_value(item) for item in value)
    return True


def _compact_history_plan_health(plan_health: Any) -> dict[str, Any] | None:
    if not isinstance(plan_health, dict):
        return None
    compact = dict(plan_health)
    for key, value in list(compact.items()):
        if not _history_summary_has_value(value):
            compact.pop(key, None)
    return compact or None


def _has_pending_decision_payload(value: Any) -> bool:
    return isinstance(value, dict) and _history_summary_has_value(value)


def _compact_history_step(step: Any) -> dict[str, Any] | None:
    if not isinstance(step, dict):
        return None
    compact = {
        key: step.get(key)
        for key in (
            "intent",
            "capability",
            "risk_level",
            "target_scope",
            "surface_kind",
            "requires_approval",
            "completes_subgoal",
            "current_focus",
        )
        if key in step and step.get(key) is not None
    }
    for key in ("progress_signals", "repair_strategy", "remaining_steps"):
        if isinstance(step.get(key), list):
            compact[key] = list(step[key][:4])
    actions = step.get("actions") if isinstance(step.get("actions"), list) else []
    compact["actions"] = [
        item
        for item in (_compact_history_action(action) for action in actions[:4])
        if item is not None
    ]
    return compact if _history_summary_has_value(compact) else None


def _compact_history_action(action: Any) -> dict[str, Any] | None:
    if not isinstance(action, dict):
        return None
    compact: dict[str, Any] = {
        "type": action.get("type") or action.get("action"),
        "label": action.get("label")
        or action.get("text")
        or action.get("selector")
        or action.get("title")
        or action.get("app")
        or action.get("url"),
        "text": action.get("text"),
        "selector": action.get("selector"),
        "title": action.get("title"),
        "app": action.get("app"),
        "key": action.get("key"),
        "keys": action.get("keys")[:6] if isinstance(action.get("keys"), list) else [],
        "button": action.get("button"),
        "status": action.get("status"),
        "phase": action.get("phase"),
        "risk_level": action.get("risk_level"),
        "target_scope": action.get("target_scope"),
        "recipe": action.get("recipe"),
        "url": action.get("url"),
    }
    for key in ("x", "y", "width", "height", "end_x", "end_y", "relative_x", "relative_y", "clicks", "seconds", "amount"):
        try:
            value = float(action.get(key))
        except (TypeError, ValueError):
            continue
        compact[key] = round(value, 4)
    return {key: value for key, value in compact.items() if value not in (None, "", [], {})} or None


def _compact_history_verification(verification: Any) -> dict[str, Any] | None:
    if not isinstance(verification, dict):
        return None
    compact = {
        key: verification.get(key)
        for key in ("success", "status", "failure_kind", "message", "verified_at")
        if key in verification and verification.get(key) is not None
    }
    evidence = verification.get("evidence") if isinstance(verification.get("evidence"), list) else []
    compact["evidence"] = [
        item
        for item in (_compact_history_evidence_item(entry) for entry in evidence[:4])
        if item is not None
    ]
    return compact if _history_summary_has_value(compact) else None


def _compact_history_evidence_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    compact = {
        key: item.get(key)
        for key in (
            "subgoal_id",
            "capability",
            "kind",
            "status",
            "scope",
            "satisfied",
            "title",
            "value",
            "message",
            "detail",
            "selector",
            "url",
            "verified_at",
        )
        if key in item and item.get(key) is not None
    }
    if isinstance(item.get("evidence"), list):
        compact["evidence"] = [
            entry
            for entry in (_compact_history_evidence_item(entry) for entry in item.get("evidence", [])[:3])
            if entry is not None
        ]
    return compact if _history_summary_has_value(compact) else None


def _history_index_for(run_root: Path) -> RunHistoryIndex:
    resolved_root = run_root.resolve()
    key = str(resolved_root)
    with _RUN_HISTORY_INDEXES_LOCK:
        index = _RUN_HISTORY_INDEXES.get(key)
        if index is None:
            index = RunHistoryIndex(resolved_root)
            _RUN_HISTORY_INDEXES[key] = index
        return index


def _load_summary_payload(summary_path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if not lowered:
            return None
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        return None
    return bool(value)


def _bool_value(value: Any, *, default: bool = False) -> bool:
    parsed = _optional_bool(value)
    return default if parsed is None else parsed


def _summary_bool(value: Any) -> Any:
    parsed = _optional_bool(value)
    return value if parsed is None else parsed


def _summary_contract_value(summary: dict[str, Any], contract_key: str, field_key: str) -> Any:
    value = summary.get(field_key)
    if value is not None and value != "":
        return value
    contract = summary.get(contract_key) if isinstance(summary.get(contract_key), dict) else {}
    nested_value = contract.get(field_key)
    if nested_value is not None and nested_value != "":
        return nested_value
    return value


def _summary_execution_budget(summary: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in _EXECUTION_BUDGET_SUMMARY_FIELDS:
        value = _summary_contract_value(summary, "execution_budget", key)
        if key in _EXECUTION_BUDGET_BOOLEAN_FIELDS:
            value = _summary_bool(value)
        payload[key] = value
    return payload


def _summary_execution_environment(summary: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in _EXECUTION_ENVIRONMENT_SUMMARY_FIELDS:
        value = _summary_contract_value(summary, "execution_environment", key)
        if key in _EXECUTION_ENVIRONMENT_BOOLEAN_FIELDS:
            value = _summary_bool(value)
        payload[key] = value
    return payload


def _requires_manual_continuation(payload: dict[str, Any] | list[Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    return bool(
        _optional_bool(payload.get("requires_human")) is True
        or _has_pending_decision_payload(payload.get("pending_decision"))
        or str(payload.get("interruption_kind") or "").strip()
        or str(payload.get("interruption_reason") or "").strip()
        or _has_pending_manual_handoff_context(payload)
    )


def _summary_has_terminal_result(summary_payload: dict[str, Any] | list[Any] | None) -> bool:
    if not isinstance(summary_payload, dict):
        return False
    return bool(
        _optional_bool(summary_payload.get("completed")) is True
        or _optional_bool(summary_payload.get("cancelled")) is True
        or str(summary_payload.get("error") or "").strip()
    )


def _has_pending_manual_handoff_context(payload: dict[str, Any]) -> bool:
    app_context = payload.get("app_context") if isinstance(payload.get("app_context"), dict) else {}
    manual_resume_status = str(app_context.get("manual_resume_status") or "").strip().lower()
    if manual_resume_status in {"resumed", "complete", "completed", "cleared"}:
        return False
    return bool(
        str(payload.get("orchestration_phase") or "").strip().lower() in {"awaiting_user", "awaiting_approval"}
        or str(app_context.get("human_handoff_kind") or "").strip()
        or str(app_context.get("human_handoff_reason") or "").strip()
        or str(app_context.get("human_handoff_summary") or "").strip()
        or str(app_context.get("standard_recovery_kind") or "").strip().lower() == "requires_user"
    )


def _can_resume_run(summary_payload: dict[str, Any], run_dir: Path) -> bool:
    return bool(_resume_mode_for_run(summary_payload, run_dir))


def _resume_mode_for_run(summary_payload: dict[str, Any], run_dir: Path) -> str | None:
    if _optional_bool(summary_payload.get("completed")) is True:
        return None
    return _resume_mode_from_payloads(
        summary_payload,
        execution_state_payload=_load_optional_json(run_dir / "execution_state.json"),
        state_payload=_load_optional_json(run_dir / "state.json"),
        plan_payload=_load_optional_json(run_dir / "plan.json"),
    )


def _can_resume_from_payloads(
    summary_payload: dict[str, Any],
    *,
    execution_state_payload: dict[str, Any] | list[Any] | None,
    state_payload: dict[str, Any] | list[Any] | None,
    plan_payload: dict[str, Any] | list[Any] | None,
) -> bool:
    return bool(
        _resume_mode_from_payloads(
            summary_payload,
            execution_state_payload=execution_state_payload,
            state_payload=state_payload,
            plan_payload=plan_payload,
        )
    )


def _resume_mode_from_payloads(
    summary_payload: dict[str, Any],
    *,
    execution_state_payload: dict[str, Any] | list[Any] | None,
    state_payload: dict[str, Any] | list[Any] | None,
    plan_payload: dict[str, Any] | list[Any] | None,
) -> str | None:
    if _optional_bool(summary_payload.get("completed")) is True:
        return None
    if not _summary_has_terminal_result(summary_payload):
        if _requires_manual_continuation(summary_payload):
            return "manual"
        if _requires_manual_continuation(execution_state_payload) or _requires_manual_continuation(state_payload):
            return "manual"
    if isinstance(execution_state_payload, dict) and isinstance(execution_state_payload.get("task_graph"), dict):
        return "execution_state"
    if isinstance(state_payload, dict):
        if isinstance(state_payload.get("task_graph"), dict):
            return "state"
        if isinstance(state_payload.get("subgoals"), list) and bool(state_payload.get("subgoals")):
            return "state"
    if isinstance(plan_payload, dict) and isinstance(plan_payload.get("subgoals"), list) and bool(plan_payload.get("subgoals")):
        return "plan"
    return None


def _build_run_record(
    *,
    run_dir: Path,
    summary_path: Path,
    summary_payload: dict[str, Any],
    summary_stat,
) -> RunRecord:
    started_at = summary_payload.get("started_at")
    return RunRecord(
        run_id=run_dir.name,
        task=str(summary_payload.get("task", run_dir.name)),
        completed=_bool_value(summary_payload.get("completed")),
        steps=int(summary_payload.get("steps", 0) or 0),
        error=summary_payload.get("error"),
        created_at=float(started_at) if isinstance(started_at, (int, float)) else summary_stat.st_mtime,
        summary_payload=summary_payload,
        summary_path=summary_path,
        run_dir=run_dir,
    )


def _load_optional_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
