from __future__ import annotations

import json
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
from desktop_agent.controller import discover_config_path, load_agent_config, run_task
from desktop_agent.history import list_runs, load_run_details, resolve_artifact_path
from desktop_agent.provider_tools import (
    ProviderModelEntry,
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
    config_overrides: dict[str, Any] = field(default_factory=dict)
    status: str = "queued"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    updated_at: float = field(default_factory=time.time)
    result: dict[str, Any] | None = None
    error: str | None = None
    cancel_requested: bool = False
    cancelled: bool = False
    requires_human: bool = False
    interruption_kind: str | None = None
    interruption_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.job_id,
            "task": self.task,
            "planner_mode": self.planner_mode,
            "dry_run": self.dry_run,
            "max_steps": self.max_steps,
            "pause_after_action": self.pause_after_action,
            "config_overrides": self.config_overrides,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "updated_at": self.updated_at,
            "result": self.result,
            "error": self.error,
            "cancel_requested": self.cancel_requested,
            "cancelled": self.cancelled,
            "requires_human": self.requires_human,
            "interruption_kind": self.interruption_kind,
            "interruption_reason": self.interruption_reason,
        }


class TaskQueue:
    def __init__(self, config_path: Path | None) -> None:
        self.config_path = config_path
        self.lock = threading.Lock()
        self.jobs: dict[str, DashboardJob] = {}
        self.cancel_events: dict[str, threading.Event] = {}
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
            job = DashboardJob(
                job_id=uuid.uuid4().hex[:12],
                task=clean_task,
                planner_mode=config.planner_mode,
                dry_run=config.dry_run,
                max_steps=max_steps,
                pause_after_action=pause_after_action,
                config_overrides=resolved_overrides,
            )
            self.jobs[job.job_id] = job
            self.cancel_events[job.job_id] = threading.Event()
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

    def cancel_active(self) -> dict[str, Any]:
        with self.lock:
            if self.active_job_id is None:
                raise RuntimeError("No active task is running.")
            job = self.jobs[self.active_job_id]
            cancel_event = self.cancel_events.get(job.job_id)
            if cancel_event is not None:
                cancel_event.set()
            job.cancel_requested = True
            job.status = "stopping"
            job.updated_at = time.time()
            return job.to_dict()

    def _run_job(self, job_id: str) -> None:
        with self.lock:
            job = self.jobs[job_id]
            job.status = "running"
            job.started_at = time.time()
            job.updated_at = time.time()
            cancel_event = self.cancel_events.get(job_id)

        try:
            result = run_task(
                job.task,
                config_path=self.config_path,
                planner_mode=job.planner_mode,
                dry_run=job.dry_run,
                max_steps=job.max_steps,
                pause_after_action=job.pause_after_action,
                config_overrides=job.config_overrides,
                stop_requested=cancel_event.is_set if cancel_event is not None else None,
                progress_callback=lambda payload: self._update_job_progress(job_id, payload),
            )
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
                "requires_human": result.requires_human,
                "interruption_kind": result.interruption_kind,
                "interruption_reason": result.interruption_reason,
            }
            with self.lock:
                if result.completed:
                    job.status = "completed"
                elif result.cancelled:
                    job.status = "cancelled"
                elif result.requires_human:
                    job.status = "attention"
                else:
                    job.status = "failed"
                job.result = payload
                job.error = result.error
                job.cancelled = result.cancelled
                job.started_at = result.started_at
                job.finished_at = result.finished_at
                job.requires_human = result.requires_human
                job.interruption_kind = result.interruption_kind
                job.interruption_reason = result.interruption_reason
                job.updated_at = time.time()
                self.active_job_id = None
        except Exception as exc:  # pragma: no cover - runtime safety
            with self.lock:
                job.status = "failed"
                job.error = str(exc)
                job.finished_at = time.time()
                job.updated_at = time.time()
                self.active_job_id = None
        finally:
            with self.lock:
                self.cancel_events.pop(job_id, None)

    def _update_job_progress(self, job_id: str, payload: dict[str, Any]) -> None:
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                return
            current_result = dict(job.result or {})
            current_result.update(payload)
            job.result = current_result
            if isinstance(payload.get("started_at"), (int, float)):
                job.started_at = float(payload["started_at"])
            job.updated_at = time.time()

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
        base.setdefault("onboarding_completed", False)
        return {
            "onboarding_completed": bool(base.get("onboarding_completed")),
        }

    if "onboarding_completed" in raw:
        base["onboarding_completed"] = bool(raw.get("onboarding_completed"))
    base.setdefault("onboarding_completed", False)
    return {
        "onboarding_completed": bool(base.get("onboarding_completed")),
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
                    return self._send_json(app.help_content(locale=locale))
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
                        job = app.queue.submit(
                            task=str(body.get("task", "")),
                            planner_mode="auto",
                            dry_run=False,
                            max_steps=_optional_int(body.get("max_steps")),
                            pause_after_action=_optional_float(body.get("pause_after_action")),
                            config_overrides=_clean_config_overrides(body.get("config_overrides")),
                        )
                    except ValueError as exc:
                        return self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    except RuntimeError as exc:
                        return self._send_error(HTTPStatus.CONFLICT, str(exc))
                    return self._send_json(job.to_dict(), status=HTTPStatus.ACCEPTED)

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

                if path == "/api/chat":
                    try:
                        payload = app.chat_reply(
                            messages=body.get("messages"),
                            config_overrides=_clean_config_overrides(body.get("config_overrides")),
                            session_meta=body.get("session_meta"),
                            recovery_context=body.get("recovery_context"),
                        )
                    except ValueError as exc:
                        return self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    except ProviderToolError as exc:
                        return self._send_json(_provider_error_payload(exc), status=HTTPStatus.BAD_REQUEST)
                    return self._send_json(payload)

                if path == "/api/chat/stream":
                    return self._send_event_stream(
                        app.chat_reply_stream(
                            messages=body.get("messages"),
                            config_overrides=_clean_config_overrides(body.get("config_overrides")),
                            session_meta=body.get("session_meta"),
                            recovery_context=body.get("recovery_context"),
                        )
                    )

                if path == "/api/provider/models":
                    try:
                        snapshot = app.provider_models(_clean_config_overrides(body.get("config_overrides")))
                    except ProviderToolError as exc:
                        return self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    return self._send_json(snapshot)

                if path == "/api/provider/load-model":
                    try:
                        payload = app.provider_load_model(
                            config_overrides=_clean_config_overrides(body.get("config_overrides")),
                            model_id=str(body.get("model_id", "")).strip(),
                            unload_first=bool(body.get("unload_first")),
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
                "pause_after_action": config.pause_after_action,
                "model_provider": config.model_provider,
                "model_base_url": config.model_base_url,
                "model_name": config.model_name,
                "model_api_key": config.model_api_key or "",
                "model_auto_discover": config.model_auto_discover,
                "model_structured_output": config.model_structured_output,
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
            "planner_modes": [
                {"value": "auto", "label": "Auto"},
                {"value": "rule", "label": "Rule"},
                {"value": "vlm", "label": "VLM"},
            ],
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
                {"id": "visit_docs", "label": "Visit Docs", "task": "visit openai.com/docs"},
                {"id": "dom_follow_up", "label": "DOM Follow-up", "task": "visit openai.com and click login"},
                {"id": "shopping_search", "label": "Shopping Search", "task": "shop for high-value men's pants on amazon"},
            ],
            "workflow_recipes": [
                {
                    "id": "ordered_browser_task",
                    "label": "Ordered Browser Task",
                    "task": "visit openai.com and click login and then type your email",
                    "hint": "Put the goal first, then order follow-up actions so the planner can keep moving without repeating the entry step.",
                },
                {
                    "id": "shopping_refine",
                    "label": "Style + Color Refine",
                    "task": "shop for high-value men's pants on amazon and filter by style and choose black and sort by price low to high",
                    "hint": "Useful for validating chained shopping plans where filters, color selection, and sorting happen step by step.",
                },
                {
                    "id": "shopping_compare",
                    "label": "Top-Rated Compare",
                    "task": "shop for high-value men's pants on amazon and sort by customer review and filter by price range",
                    "hint": "Good for narrowing the result set before you compare products or continue with a manual decision.",
                },
                {
                    "id": "login_flow",
                    "label": "Login Flow",
                    "task": "visit openai.com and click login",
                    "hint": "Great for testing a two-step browser workflow with DOM follow-up.",
                },
                {
                    "id": "provider_check",
                    "label": "Provider Check",
                    "task": "visit platform.openai.com/docs and click API reference",
                    "hint": "Useful for validating provider links and docs-oriented navigation.",
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

    def help_content(self, *, locale: str = "zh-CN") -> dict[str, Any]:
        normalized_locale = normalize_help_locale(locale)
        return {
            "title": f"{APP_NAME} Help Center" if normalized_locale == "en-US" else f"{APP_NAME} 帮助中心",
            "locale": normalized_locale,
            "markdown": load_help_markdown(resolve_help_path(normalized_locale)),
        }

    def overview(self) -> dict[str, Any]:
        return {
            "meta": self.meta(),
            "runtime_preferences": self.runtime_preferences.snapshot(),
            "active_job": self.queue.active_job(),
            "jobs": self.queue.list_jobs(limit=8),
            "runs": list_runs(self.run_root, limit=12),
        }

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
        api_key = str(config.model_api_key or "").strip()
        connection_item = {
            "id": "provider_connection",
            "label": "Provider connection",
            "status": "Needs setup",
            "detail": "Complete the provider settings first.",
            "action": "refresh_model_catalog",
        }
        requires_api_key = provider_value in {"openai_api", "openai_compatible"}
        if not provider_value:
            connection_item["action"] = "open_settings"
        elif not api_base:
            connection_item["detail"] = "Add a Base URL in Settings before checking the provider connection."
            connection_item["action"] = "open_settings"
        elif requires_api_key and not api_key:
            connection_item["detail"] = "Add an API key in Settings before checking the provider connection."
            connection_item["action"] = "open_settings"
        else:
            snapshot = fetch_provider_snapshot(
                provider=provider_value,
                base_url=api_base,
                api_key=api_key,
                timeout=min(float(config.model_request_timeout), 10.0),
            )
            if snapshot.ok:
                catalog_count = len(snapshot.catalog_models)
                loaded_count = len(snapshot.loaded_models)
                if provider_value == "lmstudio_local":
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
        return {
            "items": items,
            "checked_at": time.time(),
            "provider": provider_value,
            "model_name": model_name,
        }

    def display_detection(self) -> dict[str, Any]:
        config = load_agent_config(self.config_path, config_overrides=self._runtime_config_overrides())
        return detect_display_environment(config=config).to_dict()

    def _runtime_config_overrides(self) -> dict[str, Any]:
        runtime_snapshot = self.runtime_preferences.snapshot()
        return _clean_config_overrides(runtime_snapshot.get("config_overrides"))

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
        parsed_recovery_context = self._coerce_recovery_context(recovery_context)
        if parsed_recovery_context:
            return self._chat_reply_with_temporary_text_model(
                messages=messages,
                config_overrides=config_overrides,
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
        config = load_agent_config(self.config_path, config_overrides=config_overrides)
        model_name = self._resolve_chat_model(config_overrides=config_overrides)
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
                    config_overrides=config_overrides,
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
                config_overrides=config_overrides,
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
        config = load_agent_config(self.config_path, config_overrides=config_overrides)
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
                config_overrides=config_overrides,
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
        config = load_agent_config(self.config_path, config_overrides=config_overrides)
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
        config = load_agent_config(self.config_path, config_overrides=config_overrides)
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
        suggested_text_model = recovery_context["suggested_text_model"]
        restore_to_model = recovery_context["restore_to_model"]
        retry_overrides = dict(config_overrides or {})
        retry_overrides["model_name"] = suggested_text_model

        with self.model_switch_lock:
            self.provider_load_model(
                config_overrides=config_overrides,
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
                        config_overrides=config_overrides,
                        model_id=restore_to_model,
                        unload_first=True,
                    )

    def _resolve_chat_model_selection(
        self,
        *,
        config_overrides: dict[str, Any],
        snapshot: Any | None = None,
    ) -> tuple[str, bool]:
        config = load_agent_config(self.config_path, config_overrides=config_overrides)
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


def _dashboard_help_content(self: DashboardApp, *, locale: str = "zh-CN") -> dict[str, Any]:
    normalized_locale = normalize_help_locale(locale)
    return {
        "title": "Developer Docs" if normalized_locale == "en-US" else "开发者文档",
        "locale": normalized_locale,
        "markdown": load_help_markdown(resolve_help_path(normalized_locale)),
    }


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
    print("Attempting to open the dashboard in your browser...")
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
    clean_messages = sanitize_chat_messages(messages)
    if not clean_messages:
        yield "error", {"error": "At least one chat message is required."}
        return

    session_payload = session_meta if isinstance(session_meta, dict) else {}
    locale = normalize_help_locale(session_payload.get("locale"))
    latest_user_message = _extract_latest_user_message(clean_messages)
    math_mode = looks_like_math_request(latest_user_message)
    yield "start", {"session_meta": session_payload or None}

    config = load_agent_config(self.config_path, config_overrides=config_overrides)
    parsed_recovery_context = self._coerce_recovery_context(recovery_context)
    if config.model_provider == "lmstudio_local" and parsed_recovery_context:
        try:
            payload = self.chat_reply(
                messages=clean_messages,
                config_overrides=config_overrides,
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
        model_name = self._resolve_chat_model(config_overrides=config_overrides)
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
                    config_overrides=config_overrides,
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
                        config_overrides=config_overrides,
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
                    config_overrides=config_overrides,
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


def _dashboard_help_content_clean(self: DashboardApp, *, locale: str = "zh-CN") -> dict[str, Any]:
    normalized_locale = normalize_help_locale(locale)
    return {
        "title": "Developer Docs" if normalized_locale == "en-US" else "开发者文档",
        "locale": normalized_locale,
        "markdown": load_help_markdown(resolve_help_path(normalized_locale)),
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
    if value in {None, ""}:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        return None
    return bool(value)


def _clean_config_overrides(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}

    cleaned: dict[str, Any] = {}
    parsers: dict[str, Any] = {
        "model_provider": _optional_text,
        "model_base_url": _optional_text,
        "model_name": _optional_text,
        "model_api_key": _optional_text,
        "model_auto_discover": _optional_bool,
        "model_structured_output": _optional_text,
        "browser_control_mode": _optional_text,
        "browser_dom_backend": _optional_text,
        "browser_dom_timeout": _optional_float,
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
    }
    for key, parser in parsers.items():
        value = parser(raw.get(key))
        if value is not None:
            cleaned[key] = value
    return cleaned
