from __future__ import annotations

import json
import hashlib
import mimetypes
import os
import re
import socket
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from desktop_agent.browser_dom import dom_backend_status
from desktop_agent.browser_runtime import browser_runtime_status
from desktop_agent.chat_support import (
    build_agent_handoff,
    build_chat_system_prompt,
    extract_assistant_message,
    load_help_markdown,
    looks_like_math_request,
    normalize_help_locale,
    resolve_help_path,
    sanitize_assistant_chat_text,
    sanitize_chat_messages,
)
from desktop_agent.config import desktop_autonomy_mode_presets
from desktop_agent.controller import coerce_initial_task_graph, discover_config_path, load_agent_config, resume_task, run_task
from desktop_agent.history import clear_runs, list_runs, load_run_details, resolve_artifact_path
from desktop_agent.orchestrator import task_graph_is_ambiguous, task_graph_risk_level
from desktop_agent.planner import TaskGraphPlanner
from desktop_agent.provider_tools import (
    ProviderModelEntry,
    ProviderSnapshot,
    ProviderToolError,
    build_request_headers,
    fetch_provider_snapshot,
    load_lmstudio_model,
    normalize_api_base_url,
    unload_lmstudio_model_instances,
)
from desktop_agent.runtime_paths import (
    appdata_config_root,
    default_cache_root,
    default_packaged_config_path,
    is_frozen_runtime,
    local_data_root,
    runtime_preferences_path_for,
)
from desktop_agent.version import APP_ASSET_VERSION, APP_NAME, APP_VERSION
from desktop_agent.workflow import ExecutionState, PendingDecision, TaskGraph, build_execution_plan_summary
from desktop_agent.windows_env import detect_display_environment


def _runtime_package_root() -> Path:
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        package_root = bundle_root / "desktop_agent"
        if package_root.exists():
            return package_root
        if (bundle_root.parent / "desktop_agent").exists():
            return bundle_root.parent / "desktop_agent"
    return Path(__file__).resolve().parent


@dataclass(slots=True)
class DashboardJob:
    job_id: str
    task: str
    planner_mode: str
    dry_run: bool
    max_steps: int | None
    pause_after_action: float | None
    max_run_seconds: float | None = None
    resume_run_id: str | None = None
    config_overrides: dict[str, Any] = field(default_factory=dict)
    initial_task_graph: dict[str, Any] | None = None
    initial_plan_review_status: str | None = None
    status: str = "queued"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    updated_at: float = field(default_factory=time.time)
    result: dict[str, Any] | None = None
    error: str | None = None
    cancel_requested: bool = False
    cancelled: bool = False
    cancel_reason: str | None = None
    requires_human: bool = False
    interruption_kind: str | None = None
    interruption_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "id": self.job_id,
            "task": self.task,
            "planner_mode": self.planner_mode,
            "dry_run": self.dry_run,
            "max_steps": self.max_steps,
            "pause_after_action": self.pause_after_action,
            "max_run_seconds": self.max_run_seconds,
            "resume_run_id": self.resume_run_id,
            "config_overrides": self.config_overrides,
            "initial_task_graph": self.initial_task_graph,
            "initial_plan_review_status": self.initial_plan_review_status,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "updated_at": self.updated_at,
            "result": self.result,
            "error": self.error,
            "cancel_requested": self.cancel_requested,
            "cancelled": self.cancelled,
            "cancel_reason": self.cancel_reason,
            "requires_human": self.requires_human,
            "interruption_kind": self.interruption_kind,
            "interruption_reason": self.interruption_reason,
        }
        if _payload_has_terminal_result(payload) and _optional_bool(payload.get("requires_human")) is not True:
            result = payload.get("result")
            if isinstance(result, dict):
                payload["result"] = _clear_pending_decision_from_result(result)
            payload["requires_human"] = False
        return payload


def _payload_has_terminal_result(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    status = str(payload.get("status") or "").strip().lower()
    return bool(
        _optional_bool(payload.get("completed")) is True
        or _optional_bool(payload.get("cancelled")) is True
        or payload.get("error")
        or status in {"completed", "failed", "cancelled"}
    )


def _normalize_decision_action(value: Any, *, default: str | None = None) -> str:
    decision = str(value or "").strip().lower()
    aliases = {
        "approved": "approve",
        "rejected": "reject",
        "cancelled": "cancel",
        "canceled": "cancel",
    }
    decision = aliases.get(decision, decision)
    if decision in {"approve", "reject", "cancel"}:
        return decision
    return str(default or decision)


def _payload_has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_payload_has_value(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_payload_has_value(item) for item in value)
    return True


def _has_pending_decision_payload(value: Any) -> bool:
    return isinstance(value, dict) and _payload_has_value(value)


def _is_empty_state_shell(value: Any) -> bool:
    return isinstance(value, (dict, list, tuple, set)) and not _payload_has_value(value)


_STATE_SUMMARY_EMPTY_SHELL_KEYS = {
    "pending_decision",
    "plan_health",
    "workspace_summary",
    "last_verification",
    "evidence_ledger",
    "repair_history",
    "capability_failures",
    "task_graph",
}


def _merge_execution_state_summary_payloads(
    full_state: dict[str, Any],
    display_state: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(full_state)
    for key, value in display_state.items():
        if (
            key in _STATE_SUMMARY_EMPTY_SHELL_KEYS
            and _is_empty_state_shell(value)
            and _payload_has_value(merged.get(key))
        ):
            continue
        merged[key] = value
    return merged


def _clear_pending_decision_from_result(
    result: dict[str, Any] | None,
    *,
    decision: str | None = None,
) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return result
    normalized_decision = _normalize_decision_action(decision)
    cleaned = dict(result)
    pending_decision = cleaned.pop("pending_decision", None)
    if not _has_pending_decision_payload(pending_decision):
        pending_decision = None
    execution_state = cleaned.get("execution_state")
    state_payload = cleaned.get("state")
    for candidate in (execution_state, state_payload):
        if _has_pending_decision_payload(pending_decision) or not isinstance(candidate, dict):
            continue
        candidate_pending = candidate.get("pending_decision")
        if _has_pending_decision_payload(candidate_pending):
            pending_decision = candidate_pending

    if isinstance(execution_state, dict):
        cleaned_state = dict(execution_state)
        cleaned_state.pop("pending_decision", None)
        _apply_submitted_decision_to_state(
            cleaned_state,
            decision=normalized_decision,
            pending_decision=pending_decision,
        )
        cleaned["execution_state"] = cleaned_state
    if isinstance(state_payload, dict):
        cleaned_state = dict(state_payload)
        cleaned_state.pop("pending_decision", None)
        _apply_submitted_decision_to_state(
            cleaned_state,
            decision=normalized_decision,
            pending_decision=pending_decision,
        )
        cleaned["state"] = cleaned_state
    _apply_submitted_decision_to_result(
        cleaned,
        decision=normalized_decision,
        pending_decision=pending_decision,
    )
    return cleaned


_FINAL_EXECUTION_STATE_RESULT_KEYS = (
    "intent",
    "orchestration_phase",
    "active_specialist",
    "workspace_summary",
    "plan_review_status",
    "stage_review_status",
    "last_replan_reason",
    "current_goal",
    "chosen_capability",
    "verification_status",
    "recovery_reason",
    "completion_summary",
    "last_progress_at",
    "current_surface_kind",
)


def _finalize_job_result_payload(
    current_result: dict[str, Any] | None,
    final_payload: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(current_result or {})
    merged.update(final_payload)
    if _payload_has_terminal_result(merged) and _optional_bool(merged.get("requires_human")) is not True:
        cleared = _clear_pending_decision_from_result(merged)
        if isinstance(cleared, dict):
            merged = cleared
            merged["requires_human"] = False
    execution_state = merged.get("execution_state")
    if not isinstance(execution_state, dict):
        return merged

    if not _has_pending_decision_payload(execution_state.get("pending_decision")):
        cleared = _clear_pending_decision_from_result(merged)
        if isinstance(cleared, dict):
            merged = cleared
            execution_state = merged.get("execution_state")
    if not isinstance(execution_state, dict):
        return merged

    if isinstance(merged.get("state"), dict):
        merged["state"] = dict(execution_state)
    for key in _FINAL_EXECUTION_STATE_RESULT_KEYS:
        if key in execution_state:
            merged[key] = execution_state.get(key)

    if "last_step" in execution_state:
        last_step = execution_state.get("last_step")
        if isinstance(last_step, dict):
            merged["step_proposal"] = dict(last_step)
        else:
            merged.pop("step_proposal", None)
    if "last_verification" in execution_state:
        last_verification = execution_state.get("last_verification")
        if isinstance(last_verification, dict):
            merged["verification"] = dict(last_verification)
        else:
            merged.pop("verification", None)

    pending_decision = execution_state.get("pending_decision")
    if _has_pending_decision_payload(pending_decision):
        merged["pending_decision"] = dict(pending_decision)
    else:
        merged.pop("pending_decision", None)
    return merged


def _merge_progress_job_result_payload(
    current_result: dict[str, Any] | None,
    progress_payload: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(current_result or {})
    merged.update(progress_payload)
    state_summary = _execution_state_summary_from_payload(progress_payload)
    if not isinstance(state_summary, dict):
        return merged

    if isinstance(merged.get("state"), dict):
        merged["state"] = dict(state_summary)
    for key in _FINAL_EXECUTION_STATE_RESULT_KEYS:
        if key in state_summary:
            merged[key] = state_summary.get(key)

    if "last_step" in state_summary and "step_proposal" not in progress_payload:
        last_step = state_summary.get("last_step")
        if isinstance(last_step, dict):
            merged["step_proposal"] = dict(last_step)
        else:
            merged.pop("step_proposal", None)
    if "last_verification" in state_summary and "verification" not in progress_payload:
        last_verification = state_summary.get("last_verification")
        if isinstance(last_verification, dict):
            merged["verification"] = dict(last_verification)
        else:
            merged.pop("verification", None)

    if "pending_decision" in state_summary:
        pending_decision = state_summary.get("pending_decision")
        if _has_pending_decision_payload(pending_decision):
            merged["pending_decision"] = dict(pending_decision)
        else:
            merged.pop("pending_decision", None)
    return merged


def _execution_state_summary_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    execution_state = payload.get("execution_state") if isinstance(payload.get("execution_state"), dict) else None
    state_payload = payload.get("state") if isinstance(payload.get("state"), dict) else None
    if execution_state and state_payload:
        return _merge_execution_state_summary_payloads(execution_state, state_payload)
    if execution_state:
        return dict(execution_state)
    if state_payload:
        return dict(state_payload)
    return None


def _fail_job_result_payload(
    current_result: dict[str, Any] | None,
    *,
    error: str,
    finished_at: float,
) -> dict[str, Any]:
    failed = dict(current_result or {})
    failed.update(
        {
            "completed": False,
            "error": error,
            "finished_at": finished_at,
            "requires_human": False,
        }
    )
    cleaned = _clear_pending_decision_from_result(failed)
    if isinstance(cleaned, dict):
        failed = cleaned
    for state_key in ("execution_state", "state"):
        state_payload = failed.get(state_key)
        if isinstance(state_payload, dict):
            failed[state_key] = _mark_pending_review_state_failed(state_payload, error=error)
    for review_key in ("plan_review_status", "stage_review_status"):
        if str(failed.get(review_key) or "").strip().lower() == "pending":
            failed[review_key] = "failed"
    return failed


def _mark_pending_review_state_failed(state_payload: dict[str, Any], *, error: str) -> dict[str, Any]:
    state = dict(state_payload)
    state.pop("pending_decision", None)
    phase = str(state.get("orchestration_phase") or "").strip().lower()
    if phase in {"plan_review", "stage_review", "awaiting_approval"}:
        state["orchestration_phase"] = "blocked"
    for review_key in ("plan_review_status", "stage_review_status"):
        if str(state.get(review_key) or "").strip().lower() == "pending":
            state[review_key] = "failed"

    app_context = state.get("app_context")
    if isinstance(app_context, dict):
        context = dict(app_context)
        for review_key in ("plan_review_status", "stage_review_status"):
            if str(context.get(review_key) or "").strip().lower() == "pending":
                context[review_key] = "failed"
        context["recovery_reason"] = error
        state["app_context"] = context

    plan_health = state.get("plan_health")
    if isinstance(plan_health, dict):
        updated_plan_health = dict(plan_health)
        autonomy = updated_plan_health.get("autonomy")
        if isinstance(autonomy, dict):
            updated_autonomy = dict(autonomy)
            blockers = [
                item
                for item in updated_autonomy.get("blockers", [])
                if isinstance(item, str) and item.strip()
            ]
            if error and error not in blockers:
                blockers.append(error)
            updated_autonomy.update(
                {
                    "status": "blocked",
                    "can_continue": False,
                    "requires_review": False,
                    "requires_user": False,
                    "next_action": "inspect_failure",
                    "blockers": blockers,
                }
            )
            updated_plan_health["autonomy"] = updated_autonomy
        state["plan_health"] = updated_plan_health
    return state


def _apply_submitted_decision_to_result(
    result_payload: dict[str, Any],
    *,
    decision: str,
    pending_decision: Any,
) -> None:
    if decision not in {"approve", "reject", "cancel"} or not isinstance(pending_decision, dict):
        return
    decision_type = str(pending_decision.get("decision_type") or "").strip().lower()
    status_value = {
        "approve": "approved",
        "reject": "rejected",
        "cancel": "cancelled",
    }[decision]
    if decision_type == "stage_review":
        result_payload["stage_review_status"] = status_value
    elif decision_type == "plan_review":
        result_payload["plan_review_status"] = status_value


def _apply_submitted_decision_to_state(
    state_payload: dict[str, Any],
    *,
    decision: str,
    pending_decision: Any,
) -> None:
    if decision not in {"approve", "reject", "cancel"}:
        return
    decision_type = ""
    if isinstance(pending_decision, dict):
        decision_type = str(pending_decision.get("decision_type") or "").strip().lower()
    status_value = {
        "approve": "approved",
        "reject": "rejected",
        "cancel": "cancelled",
    }[decision]
    if decision_type == "stage_review":
        state_payload["stage_review_status"] = status_value
    elif decision_type == "plan_review":
        state_payload["plan_review_status"] = status_value

    app_context = state_payload.get("app_context")
    if isinstance(app_context, dict):
        context = dict(app_context)
        if decision_type == "stage_review":
            context["stage_review_status"] = status_value
        elif decision_type == "plan_review":
            context["plan_review_status"] = status_value
        state_payload["app_context"] = context

    if decision == "approve" and str(state_payload.get("orchestration_phase") or "").strip().lower() in {
        "plan_review",
        "stage_review",
        "awaiting_approval",
    }:
        state_payload["orchestration_phase"] = "stage_ready"
    elif decision in {"reject", "cancel"}:
        state_payload["orchestration_phase"] = "blocked"

    plan_health = state_payload.get("plan_health")
    if not isinstance(plan_health, dict):
        return
    autonomy = plan_health.get("autonomy")
    if not isinstance(autonomy, dict):
        return
    updated_autonomy = dict(autonomy)
    if decision == "approve":
        updated_autonomy.update(
            {
                "status": "ready",
                "can_continue": True,
                "requires_review": False,
                "requires_user": False,
                "next_action": "execute",
                "blockers": [],
            }
        )
    elif decision == "reject":
        updated_autonomy.update(
            {
                "status": "blocked",
                "can_continue": False,
                "requires_review": False,
                "next_action": "recover_or_replan",
                "blockers": ["The pending review was rejected."],
            }
        )
    else:
        updated_autonomy.update(
            {
                "status": "waiting_user",
                "can_continue": False,
                "requires_review": False,
                "requires_user": True,
                "next_action": "resume_after_user",
                "blockers": ["The pending review was cancelled."],
            }
        )
    updated_plan_health = dict(plan_health)
    updated_plan_health["autonomy"] = updated_autonomy
    state_payload["plan_health"] = updated_plan_health


def _pending_decision_from_progress_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    pending_decision = payload.get("pending_decision")
    if _has_pending_decision_payload(pending_decision):
        return pending_decision
    for key in ("execution_state", "state"):
        execution_state = payload.get(key)
        nested_decision = execution_state.get("pending_decision") if isinstance(execution_state, dict) else None
        if _has_pending_decision_payload(nested_decision):
            return nested_decision
    return None


def _overview_expected_run_ids_from_jobs(jobs: list[dict[str, Any]]) -> set[str]:
    expected: set[str] = set()
    for job in jobs:
        if not isinstance(job, dict):
            continue
        status = str(job.get("status") or "").strip().lower()
        if status not in {"running", "approval", "stopping", "completed", "failed", "cancelled", "attention"}:
            continue
        result = job.get("result") if isinstance(job.get("result"), dict) else {}
        run_id = str(result.get("run_id") or "").strip()
        if run_id:
            expected.add(run_id)
    return expected


class TaskQueue:
    def __init__(self, config_path: Path | None) -> None:
        self.config_path = config_path
        self.lock = threading.Lock()
        self.jobs: dict[str, DashboardJob] = {}
        self.cancel_events: dict[str, threading.Event] = {}
        self.decision_events: dict[str, threading.Event] = {}
        self.pending_decisions: dict[str, dict[str, Any]] = {}
        self.decision_responses: dict[str, dict[str, Any]] = {}
        self.active_job_id: str | None = None

    def submit(
        self,
        *,
        task: str,
        planner_mode: str | None,
        dry_run: bool,
        max_steps: int | None,
        pause_after_action: float | None,
        config_overrides: dict[str, Any] | None = None,
        initial_task_graph: dict[str, Any] | None = None,
        initial_plan_review_status: str | None = None,
    ) -> DashboardJob:
        clean_task = task.strip()
        if not clean_task:
            raise ValueError("Task is required.")

        with self.lock:
            if self.active_job_id is not None:
                raise RuntimeError("Another task is running. Please wait for it to finish.")

            resolved_overrides = dict(config_overrides or {})
            config = load_agent_config(
                self.config_path,
                planner_mode=planner_mode,
                dry_run=dry_run,
                max_steps=max_steps,
                pause_after_action=pause_after_action,
                config_overrides=resolved_overrides,
            )
            graph_payload = None
            initial_result = None
            if initial_task_graph is not None:
                task_graph = coerce_initial_task_graph(
                    clean_task,
                    initial_task_graph,
                    max_subgoals=config.max_task_subgoals,
                )
                graph_payload = task_graph.to_dict()
                initial_result = _build_initial_task_graph_result(
                    task=clean_task,
                    task_graph=task_graph,
                    config=config,
                    plan_review_status=initial_plan_review_status,
                )
            job = DashboardJob(
                job_id=uuid.uuid4().hex[:12],
                task=clean_task,
                planner_mode=config.planner_mode,
                dry_run=config.dry_run,
                max_steps=config.max_steps,
                pause_after_action=config.pause_after_action,
                max_run_seconds=config.max_run_seconds,
                config_overrides=resolved_overrides,
                initial_task_graph=graph_payload,
                initial_plan_review_status=initial_plan_review_status,
                result=initial_result,
            )
            self.jobs[job.job_id] = job
            self.cancel_events[job.job_id] = threading.Event()
            self.decision_events[job.job_id] = threading.Event()
            self._seed_pending_decision_from_initial_result_locked(job)
            self.active_job_id = job.job_id

        thread = threading.Thread(
            target=self._run_job,
            args=(job.job_id,),
            name=f"desktop-agent-job-{job.job_id}",
            daemon=True,
        )
        thread.start()
        return job

    def resume(
        self,
        *,
        run_id: str,
        max_steps: int | None = None,
        pause_after_action: float | None = None,
        config_overrides: dict[str, Any] | None = None,
    ) -> DashboardJob:
        clean_run_id = str(run_id or "").strip()
        if not clean_run_id:
            raise ValueError("Run id is required.")

        with self.lock:
            if self.active_job_id is not None:
                raise RuntimeError("Another task is running. Please wait for it to finish.")

            config = load_agent_config(self.config_path)
            details = load_run_details(config.run_root, clean_run_id)
            if details is None:
                raise RuntimeError("Run not found.")
            if _optional_bool(details.get("completed")) is True:
                raise RuntimeError("This run is already complete.")
            if not _details_can_resume(details):
                raise RuntimeError("This run has no saved execution state to resume.")

            resolved_overrides = dict(config_overrides or {})
            effective_config = load_agent_config(
                self.config_path,
                max_steps=max_steps,
                pause_after_action=pause_after_action,
                config_overrides=resolved_overrides,
            )
            initial_result = _build_resume_job_result(details=details, run_id=clean_run_id)
            job = DashboardJob(
                job_id=uuid.uuid4().hex[:12],
                task=str(details.get("task") or clean_run_id),
                planner_mode=str(details.get("planner_mode") or "auto"),
                dry_run=_optional_bool(details.get("dry_run")) or False,
                max_steps=effective_config.max_steps,
                pause_after_action=effective_config.pause_after_action,
                max_run_seconds=effective_config.max_run_seconds,
                resume_run_id=clean_run_id,
                config_overrides=resolved_overrides,
                result=initial_result,
            )
            self.jobs[job.job_id] = job
            self.cancel_events[job.job_id] = threading.Event()
            self.decision_events[job.job_id] = threading.Event()
            self._seed_pending_decision_from_initial_result_locked(job)
            self.active_job_id = job.job_id

        thread = threading.Thread(
            target=self._run_job,
            args=(job.job_id,),
            name=f"desktop-agent-job-{job.job_id}",
            daemon=True,
        )
        thread.start()
        return job

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.lock:
            job = self.jobs.get(job_id)
            return job.to_dict() if job else None

    def list_jobs(self, limit: int = 12) -> list[dict[str, Any]]:
        with self.lock:
            jobs = sorted(self.jobs.values(), key=lambda item: item.created_at, reverse=True)
            return [job.to_dict() for job in jobs[:limit]]

    def active_job(self) -> dict[str, Any] | None:
        with self.lock:
            if self.active_job_id is None:
                return None
            job = self.jobs.get(self.active_job_id)
            return job.to_dict() if job else None

    def clear_history(self) -> int:
        with self.lock:
            if self.active_job_id is not None:
                raise RuntimeError("Another task is running. Please wait for it to finish.")
            cleared = len(self.jobs)
            self.jobs.clear()
            self.cancel_events.clear()
            self.decision_events.clear()
            self.pending_decisions.clear()
            self.decision_responses.clear()
            return cleared

    def cancel_active(self) -> dict[str, Any]:
        with self.lock:
            if self.active_job_id is None:
                raise RuntimeError("No active task is running.")
            job = self.jobs[self.active_job_id]
            cancel_event = self.cancel_events.get(job.job_id)
            if cancel_event is not None:
                cancel_event.set()
            decision_event = self.decision_events.get(job.job_id)
            if decision_event is not None:
                self.decision_responses[job.job_id] = {"decision": "cancel", "note": "Stopped by user."}
                decision_event.set()
            self.pending_decisions.pop(job.job_id, None)
            job.cancel_requested = True
            job.status = "stopping"
            job.result = _clear_pending_decision_from_result(job.result, decision="cancel")
            job.updated_at = time.time()
            return job.to_dict()

    def decide(self, job_id: str, *, decision: str, note: str | None = None) -> dict[str, Any]:
        normalized = _normalize_decision_action(decision)
        if normalized not in {"approve", "reject", "cancel"}:
            raise ValueError("decision must be approve, reject, or cancel.")
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                raise RuntimeError("Job not found.")
            if job.status != "approval":
                raise RuntimeError("This job is not waiting for approval.")
            event = self.decision_events.get(job_id)
            if event is None:
                raise RuntimeError("No approval wait is registered for this job.")
            self.decision_responses[job_id] = {"decision": normalized, "note": note}
            event.set()
            self.pending_decisions.pop(job_id, None)
            job.status = "stopping" if normalized == "cancel" else "running"
            job.result = _clear_pending_decision_from_result(job.result, decision=normalized)
            job.updated_at = time.time()
            return job.to_dict()

    def _seed_pending_decision_from_initial_result_locked(self, job: DashboardJob) -> None:
        if not isinstance(job.result, dict):
            return
        pending_decision = _pending_decision_from_progress_payload(job.result)
        if not pending_decision:
            return
        self.pending_decisions[job.job_id] = dict(pending_decision)
        job.status = "approval"
        job.result = _merge_progress_job_result_payload(
            job.result,
            {"pending_decision": pending_decision},
        )
        job.updated_at = time.time()

    def _apply_decision_response_locked(self, job_id: str, response: dict[str, Any]) -> dict[str, Any]:
        normalized = _normalize_decision_action(response.get("decision"), default="reject")
        response["decision"] = normalized
        event = self.decision_events.get(job_id)
        if event is not None:
            event.clear()
        self.pending_decisions.pop(job_id, None)
        job = self.jobs.get(job_id)
        if job is not None:
            job.status = "stopping" if normalized == "cancel" else "running"
            job.result = _clear_pending_decision_from_result(job.result, decision=normalized)
            job.updated_at = time.time()
        return response

    def _run_job(self, job_id: str) -> None:
        with self.lock:
            job = self.jobs[job_id]
            if job.status != "approval":
                job.status = "running"
            job.started_at = time.time()
            job.updated_at = time.time()
            cancel_event = self.cancel_events.get(job_id)

        try:
            runner = resume_task if job.resume_run_id else run_task
            runner_kwargs = {
                "config_path": self.config_path,
                "planner_mode": job.planner_mode,
                "dry_run": job.dry_run,
                "max_steps": job.max_steps,
                "pause_after_action": job.pause_after_action,
                "config_overrides": job.config_overrides,
                "stop_requested": cancel_event.is_set if cancel_event is not None else None,
                "progress_callback": lambda payload: self._update_job_progress(job_id, payload),
                "decision_callback": lambda payload: self._await_job_decision(job_id, payload),
            }
            if not job.resume_run_id:
                runner_kwargs["initial_task_graph"] = job.initial_task_graph
                runner_kwargs["initial_plan_review_status"] = job.initial_plan_review_status
            result = runner(job.resume_run_id or job.task, **runner_kwargs)
            payload = {
                "task": result.task,
                "completed": result.completed,
                "steps": result.steps,
                "run_dir": str(result.run_dir),
                "run_id": result.run_dir.name,
                "started_at": result.started_at,
                "finished_at": result.finished_at,
                "error": result.error,
                "cancelled": result.cancelled,
                "cancel_reason": result.cancel_reason,
                "requires_human": result.requires_human,
                "interruption_kind": result.interruption_kind,
                "interruption_reason": result.interruption_reason,
            }
            if result.execution_budget is not None:
                payload["execution_budget"] = result.execution_budget
            if result.execution_environment is not None:
                payload["execution_environment"] = result.execution_environment
            if result.execution_state is not None:
                payload["execution_state"] = result.execution_state
            with self.lock:
                if result.completed:
                    job.status = "completed"
                elif result.cancelled:
                    job.status = "cancelled"
                elif result.requires_human:
                    job.status = "attention"
                else:
                    job.status = "failed"
                job.result = _finalize_job_result_payload(job.result, payload)
                job.error = result.error
                job.cancelled = result.cancelled
                job.cancel_reason = result.cancel_reason
                job.started_at = result.started_at
                job.finished_at = result.finished_at
                job.requires_human = result.requires_human
                job.interruption_kind = result.interruption_kind
                job.interruption_reason = result.interruption_reason
                job.updated_at = time.time()
                self.active_job_id = None
        except Exception as exc:  # pragma: no cover - runtime safety
            with self.lock:
                finished_at = time.time()
                job.status = "failed"
                job.error = str(exc)
                job.finished_at = finished_at
                job.requires_human = False
                job.result = _fail_job_result_payload(job.result, error=str(exc), finished_at=finished_at)
                job.updated_at = time.time()
                self.active_job_id = None
        finally:
            with self.lock:
                self.cancel_events.pop(job_id, None)
                self.decision_events.pop(job_id, None)
                self.pending_decisions.pop(job_id, None)
                self.decision_responses.pop(job_id, None)

    def _update_job_progress(self, job_id: str, payload: dict[str, Any]) -> None:
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                return
            current_result = _merge_progress_job_result_payload(job.result, payload)
            pending_decision = _pending_decision_from_progress_payload(payload)
            if pending_decision:
                self.pending_decisions[job_id] = pending_decision
                job.status = "approval"
                job.result = current_result
            elif job.status == "approval":
                job.status = "running"
                self.pending_decisions.pop(job_id, None)
                job.result = _clear_pending_decision_from_result(current_result)
            else:
                job.result = current_result
            if isinstance(payload.get("started_at"), (int, float)):
                job.started_at = float(payload["started_at"])
            job.updated_at = time.time()

    def _await_job_decision(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            job = self.jobs[job_id]
            event = self.decision_events.get(job_id)
            if event is None:
                raise RuntimeError("No approval event is registered for this job.")
            pending_decision = _pending_decision_from_progress_payload(payload)
            if pending_decision is None:
                raise RuntimeError("Approval callback payload did not include a pending decision.")
            self.pending_decisions[job_id] = dict(pending_decision)
            event.clear()
            job.status = "approval"
            execution_state_payload = (
                payload.get("execution_state")
                if isinstance(payload.get("execution_state"), dict)
                else payload.get("state")
            )
            current_result = dict(job.result or {})
            current_result = _merge_progress_job_result_payload(
                current_result,
                {
                    "pending_decision": self.pending_decisions[job_id],
                    "execution_state": execution_state_payload,
                    "step_proposal": payload.get("step_proposal"),
                },
            )
            job.result = current_result
            job.updated_at = time.time()
            buffered_response = self.decision_responses.pop(job_id, None)
            if isinstance(buffered_response, dict):
                return self._apply_decision_response_locked(job_id, dict(buffered_response))
            event.clear()

        while True:
            if event.wait(timeout=0.1):
                break
            cancel_event = self.cancel_events.get(job_id)
            if cancel_event is not None and cancel_event.is_set():
                return {"decision": "cancel", "note": "Stopped by user."}

        with self.lock:
            response = dict(self.decision_responses.pop(job_id, {"decision": "reject"}))
            return self._apply_decision_response_locked(job_id, response)

_TEXT_TEMPLATE_REPLACEMENTS = {
    "__APP_NAME__": APP_NAME,
    "__APP_VERSION__": APP_VERSION,
    "__APP_ASSET_VERSION__": APP_ASSET_VERSION,
}
_RUNTIME_PREFS_UNSET = object()


class RuntimePreferencesStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        self._config_overrides: dict[str, Any] = {}
        self._ui_preferences: dict[str, Any] = {"onboarding_completed": False}
        self._updated_at: float | None = None
        self._load()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "config_overrides": dict(self._config_overrides),
                "ui_preferences": dict(self._ui_preferences),
                "updated_at": self._updated_at,
            }

    def update(
        self,
        *,
        config_overrides: Any = _RUNTIME_PREFS_UNSET,
        ui_preferences: Any = _RUNTIME_PREFS_UNSET,
    ) -> dict[str, Any]:
        with self.lock:
            if config_overrides is not _RUNTIME_PREFS_UNSET:
                self._config_overrides = _clean_config_overrides(config_overrides)
            if ui_preferences is not _RUNTIME_PREFS_UNSET:
                self._ui_preferences = _clean_ui_preferences(ui_preferences, existing=self._ui_preferences)
            self._updated_at = time.time()
            self._persist()
            return {
                "config_overrides": dict(self._config_overrides),
                "ui_preferences": dict(self._ui_preferences),
                "updated_at": self._updated_at,
            }

    def _load(self) -> None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return
        cleaned = _clean_config_overrides(payload.get("config_overrides"))
        cleaned_ui = _clean_ui_preferences(payload.get("ui_preferences"))
        updated_at = payload.get("updated_at")
        self._config_overrides = cleaned
        self._ui_preferences = cleaned_ui
        self._updated_at = float(updated_at) if isinstance(updated_at, (int, float)) else None

    def _persist(self) -> None:
        payload = {
            "config_overrides": self._config_overrides,
            "ui_preferences": self._ui_preferences,
            "updated_at": self._updated_at,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


_CHAT_PROVIDER_ERROR_LIMIT = 320
_VISION_CHAT_COMPAT_MAX_HISTORY = 2
_VISION_CHAT_COMPAT_MAX_MESSAGE_CHARS = 900
_MANAGED_BROWSER_STATUS_CACHE_SECONDS = 10.0
_OVERVIEW_RUNS_CACHE_SECONDS = 1.0
_PROVIDER_ENVIRONMENT_CACHE_SECONDS = 20.0
_PROVIDER_ENVIRONMENT_REFRESH_TIMEOUT_SECONDS = 0.9
_VISION_MODEL_PATTERN = re.compile(r"(^|[\/._:-])vl([\/._:-]|$)")
_MODEL_SIZE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*([bm])", re.I)
_MATH_LATEX_COMMAND_PATTERN = re.compile(
    r"\\(?:frac|sqrt|sum|int|prod|partial|nabla|epsilon|rho|mathbf|mathrm|text|cdot|times|alpha|beta|gamma|delta|theta|lambda|pi|sigma|phi|psi|omega)\b"
)
_MATH_HIGH_RISK_LATEX_PATTERN = re.compile(r"\\(?:begin|end|align|cases|left|right)\b")
_MATH_PARSE_FAILURE_PATTERN = re.compile(r"failed to parse input|parse input at pos", re.I)
_MATH_INLINE_DELIMITER_PATTERN = re.compile(r"(\$\$[\s\S]+?\$\$|\$[^$\n]+\$|\\\([\s\S]+?\\\)|\\\[[\s\S]+?\\\])")
_MATH_TEMPLATE_FRAGMENT_PATTERN = re.compile(r"<\|[^>]+?\|>")
_MATH_BROKEN_ESCAPE_PATTERN = re.compile(r"\\(?:\s|$|[^\\$(){}\[\]^_%&,.:;+\-/*0-9A-Za-z])")


class ChatUIError(ProviderToolError):
    def __init__(self, message: str, *, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.payload = {"error": message}
        if isinstance(payload, dict):
            self.payload.update(payload)


def _provider_error_payload(exc: Exception) -> dict[str, Any]:
    payload = getattr(exc, "payload", None)
    if isinstance(payload, dict) and payload.get("error"):
        return payload
    return {"error": str(exc)}


def _clean_ui_preferences(raw: Any, *, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    base = dict(existing or {})
    if not isinstance(raw, dict):
        return {
            "onboarding_completed": _optional_bool(base.get("onboarding_completed")) or False,
        }

    if "onboarding_completed" in raw:
        parsed_onboarding = _optional_bool(raw.get("onboarding_completed"))
        if parsed_onboarding is not None:
            base["onboarding_completed"] = parsed_onboarding
    return {
        "onboarding_completed": _optional_bool(base.get("onboarding_completed")) or False,
    }


def _open_path_in_file_manager(path: Path) -> None:
    target = path.resolve()
    if sys.platform == "win32":
        os.startfile(str(target))
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
        return
    subprocess.Popen(["xdg-open", str(target)])


def _extract_latest_user_message(messages: list[dict[str, str]]) -> str:
    return next(
        (item["content"] for item in reversed(messages) if item.get("role") == "user"),
        "",
    )


def _contains_math_markup(text: str) -> bool:
    source = str(text or "")
    if not source:
        return False
    return bool(_MATH_LATEX_COMMAND_PATTERN.search(source)) or any(
        token in source for token in ("$", "\\(", "\\)", "\\[", "\\]", "^", "_")
    )


def _looks_like_math_formula_output_unstable(text: str) -> bool:
    raw = str(text or "")
    if not raw:
        return False
    if "\ufffd" in raw:
        return True
    if _MATH_TEMPLATE_FRAGMENT_PATTERN.search(raw):
        return True
    if _MATH_BROKEN_ESCAPE_PATTERN.search(raw):
        return True
    if not _contains_math_markup(raw):
        return False
    if raw.count("$") % 2 == 1:
        return True
    if raw.count("\\(") != raw.count("\\)"):
        return True
    if raw.count("\\[") != raw.count("\\]"):
        return True
    if raw.count("{") != raw.count("}"):
        return True
    return False


def _looks_like_math_provider_failure(detail: str) -> bool:
    source = str(detail or "")
    if not source:
        return False
    if "\ufffd" in source:
        return True
    if _MATH_TEMPLATE_FRAGMENT_PATTERN.search(source):
        return True
    has_math_markup = _contains_math_markup(source)
    if _MATH_PARSE_FAILURE_PATTERN.search(source):
        return has_math_markup or bool(_MATH_BROKEN_ESCAPE_PATTERN.search(source))
    if _MATH_BROKEN_ESCAPE_PATTERN.search(source):
        return True
    if not has_math_markup:
        return False
    if source.count("$") % 2 == 1:
        return True
    if source.count("\\(") != source.count("\\)"):
        return True
    if source.count("\\[") != source.count("\\]"):
        return True
    if source.count("{") != source.count("}"):
        return True
    return False


def _format_chat_connection_error(api_base: str, exc: Exception) -> str:
    return (
        f"Could not reach the chat model at {api_base}. "
        "Check the provider, base URL, API key, and local model server. "
        f"Original error: {exc}"
    )


def _truncate_chat_provider_detail(value: Any, *, limit: int = _CHAT_PROVIDER_ERROR_LIMIT) -> str:
    text = " ".join(str(value or "").replace("\r", "\n").split())
    if not text:
        return "<empty>"
    if len(text) <= limit:
        return text
    return f"{text[: max(limit - 3, 1)]}..."


def _extract_chat_provider_detail(response: Any) -> str:
    payload = None
    try:
        payload = response.json()
    except Exception:
        payload = None

    if isinstance(payload, dict):
        error_value = payload.get("error")
        if isinstance(error_value, dict):
            for key in ("message", "detail", "type", "code"):
                candidate = error_value.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return _truncate_chat_provider_detail(candidate)
        for key in ("error", "message", "detail"):
            candidate = payload.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return _truncate_chat_provider_detail(candidate)
    elif isinstance(payload, str) and payload.strip():
        return _truncate_chat_provider_detail(payload)

    return _truncate_chat_provider_detail(getattr(response, "text", "") or "")


def _format_chat_provider_error(api_base: str, response: Any) -> str:
    status_code = getattr(response, "status_code", None)
    status_label = f"HTTP {status_code}" if status_code else "an unknown status"
    detail = _extract_chat_provider_detail(response)
    return (
        f"The chat model rejected the request at {api_base} ({status_label}). "
        f"Provider response: {detail}"
    )


def _snapshot_chat_model_entries(snapshot: Any) -> list[ProviderModelEntry]:
    entries: list[ProviderModelEntry] = []
    seen: set[str] = set()

    for item in getattr(snapshot, "catalog_models", []) or []:
        if not isinstance(item, ProviderModelEntry):
            continue
        if not item.model_id or item.model_id in seen:
            continue
        entries.append(item)
        seen.add(item.model_id)

    for model_id in getattr(snapshot, "loaded_models", []) or []:
        normalized = str(model_id or "").strip()
        if not normalized or normalized in seen:
            continue
        entries.append(ProviderModelEntry(model_id=normalized, label=normalized, loaded=True))
        seen.add(normalized)

    return entries


def _is_embedding_model(entry: ProviderModelEntry) -> bool:
    source = f"{entry.model_id} {entry.kind or ''}".lower()
    return any(token in source for token in ("embedding", "embed", "rerank", "bge"))


def _is_vision_model(entry: ProviderModelEntry) -> bool:
    source = f"{entry.model_id} {entry.kind or ''}".lower()
    return bool(_VISION_MODEL_PATTERN.search(source)) or any(
        token in source
        for token in ("vision", "llava", "moondream", "pixtral", "minicpm-v", "internvl", "visual")
    )


def _extract_model_billions(entry: ProviderModelEntry) -> float | None:
    source = f"{entry.model_id} {entry.kind or ''}".lower()
    match = _MODEL_SIZE_PATTERN.search(source)
    if not match:
        return None
    size = float(match.group(1))
    unit = match.group(2).lower()
    return size if unit == "b" else size / 1000.0


def _score_chat_model(entry: ProviderModelEntry) -> int:
    if _is_embedding_model(entry):
        return -1000
    if _is_vision_model(entry):
        return -100

    source = f"{entry.model_id} {entry.kind or ''}".lower()
    score = 0
    if entry.loaded:
        score += 5
    if any(token in source for token in ("chat", "instruct")):
        score += 4
    if any(token in source for token in ("thinking", "reasoning", "r1")):
        score -= 6
    if "coder" in source:
        score -= 3

    size_in_billions = _extract_model_billions(entry)
    if size_in_billions is not None:
        if size_in_billions > 70:
            score -= 30
        elif size_in_billions > 30:
            score -= 15
        elif size_in_billions > 20:
            score -= 8
        elif size_in_billions < 2:
            score -= 4

    return score


def _pick_best_chat_model(entries: list[ProviderModelEntry]) -> str | None:
    if not entries:
        return None

    best_entry = entries[0]
    best_score = _score_chat_model(best_entry)

    for entry in entries[1:]:
        score = _score_chat_model(entry)
        if score > best_score:
            best_entry = entry
            best_score = score

    return best_entry.model_id


def _pick_chat_model_name(snapshot: Any) -> str | None:
    entries = _snapshot_chat_model_entries(snapshot)
    if not entries:
        return None

    return _pick_best_chat_model(entries)


def _pick_text_chat_model_name(snapshot: Any, *, exclude_model: str | None = None) -> str | None:
    excluded = str(exclude_model or "").strip()
    entries = [
        entry
        for entry in _snapshot_chat_model_entries(snapshot)
        if not _is_embedding_model(entry)
        and not _is_vision_model(entry)
        and entry.model_id != excluded
    ]
    if not entries:
        return None
    return _pick_best_chat_model(entries)


def _looks_like_placeholder_chat_output(text: str) -> bool:
    normalized = "".join(str(text or "").split())
    if len(normalized) < 16:
        return False
    return bool(normalized) and set(normalized) <= set("/\\|_-.~=*+?？�")


def _is_vision_model_name(model_name: str) -> bool:
    normalized = str(model_name or "").strip()
    if not normalized:
        return False
    return _is_vision_model(ProviderModelEntry(model_id=normalized, label=normalized))


def _trim_chat_message_content(content: str, *, limit: int) -> str:
    normalized = str(content or "").replace("\r\n", "\n").strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[-limit:]


def _prepare_chat_messages(
    messages: list[dict[str, str]],
    *,
    compatibility_mode: bool,
) -> list[dict[str, str]]:
    if not compatibility_mode:
        return list(messages)
    if not messages:
        return []

    latest_user_index = next(
        (index for index in range(len(messages) - 1, -1, -1) if messages[index].get("role") == "user"),
        len(messages) - 1,
    )
    start_index = latest_user_index
    if latest_user_index > 0 and messages[latest_user_index - 1].get("role") == "assistant":
        start_index = latest_user_index - 1

    selected = messages[start_index : latest_user_index + 1]
    selected = selected[-_VISION_CHAT_COMPAT_MAX_HISTORY:]
    return [
        {
            "role": str(item.get("role") or "").strip(),
            "content": _trim_chat_message_content(
                str(item.get("content") or ""),
                limit=_VISION_CHAT_COMPAT_MAX_MESSAGE_CHARS,
            ),
        }
        for item in selected
        if str(item.get("role") or "").strip() in {"user", "assistant"}
        and _trim_chat_message_content(
            str(item.get("content") or ""),
            limit=_VISION_CHAT_COMPAT_MAX_MESSAGE_CHARS,
        )
    ]


def _order_provider_catalog_for_display(
    entries: list[ProviderModelEntry],
    *,
    preferred_model: str | None,
) -> list[ProviderModelEntry]:
    preferred = str(preferred_model or "").strip()
    indexed_entries = list(enumerate(entries))
    indexed_entries.sort(
        key=lambda pair: (
            0
            if preferred and pair[1].model_id == preferred
            else 1
            if pair[1].loaded
            else 2,
            pair[0],
        )
    )
    return [entry for _, entry in indexed_entries]


class DashboardApp:
    def __init__(self, host: str, port: int, config_path: str | Path | None = None) -> None:
        self.host = host
        self.port = port
        self.boot_id = uuid.uuid4().hex
        package_root = _runtime_package_root()
        self.ui_root = package_root / "dashboard_assets"
        self.project_root = package_root.parent
        self.config_path = discover_config_path(config_path)
        self.queue = TaskQueue(self.config_path)
        self.model_switch_lock = threading.Lock()
        config = load_agent_config(self.config_path)
        self.run_root = config.run_root
        self.runtime_preferences = RuntimePreferencesStore(runtime_preferences_path_for(self.config_path))
        self.cache_root = default_cache_root()
        self._managed_browser_status_lock = threading.Lock()
        self._managed_browser_status_cache: dict[str, Any] | None = None
        self._managed_browser_status_refreshing = False
        self._overview_runs_lock = threading.Lock()
        self._overview_runs_cache: dict[str, Any] | None = None
        self._overview_runs_refreshing = False
        self._provider_environment_lock = threading.Lock()
        self._provider_environment_cache: dict[str, dict[str, Any]] = {}
        self._provider_environment_refreshing: set[str] = set()

    def create_server(self) -> ThreadingHTTPServer:
        app = self

        class DashboardHandler(BaseHTTPRequestHandler):
            server_version = "DesktopAgentDashboard/2.0"

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                path = unquote(parsed.path)

                if path in {"/", "/index.html"}:
                    return self._serve_file(app.ui_root / "index.html", "text/html; charset=utf-8")
                if path == "/favicon.ico":
                    return self._serve_file(app.ui_root / "icons" / "app-icon-64.png", "image/png")
                if path.startswith("/assets/"):
                    return self._serve_asset(path)
                if path == "/api/meta":
                    return self._send_json(app.meta())
                if path == "/api/runtime-preferences":
                    return self._send_json(app.runtime_preferences.snapshot())
                if path == "/api/system/paths":
                    return self._send_json(app.system_paths())
                if path == "/api/system/environment-check":
                    return self._send_json(app.environment_check())
                if path == "/api/system/display-detection":
                    return self._send_json(app.display_detection())
                if path == "/api/help":
                    params = parse_qs(parsed.query)
                    locale = params.get("locale", ["zh-CN"])[0]
                    audience = params.get("audience", ["user"])[0]
                    return self._send_json(app.help_content(locale=locale, audience=audience))
                if path == "/api/overview":
                    return self._send_json(app.overview())
                if path == "/api/jobs":
                    params = parse_qs(parsed.query)
                    limit = _parse_int(params.get("limit", ["12"])[0], default=12)
                    return self._send_json({"items": app.queue.list_jobs(limit=limit)})
                if path.startswith("/api/jobs/"):
                    job_id = path.removeprefix("/api/jobs/")
                    job = app.queue.get_job(job_id)
                    if job is None:
                        return self._send_error(HTTPStatus.NOT_FOUND, "Job not found.")
                    return self._send_json(job)
                if path == "/api/runs":
                    params = parse_qs(parsed.query)
                    limit = _parse_int(params.get("limit", ["18"])[0], default=18)
                    return self._send_json({"items": list_runs(app.run_root, limit=limit)})
                if path.startswith("/api/runs/"):
                    run_id = path.removeprefix("/api/runs/")
                    details = load_run_details(app.run_root, run_id)
                    if details is None:
                        return self._send_error(HTTPStatus.NOT_FOUND, "Run not found.")
                    return self._send_json(details)
                if path.startswith("/artifacts/"):
                    return self._serve_artifact(path)
                return self._send_error(HTTPStatus.NOT_FOUND, "Route not found.")

            def do_POST(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                path = unquote(parsed.path)
                body = self._read_json_body()
                if body is None:
                    return self._send_error(HTTPStatus.BAD_REQUEST, "Expected JSON body.")

                if path == "/api/tasks":
                    try:
                        task_text = str(body.get("task", ""))
                        resolved_overrides = app._resolve_request_config_overrides(body.get("config_overrides"))
                        initial_task_graph = app._resolve_initial_task_graph(
                            task=task_text,
                            raw_task_graph=body.get("task_graph"),
                            raw_task_graph_signature=body.get("task_graph_signature"),
                            config_overrides=resolved_overrides,
                        )
                        initial_plan_review_status = app._resolve_initial_plan_review_status(
                            task=task_text,
                            task_graph=initial_task_graph,
                            raw_review_status=body.get("task_graph_review_status"),
                            raw_review_signature=body.get("task_graph_review_signature"),
                            config_overrides=resolved_overrides,
                        )
                        job = app.queue.submit(
                            task=task_text,
                            planner_mode="auto",
                            dry_run=False,
                            max_steps=_optional_int(body.get("max_steps")),
                            pause_after_action=_optional_float(body.get("pause_after_action")),
                            config_overrides=resolved_overrides,
                            initial_task_graph=initial_task_graph,
                            initial_plan_review_status=initial_plan_review_status,
                        )
                    except ValueError as exc:
                        return self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    except RuntimeError as exc:
                        return self._send_error(HTTPStatus.CONFLICT, str(exc))
                    return self._send_json(job.to_dict(), status=HTTPStatus.ACCEPTED)

                if path == "/api/tasks/preview":
                    try:
                        resolved_overrides = app._resolve_request_config_overrides(body.get("config_overrides"))
                        payload = app.preview_task(
                            task=str(body.get("task", "")),
                            config_overrides=resolved_overrides,
                        )
                    except ValueError as exc:
                        return self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    return self._send_json(payload)

                if path == "/api/runtime-preferences":
                    snapshot = app.runtime_preferences.update(
                        config_overrides=body.get("config_overrides", _RUNTIME_PREFS_UNSET),
                        ui_preferences=body.get("ui_preferences", _RUNTIME_PREFS_UNSET),
                    )
                    return self._send_json(snapshot, status=HTTPStatus.ACCEPTED)

                if path == "/api/system/open-path":
                    try:
                        payload = app.open_diagnostic_path(str(body.get("key", "")).strip())
                    except ValueError as exc:
                        return self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    except OSError as exc:
                        return self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
                    return self._send_json(payload, status=HTTPStatus.ACCEPTED)

                if path == "/api/tasks/stop":
                    try:
                        job = app.queue.cancel_active()
                    except RuntimeError as exc:
                        return self._send_error(HTTPStatus.CONFLICT, str(exc))
                    return self._send_json(job, status=HTTPStatus.ACCEPTED)

                if path == "/api/history/clear":
                    try:
                        payload = app.clear_history()
                    except RuntimeError as exc:
                        return self._send_error(HTTPStatus.CONFLICT, str(exc))
                    return self._send_json(payload, status=HTTPStatus.ACCEPTED)

                if path.startswith("/api/jobs/") and path.endswith("/decision"):
                    job_id = path.removeprefix("/api/jobs/").removesuffix("/decision").strip("/")
                    try:
                        job = app.queue.decide(
                            job_id,
                            decision=str(body.get("decision", "")).strip(),
                            note=str(body.get("note", "")).strip() or None,
                        )
                    except (RuntimeError, ValueError) as exc:
                        return self._send_error(HTTPStatus.CONFLICT, str(exc))
                    return self._send_json(job, status=HTTPStatus.ACCEPTED)

                if path.startswith("/api/runs/") and path.endswith("/resume"):
                    run_id = path.removeprefix("/api/runs/").removesuffix("/resume").strip("/")
                    try:
                        resolved_overrides = app._resolve_request_config_overrides(body.get("config_overrides"))
                        job = app.queue.resume(
                            run_id=run_id,
                            max_steps=_optional_int(body.get("max_steps")),
                            pause_after_action=_optional_float(body.get("pause_after_action")),
                            config_overrides=resolved_overrides,
                        )
                    except (RuntimeError, ValueError) as exc:
                        return self._send_error(HTTPStatus.CONFLICT, str(exc))
                    return self._send_json(job.to_dict(), status=HTTPStatus.ACCEPTED)

                if path == "/api/chat":
                    try:
                        resolved_overrides = app._resolve_request_config_overrides(body.get("config_overrides"))
                        payload = app.chat_reply(
                            messages=body.get("messages"),
                            config_overrides=resolved_overrides,
                            session_meta=body.get("session_meta"),
                            recovery_context=body.get("recovery_context"),
                        )
                    except ValueError as exc:
                        return self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    except ProviderToolError as exc:
                        return self._send_json(_provider_error_payload(exc), status=HTTPStatus.BAD_REQUEST)
                    return self._send_json(payload)

                if path == "/api/chat/stream":
                    resolved_overrides = app._resolve_request_config_overrides(body.get("config_overrides"))
                    return self._send_event_stream(
                        app.chat_reply_stream(
                            messages=body.get("messages"),
                            config_overrides=resolved_overrides,
                            session_meta=body.get("session_meta"),
                            recovery_context=body.get("recovery_context"),
                        )
                    )

                if path == "/api/provider/models":
                    try:
                        snapshot = app.provider_models(
                            app._resolve_request_config_overrides(body.get("config_overrides"))
                        )
                    except ProviderToolError as exc:
                        return self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    return self._send_json(snapshot)

                if path == "/api/provider/load-model":
                    try:
                        resolved_overrides = app._resolve_request_config_overrides(body.get("config_overrides"))
                        payload = app.provider_load_model(
                            config_overrides=resolved_overrides,
                            model_id=str(body.get("model_id", "")).strip(),
                            unload_first=_optional_bool(body.get("unload_first")) or False,
                        )
                    except ProviderToolError as exc:
                        return self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    return self._send_json(payload)

                return self._send_error(HTTPStatus.NOT_FOUND, "Route not found.")

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
                return

            def _read_json_body(self) -> dict[str, Any] | None:
                content_length = self.headers.get("Content-Length")
                if not content_length:
                    return {}
                try:
                    raw = self.rfile.read(int(content_length))
                    if not raw:
                        return {}
                    return json.loads(raw.decode("utf-8"))
                except (ValueError, json.JSONDecodeError):
                    return None

            def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_event_stream(self, events: Any) -> None:
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                try:
                    for event_name, payload in events:
                        self._write_event_stream_event(event_name, payload)
                except (BrokenPipeError, ConnectionResetError):
                    return
                finally:
                    self.close_connection = True

            def _write_event_stream_event(self, event_name: str, payload: dict[str, Any]) -> None:
                body = (
                    f"event: {event_name}\n"
                    f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                ).encode("utf-8")
                self.wfile.write(body)
                self.wfile.flush()

            def _send_error(self, status: HTTPStatus, message: str) -> None:
                self._send_json({"error": message}, status=status)

            def _serve_asset(self, path: str) -> None:
                relative_path = path.removeprefix("/assets/")
                asset_path = (app.ui_root / relative_path).resolve()
                try:
                    asset_path.relative_to(app.ui_root.resolve())
                except ValueError:
                    return self._send_error(HTTPStatus.NOT_FOUND, "Asset not found.")
                if not asset_path.exists():
                    return self._send_error(HTTPStatus.NOT_FOUND, "Asset not found.")
                content_type, _ = mimetypes.guess_type(asset_path.name)
                return self._serve_file(asset_path, content_type or "application/octet-stream")

            def _serve_artifact(self, path: str) -> None:
                parts = path.split("/", 3)
                if len(parts) != 4:
                    return self._send_error(HTTPStatus.NOT_FOUND, "Artifact not found.")
                _, _, run_id, artifact_name = parts
                artifact_path = resolve_artifact_path(app.run_root, run_id, artifact_name)
                if artifact_path is None:
                    return self._send_error(HTTPStatus.NOT_FOUND, "Artifact not found.")
                content_type, _ = mimetypes.guess_type(artifact_path.name)
                return self._serve_file(artifact_path, content_type or "application/octet-stream")

            def _serve_file(
                self,
                path: Path,
                content_type: str,
                *,
                cache_control: str | None = None,
            ) -> None:
                try:
                    if content_type.startswith("text/") or "javascript" in content_type or "json" in content_type:
                        text_payload = path.read_text(encoding="utf-8")
                        for placeholder, replacement in _TEXT_TEMPLATE_REPLACEMENTS.items():
                            text_payload = text_payload.replace(placeholder, replacement)
                        payload = text_payload.encode("utf-8")
                    else:
                        payload = path.read_bytes()
                except OSError:
                    return self._send_error(HTTPStatus.NOT_FOUND, "File not found.")
                resolved_path = path.resolve()
                ui_root = app.ui_root.resolve()
                if cache_control is None:
                    try:
                        resolved_path.relative_to(ui_root)
                        cache_control = "no-store"
                    except ValueError:
                        cache_control = "no-cache"
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", cache_control)
                self.end_headers()
                self.wfile.write(payload)

        return ThreadingHTTPServer((self.host, self.port), DashboardHandler)

    def meta(self) -> dict[str, Any]:
        config = load_agent_config(self.config_path)
        dom_status = dom_backend_status(config.browser_dom_backend)
        diagnostics = self.system_paths()
        managed_browser = self._managed_browser_status(config)
        return {
            "title": APP_NAME,
            "version": APP_VERSION,
            "publisher": APP_NAME,
            "default_locale": "zh-CN",
            "chat_launch_id": self.boot_id,
            "runtime_mode": "packaged" if is_frozen_runtime() else "source",
            "diagnostics": diagnostics,
            "ui_languages": [
                {"value": "zh-CN", "label": "简体中文"},
                {"value": "en-US", "label": "English"},
            ],
            "config_path": str(self.config_path) if self.config_path else None,
            "defaults": {
                "planner_mode": "auto",
                "dry_run": False,
                "max_steps": config.max_steps,
                "max_run_seconds": config.max_run_seconds,
                "pause_after_action": config.pause_after_action,
                "cursor_motion_enabled": config.cursor_motion_enabled,
                "cursor_motion_duration": config.cursor_motion_duration,
                "primary_model_profile": config.primary_model_profile,
                "fallback_model_profile": config.fallback_model_profile,
                "model_provider": config.model_provider,
                "model_base_url": config.model_base_url,
                "model_name": config.model_name,
                "model_api_key": config.model_api_key or "",
                "model_request_timeout": config.model_request_timeout,
                "task_graph_request_timeout": config.task_graph_request_timeout,
                "model_auto_discover": config.model_auto_discover,
                "model_structured_output": config.model_structured_output,
                "default_surface_policy": config.default_surface_policy,
                "managed_browser_enabled": config.managed_browser_enabled,
                "external_browser_attach_enabled": config.external_browser_attach_enabled,
                "safe_mode_enabled": config.safe_mode_enabled,
                "user_input_preemption_policy": config.user_input_preemption_policy,
                "browser_runtime_transport": config.browser_runtime_transport,
                "browser_profile_strategy": config.browser_profile_strategy,
                "desktop_autonomy_mode": config.desktop_autonomy_mode,
                "approval_policy": config.approval_policy,
                "complex_task_planning": config.complex_task_planning,
                "plan_review_policy": config.plan_review_policy,
                "max_task_subgoals": config.max_task_subgoals,
                "max_subgoal_retries": config.max_subgoal_retries,
                "orchestrator_mode": config.orchestrator_mode,
                "stage_review_policy": config.stage_review_policy,
                "task_workspace_enabled": config.task_workspace_enabled,
                "max_replans_per_run": config.max_replans_per_run,
                "max_failures_per_subgoal": config.max_failures_per_subgoal,
                "replan_on_recoverable_error": config.replan_on_recoverable_error,
                "recoverable_error_retry_limit": config.recoverable_error_retry_limit,
                "enabled_capabilities": list(config.enabled_capabilities),
                "driver_preferences": list(config.driver_preferences),
                "plugin_modules": list(getattr(config, "plugin_modules", []) or []),
                "plugin_fail_fast": bool(getattr(config, "plugin_fail_fast", False)),
                "shell_recipe_policy": config.shell_recipe_policy,
                "browser_control_mode": config.browser_control_mode,
                "browser_dom_backend": config.browser_dom_backend,
                "browser_dom_timeout": config.browser_dom_timeout,
                "browser_headless": config.browser_headless,
                "browser_channel": config.browser_channel or "",
                "browser_executable_path": config.browser_executable_path or "",
                "display_override_enabled": config.display_override_enabled,
                "display_override_monitor_device_name": config.display_override_monitor_device_name or "",
                "display_override_dpi_scale": config.display_override_dpi_scale or "",
                "display_override_work_area_left": config.display_override_work_area_left,
                "display_override_work_area_top": config.display_override_work_area_top,
                "display_override_work_area_width": config.display_override_work_area_width,
                "display_override_work_area_height": config.display_override_work_area_height,
            },
            "dom_status": {
                "available": dom_status.available,
                "backend": dom_status.backend,
                "detail": dom_status.detail,
            },
            "managed_browser_status": managed_browser,
            "planner_modes": [
                {"value": "auto", "label": "Auto"},
                {"value": "rule", "label": "Rule"},
                {"value": "vlm", "label": "VLM"},
            ],
            "autonomy_mode_presets": desktop_autonomy_mode_presets(),
            "model_providers": [
                {
                    "value": "lmstudio_local",
                    "label": "Local LM Studio",
                    "description": "Use your local LM Studio OpenAI-compatible server.",
                    "base_url": "http://127.0.0.1:1234/v1",
                    "api_key_required": False,
                    "auto_discover": True,
                    "supports_model_refresh": True,
                    "supports_model_load": True,
                    "portal_url": "http://127.0.0.1:1234",
                    "docs_url": None,
                    "purchase_url": None,
                },
                {
                    "value": "openai_api",
                    "label": "OpenAI API",
                    "description": "Use OpenAI's hosted API and manage billing or keys in the platform console.",
                    "base_url": "https://api.openai.com/v1",
                    "api_key_required": True,
                    "auto_discover": False,
                    "supports_model_refresh": True,
                    "supports_model_load": False,
                    "portal_url": "https://platform.openai.com/",
                    "docs_url": "https://platform.openai.com/docs/overview",
                    "purchase_url": "https://platform.openai.com/",
                },
                {
                    "value": "openai_compatible",
                    "label": "OpenAI-Compatible API",
                    "description": "Use a third-party hosted API that follows the OpenAI chat format.",
                    "base_url": "https://api.openai.com/v1",
                    "api_key_required": True,
                    "auto_discover": False,
                    "supports_model_refresh": True,
                    "supports_model_load": False,
                    "portal_url": None,
                    "docs_url": None,
                    "purchase_url": None,
                },
                {
                    "value": "custom",
                    "label": "Custom Provider",
                    "description": "Bring your own endpoint and tune the request settings manually.",
                    "base_url": config.model_base_url,
                    "api_key_required": False,
                    "auto_discover": config.model_auto_discover,
                    "supports_model_refresh": True,
                    "supports_model_load": False,
                    "portal_url": None,
                    "docs_url": None,
                    "purchase_url": None,
                },
            ],
            "structured_output_modes": [
                {"value": "auto", "label": "Auto"},
                {"value": "json_schema", "label": "JSON Schema"},
                {"value": "json_object", "label": "JSON Object"},
                {"value": "off", "label": "Off"},
            ],
            "surface_policies": [
                {"value": "current_user_desktop", "label": "Current User Desktop"},
                {"value": "managed_aoryn_browser", "label": "Managed Aoryn Browser"},
                {"value": "external_browser_attach", "label": "External Browser Attach"},
                {"value": "safe_mode_desktop", "label": "Safe Mode Desktop"},
            ],
            "user_input_preemption_policies": [
                {"value": "pause_and_resume", "label": "Pause And Resume"},
                {"value": "ignore", "label": "Ignore"},
            ],
            "browser_runtime_transports": [
                {"value": "local_http", "label": "Local HTTP"},
                {"value": "local_ipc", "label": "Local IPC"},
            ],
            "browser_profile_strategies": [
                {"value": "separate_managed_profile", "label": "Separate Managed Profile"},
            ],
            "browser_control_modes": [
                {"value": "hybrid", "label": "Hybrid GUI + DOM"},
            ],
            "browser_dom_backends": [
                {"value": "playwright", "label": "Playwright"},
            ],
            "browser_channels": [
                {"value": "", "label": "System default"},
                {"value": "msedge", "label": "Microsoft Edge"},
                {"value": "chrome", "label": "Google Chrome"},
                {"value": "firefox", "label": "Mozilla Firefox"},
            ],
            "presets": [
                {"id": "visit_docs", "label": "Open Docs", "task": "visit openai.com/docs"},
                {"id": "dom_follow_up", "label": "Open and Continue", "task": "visit openai.com and click login"},
                {"id": "shopping_search", "label": "Find a Product", "task": "shop for high-value men's pants on amazon"},
            ],
            "workflow_recipes": [
                {
                    "id": "ordered_browser_task",
                    "label": "Open, Click, Continue",
                    "task": "visit openai.com and click login and then type your email",
                    "hint": "Start with the page you want, then list the next action so Aoryn can keep moving without repeating the first step.",
                },
                {
                    "id": "shopping_refine",
                    "label": "Filter and Refine",
                    "task": "shop for high-value men's pants on amazon and filter by style and choose black and sort by price low to high",
                    "hint": "Useful when you want Aoryn to narrow a page step by step instead of comparing everything at once.",
                },
                {
                    "id": "shopping_compare",
                    "label": "Shortlist and Compare",
                    "task": "shop for high-value men's pants on amazon and sort by customer review and filter by price range",
                    "hint": "Good for reducing a long result list before you pause and review the best options.",
                },
                {
                    "id": "login_flow",
                    "label": "Login Warm-up",
                    "task": "visit openai.com and click login",
                    "hint": "A low-risk first browser task that confirms page opening, clicking, and DOM follow-up are working.",
                },
                {
                    "id": "provider_check",
                    "label": "Docs Check",
                    "task": "visit platform.openai.com/docs and click API reference",
                    "hint": "Useful for checking provider links, docs navigation, and model setup before a longer run.",
                },
            ],
            "documentation_links": [
                {
                    "id": "openai_overview",
                    "label": "OpenAI Platform Overview",
                    "url": "https://platform.openai.com/docs/overview",
                    "description": "Official platform onboarding, model access, and provider setup guidance.",
                    "source": "OpenAI",
                },
                {
                    "id": "openai_prompting",
                    "label": "Prompting Best Practices",
                    "url": "https://help.openai.com/en/articles/6654000-best-practices-for-prompting",
                    "description": "Official advice on writing specific, structured prompts and using examples well.",
                    "source": "OpenAI",
                },
                {
                    "id": "browser_use_readme",
                    "label": "browser-use README",
                    "url": "https://github.com/browser-use/browser-use",
                    "description": "A mature open-source browser agent project with practical workflow patterns and setup notes.",
                    "source": "GitHub",
                },
            ],
        }

    def help_content(self, *, locale: str = "zh-CN", audience: str = "user") -> dict[str, Any]:
        normalized_locale = normalize_help_locale(locale)
        normalized_audience = _normalize_help_audience(audience)
        return {
            "title": (
                "Advanced Docs"
                if normalized_locale == "en-US" and normalized_audience == "developer"
                else "高级文档"
                if normalized_audience == "developer"
                else "Help Center"
                if normalized_locale == "en-US"
                else "帮助中心"
            ),
            "locale": normalized_locale,
            "audience": normalized_audience,
            "markdown": (
                load_help_markdown(resolve_help_path(normalized_locale))
                if normalized_audience == "developer"
                else _build_user_help_markdown(normalized_locale)
            ),
        }

    def overview(self) -> dict[str, Any]:
        active_job = self.queue.active_job()
        jobs = self.queue.list_jobs(limit=8)
        return {
            "meta": self.meta(),
            "runtime_preferences": self.runtime_preferences.snapshot(),
            "active_job": active_job,
            "jobs": jobs,
            "runs": self._overview_runs(
                limit=12,
                expected_run_ids=_overview_expected_run_ids_from_jobs(jobs),
            ),
        }

    def clear_history(self) -> dict[str, Any]:
        jobs_cleared = self.queue.clear_history()
        runs_cleared = clear_runs(self.run_root)
        with self._overview_runs_lock:
            self._overview_runs_cache = None
            self._overview_runs_refreshing = False
        return {
            "ok": True,
            "jobs_cleared": jobs_cleared,
            "runs_cleared": runs_cleared,
        }

    def _overview_runs(self, *, limit: int, expected_run_ids: set[str] | None = None) -> list[dict[str, Any]]:
        now = time.time()
        expected_ids = {run_id for run_id in (expected_run_ids or set()) if run_id}
        with self._overview_runs_lock:
            cached = self._overview_runs_cache
            cache_miss = cached is None or int(cached.get("limit") or 0) != int(limit)
            cached_run_ids = {
                str(item.get("id") or "").strip()
                for item in (cached.get("items", []) if isinstance(cached, dict) else [])
                if isinstance(item, dict)
            }
            cache_missing_expected = bool(expected_ids and not expected_ids.issubset(cached_run_ids))
            cache_stale = cached is not None and now - float(cached.get("updated_at") or 0.0) >= _OVERVIEW_RUNS_CACHE_SECONDS
            if cache_miss or cache_missing_expected:
                try:
                    items = list_runs(self.run_root, limit=limit)
                except Exception:
                    items = []
                self._overview_runs_cache = {
                    "limit": int(limit),
                    "updated_at": now,
                    "items": [dict(item) for item in items if isinstance(item, dict)],
                }
                return [dict(item) for item in self._overview_runs_cache["items"]]
            if not self._overview_runs_refreshing and cache_stale:
                self._overview_runs_refreshing = True
                threading.Thread(
                    target=self._refresh_overview_runs,
                    kwargs={"limit": int(limit)},
                    name="dashboard-overview-runs",
                    daemon=True,
                ).start()
            if cached is not None and int(cached.get("limit") or 0) == int(limit):
                return [dict(item) for item in cached.get("items", []) if isinstance(item, dict)]
        return []

    def _refresh_overview_runs(self, *, limit: int) -> None:
        try:
            items = list_runs(self.run_root, limit=limit)
        except Exception:
            items = []
        with self._overview_runs_lock:
            self._overview_runs_cache = {
                "limit": int(limit),
                "updated_at": time.time(),
                "items": [dict(item) for item in items if isinstance(item, dict)],
            }
            self._overview_runs_refreshing = False

    def _managed_browser_status(self, config: Any) -> dict[str, Any]:
        now = time.time()
        signature = _managed_browser_status_signature(config)
        with self._managed_browser_status_lock:
            cached = self._managed_browser_status_cache
            if (
                cached
                and cached.get("signature") == signature
                and now - float(cached.get("updated_at") or 0.0) < _MANAGED_BROWSER_STATUS_CACHE_SECONDS
            ):
                return dict(cached.get("payload") or _default_managed_browser_status(config))
            if not self._managed_browser_status_refreshing:
                self._managed_browser_status_refreshing = True
                threading.Thread(
                    target=self._refresh_managed_browser_status,
                    args=(config, signature),
                    name="dashboard-managed-browser-status",
                    daemon=True,
                ).start()
            if cached and cached.get("signature") == signature:
                return dict(cached.get("payload") or _default_managed_browser_status(config))
        return _default_managed_browser_status(config)

    def _refresh_managed_browser_status(self, config: Any, signature: str) -> None:
        try:
            payload = browser_runtime_status(config)
        except Exception as exc:
            payload = _default_managed_browser_status(config, detail=f"Aoryn Browser status unavailable: {exc}")
        with self._managed_browser_status_lock:
            self._managed_browser_status_cache = {
                "signature": signature,
                "updated_at": time.time(),
                "payload": dict(payload),
            }
            self._managed_browser_status_refreshing = False

    def system_paths(self) -> dict[str, Any]:
        config_path = self.config_path or (
            default_packaged_config_path() if is_frozen_runtime() else (self.project_root / "config.yaml")
        )
        install_dir = Path(sys.executable).resolve().parent if is_frozen_runtime() else self.project_root.resolve()
        roaming_root = appdata_config_root()
        local_root = local_data_root()
        return {
            "app_name": APP_NAME,
            "version": APP_VERSION,
            "packaged": is_frozen_runtime(),
            "executable_path": str(Path(sys.executable).resolve()),
            "install_dir": str(install_dir),
            "config_file": str(config_path),
            "config_dir": str(config_path.parent),
            "runtime_preferences_file": str(self.runtime_preferences.path),
            "appdata_dir": str(roaming_root),
            "data_dir": str(local_root),
            "run_root": str(self.run_root),
            "cache_dir": str(self.cache_root),
        }

    def environment_check(self) -> dict[str, Any]:
        runtime_overrides = self._runtime_config_overrides()
        config = load_agent_config(self.config_path, config_overrides=runtime_overrides)
        browser_status = dom_backend_status(config.browser_dom_backend)
        display_detection = detect_display_environment(config=config)
        items: list[dict[str, Any]] = []

        browser_path = str(config.browser_executable_path or "").strip()
        browser_channel = str(config.browser_channel or "").strip()
        if browser_path:
            browser_ready = Path(browser_path).exists()
            items.append(
                {
                    "id": "browser_execution",
                    "label": "Browser execution",
                    "status": "Ready" if browser_ready else "Needs setup",
                    "detail": (
                        f"Using browser executable: {browser_path}."
                        if browser_ready
                        else f"The configured browser executable could not be found: {browser_path}."
                    ),
                    "action": "open_settings",
                }
            )
        elif browser_channel or browser_status.available:
            detail = (
                f"Using browser channel: {browser_channel}."
                if browser_channel
                else f"{browser_status.backend} backend is available and can use the system browser."
            )
            items.append(
                {
                    "id": "browser_execution",
                    "label": "Browser execution",
                    "status": "Ready",
                    "detail": detail,
                    "action": "open_settings",
                }
            )
        else:
            items.append(
                {
                    "id": "browser_execution",
                    "label": "Browser execution",
                    "status": "Needs setup",
                    "detail": browser_status.detail
                    or "Configure a browser channel or executable path before running browser tasks.",
                    "action": "open_settings",
                }
            )

        display_override = display_detection.override
        display_status = "Ready"
        if display_override.status == "override":
            display_detail = "Manual display correction is active. Planning and window positioning use the effective values."
        elif display_override.status == "invalid_override":
            display_status = "Needs setup"
            warning = display_override.warnings[0] if display_override.warnings else "The saved display override is invalid."
            display_detail = f"{warning} Open Settings to review the display correction values."
        elif display_override.status == "readonly":
            display_detail = "Display detection is read-only on this platform."
        else:
            display_detail = "Automatic display detection is active."
        items.append(
            {
                "id": "display_detection",
                "label": "Display detection",
                "status": display_status,
                "detail": display_detail,
                "action": "open_settings",
            }
        )

        provider_labels = {
            "lmstudio_local": "Local LM Studio",
            "openai_api": "OpenAI API",
            "openai_compatible": "OpenAI-compatible API",
            "custom": "Custom provider",
        }
        provider_value = str(config.model_provider or "").strip()
        planner_mode = str(getattr(config, "planner_mode", "") or "").strip().lower().replace("-", "_")
        computer_use_mode = planner_mode in {"computer_use", "cua"}
        connection_provider_value = "openai_api" if computer_use_mode else provider_value
        provider_label = provider_labels.get(provider_value, provider_value or "Not selected")
        items.append(
            {
                "id": "model_provider",
                "label": "Model provider",
                "status": "Ready" if provider_value else "Needs setup",
                "detail": (
                    f"Current provider: {provider_label}."
                    if provider_value
                    else "Choose a model provider in Settings before your first run."
                ),
                "action": "open_settings",
            }
        )

        model_name = str(config.model_name or "").strip()
        auto_discover = bool(config.model_auto_discover)
        items.append(
            {
                "id": "model_selection",
                "label": "Model selection",
                "status": "Ready" if (model_name or auto_discover) else "Needs setup",
                "detail": (
                    f"Configured model: {model_name}."
                    if model_name
                    else "Auto discovery is enabled."
                    if auto_discover
                    else "Choose a model or enable auto discovery in Settings."
                ),
                "action": "open_settings",
            }
        )

        api_base = normalize_api_base_url(config.model_base_url)
        if computer_use_mode and _looks_like_local_api_base(api_base):
            api_base = "https://api.openai.com/v1"
        api_key = str(config.model_api_key or "").strip()
        env_api_key = str(os.environ.get("OPENAI_API_KEY") or "").strip()
        effective_api_key = api_key or env_api_key
        connection_item = {
            "id": "provider_connection",
            "label": "Provider connection",
            "status": "Needs setup",
            "detail": "Complete the provider settings first.",
            "action": "refresh_model_catalog",
        }
        requires_api_key = connection_provider_value in {"openai_api", "openai_compatible"}
        if not connection_provider_value:
            connection_item["action"] = "open_settings"
        elif not api_base:
            connection_item["detail"] = "Add a Base URL in Settings before checking the provider connection."
            connection_item["action"] = "open_settings"
        elif requires_api_key and not effective_api_key:
            connection_item["detail"] = "Add an API key in Settings or set OPENAI_API_KEY before checking the provider connection."
            connection_item["action"] = "open_settings"
        else:
            snapshot = self._environment_provider_snapshot(
                provider=connection_provider_value,
                base_url=api_base,
                api_key=effective_api_key,
                timeout=float(config.model_request_timeout),
            )
            if snapshot is None:
                connection_item["detail"] = "Checking the provider connection in the background."
            elif snapshot.ok:
                catalog_count = len(snapshot.catalog_models)
                loaded_count = len(snapshot.loaded_models)
                if connection_provider_value == "lmstudio_local":
                    connection_item["label"] = "LM Studio connection"
                    if catalog_count or loaded_count:
                        connection_item["status"] = "Ready"
                        connection_item["detail"] = (
                            f"LM Studio responded successfully. "
                            f"Loaded models: {loaded_count}. Available models: {catalog_count or loaded_count}."
                        )
                    else:
                        connection_item["status"] = "Needs setup"
                        connection_item["detail"] = "LM Studio is reachable, but no models are available yet."
                else:
                    connection_item["label"] = "Hosted provider connection"
                    if model_name or auto_discover:
                        connection_item["status"] = "Ready"
                        connection_item["detail"] = (
                            f"Provider responded successfully. Model catalog entries: {catalog_count or loaded_count}."
                        )
                    else:
                        connection_item["status"] = "Needs setup"
                        connection_item["detail"] = "Provider responded, but you still need to choose a model."
            else:
                detail = snapshot.error or "The provider did not return any models."
                if "No models were returned" in detail:
                    connection_item["status"] = "Needs setup"
                else:
                    connection_item["status"] = "Connection failed"
                connection_item["detail"] = detail

        items.append(connection_item)
        if computer_use_mode:
            items.append(
                {
                    "id": "computer_use_api",
                    "label": "Computer use API",
                    "status": "Ready" if effective_api_key else "Needs setup",
                    "detail": (
                        f"Responses API computer tool will use {api_base}; local model discovery is skipped."
                        if effective_api_key
                        else "Set model_api_key or OPENAI_API_KEY before running computer_use mode."
                    ),
                    "action": "open_settings",
                }
            )
        plugin_modules = list(getattr(config, "plugin_modules", []) or [])
        if plugin_modules:
            from desktop_agent.plugins import build_runtime_registries

            _capability_registry, _driver_registry, plugin_results = build_runtime_registries(config)
            failed_plugins = [item for item in plugin_results if not item.loaded]
            registered_capabilities = sum(len(item.capabilities) for item in plugin_results if item.loaded)
            registered_drivers = sum(len(item.drivers) for item in plugin_results if item.loaded)
            items.append(
                {
                    "id": "software_plugins",
                    "label": "Software plugins",
                    "status": "Needs setup" if failed_plugins else "Ready",
                    "detail": (
                        f"{len(failed_plugins)} plugin(s) failed to load: "
                        + "; ".join(f"{item.module}: {item.error}" for item in failed_plugins[:3])
                        if failed_plugins
                        else (
                            f"Loaded {len(plugin_results)} plugin module(s), "
                            f"{registered_capabilities} capability adapter(s), {registered_drivers} app driver(s)."
                        )
                    ),
                    "action": "open_settings",
                }
            )
        return {
            "items": items,
            "checked_at": time.time(),
            "provider": provider_value,
            "model_name": model_name,
        }

    def _environment_provider_snapshot(
        self,
        *,
        provider: str,
        base_url: str,
        api_key: str,
        timeout: float,
    ) -> ProviderSnapshot | None:
        now = time.time()
        signature = _provider_environment_signature(provider=provider, base_url=base_url, api_key=api_key)
        with self._provider_environment_lock:
            cached = self._provider_environment_cache.get(signature)
            if cached and now - float(cached.get("updated_at") or 0.0) < _PROVIDER_ENVIRONMENT_CACHE_SECONDS:
                snapshot = cached.get("snapshot")
                return snapshot if isinstance(snapshot, ProviderSnapshot) else None
            if signature not in self._provider_environment_refreshing:
                self._provider_environment_refreshing.add(signature)
                threading.Thread(
                    target=self._refresh_environment_provider_snapshot,
                    kwargs={
                        "signature": signature,
                        "provider": provider,
                        "base_url": base_url,
                        "api_key": api_key,
                        "timeout": timeout,
                    },
                    name="dashboard-provider-environment-check",
                    daemon=True,
                ).start()
            if cached:
                snapshot = cached.get("snapshot")
                return snapshot if isinstance(snapshot, ProviderSnapshot) else None
        return None

    def _refresh_environment_provider_snapshot(
        self,
        *,
        signature: str,
        provider: str,
        base_url: str,
        api_key: str,
        timeout: float,
    ) -> None:
        try:
            snapshot = fetch_provider_snapshot(
                provider=provider,
                base_url=base_url,
                api_key=api_key,
                timeout=min(float(timeout), _PROVIDER_ENVIRONMENT_REFRESH_TIMEOUT_SECONDS),
            )
        except Exception as exc:
            api_base = normalize_api_base_url(base_url)
            snapshot = ProviderSnapshot(
                ok=False,
                provider=provider,
                api_base=api_base,
                root_base=api_base,
                loaded_models=[],
                catalog_models=[],
                error=f"Could not check provider connection: {exc}",
            )
        with self._provider_environment_lock:
            self._provider_environment_cache[signature] = {
                "updated_at": time.time(),
                "snapshot": snapshot,
            }
            self._provider_environment_refreshing.discard(signature)

    def display_detection(self) -> dict[str, Any]:
        config = load_agent_config(self.config_path, config_overrides=self._runtime_config_overrides())
        return detect_display_environment(config=config).to_dict()

    def _runtime_config_overrides(self) -> dict[str, Any]:
        runtime_snapshot = self.runtime_preferences.snapshot()
        return _clean_config_overrides(runtime_snapshot.get("config_overrides"))

    def _resolve_request_config_overrides(self, raw_overrides: Any | None = None) -> dict[str, Any]:
        merged = self._runtime_config_overrides()
        merged.update(_clean_config_overrides(raw_overrides))
        return _clean_config_overrides(merged)

    def _resolve_initial_task_graph(
        self,
        *,
        task: str,
        raw_task_graph: Any,
        raw_task_graph_signature: Any = None,
        config_overrides: dict[str, Any],
    ) -> dict[str, Any] | None:
        if raw_task_graph is None:
            return None
        config = load_agent_config(self.config_path, config_overrides=config_overrides)
        graph_payload = coerce_initial_task_graph(
            task,
            raw_task_graph,
            max_subgoals=config.max_task_subgoals,
        ).to_dict()
        clean_signature = str(raw_task_graph_signature or "").strip()
        if not clean_signature:
            raise ValueError("Task graph signature is required. Refresh the plan preview.")
        expected_signature = self._preview_task_graph_signature(
            task=task,
            task_graph=graph_payload,
            config_overrides=config_overrides,
            config=config,
        )
        if clean_signature != expected_signature:
            raise ValueError("Task graph signature does not match the current task or configuration. Refresh the plan preview.")
        start_blocker = _preview_task_graph_start_blocker(config, graph_payload)
        if start_blocker:
            raise ValueError(start_blocker)
        return graph_payload

    def _resolve_initial_plan_review_status(
        self,
        *,
        task: str,
        task_graph: dict[str, Any] | None,
        raw_review_status: Any = None,
        raw_review_signature: Any = None,
        config_overrides: dict[str, Any],
    ) -> str | None:
        review_status = str(raw_review_status or "").strip().lower()
        if not review_status:
            return None
        if review_status != "approved":
            raise ValueError("Unsupported task graph review status.")
        if task_graph is None:
            raise ValueError("Task graph review status requires a matching preview task graph.")
        review_signature = str(raw_review_signature or "").strip()
        if not review_signature:
            raise ValueError("Task graph review signature is required.")
        config = load_agent_config(self.config_path, config_overrides=config_overrides)
        expected_signature = self._preview_task_graph_signature(
            task=task,
            task_graph=task_graph,
            config_overrides=config_overrides,
            config=config,
        )
        if review_signature != expected_signature:
            raise ValueError("Task graph review signature does not match the current task or configuration. Refresh the plan preview.")
        graph = TaskGraph.from_dict(task_graph)
        graph.task = str(task or graph.task or "").strip()
        if not _preview_plan_review_required(config, graph):
            raise ValueError("Task graph review status does not match the current review policy. Refresh the plan preview.")
        return "approved"

    def _preview_task_graph_signature(
        self,
        *,
        task: str,
        task_graph: dict[str, Any],
        config_overrides: dict[str, Any],
        config: Any | None = None,
    ) -> str:
        effective_config = config or load_agent_config(self.config_path, config_overrides=config_overrides)
        payload = {
            "task": str(task or "").strip(),
            "task_graph": _stable_preview_value(task_graph),
            "config_overrides": _stable_preview_value(_redact_preview_signature_config(config_overrides)),
            "planning_contract": _stable_preview_value(_preview_signature_config_contract(effective_config)),
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def preview_task(self, *, task: str, config_overrides: dict[str, Any]) -> dict[str, Any]:
        normalized_task = str(task or "").strip()
        if not normalized_task:
            raise ValueError("Task is required.")

        resolved_overrides = self._resolve_request_config_overrides(config_overrides)
        config = load_agent_config(self.config_path, config_overrides=resolved_overrides)
        task_graph = TaskGraphPlanner(config).plan(normalized_task, history=[], world_model=None)
        risk_level = task_graph_risk_level(task_graph)
        ambiguous = task_graph_is_ambiguous(task_graph)
        requires_review = _preview_plan_review_required(config, task_graph)
        preview_state = ExecutionState(
            task=task_graph.task,
            run_id=f"preview-{uuid.uuid4().hex[:12]}",
            task_graph=task_graph,
        )
        if requires_review:
            preview_state.app_context["plan_review_status"] = "pending"
            preview_state.app_context["plan_review_reason"] = "Preview uses the same plan review policy as execution."
        summary = build_execution_plan_summary(preview_state)
        intent = dict(task_graph.intent) if isinstance(task_graph.intent, dict) else {}
        task_graph_payload = task_graph.to_dict()
        start_blocker = _preview_task_graph_start_blocker(config, task_graph)
        return {
            "task": normalized_task,
            "task_graph": task_graph_payload,
            "task_graph_signature": self._preview_task_graph_signature(
                task=normalized_task,
                task_graph=task_graph_payload,
                config_overrides=resolved_overrides,
                config=config,
            ),
            "intent": intent,
            "risk_level": risk_level,
            "ambiguous": ambiguous,
            "requires_review": requires_review,
            "can_start": start_blocker is None,
            "start_blocker": start_blocker,
            "execution_budget": {
                "task_graph_request_timeout": config.task_graph_request_timeout,
                "max_steps": config.max_steps,
                "max_run_seconds": config.max_run_seconds,
                "pause_after_action": config.pause_after_action,
                "desktop_autonomy_mode": config.desktop_autonomy_mode,
                "approval_policy": config.approval_policy,
                "complex_task_planning": config.complex_task_planning,
                "plan_review_policy": config.plan_review_policy,
                "max_task_subgoals": config.max_task_subgoals,
                "max_subgoal_retries": config.max_subgoal_retries,
                "stage_review_policy": config.stage_review_policy,
                "max_replans_per_run": config.max_replans_per_run,
                "max_failures_per_subgoal": config.max_failures_per_subgoal,
                "replan_on_recoverable_error": config.replan_on_recoverable_error,
                "recoverable_error_retry_limit": config.recoverable_error_retry_limit,
            },
            "execution_environment": {
                "browser_control_mode": config.browser_control_mode,
                "browser_dom_backend": config.browser_dom_backend,
                "browser_dom_timeout": config.browser_dom_timeout,
                "browser_headless": config.browser_headless,
                "browser_channel": config.browser_channel,
                "browser_executable_path": config.browser_executable_path,
                "cursor_motion_enabled": config.cursor_motion_enabled,
                "cursor_motion_duration": config.cursor_motion_duration,
                "display_override_enabled": config.display_override_enabled,
                "display_override_monitor_device_name": config.display_override_monitor_device_name,
                "display_override_dpi_scale": config.display_override_dpi_scale,
                "display_override_work_area_left": config.display_override_work_area_left,
                "display_override_work_area_top": config.display_override_work_area_top,
                "display_override_work_area_width": config.display_override_work_area_width,
                "display_override_work_area_height": config.display_override_work_area_height,
                "generic_app_launch_enabled": config.generic_app_launch_enabled,
                "shell_recipe_policy": config.shell_recipe_policy,
            },
            "plan_health": summary.get("plan_health", {}),
            "summary": summary,
        }

    def open_diagnostic_path(self, key: str) -> dict[str, Any]:
        diagnostics = self.system_paths()
        path_map = {
            "config_dir": Path(diagnostics["config_dir"]),
            "data_dir": Path(diagnostics["data_dir"]),
            "run_root": Path(diagnostics["run_root"]),
            "cache_dir": Path(diagnostics["cache_dir"]),
            "install_dir": Path(diagnostics["install_dir"]),
        }
        target = path_map.get(key)
        if target is None:
            raise ValueError("Unsupported path key.")
        target.mkdir(parents=True, exist_ok=True)
        _open_path_in_file_manager(target)
        return {"ok": True, "key": key, "path": str(target)}

    def chat_reply(
        self,
        *,
        messages: Any,
        config_overrides: dict[str, Any],
        session_meta: Any | None = None,
        recovery_context: Any | None = None,
    ) -> dict[str, Any]:
        resolved_overrides = self._resolve_request_config_overrides(config_overrides)
        parsed_recovery_context = self._coerce_recovery_context(recovery_context)
        if parsed_recovery_context:
            return self._chat_reply_with_temporary_text_model(
                messages=messages,
                config_overrides=resolved_overrides,
                session_meta=session_meta,
                recovery_context=parsed_recovery_context,
            )

        clean_messages = sanitize_chat_messages(messages)
        if not clean_messages:
            raise ValueError("At least one chat message is required.")

        session_payload = session_meta if isinstance(session_meta, dict) else {}
        locale = normalize_help_locale(session_payload.get("locale"))
        latest_user_message = _extract_latest_user_message(clean_messages)
        math_mode = looks_like_math_request(latest_user_message)
        config = load_agent_config(self.config_path, config_overrides=resolved_overrides)
        model_name = self._resolve_chat_model(config_overrides=resolved_overrides)
        compatibility_mode = (
            config.model_provider == "lmstudio_local" and _is_vision_model_name(model_name)
        )
        api_base = normalize_api_base_url(config.model_base_url)
        headers = build_request_headers(config.model_api_key)
        prepared_messages = _prepare_chat_messages(
            clean_messages,
            compatibility_mode=compatibility_mode,
        )
        system_prompt = build_chat_system_prompt(
            help_markdown="",
            locale=locale,
            provider_name=config.model_provider,
            model_name=model_name,
            compatibility_mode=compatibility_mode,
            math_mode=math_mode,
        )
        payload = {
            "model": model_name,
            "temperature": 0.4,
            "messages": [{"role": "system", "content": system_prompt}, *prepared_messages],
        }

        try:
            import requests
        except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
            raise ProviderToolError(
                "Chat mode requires the requests package. Install dependencies from requirements.txt first."
            ) from exc

        try:
            response = requests.post(
                f"{api_base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=min(float(config.model_request_timeout), 90.0),
            )
        except requests.RequestException as exc:
            raise ProviderToolError(_format_chat_connection_error(api_base, exc)) from exc

        if getattr(response, "status_code", 200) >= 400:
            detail = _extract_chat_provider_detail(response)
            if compatibility_mode and math_mode and _looks_like_math_provider_failure(detail):
                self._raise_math_formula_unstable_error(
                    locale=locale,
                    clean_messages=clean_messages,
                    config_overrides=resolved_overrides,
                    current_model_name=model_name,
                    detail=_truncate_chat_provider_detail(detail, limit=180),
                )
            raise ProviderToolError(_format_chat_provider_error(api_base, response))

        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderToolError("The chat model returned invalid JSON.") from exc

        assistant_message = extract_assistant_message(data)
        if not assistant_message:
            raise ProviderToolError("The chat model returned an empty response.")
        if compatibility_mode and math_mode and _looks_like_math_formula_output_unstable(assistant_message):
            self._raise_math_formula_unstable_error(
                locale=locale,
                clean_messages=clean_messages,
                config_overrides=resolved_overrides,
                current_model_name=model_name,
            )
        if _looks_like_placeholder_chat_output(assistant_message):
            raise ProviderToolError(
                "The current chat model returned placeholder output instead of a usable reply. "
                "If you are using a vision model, try a text chat model in LM Studio for the most reliable results."
            )

        return {
            "assistant_message": assistant_message,
            "agent_handoff": build_agent_handoff(latest_user_message, locale=locale),
            "session_meta": session_payload or None,
        }

    def provider_models(self, config_overrides: dict[str, Any]) -> dict[str, Any]:
        resolved_overrides = self._resolve_request_config_overrides(config_overrides)
        config = load_agent_config(self.config_path, config_overrides=resolved_overrides)
        snapshot = fetch_provider_snapshot(
            provider=config.model_provider,
            base_url=config.model_base_url,
            api_key=config.model_api_key,
            timeout=min(float(config.model_request_timeout), 15.0),
        )
        preferred_chat_model = None
        preferred_chat_compatibility_mode = False
        try:
            preferred_chat_model, preferred_chat_compatibility_mode = self._resolve_chat_model_selection(
                config_overrides=resolved_overrides,
                snapshot=snapshot,
            )
        except ProviderToolError:
            preferred_chat_model = None
            preferred_chat_compatibility_mode = False

        ordered_snapshot = snapshot.to_dict()
        ordered_snapshot["catalog_models"] = [
            item.to_dict()
            for item in _order_provider_catalog_for_display(
                snapshot.catalog_models,
                preferred_model=preferred_chat_model,
            )
        ]
        ordered_snapshot["preferred_chat_model"] = preferred_chat_model
        ordered_snapshot["preferred_chat_compatibility_mode"] = preferred_chat_compatibility_mode
        return ordered_snapshot

    def provider_load_model(
        self,
        *,
        config_overrides: dict[str, Any],
        model_id: str,
        unload_first: bool = False,
    ) -> dict[str, Any]:
        resolved_overrides = self._resolve_request_config_overrides(config_overrides)
        config = load_agent_config(self.config_path, config_overrides=resolved_overrides)
        if config.model_provider != "lmstudio_local":
            raise ProviderToolError("Model loading is only supported for the LM Studio local provider.")
        timeout = min(float(config.model_request_timeout), 20.0)
        unloaded_instance_ids: list[str] = []

        if unload_first:
            snapshot = fetch_provider_snapshot(
                provider=config.model_provider,
                base_url=config.model_base_url,
                api_key=config.model_api_key,
                timeout=min(float(config.model_request_timeout), 15.0),
            )
            loaded_entries = [
                entry
                for entry in snapshot.catalog_models
                if isinstance(entry, ProviderModelEntry) and entry.loaded
            ]
            target_is_loaded = any(entry.model_id == model_id for entry in loaded_entries)
            instances_to_unload: list[str] = []
            for entry in loaded_entries:
                if entry.model_id == model_id:
                    continue
                candidate_ids = entry.loaded_instance_ids or [entry.model_id]
                for instance_id in candidate_ids:
                    normalized = str(instance_id or "").strip()
                    if normalized and normalized not in instances_to_unload:
                        instances_to_unload.append(normalized)

            if instances_to_unload:
                unload_payload = unload_lmstudio_model_instances(
                    base_url=config.model_base_url,
                    api_key=config.model_api_key,
                    instance_ids=instances_to_unload,
                    timeout=timeout,
                )
                unloaded_instance_ids = list(unload_payload.get("unloaded_instance_ids") or [])

            if target_is_loaded:
                return {
                    "ok": True,
                    "api_base": normalize_api_base_url(config.model_base_url),
                    "root_base": snapshot.root_base,
                    "model_id": model_id,
                    "already_loaded": True,
                    "unloaded_instance_ids": unloaded_instance_ids,
                }

        payload = load_lmstudio_model(
            base_url=config.model_base_url,
            api_key=config.model_api_key,
            model_id=model_id,
            timeout=timeout,
        )
        payload["unloaded_instance_ids"] = unloaded_instance_ids
        return payload

    def _suggest_text_chat_model(
        self,
        *,
        config_overrides: dict[str, Any],
        current_model_name: str,
    ) -> str | None:
        resolved_overrides = self._resolve_request_config_overrides(config_overrides)
        config = load_agent_config(self.config_path, config_overrides=resolved_overrides)
        snapshot = fetch_provider_snapshot(
            provider=config.model_provider,
            base_url=config.model_base_url,
            api_key=config.model_api_key,
            timeout=min(float(config.model_request_timeout), 15.0),
        )
        return _pick_text_chat_model_name(snapshot, exclude_model=current_model_name)

    def _build_math_recovery_context(
        self,
        *,
        clean_messages: list[dict[str, str]],
        config_overrides: dict[str, Any],
        current_model_name: str,
    ) -> dict[str, Any] | None:
        suggested_text_model = self._suggest_text_chat_model(
            config_overrides=config_overrides,
            current_model_name=current_model_name,
        )
        if not suggested_text_model:
            return None
        return {
            "messages": [dict(item) for item in clean_messages],
            "previous_model": current_model_name,
            "suggested_text_model": suggested_text_model,
            "restore_to_model": current_model_name,
        }

    def _raise_math_formula_unstable_error(
        self,
        *,
        locale: str,
        clean_messages: list[dict[str, str]],
        config_overrides: dict[str, Any],
        current_model_name: str,
        detail: str | None = None,
    ) -> None:
        message = (
            "当前视觉模型在 LM Studio 兼容聊天链路下生成数学公式时不稳定。前端公式渲染本身可用，但这次回复在上游模型侧损坏或被 provider 拒绝。"
            if locale == "zh-CN"
            else "The current vision model is unstable for formula-heavy replies in the LM Studio compatibility chat path. Frontend math rendering is available, but this reply was corrupted or rejected upstream."
        )
        if detail:
            message = f"{message} {detail}"

        payload: dict[str, Any] = {
            "error_code": "math_formula_unstable",
        }
        retry_context = self._build_math_recovery_context(
            clean_messages=clean_messages,
            config_overrides=config_overrides,
            current_model_name=current_model_name,
        )
        if retry_context:
            payload.update(
                {
                    "recovery_action": "switch_text_model_retry",
                    "recovery_label": (
                        "切换到文本模型重试" if locale == "zh-CN" else "Retry with a text model"
                    ),
                    "retry_context": retry_context,
                }
            )
        raise ChatUIError(message, payload=payload)

    def _coerce_recovery_context(self, raw: Any) -> dict[str, str] | None:
        if not isinstance(raw, dict):
            return None
        suggested_text_model = str(raw.get("suggested_text_model", "")).strip()
        previous_model = str(raw.get("previous_model", "")).strip()
        restore_to_model = str(raw.get("restore_to_model", "")).strip() or previous_model
        if not suggested_text_model or not previous_model:
            return None
        return {
            "suggested_text_model": suggested_text_model,
            "previous_model": previous_model,
            "restore_to_model": restore_to_model,
        }

    def _chat_reply_with_temporary_text_model(
        self,
        *,
        messages: Any,
        config_overrides: dict[str, Any],
        session_meta: Any | None,
        recovery_context: dict[str, str],
    ) -> dict[str, Any]:
        resolved_overrides = self._resolve_request_config_overrides(config_overrides)
        suggested_text_model = recovery_context["suggested_text_model"]
        restore_to_model = recovery_context["restore_to_model"]
        retry_overrides = dict(resolved_overrides)
        retry_overrides["model_name"] = suggested_text_model

        with self.model_switch_lock:
            self.provider_load_model(
                config_overrides=resolved_overrides,
                model_id=suggested_text_model,
                unload_first=True,
            )
            try:
                return self.chat_reply(
                    messages=messages,
                    config_overrides=retry_overrides,
                    session_meta=session_meta,
                    recovery_context=None,
                )
            finally:
                if restore_to_model and restore_to_model != suggested_text_model:
                    self.provider_load_model(
                        config_overrides=resolved_overrides,
                        model_id=restore_to_model,
                        unload_first=True,
                    )

    def _resolve_chat_model_selection(
        self,
        *,
        config_overrides: dict[str, Any],
        snapshot: Any | None = None,
    ) -> tuple[str, bool]:
        resolved_overrides = self._resolve_request_config_overrides(config_overrides)
        config = load_agent_config(self.config_path, config_overrides=resolved_overrides)
        configured_model = (config.model_name or "").strip()
        if configured_model and configured_model.lower() not in {"auto", "first"}:
            return (
                configured_model,
                config.model_provider == "lmstudio_local" and _is_vision_model_name(configured_model),
            )

        if snapshot is None:
            snapshot = fetch_provider_snapshot(
                provider=config.model_provider,
                base_url=config.model_base_url,
                api_key=config.model_api_key,
                timeout=min(float(config.model_request_timeout), 15.0),
            )
        entries = _snapshot_chat_model_entries(snapshot)
        loaded_ids = {
            str(model_id or "").strip()
            for model_id in snapshot.loaded_models
            if str(model_id or "").strip()
        }
        loaded_entries = [entry for entry in entries if entry.loaded or entry.model_id in loaded_ids]
        loaded_text_entries = [
            entry
            for entry in loaded_entries
            if not _is_embedding_model(entry) and not _is_vision_model(entry)
        ]

        if loaded_text_entries:
            resolved_loaded_model = _pick_best_chat_model(loaded_text_entries)
            if resolved_loaded_model:
                return resolved_loaded_model, False

        if config.model_provider == "lmstudio_local" and loaded_entries:
            loaded_chat_entries = [
                entry for entry in loaded_entries if not _is_embedding_model(entry)
            ]
            resolved_loaded_model = _pick_best_chat_model(loaded_chat_entries)
            if resolved_loaded_model:
                return resolved_loaded_model, _is_vision_model_name(resolved_loaded_model)

        resolved_model = _pick_chat_model_name(snapshot)
        if resolved_model:
            return (
                resolved_model,
                config.model_provider == "lmstudio_local" and _is_vision_model_name(resolved_model),
            )
        raise ProviderToolError(snapshot.error or "No models were returned by the provider.")

    def _resolve_chat_model(self, *, config_overrides: dict[str, Any]) -> str:
        return self._resolve_chat_model_selection(config_overrides=config_overrides)[0]


def _dashboard_help_content(self: DashboardApp, *, locale: str = "zh-CN", audience: str = "user") -> dict[str, Any]:
    return _dashboard_help_content_clean(self, locale=locale, audience=audience)


DashboardApp.help_content = _dashboard_help_content


def launch_dashboard(
    *,
    host: str,
    port: int,
    config_path: str | Path | None = None,
    open_browser: bool = True,
) -> int:
    app = DashboardApp(host=host, port=port, config_path=config_path)
    server = app.create_server()
    url = f"http://{host}:{port}"
    print(f"{APP_NAME} {APP_VERSION} is running at {url}")
    if open_browser:
        print("Attempting to open the dashboard in your browser...")
    else:
        print("Browser auto-open is disabled for this session.")
    print("Keep this terminal open while you use the dashboard. Press Ctrl+C to stop the server.")
    print(f"If the page does not appear automatically, open {url} in your browser.")
    if open_browser:
        threading.Thread(target=_open_browser_when_ready, args=(url,), daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down dashboard...")
    finally:
        server.server_close()
    return 0


def _open_browser(url: str) -> None:
    if _open_with_platform_fallback(url):
        return
    if _try_webbrowser_open(url):
        return


def _extract_stream_delta_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""

    delta = choices[0].get("delta", {})
    content = delta.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return ""


def _dashboard_chat_reply_stream(
    self: DashboardApp,
    *,
    messages: Any,
    config_overrides: dict[str, Any],
    session_meta: Any | None = None,
    recovery_context: Any | None = None,
):
    resolved_overrides = self._resolve_request_config_overrides(config_overrides)
    clean_messages = sanitize_chat_messages(messages)
    if not clean_messages:
        yield "error", {"error": "At least one chat message is required."}
        return

    session_payload = session_meta if isinstance(session_meta, dict) else {}
    locale = normalize_help_locale(session_payload.get("locale"))
    latest_user_message = _extract_latest_user_message(clean_messages)
    math_mode = looks_like_math_request(latest_user_message)
    yield "start", {"session_meta": session_payload or None}

    config = load_agent_config(self.config_path, config_overrides=resolved_overrides)
    parsed_recovery_context = self._coerce_recovery_context(recovery_context)
    if config.model_provider == "lmstudio_local" and parsed_recovery_context:
        try:
            payload = self.chat_reply(
                messages=clean_messages,
                config_overrides=resolved_overrides,
                session_meta=session_payload,
                recovery_context=parsed_recovery_context,
            )
        except ValueError as exc:
            yield "error", {"error": str(exc)}
            return
        except ProviderToolError as exc:
            yield "error", _provider_error_payload(exc)
            return

        assistant_message = str(payload.get("assistant_message", "") or "").strip()
        if not assistant_message:
            yield "error", {"error": "The chat model returned an empty response."}
            return

        yield "delta", {"content_delta": assistant_message}
        yield "done", payload
        return

    try:
        import requests
    except ModuleNotFoundError:
        yield "error", {"error": "Chat mode requires the requests package. Install requirements first."}
        return

    try:
        model_name = self._resolve_chat_model(config_overrides=resolved_overrides)
        compatibility_mode = (
            config.model_provider == "lmstudio_local" and _is_vision_model_name(model_name)
        )
        api_base = normalize_api_base_url(config.model_base_url)
        headers = build_request_headers(config.model_api_key)
        headers.setdefault("Accept", "text/event-stream")
        prepared_messages = _prepare_chat_messages(
            clean_messages,
            compatibility_mode=compatibility_mode,
        )
        system_prompt = build_chat_system_prompt(
            help_markdown="",
            locale=locale,
            provider_name=config.model_provider,
            model_name=model_name,
            compatibility_mode=compatibility_mode,
            math_mode=math_mode,
        )
        payload = {
            "model": model_name,
            "temperature": 0.4,
            "stream": True,
            "messages": [{"role": "system", "content": system_prompt}, *prepared_messages],
        }
        response = requests.post(
            f"{api_base}/chat/completions",
            headers=headers,
            json=payload,
            timeout=min(float(config.model_request_timeout), 90.0),
            stream=True,
        )
    except ProviderToolError as exc:
        yield "error", _provider_error_payload(exc)
        return
    except requests.RequestException as exc:
        yield "error", {"error": _format_chat_connection_error(api_base, exc)}
        return
    except ValueError as exc:
        yield "error", {"error": str(exc)}
        return

    if getattr(response, "status_code", 200) >= 400:
        detail = _extract_chat_provider_detail(response)
        if compatibility_mode and math_mode and _looks_like_math_provider_failure(detail):
            try:
                self._raise_math_formula_unstable_error(
                    locale=locale,
                    clean_messages=clean_messages,
                    config_overrides=resolved_overrides,
                    current_model_name=model_name,
                    detail=_truncate_chat_provider_detail(detail, limit=180),
                )
            except ProviderToolError as exc:
                yield "error", _provider_error_payload(exc)
                response.close()
                return
        yield "error", {"error": _format_chat_provider_error(api_base, response)}
        response.close()
        return

    try:
        content_type = (response.headers.get("Content-Type") or "").lower()
        if "text/event-stream" not in content_type:
            try:
                data = response.json()
            except ValueError:
                yield "error", {"error": "The chat model returned invalid JSON."}
                return

            assistant_message = extract_assistant_message(data)
            if not assistant_message:
                yield "error", {"error": "The chat model returned an empty response."}
                return
            if compatibility_mode and math_mode and _looks_like_math_formula_output_unstable(assistant_message):
                try:
                    self._raise_math_formula_unstable_error(
                        locale=locale,
                        clean_messages=clean_messages,
                        config_overrides=resolved_overrides,
                        current_model_name=model_name,
                    )
                except ProviderToolError as exc:
                    yield "error", _provider_error_payload(exc)
                    return
            if _looks_like_placeholder_chat_output(assistant_message):
                yield "error", {
                    "error": (
                        "The current chat model returned placeholder output instead of a usable reply. "
                        "If you are using a vision model, try a text chat model in LM Studio for the most reliable results."
                    )
                }
                return

            yield "delta", {"content_delta": assistant_message}
            yield "done", {
                "assistant_message": assistant_message,
                "agent_handoff": build_agent_handoff(latest_user_message, locale=locale),
                "session_meta": session_payload or None,
            }
            return

        assistant_parts: list[str] = []
        for raw_line in response.iter_lines(decode_unicode=False):
            if isinstance(raw_line, bytes):
                try:
                    line = raw_line.decode("utf-8").strip()
                except UnicodeDecodeError:
                    yield "error", {
                        "error": "The chat model stream was not valid UTF-8.",
                    }
                    return
            else:
                line = str(raw_line or "").strip()
            if not line or not line.startswith("data:"):
                continue
            data_line = line[5:].strip()
            if data_line == "[DONE]":
                break
            try:
                chunk = json.loads(data_line)
            except json.JSONDecodeError:
                continue
            delta_text = _extract_stream_delta_text(chunk)
            if not delta_text:
                continue
            assistant_parts.append(delta_text)
            yield "delta", {"content_delta": delta_text}

        assistant_message = sanitize_assistant_chat_text("".join(assistant_parts))
        if not assistant_message:
            yield "error", {"error": "The chat model returned an empty response."}
            return
        if compatibility_mode and math_mode and _looks_like_math_formula_output_unstable(assistant_message):
            try:
                self._raise_math_formula_unstable_error(
                    locale=locale,
                    clean_messages=clean_messages,
                    config_overrides=resolved_overrides,
                    current_model_name=model_name,
                )
            except ProviderToolError as exc:
                yield "error", _provider_error_payload(exc)
                return
        if _looks_like_placeholder_chat_output(assistant_message):
            yield "error", {
                "error": (
                    "The current chat model returned placeholder output instead of a usable reply. "
                    "If you are using a vision model, try a text chat model in LM Studio for the most reliable results."
                )
            }
            return

        yield "done", {
            "assistant_message": assistant_message,
            "agent_handoff": build_agent_handoff(latest_user_message, locale=locale),
            "session_meta": session_payload or None,
        }
    finally:
        response.close()


DashboardApp.chat_reply_stream = _dashboard_chat_reply_stream


def _normalize_help_audience(audience: str | None) -> str:
    return "developer" if str(audience or "").strip().lower() == "developer" else "user"


def _build_user_help_markdown(locale: str) -> str:
    if normalize_help_locale(locale) == "en-US":
        return f"""# {APP_NAME} Help Center

## First run

- Install the desktop app, launch it, and stay in the main workbench for your first task.
- Use the four-step onboarding flow to pick a model path, confirm the environment, run a starter task, and review the timeline.
- Your account is only used for identity and download access. The desktop app does not require another sign-in gate after installation.

## Model and browser setup

- Choose **Local LM Studio** when you want a local-first model path on the same machine.
- Choose **Hosted / compatible API** when you want to connect an OpenAI-compatible endpoint with your own key.
- Browser settings, model settings, and display correction all live in local runtime preferences so the browser and desktop runs stay aligned.

## How to write a good task

- Start with the goal first, then list the next concrete action if it matters.
- Keep one task focused on one outcome such as opening a page, checking a status, or narrowing a shortlist.
- Mention constraints that matter, like account context, price range, color, or the exact page to open.
- When a task is risky, ask Aoryn to pause for review before final submission or confirmation.

## Common failures and recovery

- If model checks fail, open **Settings** and confirm provider, base URL, model name, and API key.
- If the browser is visible but clicks are not progressing, run the environment check and then try a shorter starter task.
- If a task pauses for human review, open the timeline or browser handoff view, make the decision, and continue from the current state.
- If a run stops midway, reopen it from history and resume instead of starting the whole flow again.

## Privacy and local data boundary

- Aoryn keeps task history, screenshots, browser state, settings, and local diagnostics on your device.
- Cloud services only hold the minimum identity and download access data needed for the website.
- Removing the app does not automatically delete your local work history unless you choose to remove local data too.

## Need advanced docs?

- Open **Advanced Docs** from the settings panel when you want developer-facing setup notes and deeper implementation details.
"""

    return f"""# {APP_NAME} 帮助中心

## 第一次使用

- 安装桌面版后直接进入工作台，从第一条任务开始，不需要再次登录。
- 按四步引导完成首次启动：选择模型路径、检查环境、运行推荐任务、查看结果时间线。
- 账号只负责身份和下载权限，不负责同步你的本地任务数据。

## 模型与浏览器设置

- 想走本地优先路径时，优先选择 **Local LM Studio**。
- 想接入托管模型时，可以选择 **Hosted / compatible API** 并填写你自己的 Key。
- 浏览器、模型和显示修正都会写入本地运行时偏好，保证浏览器工作流和桌面任务共用同一套设置。

## 如何提交好任务

- 先写目标，再补充下一步关键动作。
- 一条任务只聚焦一个结果，比如打开页面、检查状态、筛选候选项。
- 把真正重要的限制条件写清楚，比如账号环境、价格范围、颜色、目标页面。
- 涉及提交、确认或高风险操作时，明确要求先暂停给你复核。

## 常见失败与恢复

- 如果模型检查失败，先打开 **设置** 确认 provider、Base URL、模型名和 API key。
- 如果浏览器能打开但流程没有继续，先运行环境检查，再尝试一条更短的推荐起步任务。
- 如果任务进入人工复核，去时间线或浏览器接力页完成决策，再从当前状态继续。
- 如果运行中途停止，优先从历史记录恢复，而不是从头重来。

## 隐私与本地数据边界

- 任务历史、截图、浏览器状态、设置和本地诊断都保留在你的设备上。
- 云端只保存网站登录和下载权限所需的最少身份数据。
- 卸载应用时，只有在你明确选择删除时，本地工作数据才会一起移除。

## 需要高级文档？

- 想看开发者向的配置说明或更底层的实现细节时，可以在设置里打开 **高级文档**。
"""


def _dashboard_help_content_clean(self: DashboardApp, *, locale: str = "zh-CN", audience: str = "user") -> dict[str, Any]:
    normalized_locale = normalize_help_locale(locale)
    normalized_audience = _normalize_help_audience(audience)
    return {
        "title": (
            "Advanced Docs"
            if normalized_locale == "en-US" and normalized_audience == "developer"
            else "高级文档"
            if normalized_audience == "developer"
            else "Help Center"
            if normalized_locale == "en-US"
            else "帮助中心"
        ),
        "locale": normalized_locale,
        "audience": normalized_audience,
        "markdown": (
            load_help_markdown(resolve_help_path(normalized_locale))
            if normalized_audience == "developer"
            else _build_user_help_markdown(normalized_locale)
        ),
    }


DashboardApp.help_content = _dashboard_help_content_clean


def _open_browser_when_ready(url: str, *, attempts: int = 20, delay_seconds: float = 0.2) -> None:
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80

    for _ in range(max(attempts, 1)):
        try:
            with socket.create_connection((host, port), timeout=0.4):
                break
        except OSError:
            time.sleep(delay_seconds)

    _open_browser(url)


def _managed_browser_base_url(config: Any) -> str:
    host = str(getattr(config, "managed_browser_host", "127.0.0.1") or "127.0.0.1").strip() or "127.0.0.1"
    try:
        port = int(getattr(config, "managed_browser_port", 38991) or 38991)
    except (TypeError, ValueError):
        port = 38991
    return f"http://{host}:{port}"


def _managed_browser_status_signature(config: Any) -> str:
    try:
        port = int(getattr(config, "managed_browser_port", 38991) or 38991)
    except (TypeError, ValueError):
        port = 38991
    return json.dumps(
        {
            "transport": str(getattr(config, "browser_runtime_transport", "local_http") or "local_http"),
            "host": str(getattr(config, "managed_browser_host", "127.0.0.1") or "127.0.0.1"),
            "port": port,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _default_managed_browser_status(config: Any, *, detail: str = "Aoryn Browser is not running.") -> dict[str, Any]:
    return {
        "available": False,
        "detail": detail,
        "base_url": _managed_browser_base_url(config),
    }


def _provider_environment_signature(*, provider: str, base_url: str, api_key: str) -> str:
    return json.dumps(
        {
            "provider": str(provider or "").strip(),
            "base_url": normalize_api_base_url(base_url),
            "api_key": str(api_key or ""),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _try_webbrowser_open(url: str) -> bool:
    try:
        return bool(webbrowser.open(url, new=2))
    except Exception:
        return False


def _open_with_platform_fallback(url: str) -> bool:
    if sys.platform.startswith("win"):
        if _open_with_windows_startfile(url):
            return True
        if _spawn_open_command(["cmd", "/c", "start", "", url]):
            return True
        return _spawn_open_command(["explorer.exe", url])
    if sys.platform == "darwin":
        return _spawn_open_command(["open", url])
    return _spawn_open_command(["xdg-open", url])


def _open_with_windows_startfile(url: str) -> bool:
    starter = getattr(os, "startfile", None)
    if starter is None:
        return False
    try:
        starter(url)
        return True
    except OSError:
        return False


def _spawn_open_command(command: list[str]) -> bool:
    try:
        subprocess.Popen(command)
        return True
    except OSError:
        return False


def _parse_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
    return None


def _looks_like_local_api_base(base_url: str) -> bool:
    try:
        parsed = urlparse(str(base_url or "").strip())
    except Exception:
        return False
    host = (parsed.hostname or "").strip().lower()
    return host in {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


def _stable_preview_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _stable_preview_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_stable_preview_value(item) for item in value]
    return value


def _redact_preview_signature_config(config_overrides: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in (config_overrides or {}).items():
        if "api_key" in key.lower() or key.lower().endswith("_secret"):
            redacted[key] = "<redacted>"
        else:
            redacted[key] = value
    return redacted


def _preview_signature_config_contract(config: Any) -> dict[str, Any]:
    keys = (
        "model_provider",
        "model_base_url",
        "model_name",
        "model_auto_discover",
        "model_structured_output",
        "task_graph_request_timeout",
        "max_steps",
        "max_run_seconds",
        "pause_after_action",
        "cursor_motion_enabled",
        "cursor_motion_duration",
        "default_surface_policy",
        "browser_control_mode",
        "browser_dom_backend",
        "browser_dom_timeout",
        "browser_headless",
        "browser_channel",
        "browser_executable_path",
        "desktop_autonomy_mode",
        "approval_policy",
        "complex_task_planning",
        "plan_review_policy",
        "max_task_subgoals",
        "max_subgoal_retries",
        "orchestrator_mode",
        "stage_review_policy",
        "task_workspace_enabled",
        "max_replans_per_run",
        "max_failures_per_subgoal",
        "replan_on_recoverable_error",
        "recoverable_error_retry_limit",
        "enabled_capabilities",
        "driver_preferences",
        "shell_recipe_policy",
        "display_override_enabled",
        "display_override_monitor_device_name",
        "display_override_dpi_scale",
        "display_override_work_area_left",
        "display_override_work_area_top",
        "display_override_work_area_width",
        "display_override_work_area_height",
        "generic_app_launch_enabled",
    )
    contract: dict[str, Any] = {}
    for key in keys:
        value = getattr(config, key, None)
        if isinstance(value, tuple):
            value = list(value)
        contract[key] = value
    return contract


def _preview_task_graph_start_blocker(config: Any, task_graph: TaskGraph | dict[str, Any]) -> str | None:
    graph = task_graph if isinstance(task_graph, TaskGraph) else TaskGraph.from_dict(task_graph)
    graph = TaskGraph.from_dict(graph.to_dict())
    state = ExecutionState(
        task=str(graph.task or "").strip(),
        run_id=f"preview-check-{uuid.uuid4().hex[:12]}",
        task_graph=graph,
        app_context={"plan_source": "preview"},
    )
    if _preview_plan_review_required(config, graph):
        state.orchestration_phase = "plan_review"
        state.app_context["plan_review_status"] = "pending"
    summary = build_execution_plan_summary(state)
    plan_health = summary.get("plan_health") if isinstance(summary, dict) else None
    autonomy = plan_health.get("autonomy") if isinstance(plan_health, dict) else None
    if not isinstance(autonomy, dict):
        return None
    status = str(autonomy.get("status") or "").strip().lower()
    next_action = str(autonomy.get("next_action") or "").strip().lower()
    if status == "review_required" or next_action.startswith("approve_") or _optional_bool(autonomy.get("requires_review")) is True:
        return None
    blockers = [str(item).strip() for item in autonomy.get("blockers", []) or [] if str(item).strip()]
    if status == "needs_clarification" or next_action == "ask_user" or _optional_bool(autonomy.get("requires_user")) is True:
        return blockers[0] if blockers else "Clarify the task before starting."
    if status == "blocked" or next_action in {"recover_or_replan", "inspect_failure"} or _optional_bool(autonomy.get("can_continue")) is False:
        return blockers[0] if blockers else "The preview plan is not ready to start."
    return None


def _preview_plan_review_required(config: Any, task_graph: Any) -> bool:
    policy = str(getattr(config, "plan_review_policy", "low_risk_auto") or "low_risk_auto").strip().lower()
    if policy == "never":
        return False
    current_subgoal = task_graph.current_subgoal() if hasattr(task_graph, "current_subgoal") else None
    if current_subgoal is not None and getattr(current_subgoal, "goal_type", None) == "clarify":
        return False
    if policy == "always":
        return True
    return task_graph_risk_level(task_graph) != "low" or task_graph_is_ambiguous(task_graph)


def _build_initial_task_graph_result(
    *,
    task: str,
    task_graph: TaskGraph | dict[str, Any],
    config: Any,
    plan_review_status: str | None = None,
) -> dict[str, Any]:
    graph = task_graph if isinstance(task_graph, TaskGraph) else TaskGraph.from_dict(task_graph)
    graph = TaskGraph.from_dict(graph.to_dict())
    graph.task = str(task or graph.task or "").strip()
    state = ExecutionState(
        task=graph.task,
        run_id=f"queued-{uuid.uuid4().hex[:12]}",
        task_graph=graph,
        app_context={"plan_source": "preview"},
    )
    if plan_review_status == "approved":
        state.orchestration_phase = "stage_ready"
        state.app_context["plan_review_status"] = "approved"
        state.app_context["plan_review_reason"] = "The matching dashboard preview was approved before execution."
    elif _preview_plan_review_required(config, graph):
        state.orchestration_phase = "plan_review"
        state.pending_decision = PendingDecision(
            id=f"plan-review-{state.run_id}",
            summary=f"Review the task plan before execution: {graph.task}",
            reason="Plan review is required before execution.",
            risk_level=task_graph_risk_level(graph),
            decision_type="plan_review",
            actions=[],
        )
        state.app_context["plan_review_status"] = "pending"
        state.app_context["plan_review_reason"] = "The previewed plan matches a policy that requires review before execution."
    else:
        state.orchestration_phase = "stage_ready"
    summary = build_execution_plan_summary(state)
    return {
        "latest_summary": summary.get("current_goal") or graph.completion_summary or graph.task,
        "current_goal": summary.get("current_goal"),
        "orchestration_phase": summary.get("orchestration_phase"),
        "active_specialist": summary.get("active_specialist"),
        "stage_review_status": summary.get("stage_review_status"),
        "last_replan_reason": summary.get("last_replan_reason"),
        "verification_status": summary.get("verification_status"),
        "recovery_reason": summary.get("recovery_reason"),
        "execution_state": summary,
    }


def _build_resume_job_result(*, details: dict[str, Any], run_id: str) -> dict[str, Any] | None:
    execution_state = _resume_display_execution_state(details)
    if not isinstance(execution_state, dict):
        return None
    execution_state = _prepare_resume_display_execution_state(execution_state, details=details)
    timeline = [item for item in details.get("timeline", []) or [] if isinstance(item, dict)]
    latest_step = timeline[-1] if timeline else {}
    latest_plan = latest_step.get("plan") if isinstance(latest_step.get("plan"), dict) else {}
    latest_summary = (
        _optional_text(latest_plan.get("status_summary"))
        or _optional_text(execution_state.get("current_goal"))
        or _optional_text(details.get("interruption_reason"))
        or _optional_text(details.get("task"))
    )
    result = {
        "run_id": run_id,
        "steps": details.get("steps"),
        "latest_summary": latest_summary,
        "latest_screenshot": latest_step.get("screenshot"),
        "execution_state": execution_state,
    }
    return {key: value for key, value in result.items() if value is not None}


def _prepare_resume_display_execution_state(
    execution_state: dict[str, Any],
    *,
    details: dict[str, Any],
) -> dict[str, Any]:
    state_payload = dict(execution_state)
    app_context = dict(state_payload.get("app_context") or {}) if isinstance(state_payload.get("app_context"), dict) else {}
    handoff_kind = str(app_context.get("human_handoff_kind") or details.get("interruption_kind") or "").strip().lower()
    last_verification = state_payload.get("last_verification")
    verification_kind = (
        str(last_verification.get("failure_kind") or "").strip().lower()
        if isinstance(last_verification, dict)
        else ""
    )
    verification_message = (
        str(last_verification.get("message") or "").strip()
        if isinstance(last_verification, dict)
        else ""
    )
    if handoff_kind == "requires_clarification" or verification_kind == "requires_clarification":
        return state_payload
    if _has_pending_decision_payload(state_payload.get("pending_decision")):
        for key in ("human_handoff_kind", "human_handoff_summary", "human_handoff_reason"):
            app_context.pop(key, None)
        if str(app_context.get("standard_recovery_kind") or "").strip().lower() == "requires_user":
            app_context.pop("standard_recovery_kind", None)
        state_payload["app_context"] = app_context
        return state_payload

    handoff_reason = str(
        app_context.get("human_handoff_reason")
        or app_context.get("human_handoff_summary")
        or state_payload.get("recovery_reason")
        or details.get("interruption_reason")
        or (verification_message if verification_kind in {"requires_human", "requires_auth"} else "")
        or ""
    ).strip()
    orchestration_phase = str(state_payload.get("orchestration_phase") or "").strip().lower()
    was_waiting_for_user = (
        orchestration_phase in {"awaiting_user", "awaiting_approval"}
        or _optional_bool(details.get("requires_human")) is True
        or bool(str(details.get("interruption_kind") or "").strip())
        or bool(str(details.get("interruption_reason") or "").strip())
        or bool(handoff_reason)
        or verification_kind in {"requires_human", "requires_auth"}
    )
    if not was_waiting_for_user:
        return state_payload

    for key in ("human_handoff_kind", "human_handoff_summary", "human_handoff_reason"):
        app_context.pop(key, None)
    if str(app_context.get("standard_recovery_kind") or "").strip().lower() == "requires_user":
        app_context.pop("standard_recovery_kind", None)
    if handoff_reason and str(app_context.get("recovery_reason") or "").strip() == handoff_reason:
        app_context.pop("recovery_reason", None)
    app_context["manual_resume_status"] = "resumed"
    app_context["manual_resume_reason"] = handoff_reason or "User resumed the paused run."
    state_payload["app_context"] = app_context
    state_payload["orchestration_phase"] = "stage_ready"
    state_payload["pending_decision"] = None
    state_payload["last_verification"] = None
    if state_payload.get("verification_status"):
        state_payload["verification_status"] = None
    if state_payload.get("recovery_reason") == handoff_reason:
        state_payload["recovery_reason"] = None

    plan_health = state_payload.get("plan_health")
    if isinstance(plan_health, dict):
        updated_plan_health = dict(plan_health)
        autonomy = updated_plan_health.get("autonomy")
        updated_autonomy = dict(autonomy) if isinstance(autonomy, dict) else {}
        updated_autonomy.update(
            {
                "status": "ready",
                "can_continue": True,
                "requires_review": False,
                "requires_user": False,
                "next_action": "execute",
                "blockers": [],
            }
        )
        updated_plan_health["autonomy"] = updated_autonomy
        state_payload["plan_health"] = updated_plan_health
    return state_payload


def _resume_display_execution_state(details: dict[str, Any]) -> dict[str, Any] | None:
    full_state = details.get("execution_state") if isinstance(details.get("execution_state"), dict) else None
    display_state = details.get("state") if isinstance(details.get("state"), dict) else None
    plan_payload = details.get("plan") if isinstance(details.get("plan"), dict) else None
    merged: dict[str, Any] = {}
    if isinstance(full_state, dict):
        merged.update(full_state)
    if isinstance(plan_payload, dict) and "task_graph" not in merged:
        merged["task_graph"] = plan_payload
    if isinstance(display_state, dict):
        merged = _merge_execution_state_summary_payloads(merged, display_state)
        if not isinstance(merged.get("task_graph"), dict) and isinstance(full_state, dict) and isinstance(full_state.get("task_graph"), dict):
            merged["task_graph"] = full_state["task_graph"]
        if not isinstance(merged.get("task_graph"), dict) and isinstance(plan_payload, dict):
            merged["task_graph"] = plan_payload
    if not merged:
        return None
    if not str(merged.get("task") or "").strip():
        merged["task"] = details.get("task")
    return {key: value for key, value in merged.items() if value is not None}


def _details_can_resume(details: dict[str, Any]) -> bool:
    if not isinstance(details, dict) or _optional_bool(details.get("completed")) is True:
        return False
    can_resume = _optional_bool(details.get("can_resume"))
    if can_resume is not None:
        return can_resume
    if str(details.get("resume_mode") or "").strip():
        return True
    if _optional_bool(details.get("requires_human")) is True:
        return True
    return _details_have_resume_state(details)


def _details_have_resume_state(details: dict[str, Any]) -> bool:
    execution_state = details.get("execution_state")
    if isinstance(execution_state, dict) and isinstance(execution_state.get("task_graph"), dict):
        return True
    state_payload = details.get("state")
    if isinstance(state_payload, dict) and (
        isinstance(state_payload.get("task_graph"), dict) or isinstance(state_payload.get("subgoals"), list)
    ):
        return True
    plan_payload = details.get("plan")
    return isinstance(plan_payload, dict) and isinstance(plan_payload.get("subgoals"), list)


def _clean_config_overrides(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}

    cleaned: dict[str, Any] = {}
    parsers: dict[str, Any] = {
        "primary_model_profile": _optional_text,
        "fallback_model_profile": _optional_text,
        "model_provider": _optional_text,
        "model_base_url": _optional_text,
        "model_name": _optional_text,
        "model_api_key": _optional_text,
        "model_request_timeout": _optional_float,
        "task_graph_request_timeout": _optional_float,
        "max_steps": _optional_int,
        "max_run_seconds": _optional_float,
        "pause_after_action": _optional_float,
        "model_auto_discover": _optional_bool,
        "model_structured_output": _optional_text,
        "default_surface_policy": _optional_text,
        "managed_browser_enabled": _optional_bool,
        "external_browser_attach_enabled": _optional_bool,
        "safe_mode_enabled": _optional_bool,
        "user_input_preemption_policy": _optional_text,
        "shell_start_mode": _optional_text,
        "browser_runtime_transport": _optional_text,
        "browser_profile_strategy": _optional_text,
        "desktop_autonomy_mode": _optional_text,
        "approval_policy": _optional_text,
        "complex_task_planning": _optional_text,
        "plan_review_policy": _optional_text,
        "max_task_subgoals": _optional_int,
        "max_subgoal_retries": _optional_int,
        "orchestrator_mode": _optional_text,
        "stage_review_policy": _optional_text,
        "task_workspace_enabled": _optional_bool,
        "max_replans_per_run": _optional_int,
        "max_failures_per_subgoal": _optional_int,
        "replan_on_recoverable_error": _optional_bool,
        "recoverable_error_retry_limit": _optional_int,
        "plugin_fail_fast": _optional_bool,
        "browser_control_mode": _optional_text,
        "browser_dom_backend": _optional_text,
        "browser_dom_timeout": _optional_float,
        "cursor_motion_enabled": _optional_bool,
        "cursor_motion_duration": _optional_float,
        "browser_headless": _optional_bool,
        "browser_channel": _optional_text,
        "browser_executable_path": _optional_text,
        "display_override_enabled": _optional_bool,
        "display_override_monitor_device_name": _optional_text,
        "display_override_dpi_scale": _optional_float,
        "display_override_work_area_left": _optional_int,
        "display_override_work_area_top": _optional_int,
        "display_override_work_area_width": _optional_int,
        "display_override_work_area_height": _optional_int,
        "shell_recipe_policy": _optional_text,
    }
    for key, parser in parsers.items():
        value = parser(raw.get(key))
        if value is not None:
            cleaned[key] = value
    enabled_capabilities = raw.get("enabled_capabilities")
    if isinstance(enabled_capabilities, list):
        cleaned["enabled_capabilities"] = [str(item).strip() for item in enabled_capabilities if str(item).strip()]
    driver_preferences = raw.get("driver_preferences")
    if isinstance(driver_preferences, list):
        cleaned["driver_preferences"] = [str(item).strip() for item in driver_preferences if str(item).strip()]
    plugin_modules = raw.get("plugin_modules")
    if isinstance(plugin_modules, str):
        cleaned["plugin_modules"] = [item.strip() for item in plugin_modules.replace(";", ",").split(",") if item.strip()]
    elif isinstance(plugin_modules, list):
        cleaned["plugin_modules"] = [str(item).strip() for item in plugin_modules if str(item).strip()]
    return cleaned
