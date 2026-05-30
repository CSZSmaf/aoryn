from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import requests

from desktop_agent.dashboard import DashboardApp
from desktop_agent.controller import load_agent_config
from desktop_agent.runtime_paths import default_cache_root, local_data_root
from desktop_agent.version import APP_ASSET_VERSION, APP_ID, APP_NAME, APP_VERSION

try:  # pragma: no cover - import availability depends on runtime environment
    from PySide6.QtCore import QEvent, QObject, QPoint, QRectF, QSize, QTimer, Qt, QUrl, Signal
    from PySide6.QtGui import QAction, QCloseEvent, QCursor, QIcon, QPainterPath, QRegion
    from PySide6.QtWidgets import (
        QApplication,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMenu,
        QPushButton,
        QSizePolicy,
        QSystemTrayIcon,
        QVBoxLayout,
        QWidget,
    )
    from PySide6.QtWebEngineCore import QWebEngineProfile
    from PySide6.QtWebEngineWidgets import QWebEngineView

    _QT_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - import availability depends on runtime environment
    QApplication = None  # type: ignore[assignment]
    QCloseEvent = object  # type: ignore[assignment]
    QFrame = object  # type: ignore[assignment]
    QHBoxLayout = object  # type: ignore[assignment]
    QLabel = object  # type: ignore[assignment]
    QLineEdit = object  # type: ignore[assignment]
    QMainWindow = object  # type: ignore[assignment]
    QMenu = object  # type: ignore[assignment]
    QPushButton = object  # type: ignore[assignment]
    QSizePolicy = object  # type: ignore[assignment]
    QSystemTrayIcon = object  # type: ignore[assignment]
    QTimer = object  # type: ignore[assignment]
    QUrl = object  # type: ignore[assignment]
    QVBoxLayout = object  # type: ignore[assignment]
    QWidget = object  # type: ignore[assignment]
    QAction = object  # type: ignore[assignment]
    QCursor = object  # type: ignore[assignment]
    QIcon = object  # type: ignore[assignment]
    QObject = object  # type: ignore[assignment]
    QPoint = object  # type: ignore[assignment]
    QRectF = object  # type: ignore[assignment]
    QSize = object  # type: ignore[assignment]
    QEvent = object  # type: ignore[assignment]
    Signal = object  # type: ignore[assignment]
    Qt = object  # type: ignore[assignment]
    QPainterPath = object  # type: ignore[assignment]
    QRegion = object  # type: ignore[assignment]
    QWebEngineProfile = object  # type: ignore[assignment]
    QWebEngineView = object  # type: ignore[assignment]
    _QT_IMPORT_ERROR = exc

from desktop_agent.windows_env import capture_effective_desktop_environment, preferred_work_area


class DesktopShellUnavailable(RuntimeError):
    """Raised when the native desktop shell cannot be launched."""


_FLOATING_IDLE_WIDTH = 220
_FLOATING_RUNNING_WIDTH = 280
_FLOATING_EXPANDED_WIDTH = 440
_FLOATING_DECISION_WIDTH = 360
_FLOATING_IDLE_HEIGHT = 46
_FLOATING_EXPANDED_HEIGHT = 54
_FLOATING_DECISION_HEIGHT = 50
_FLOATING_TITLE_LIMIT = 22
_TRUE_STRING_VALUES = {"1", "true", "t", "yes", "y", "on"}
_FALSE_STRING_VALUES = {"0", "false", "f", "no", "n", "off"}
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


@dataclass(frozen=True, slots=True)
class FloatingViewState:
    mode: str
    title: str
    width: int
    height: int
    show_timer: bool = False
    show_input: bool = False
    show_open: bool = False
    show_add: bool = False
    show_submit: bool = False
    show_cancel: bool = False
    show_stop: bool = False
    show_continue: bool = False
    stop_enabled: bool = True
    stop_label: str = "停止"
    continue_label: str = "继续"
    submit_label: str = "开始"
    add_label: str = "+"
    input_placeholder: str = "输入任务"
    input_text: str = ""


def _short_floating_text(value: object, *, fallback: str, limit: int = _FLOATING_TITLE_LIMIT) -> str:
    text = " ".join(str(value or "").split()).strip() or fallback
    if len(text) <= limit:
        return text
    return f"{text[: max(1, limit - 3)]}..."


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _TRUE_STRING_VALUES:
            return True
        if normalized in _FALSE_STRING_VALUES:
            return False
    return None


def _bool_value(value: object) -> bool:
    return _optional_bool(value) is True


def _summary_bool(value: object) -> object:
    parsed = _optional_bool(value)
    return value if parsed is None else parsed


def _job_is_terminal_result(active_job: dict[str, Any]) -> bool:
    if not isinstance(active_job, dict) or not active_job:
        return False
    result = active_job.get("result") if isinstance(active_job.get("result"), dict) else {}
    status = str(active_job.get("status") or "").strip().lower()
    return bool(
        _bool_value(result.get("cancelled"))
        or _bool_value(active_job.get("cancelled"))
        or status == "cancelled"
        or result.get("error")
        or active_job.get("error")
        or status == "failed"
        or _bool_value(result.get("completed"))
        or _bool_value(active_job.get("completed"))
        or status == "completed"
    )


def _pending_decision_from_job(active_job: dict[str, Any]) -> dict[str, Any] | None:
    pending_decision = active_job.get("pending_decision") if isinstance(active_job, dict) else None
    if isinstance(pending_decision, dict) and pending_decision:
        return pending_decision
    result = active_job.get("result") if isinstance(active_job.get("result"), dict) else {}
    pending_decision = result.get("pending_decision") if isinstance(result, dict) else None
    if not isinstance(pending_decision, dict):
        execution_state = _job_execution_state_from_result(result)
        pending_decision = execution_state.get("pending_decision") if isinstance(execution_state, dict) else None
    return pending_decision if isinstance(pending_decision, dict) and pending_decision else None


def _job_execution_state_from_result(result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    full_state = result.get("execution_state") if isinstance(result.get("execution_state"), dict) else {}
    summary_state = result.get("state") if isinstance(result.get("state"), dict) else {}
    if full_state or summary_state:
        return {**full_state, **summary_state}
    return {}


def _job_orchestration_phase(active_job: dict[str, Any]) -> str:
    if not isinstance(active_job, dict):
        return ""
    result = active_job.get("result") if isinstance(active_job.get("result"), dict) else {}
    execution_state = _job_execution_state_from_result(result)
    return str(
        active_job.get("orchestration_phase")
        or result.get("orchestration_phase")
        or execution_state.get("orchestration_phase")
        or ""
    ).strip().lower()


def _run_execution_state(run: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(run, dict):
        return {}
    execution_state = run.get("execution_state") if isinstance(run.get("execution_state"), dict) else {}
    state_payload = run.get("state") if isinstance(run.get("state"), dict) else {}
    if execution_state or state_payload:
        return {**execution_state, **state_payload}
    return {}


def _run_orchestration_phase(run: dict[str, Any] | None) -> str:
    if not isinstance(run, dict):
        return ""
    execution_state = _run_execution_state(run)
    return str(run.get("orchestration_phase") or execution_state.get("orchestration_phase") or "").strip().lower()


def _job_waits_for_decision(active_job: dict[str, Any]) -> bool:
    if not isinstance(active_job, dict) or not active_job:
        return False
    if _job_is_terminal_result(active_job):
        return False
    status = str(active_job.get("status") or "").strip().lower()
    return (
        status == "approval"
        or _pending_decision_from_job(active_job) is not None
        or _job_orchestration_phase(active_job) == "awaiting_approval"
    )


def _manual_handoff_title_from_state(execution_state: dict[str, Any]) -> str:
    app_context = execution_state.get("app_context") if isinstance(execution_state.get("app_context"), dict) else {}
    manual_resume_status = str(app_context.get("manual_resume_status") or "").strip().lower()
    if manual_resume_status in {"resumed", "complete", "completed", "cleared"}:
        return ""
    orchestration_phase = str(execution_state.get("orchestration_phase") or "").strip().lower()
    if orchestration_phase == "awaiting_approval":
        return "\u7b49\u5f85\u786e\u8ba4: \u4e0b\u4e00\u6b65\u52a8\u4f5c\u9700\u8981\u6279\u51c6"
    handoff_reason = str(
        app_context.get("human_handoff_reason")
        or app_context.get("human_handoff_summary")
        or app_context.get("recovery_reason")
        or ""
    ).strip()
    handoff_kind = str(app_context.get("human_handoff_kind") or "").strip()
    recovery_kind = str(app_context.get("standard_recovery_kind") or "").strip().lower()
    if not (handoff_reason or handoff_kind or recovery_kind == "requires_user"):
        return ""
    return f"等待人工处理: {handoff_reason or handoff_kind or '需要继续确认'}"


def _active_job_goal_title(active_job: dict[str, Any], *, stop_requested: bool) -> str:
    if stop_requested:
        return "\u6b63\u5728\u505c\u6b62"
    result = active_job.get("result") if isinstance(active_job.get("result"), dict) else {}
    status = str(active_job.get("status") or "").strip().lower()
    if _bool_value(result.get("cancelled")) or _bool_value(active_job.get("cancelled")) or status == "cancelled":
        return "\u4efb\u52a1\u5df2\u505c\u6b62"
    execution_state = _job_execution_state_from_result(result)
    handoff_title = _manual_handoff_title_from_state(execution_state)
    if handoff_title:
        return handoff_title
    result_handoff_reason = str(result.get("interruption_reason") or "").strip()
    result_handoff_kind = str(result.get("interruption_kind") or "").strip()
    if _bool_value(result.get("requires_human")) or result_handoff_reason or result_handoff_kind:
        return f"等待人工处理: {result_handoff_reason or result_handoff_kind or '需要继续确认'}"
    error_text = str(result.get("error") or active_job.get("error") or "").strip()
    if error_text or status == "failed":
        return "\u9700\u8981\u5904\u7406: " + (error_text or "\u6267\u884c\u5931\u8d25")
    if _bool_value(result.get("completed")) or _bool_value(active_job.get("completed")) or status == "completed":
        return "\u4efb\u52a1\u5b8c\u6210"
    recovery_reason = str(result.get("recovery_reason") or execution_state.get("recovery_reason") or "").strip()
    if recovery_reason:
        return f"\u4fee\u590d\u4e2d: {recovery_reason}"
    current_goal = str(result.get("current_goal") or execution_state.get("current_goal") or "").strip()
    if current_goal:
        return current_goal
    latest_summary = str(result.get("latest_summary") or "").strip()
    if latest_summary:
        return latest_summary
    return str(active_job.get("task") or "").strip() or "\u6b63\u5728\u6267\u884c\u4efb\u52a1"


def build_floating_view_state(
    *,
    active_job: dict[str, Any] | None = None,
    follow_up_draft: str = "",
    resume_run_id: str | None = None,
    resume_task: str = "",
    resume_reason: str = "",
    waiting_status: str = "",
    input_expanded: bool = False,
    app_name: str = APP_NAME,
) -> FloatingViewState:
    active = active_job if isinstance(active_job, dict) else {}
    draft = str(follow_up_draft or "").strip()
    has_job = bool(active)
    status = str(active.get("status") or "").strip().lower() if has_job else ""
    result = active.get("result") if has_job and isinstance(active.get("result"), dict) else {}
    terminal_cancelled = bool(
        has_job and (_bool_value(result.get("cancelled")) or _bool_value(active.get("cancelled")) or status == "cancelled")
    )
    terminal_failed = bool(has_job and (result.get("error") or active.get("error") or status == "failed"))
    terminal_completed = bool(
        has_job and (_bool_value(result.get("completed")) or _bool_value(active.get("completed")) or status == "completed")
    )
    terminal_result = terminal_cancelled or terminal_failed or terminal_completed
    pending_decision = _pending_decision_from_job(active) if has_job else None
    is_approval = _job_waits_for_decision(active) if has_job and not terminal_result else False
    stop_requested = _bool_value(active.get("cancel_requested")) or status == "stopping"
    has_resume = bool(str(resume_run_id or "").strip())
    expanded = bool(input_expanded)

    if is_approval:
        title = "需要确认"
        if pending_decision is not None:
            title = str(pending_decision.get("summary") or pending_decision.get("reason") or title)
        return FloatingViewState(
            mode="approval",
            title=_short_floating_text(title, fallback="需要确认"),
            width=_FLOATING_DECISION_WIDTH,
            height=_FLOATING_DECISION_HEIGHT,
            show_stop=True,
            show_continue=True,
            stop_label="驳回",
            continue_label="批准",
        )

    if has_job:
        title = _short_floating_text(active.get("task"), fallback="正在执行任务")
        if stop_requested:
            title = "正在停止"
        title = _short_floating_text(
            _active_job_goal_title(active, stop_requested=stop_requested),
            fallback="\u6b63\u5728\u6267\u884c\u4efb\u52a1",
        )
        if terminal_result:
            return FloatingViewState(
                mode="stopping" if terminal_cancelled else "running",
                title=title,
                width=_FLOATING_IDLE_WIDTH,
                height=_FLOATING_IDLE_HEIGHT,
                show_open=True,
            )
        if expanded:
            return FloatingViewState(
                mode="running_input",
                title=title,
                width=_FLOATING_EXPANDED_WIDTH,
                height=_FLOATING_EXPANDED_HEIGHT,
                show_input=True,
                show_submit=True,
                show_cancel=True,
                submit_label="排队",
                input_placeholder="补充下一步任务",
                input_text=draft,
            )
        return FloatingViewState(
            mode="stopping" if stop_requested else ("running_queued" if draft else "running"),
            title=title,
            width=_FLOATING_IDLE_WIDTH if stop_requested else _FLOATING_RUNNING_WIDTH,
            height=_FLOATING_IDLE_HEIGHT,
            show_timer=True,
            show_open=True,
            show_add=not stop_requested,
            show_stop=not stop_requested,
            stop_enabled=not stop_requested,
            stop_label="停止中" if stop_requested else "停止",
            add_label="编辑" if draft else "+",
        )

    if has_resume:
        title = str(resume_reason or waiting_status or "等待手动处理").strip()
        if str(resume_task or "").strip():
            title = f"继续：{resume_task}"
        return FloatingViewState(
            mode="resume",
            title=_short_floating_text(title, fallback="等待手动处理"),
            width=_FLOATING_DECISION_WIDTH,
            height=_FLOATING_DECISION_HEIGHT,
            show_open=True,
            show_continue=True,
            continue_label="恢复",
        )

    if draft:
        if expanded:
            return FloatingViewState(
                mode="followup_input",
                title=_short_floating_text(waiting_status, fallback="下一条任务已排队"),
                width=_FLOATING_EXPANDED_WIDTH,
                height=_FLOATING_EXPANDED_HEIGHT,
                show_input=True,
                show_submit=True,
                show_cancel=True,
                submit_label="更新",
                input_placeholder="修改排队中的任务",
                input_text=draft,
            )
        return FloatingViewState(
            mode="followup",
            title=_short_floating_text(waiting_status, fallback="下一条任务已排队"),
            width=_FLOATING_DECISION_WIDTH,
            height=_FLOATING_DECISION_HEIGHT,
            show_open=True,
            show_add=True,
            show_continue=True,
            add_label="编辑",
            continue_label="继续",
        )

    if expanded:
        return FloatingViewState(
            mode="idle_input",
            title=_short_floating_text(waiting_status, fallback=f"{app_name} 就绪"),
            width=_FLOATING_EXPANDED_WIDTH,
            height=_FLOATING_EXPANDED_HEIGHT,
            show_input=True,
            show_submit=True,
            show_cancel=True,
            submit_label="开始",
            input_placeholder="输入任务",
        )

    return FloatingViewState(
        mode="idle",
        title=_short_floating_text(waiting_status, fallback=f"{app_name} 就绪"),
        width=_FLOATING_IDLE_WIDTH,
        height=_FLOATING_IDLE_HEIGHT,
        show_open=True,
        show_add=True,
    )


def _normalize_shell_host(host: str) -> str:
    cleaned = (host or "").strip()
    if cleaned in {"", "0.0.0.0", "::"}:
        return "127.0.0.1"
    return cleaned


def _wait_for_server(url: str, *, attempts: int = 40, delay_seconds: float = 0.15) -> None:
    parsed = requests.utils.urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    for _ in range(max(1, attempts)):
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError:
            time.sleep(delay_seconds)
    raise DesktopShellUnavailable(f"Desktop shell could not reach the local dashboard at {url}.")


def _configure_qtwebengine_environment() -> None:
    existing_flags = (os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS") or "").strip()
    extra_flags = ["--no-sandbox"]
    single_process_requested = str(os.environ.get("AORYN_QTWEBENGINE_SINGLE_PROCESS", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if sys.platform == "win32" and single_process_requested:
        # Keep a compatibility escape hatch for older Windows environments that
        # still need single-process mode to start QtWebEngine reliably.
        extra_flags.append("--single-process")
    merged_flags = existing_flags.split() if existing_flags else []
    for flag in extra_flags:
        if flag not in merged_flags:
            merged_flags.append(flag)
    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    if merged_flags:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(merged_flags)


def _qtwebengine_storage_candidates() -> list[Path]:
    candidates: list[Path] = []

    if sys.platform == "win32":
        candidates.append(local_data_root())

    default_root = default_cache_root()
    candidates.append(default_root.parent if default_root.name.lower() == "cache" else default_root)
    candidates.append(Path(tempfile.gettempdir()) / APP_NAME)

    unique_candidates: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append(candidate)
    return unique_candidates


def _is_writable_directory(path: Path) -> bool:
    probe_name = f".qtwebengine-write-test-{os.getpid()}"
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe_path = path / probe_name
        probe_path.write_text("ok", encoding="utf-8")
        probe_path.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _resolve_qtwebengine_storage_root() -> Path | None:
    for base_root in _qtwebengine_storage_candidates():
        qt_root = base_root / "qtwebengine"
        profile_root = qt_root / "profile"
        cache_root = qt_root / "cache"
        if _is_writable_directory(profile_root) and _is_writable_directory(cache_root):
            return qt_root
    return None


def _configure_qtwebengine_profile_storage() -> None:
    if QWebEngineProfile is object:
        return
    try:
        qt_root = _resolve_qtwebengine_storage_root()
        if qt_root is None:
            return
        profile_root = qt_root / "profile"
        cache_root = qt_root / "cache"

        profile = QWebEngineProfile.defaultProfile()
        profile.setPersistentStoragePath(str(profile_root))
        profile.setCachePath(str(cache_root))
    except Exception:
        return


def _configure_windows_app_identity(app_id: str) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        return


def _configure_windows_frameless_window(hwnd: int) -> None:
    if sys.platform != "win32" or not hwnd:
        return
    try:
        import ctypes
        from ctypes import wintypes

        dwmapi = ctypes.windll.dwmapi

        corner_attribute = ctypes.c_uint(33)  # DWMWA_WINDOW_CORNER_PREFERENCE
        corner_preference = ctypes.c_int(1)  # DWMWCP_DONOTROUND
        dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            corner_attribute,
            ctypes.byref(corner_preference),
            ctypes.sizeof(corner_preference),
        )

        border_attribute = ctypes.c_uint(34)  # DWMWA_BORDER_COLOR
        border_color_none = ctypes.c_uint(0xFFFFFFFE)  # DWM_COLOR_NONE
        dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            border_attribute,
            ctypes.byref(border_color_none),
            ctypes.sizeof(border_color_none),
        )
    except Exception:
        return


if QApplication is not None:

    class DesktopMainWindow(QMainWindow):
        def __init__(
            self,
            *,
            url: str,
            icon_path: Path,
            display_mode: str = "workarea_maximized",
            on_hide_requested=None,
            environment_provider=None,
        ) -> None:
            super().__init__()
            self._allow_close = False
            self._pending_run_id: str | None = None
            self._on_hide_requested = on_hide_requested
            self._environment_provider = environment_provider
            self._display_mode = (display_mode or "workarea_maximized").strip().lower()
            self.setWindowTitle(APP_NAME)
            self.setMinimumSize(1180, 760)
            self.setWindowIcon(QIcon(str(icon_path)))

            self.webview = QWebEngineView(self)
            self.setCentralWidget(self.webview)
            self.webview.load(QUrl(url))
            self.webview.loadFinished.connect(self._handle_load_finished)

        def closeEvent(self, event: QCloseEvent) -> None:  # pragma: no cover - GUI runtime behavior
            if self._allow_close:
                super().closeEvent(event)
                return
            event.ignore()
            self.hide()
            if callable(self._on_hide_requested):
                self._on_hide_requested()

        def allow_close(self) -> None:
            self._allow_close = True

        def show_and_focus(self) -> None:  # pragma: no cover - GUI runtime behavior
            self._show_with_display_policy()
            self.raise_()
            self.activateWindow()

        def _show_with_display_policy(self) -> None:  # pragma: no cover - GUI runtime behavior
            self.showNormal()
            environment = None
            if sys.platform == "win32":
                if callable(self._environment_provider):
                    try:
                        environment = self._environment_provider()
                    except Exception:
                        environment = None
                if environment is None:
                    environment = capture_effective_desktop_environment()
            target_rect = preferred_work_area(environment)
            if target_rect is not None and target_rect.width > 0 and target_rect.height > 0:
                target_width = max(self.minimumWidth(), target_rect.width)
                target_height = max(self.minimumHeight(), target_rect.height)
                self.setGeometry(target_rect.left, target_rect.top, target_width, target_height)
            self.show()
            if self._display_mode == "fullscreen":
                self.showFullScreen()
            elif sys.platform == "win32" and self._display_mode == "workarea_maximized":
                self.showMaximized()

        def open_run(self, run_id: str | None) -> None:  # pragma: no cover - GUI runtime behavior
            if not run_id:
                return
            self._pending_run_id = run_id
            self._flush_pending_run()

        def _handle_load_finished(self, ok: bool) -> None:  # pragma: no cover - GUI runtime behavior
            if ok:
                self._flush_pending_run()

        def _flush_pending_run(self) -> None:  # pragma: no cover - GUI runtime behavior
            if not self._pending_run_id:
                return
            run_id = self._pending_run_id
            script = (
                "if (window.desktopAgentShell && typeof window.desktopAgentShell.openRun === 'function') {"
                f"window.desktopAgentShell.openRun({run_id!r});"
                "}"
            )
            self.webview.page().runJavaScript(script)
            self._pending_run_id = None


if QApplication is not None:

    class _OverviewFetchBridge(QObject):
        payload_ready = Signal(object)
        error_ready = Signal(str)


    class FloatingExecutionWindow(QWidget):
        _CARD_RADIUS = 18
        _OUTER_PADDING = 0

        def __init__(
            self,
            *,
            icon_path: Path,
            on_toggle_main,
            on_stop_task,
            on_submit_text,
            on_continue_follow_up,
            on_resume_run,
            on_decide_job,
            on_open_main=None,
        ) -> None:
            flags = (
                Qt.WindowType.Window
                | Qt.WindowType.CustomizeWindowHint
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
            )
            no_shadow_flag = getattr(Qt.WindowType, "NoDropShadowWindowHint", None)
            if no_shadow_flag is not None:
                flags |= no_shadow_flag
            super().__init__(None, flags)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
            self.setObjectName("floatingShellWindow")
            self.setWindowTitle(f"{APP_NAME} 悬浮窗")
            self.setWindowIcon(QIcon(str(icon_path)))

            self._allow_close = False
            self._active_job: dict[str, Any] | None = None
            self._follow_up_draft = ""
            self._resume_run_id: str | None = None
            self._resume_task = ""
            self._resume_reason = ""
            self._waiting_status = ""
            self._started_at: float | None = None
            self._active_job_id: str | None = None
            self._input_expanded = False
            self._drag_global: QPoint | None = None
            self._drag_origin: QPoint | None = None
            self._dragging = False
            self._on_toggle_main = on_toggle_main
            self._on_open_main = on_open_main or on_toggle_main
            self._on_stop_task = on_stop_task
            self._on_submit_text = on_submit_text
            self._on_continue_follow_up = on_continue_follow_up
            self._on_resume_run = on_resume_run
            self._on_decide_job = on_decide_job
            self._suppress_taskbar_activation_until = 0.0

            self._timer = QTimer(self)
            self._timer.setInterval(1000)
            self._timer.timeout.connect(self._refresh_timer_label)

            root = QVBoxLayout(self)
            root.setContentsMargins(
                self._OUTER_PADDING,
                self._OUTER_PADDING,
                self._OUTER_PADDING,
                self._OUTER_PADDING,
            )
            root.setSpacing(0)

            self.card = QFrame(self)
            self.card.setObjectName("floatingShellCard")
            self.card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            root.addWidget(self.card)

            card_layout = QHBoxLayout(self.card)
            card_layout.setContentsMargins(7, 6, 7, 6)
            card_layout.setSpacing(5)

            self.logo_button = QPushButton(self.card)
            self.logo_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.logo_button.setFixedSize(28, 28)
            self.logo_button.setIcon(QIcon(str(icon_path)))
            self.logo_button.setIconSize(QSize(15, 15))
            self.logo_button.setObjectName("floatingLogoButton")
            self.logo_button.clicked.connect(self._on_open_main)
            card_layout.addWidget(self.logo_button, 0, Qt.AlignmentFlag.AlignVCenter)

            self.task_label = QLabel(f"{APP_NAME} 就绪", self.card)
            self.task_label.setObjectName("floatingTaskLabel")
            self.task_label.setMinimumWidth(0)
            self.task_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            card_layout.addWidget(self.task_label, 1)

            self.timer_label = QLabel("--", self.card)
            self.timer_label.setObjectName("floatingTimerLabel")
            self.timer_label.setFixedWidth(32)
            card_layout.addWidget(self.timer_label, 0, Qt.AlignmentFlag.AlignVCenter)

            self.input_line = QLineEdit(self.card)
            self.input_line.setObjectName("floatingInputLine")
            self.input_line.setPlaceholderText("输入下一条任务")
            self.input_line.returnPressed.connect(self._handle_submit)
            self.input_line.setClearButtonEnabled(True)
            card_layout.addWidget(self.input_line, 1)

            self.submit_button = QPushButton("排队", self.card)
            self.submit_button.setObjectName("floatingPrimaryButton")
            self.submit_button.setMinimumWidth(50)
            self.submit_button.clicked.connect(self._handle_submit)
            card_layout.addWidget(self.submit_button)

            self.continue_button = QPushButton("继续", self.card)
            self.continue_button.setObjectName("floatingPrimaryButton")
            self.continue_button.setMinimumWidth(50)
            self.continue_button.clicked.connect(self._handle_continue_follow_up)
            card_layout.addWidget(self.continue_button)

            self.stop_button = QPushButton("停止", self.card)
            self.stop_button.setObjectName("floatingDangerButton")
            self.stop_button.setMinimumWidth(46)
            self.stop_button.clicked.connect(self._handle_stop_action)
            card_layout.addWidget(self.stop_button)

            self.open_button = QPushButton("打开", self.card)
            self.open_button.setObjectName("floatingGhostButton")
            self.open_button.setMinimumWidth(44)
            self.open_button.clicked.connect(self._on_open_main)
            card_layout.addWidget(self.open_button)

            self.add_button = QPushButton("+", self.card)
            self.add_button.setObjectName("floatingIconButton")
            self.add_button.setFixedWidth(30)
            self.add_button.clicked.connect(self._handle_expand_input)
            card_layout.addWidget(self.add_button)

            self.cancel_button = QPushButton("取消", self.card)
            self.cancel_button.setObjectName("floatingGhostButton")
            self.cancel_button.setMinimumWidth(44)
            self.cancel_button.clicked.connect(self._handle_cancel_input)
            card_layout.addWidget(self.cancel_button)

            self.setStyleSheet(
                """
                QWidget#floatingShellWindow {
                  background: rgba(0, 0, 0, 0);
                  border: none;
                }
                #floatingShellCard {
                  background: rgba(255, 255, 255, 0.96);
                  border: 1px solid rgba(15, 23, 42, 0.07);
                  border-radius: 19px;
                }
                #floatingLogoButton {
                  border: none;
                  border-radius: 14px;
                  background: rgba(37, 99, 235, 0.08);
                  padding: 0;
                }
                #floatingLogoButton:hover {
                  background: rgba(37, 99, 235, 0.12);
                }
                #floatingTaskLabel {
                  color: #1f2328;
                  font-size: 12px;
                  font-weight: 650;
                }
                #floatingTimerLabel {
                  padding: 0;
                  border: none;
                  background: transparent;
                  color: #0d8a6d;
                  font-size: 11px;
                  font-weight: 700;
                }
                #floatingInputLine {
                  min-height: 34px;
                  padding: 0 8px;
                  border-radius: 11px;
                  border: 1px solid rgba(15, 23, 42, 0.08);
                  background: #f5f7fa;
                  color: #1f2328;
                  selection-background-color: rgba(15, 143, 115, 0.18);
                }
                #floatingGhostButton, #floatingDangerButton, #floatingPrimaryButton, #floatingIconButton {
                  min-height: 30px;
                  padding: 0 9px;
                  border-radius: 15px;
                  font-weight: 600;
                  font-size: 11px;
                }
                #floatingGhostButton {
                  border: 1px solid rgba(15, 23, 42, 0.06);
                  background: rgba(248, 250, 252, 0.76);
                  color: #475467;
                }
                #floatingGhostButton:hover {
                  background: #f1f5f9;
                  color: #1f2328;
                }
                #floatingDangerButton {
                  border: 1px solid rgba(220, 38, 38, 0.08);
                  background: rgba(254, 242, 242, 0.86);
                  color: #c62828;
                }
                #floatingPrimaryButton {
                  border: 1px solid rgba(15, 143, 115, 0.1);
                  background: rgba(236, 253, 245, 0.9);
                  color: #0d8a6d;
                }
                #floatingIconButton {
                  border: 1px solid rgba(15, 23, 42, 0.06);
                  background: rgba(248, 250, 252, 0.76);
                  color: #344054;
                  padding: 0;
                  font-size: 16px;
                  font-weight: 700;
                }
                #floatingIconButton:hover {
                  background: #eef2f6;
                  color: #111827;
                }
                """
            )

            self._drag_surfaces = (self, self.card, self.task_label, self.timer_label)
            for surface in self._drag_surfaces:
                surface.installEventFilter(self)
                surface.setCursor(Qt.CursorShape.OpenHandCursor)

            self.show_idle()

        def allow_close(self) -> None:
            self._allow_close = True

        def closeEvent(self, event) -> None:  # pragma: no cover - GUI runtime behavior
            if self._allow_close:
                super().closeEvent(event)
                return
            event.ignore()
            self._on_open_main()

        def event(self, event) -> bool:  # pragma: no cover - GUI runtime behavior
            event_type = event.type()
            if event_type == QEvent.Type.WindowActivate:
                QTimer.singleShot(0, self._handle_possible_taskbar_activation)
            elif event_type == QEvent.Type.WindowStateChange:
                QTimer.singleShot(0, self._handle_possible_taskbar_restore)
            return super().event(event)

        def eventFilter(self, watched, event) -> bool:  # pragma: no cover - GUI runtime behavior
            if watched not in self._drag_surfaces:
                return super().eventFilter(watched, event)
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._drag_global = event.globalPosition().toPoint()
                self._drag_origin = self.frameGeometry().topLeft()
                self._dragging = False
                return False
            if event.type() == QEvent.Type.MouseMove and self._drag_global is not None and self._drag_origin is not None:
                delta = event.globalPosition().toPoint() - self._drag_global
                if delta.manhattanLength() > 5:
                    self._dragging = True
                    self.move(self._drag_origin + delta)
                    return True
                return False
            if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                if self._dragging:
                    self._clear_drag_state()
                    return True
                self._clear_drag_state()
            return super().eventFilter(watched, event)

        def show_idle(self, *, status: str = f"{APP_NAME} 就绪") -> None:  # pragma: no cover - GUI runtime behavior
            self._active_job = None
            self._active_job_id = None
            self._follow_up_draft = ""
            self._resume_run_id = None
            self._resume_task = ""
            self._resume_reason = ""
            self._waiting_status = status
            self._started_at = None
            self._input_expanded = False
            self._timer.stop()
            self.timer_label.setText("--")
            self.input_line.clear()
            self._apply_layout_state()
            self._show_floating_window()

        def hide_floating(self) -> None:  # pragma: no cover - GUI runtime behavior
            self._input_expanded = False
            self._timer.stop()
            self.hide()

        def show_waiting_follow_up(
            self,
            draft: str,
            *,
            status: str = "下一条任务已排队",
        ) -> None:  # pragma: no cover - GUI runtime behavior
            self._active_job = None
            self._active_job_id = None
            self._follow_up_draft = draft
            self._resume_run_id = None
            self._resume_task = ""
            self._resume_reason = ""
            self._waiting_status = status
            self._started_at = None
            self._input_expanded = False
            self._timer.stop()
            self.timer_label.setText("--")
            self.input_line.setText(draft)
            self._apply_layout_state()
            self._show_floating_window()

        def show_resume_prompt(
            self,
            *,
            run_id: str,
            task: str,
            reason: str = "",
            status: str = "手动处理完成后继续",
        ) -> None:  # pragma: no cover - GUI runtime behavior
            self._active_job = None
            self._active_job_id = None
            self._follow_up_draft = ""
            self._resume_run_id = str(run_id or "").strip() or None
            self._resume_task = str(task or "").strip()
            self._resume_reason = str(reason or "").strip()
            self._waiting_status = status
            self._started_at = None
            self._input_expanded = False
            self._timer.stop()
            self.timer_label.setText("--")
            self.input_line.clear()
            self._apply_layout_state()
            self._show_floating_window()

        def update_active_job(self, active_job: dict[str, Any] | None, follow_up_draft: str) -> None:  # pragma: no cover
            next_active_job_id = str(active_job.get("id") or "").strip() if isinstance(active_job, dict) else None
            if next_active_job_id != self._active_job_id:
                self._input_expanded = False
            self._active_job_id = next_active_job_id
            self._active_job = active_job
            self._follow_up_draft = follow_up_draft
            self._resume_run_id = None
            self._resume_task = ""
            self._resume_reason = ""
            self._waiting_status = ""
            result = active_job.get("result") if isinstance(active_job, dict) else {}
            started_at = (
                result.get("started_at") if isinstance(result, dict) else None
            ) or (active_job.get("started_at") if isinstance(active_job, dict) else None)
            self._started_at = float(started_at) if isinstance(started_at, (int, float)) else None
            if self._started_at is not None:
                self._timer.start()
            else:
                self._timer.stop()
                self.timer_label.setText("--")
            self._refresh_timer_label()
            self._apply_layout_state()
            self._show_floating_window()

        def _handle_submit(self) -> None:  # pragma: no cover - GUI runtime behavior
            text = self.input_line.text().strip()
            if not text:
                return
            accepted = self._on_submit_text(text)
            if accepted is False:
                return
            if self._active_job or self._follow_up_draft:
                self._follow_up_draft = text
            else:
                self._follow_up_draft = ""
            self.input_line.clear()
            self._input_expanded = False
            self._apply_layout_state()

        def _handle_continue_follow_up(self) -> None:  # pragma: no cover - GUI runtime behavior
            if self._is_approval_job():
                accepted = self._on_decide_job("approve")
                if accepted is not False:
                    self._input_expanded = False
                return
            if self._resume_run_id:
                accepted = self._on_resume_run(self._resume_run_id)
                if accepted is not False:
                    self._input_expanded = False
                return
            accepted = self._on_continue_follow_up()
            if accepted is False:
                return
            self._follow_up_draft = ""
            self._input_expanded = False
            self.input_line.clear()
            self._apply_layout_state()

        def _handle_stop_action(self) -> None:  # pragma: no cover - GUI runtime behavior
            if self._is_approval_job():
                accepted = self._on_decide_job("reject")
                if accepted is not False:
                    self._input_expanded = False
                return
            accepted = self._on_stop_task()
            if accepted is False:
                return
            self._input_expanded = False
            self._apply_layout_state()

        def _handle_expand_input(self) -> None:  # pragma: no cover - GUI runtime behavior
            self._input_expanded = True
            if self._follow_up_draft:
                self.input_line.setText(self._follow_up_draft)
            self._apply_layout_state()
            self.input_line.setFocus()
            self.input_line.selectAll()

        def _handle_cancel_input(self) -> None:  # pragma: no cover - GUI runtime behavior
            self._input_expanded = False
            if self._follow_up_draft:
                self.input_line.setText(self._follow_up_draft)
            else:
                self.input_line.clear()
            self._apply_layout_state()

        def _is_approval_job(self) -> bool:
            return _job_waits_for_decision(self._active_job or {})

        def _refresh_timer_label(self) -> None:  # pragma: no cover - GUI runtime behavior
            if self._started_at is None:
                self.timer_label.setText("--")
                return
            elapsed = max(0, int(time.time() - self._started_at))
            if elapsed < 60:
                self.timer_label.setText(f"{elapsed}s")
                return
            minutes, seconds = divmod(elapsed, 60)
            self.timer_label.setText(f"{minutes}:{seconds:02d}")

        def _clear_drag_state(self) -> None:
            self._drag_global = None
            self._drag_origin = None
            self._dragging = False

        def _show_floating_window(self) -> None:  # pragma: no cover - GUI runtime behavior
            self._remember_programmatic_activation()
            self.show()
            self.raise_()

        def _remember_programmatic_activation(self, duration: float = 0.5) -> None:
            self._suppress_taskbar_activation_until = time.time() + max(0.0, float(duration or 0.0))

        def _handle_possible_taskbar_restore(self) -> None:  # pragma: no cover - GUI runtime behavior
            try:
                minimized = self.isMinimized()
            except Exception:
                minimized = False
            if minimized:
                self._open_main_from_taskbar(force=True)

        def _handle_possible_taskbar_activation(self) -> None:  # pragma: no cover - GUI runtime behavior
            self._open_main_from_taskbar(force=False)

        def _open_main_from_taskbar(self, *, force: bool) -> None:  # pragma: no cover - GUI runtime behavior
            if time.time() < self._suppress_taskbar_activation_until:
                return
            if not force and self._cursor_is_over_window():
                return
            self._remember_programmatic_activation()
            self._on_open_main()

        def _cursor_is_over_window(self) -> bool:  # pragma: no cover - GUI runtime behavior
            if QCursor is object:
                return False
            try:
                return self.rect().contains(self.mapFromGlobal(QCursor.pos()))
            except Exception:
                return False

        def _apply_window_shape(self) -> None:
            if QPainterPath is object or QRectF is object or QRegion is object:
                return
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), self._CARD_RADIUS, self._CARD_RADIUS)
            self.setMask(QRegion(path.toFillPolygon().toPolygon()))

        def _apply_native_window_chrome(self) -> None:
            try:
                _configure_windows_frameless_window(int(self.winId()))
            except Exception:
                return

        def _apply_layout_state(self) -> None:  # pragma: no cover - GUI runtime behavior
            was_input_visible = self.input_line.isVisible()
            state = build_floating_view_state(
                active_job=self._active_job,
                follow_up_draft=self._follow_up_draft,
                resume_run_id=self._resume_run_id,
                resume_task=self._resume_task,
                resume_reason=self._resume_reason,
                waiting_status=self._waiting_status,
                input_expanded=self._input_expanded,
            )

            self.setFixedSize(state.width, state.height)
            self.card.setFixedSize(state.width, state.height)
            self._apply_window_shape()
            self._apply_native_window_chrome()

            self.task_label.setText(state.title)
            self.task_label.setVisible(not state.show_input)

            self.timer_label.setVisible(state.show_timer and not state.show_input)

            self.input_line.setVisible(state.show_input)
            if state.show_input:
                self.input_line.setPlaceholderText(state.input_placeholder)
                if (not was_input_visible) or not self.input_line.text().strip():
                    self.input_line.setText(state.input_text)
            elif not self._follow_up_draft:
                self.input_line.clear()

            self.submit_button.setVisible(state.show_submit)
            self.submit_button.setText(state.submit_label)

            self.continue_button.setVisible(state.show_continue)
            self.continue_button.setText(state.continue_label)

            self.stop_button.setVisible(state.show_stop)
            self.stop_button.setEnabled(state.stop_enabled)
            self.stop_button.setText(state.stop_label)

            self.open_button.setVisible(state.show_open)
            self.add_button.setVisible(state.show_add)
            self.add_button.setText(state.add_label)
            self.add_button.setFixedWidth(44 if state.add_label != "+" else 30)
            self.cancel_button.setVisible(state.show_cancel)


    class DesktopShellController:
        def __init__(
            self,
            *,
            qt_app,
            dashboard_app: DashboardApp,
            server: ThreadingHTTPServer,
            base_url: str,
        ) -> None:
            self.qt_app = qt_app
            self.dashboard_app = dashboard_app
            self.server = server
            self.base_url = base_url.rstrip("/")
            self.icons_root = self.dashboard_app.ui_root / "icons"
            self.main_window = DesktopMainWindow(
                url=f"{self.base_url}/index.html?v={APP_ASSET_VERSION}",
                icon_path=self.icons_root / "app-icon-64.png",
                display_mode=getattr(self.dashboard_app.config, "window_display_mode", "workarea_maximized"),
                on_hide_requested=self._handle_main_window_hidden,
                environment_provider=self._capture_effective_environment,
            )
            self.tray_icon = self._build_tray()
            self.floating = FloatingExecutionWindow(
                icon_path=self.icons_root / "logo-mark.png",
                on_toggle_main=self._toggle_main_window,
                on_stop_task=self._stop_active_task,
                on_submit_text=self._submit_or_stage_follow_up,
                on_continue_follow_up=self._continue_follow_up,
                on_resume_run=self._resume_interrupted_run,
                on_decide_job=self._decide_active_job,
                on_open_main=self.show_main_window,
            )
            self.floating.move(24, 120)
            self.current_active_job_id: str | None = None
            self.current_active_job: dict[str, Any] | None = None
            self.paused_run_id: str | None = None
            self.paused_task = ""
            self.paused_reason = ""
            self.follow_up_draft = ""
            self.auto_collapsed_for_current_job = False
            self.success_feedback_deadline = 0.0
            self.last_finished_run_id: str | None = None
            self.tray_menu_open = False
            self.quitting = False
            self.ignore_tray_activation_until = 0.0
            self._overview_request_in_flight = False
            self._last_overview_signature = ""
            self._overview_bridge = _OverviewFetchBridge()
            self._overview_bridge.payload_ready.connect(self._handle_overview_payload)
            self._overview_bridge.error_ready.connect(self._handle_overview_error)

            self.poll_timer = QTimer()
            self.poll_timer.setInterval(1250)
            self.poll_timer.timeout.connect(self.refresh_overview)
            self.poll_timer.start()

            self.main_window.show()
            self.tray_icon.show()
            QTimer.singleShot(250, self.refresh_overview)

        def shutdown(self) -> None:
            try:
                self.poll_timer.stop()
            except Exception:
                pass
            try:
                self.tray_icon.hide()
            except Exception:
                pass
            self.main_window.allow_close()
            self.main_window.close()
            self.floating.allow_close()
            self.floating.close()
            self.server.shutdown()
            self.server.server_close()

        def refresh_overview(self) -> bool:  # pragma: no cover - exercised through runtime UI
            return self._request_overview_refresh()

        def _request_overview_refresh(self) -> bool:
            if self._overview_request_in_flight:
                return False
            self._overview_request_in_flight = True
            thread = threading.Thread(
                target=self._fetch_overview_payload,
                name="desktop-agent-overview-refresh",
                daemon=True,
            )
            thread.start()
            return True

        def _fetch_overview_payload(self) -> None:
            try:
                response = requests.get(f"{self.base_url}/api/overview", timeout=1.5)
                if not response.ok:
                    raise RuntimeError(f"Overview request failed with status {response.status_code}.")
                self._overview_bridge.payload_ready.emit(response.json())
            except Exception as exc:
                self._overview_bridge.error_ready.emit(str(exc))

        def _handle_overview_payload(self, payload: object) -> bool:
            self._overview_request_in_flight = False
            normalized_payload = payload if isinstance(payload, dict) else {}
            signature = DesktopShellController._build_overview_signature(
                normalized_payload,
                success_feedback_active=self.success_feedback_deadline > time.time(),
            )
            if signature == self._last_overview_signature:
                return False
            self._last_overview_signature = signature
            self._apply_overview_payload(normalized_payload)
            return True

        def _handle_overview_error(self, _error: str = "") -> bool:
            self._overview_request_in_flight = False
            if self.success_feedback_deadline and time.time() >= self.success_feedback_deadline:
                self.success_feedback_deadline = 0
                if self.main_window.isVisible():
                    self.floating.hide_floating()
                else:
                    self.floating.show_idle()
            return False

        @staticmethod
        def _build_overview_signature(payload: dict[str, Any], *, success_feedback_active: bool) -> str:
            runtime_preferences = payload.get("runtime_preferences") if isinstance(payload, dict) else {}
            jobs = payload.get("jobs") if isinstance(payload, dict) else []
            runs = payload.get("runs") if isinstance(payload, dict) else []
            summarized = {
                "active_job": DesktopShellController._summarize_job(payload.get("active_job") if isinstance(payload, dict) else None),
                "jobs": [DesktopShellController._summarize_job(job) for job in (jobs or [])[:8]],
                "runs": [DesktopShellController._summarize_run(run) for run in (runs or [])[:12]],
                "runtime_preferences_updated_at": (
                    runtime_preferences.get("updated_at") if isinstance(runtime_preferences, dict) else None
                ),
                "success_feedback_active": bool(success_feedback_active),
            }
            return json.dumps(summarized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

        @staticmethod
        def _resolve_run_policy_value(record: dict[str, Any] | None, key: str) -> Any:
            if not isinstance(record, dict):
                return None
            value = record.get(key)
            if value is not None and value != "":
                return value
            result = record.get("result") if isinstance(record.get("result"), dict) else {}
            value = result.get(key)
            if value is not None and value != "":
                return value
            result_budget = result.get("execution_budget") if isinstance(result.get("execution_budget"), dict) else {}
            value = result_budget.get(key)
            if value is not None and value != "":
                return value
            overrides = record.get("config_overrides") if isinstance(record.get("config_overrides"), dict) else {}
            value = overrides.get(key)
            if value is not None and value != "":
                return value
            budget = record.get("execution_budget") if isinstance(record.get("execution_budget"), dict) else {}
            value = budget.get(key)
            return None if value == "" else value

        @staticmethod
        def _summarize_execution_budget(record: dict[str, Any] | None) -> dict[str, Any]:
            summary: dict[str, Any] = {}
            for key in _EXECUTION_BUDGET_SUMMARY_FIELDS:
                value = DesktopShellController._resolve_run_policy_value(record, key)
                if key in _EXECUTION_BUDGET_BOOLEAN_FIELDS:
                    value = _summary_bool(value)
                summary[key] = value
            return summary

        @staticmethod
        def _resolve_run_environment_value(record: dict[str, Any] | None, key: str) -> Any:
            if not isinstance(record, dict):
                return None
            value = record.get(key)
            if value is not None and value != "":
                return value
            result = record.get("result") if isinstance(record.get("result"), dict) else {}
            value = result.get(key)
            if value is not None and value != "":
                return value
            result_environment = (
                result.get("execution_environment")
                if isinstance(result.get("execution_environment"), dict)
                else {}
            )
            value = result_environment.get(key)
            if value is not None and value != "":
                return value
            overrides = record.get("config_overrides") if isinstance(record.get("config_overrides"), dict) else {}
            value = overrides.get(key)
            if value is not None and value != "":
                return value
            environment = record.get("execution_environment") if isinstance(record.get("execution_environment"), dict) else {}
            value = environment.get(key)
            return None if value == "" else value

        @staticmethod
        def _summarize_execution_environment(record: dict[str, Any] | None) -> dict[str, Any]:
            summary: dict[str, Any] = {}
            for key in _EXECUTION_ENVIRONMENT_SUMMARY_FIELDS:
                value = DesktopShellController._resolve_run_environment_value(record, key)
                if key in _EXECUTION_ENVIRONMENT_BOOLEAN_FIELDS:
                    value = _summary_bool(value)
                summary[key] = value
            return summary

        @staticmethod
        def _summary_has_value(value: Any) -> bool:
            if value is None:
                return False
            if isinstance(value, str):
                return bool(value.strip())
            if isinstance(value, (dict, list, tuple, set)):
                return bool(value)
            return True

        @staticmethod
        def _summarize_autonomy_readiness(autonomy: dict[str, Any] | None) -> dict[str, Any] | None:
            if not isinstance(autonomy, dict):
                return None
            compact = {
                "status": autonomy.get("status"),
                "can_continue": _summary_bool(autonomy.get("can_continue")),
                "requires_review": _summary_bool(autonomy.get("requires_review")),
                "requires_user": _summary_bool(autonomy.get("requires_user")),
                "next_action": autonomy.get("next_action"),
                "next_subgoal_id": autonomy.get("next_subgoal_id"),
                "blockers": autonomy.get("blockers")[:4] if isinstance(autonomy.get("blockers"), list) else [],
                "warnings": autonomy.get("warnings")[:4] if isinstance(autonomy.get("warnings"), list) else [],
            }
            if any(DesktopShellController._summary_has_value(value) for value in compact.values()):
                return compact
            return None

        @staticmethod
        def _summarize_plan_health_item(item: Any) -> dict[str, Any] | None:
            if not isinstance(item, dict):
                return None
            compact = {
                "id": item.get("id"),
                "title": item.get("title"),
                "status": item.get("status"),
                "ready": _summary_bool(item.get("ready")),
                "is_next": _summary_bool(item.get("is_next")),
                "exhausted": _summary_bool(item.get("exhausted")),
                "attempts": item.get("attempts"),
                "retry_remaining": item.get("retry_remaining"),
                "capability_preference": item.get("capability_preference") or item.get("capability"),
                "risk_level": item.get("risk_level"),
            }
            if any(DesktopShellController._summary_has_value(value) for value in compact.values()):
                return compact
            return None

        @staticmethod
        def _summarize_plan_health(
            plan_health: dict[str, Any] | None,
            items: list[Any] | None,
            *,
            include_remaining: bool = False,
        ) -> dict[str, Any] | None:
            source = plan_health if isinstance(plan_health, dict) else {}
            counts = source.get("counts") if isinstance(source.get("counts"), dict) else {}
            count_keys = ("total", "completed", "pending", "in_progress", "ready", "blocked", "failed", "exhausted")
            compact_counts = {key: counts.get(key) for key in count_keys}
            if not any(DesktopShellController._summary_has_value(value) for value in compact_counts.values()):
                compact_counts = {}
            compact_items = [
                compact
                for compact in (DesktopShellController._summarize_plan_health_item(item) for item in (items or [])[:8])
                if compact is not None
            ]
            compact: dict[str, Any] = {
                "next_subgoal_id": source.get("next_subgoal_id"),
                "blocked_reason": source.get("blocked_reason"),
            }
            if include_remaining:
                compact["remaining"] = source.get("remaining")
            if compact_counts:
                compact["counts"] = compact_counts
            autonomy = DesktopShellController._summarize_autonomy_readiness(
                source.get("autonomy") if isinstance(source.get("autonomy"), dict) else None
            )
            if autonomy is not None:
                compact["autonomy"] = autonomy
            if compact_items:
                compact["items"] = compact_items
            if any(DesktopShellController._summary_has_value(value) for value in compact.values()):
                return compact
            return None

        @staticmethod
        def _summarize_job(job: dict[str, Any] | None) -> dict[str, Any] | None:
            if not isinstance(job, dict):
                return None
            result = job.get("result") if isinstance(job.get("result"), dict) else {}
            execution_state = _job_execution_state_from_result(result)
            execution_context = (
                execution_state.get("app_context") if isinstance(execution_state.get("app_context"), dict) else {}
            )
            plan_health = execution_state.get("plan_health") if isinstance(execution_state.get("plan_health"), dict) else {}
            workspace_summary = (
                result.get("workspace_summary")
                if isinstance(result.get("workspace_summary"), dict)
                else execution_state.get("workspace_summary")
                if isinstance(execution_state.get("workspace_summary"), dict)
                else None
            )
            repair_history = execution_state.get("repair_history") if isinstance(execution_state.get("repair_history"), list) else None
            capability_failures = (
                execution_state.get("capability_failures")
                if isinstance(execution_state.get("capability_failures"), dict)
                else None
            )
            step_proposal = (
                result.get("step_proposal")
                if isinstance(result.get("step_proposal"), dict)
                else execution_state.get("step_proposal")
                if isinstance(execution_state.get("step_proposal"), dict)
                else execution_state.get("last_step")
                if isinstance(execution_state.get("last_step"), dict)
                else None
            )
            health_items = (
                plan_health.get("items")
                if isinstance(plan_health.get("items"), list)
                else execution_state.get("subgoals")
                if isinstance(execution_state.get("subgoals"), list)
                else []
            )
            pending_decision = None if _job_is_terminal_result(job) else _pending_decision_from_job(job)
            config_overrides = job.get("config_overrides") if isinstance(job.get("config_overrides"), dict) else {}
            budget_summary = DesktopShellController._summarize_execution_budget(job)
            environment_summary = DesktopShellController._summarize_execution_environment(job)
            return {
                "id": job.get("id"),
                "status": job.get("status"),
                "task": job.get("task"),
                "started_at": job.get("started_at"),
                "updated_at": None if job.get("status") == "running" else job.get("updated_at"),
                "dry_run": _summary_bool(
                    result.get("dry_run") if result.get("dry_run") is not None else job.get("dry_run")
                ),
                "max_steps": job.get("max_steps"),
                "pause_after_action": job.get("pause_after_action"),
                "max_run_seconds": (
                    config_overrides.get("max_run_seconds")
                    if config_overrides.get("max_run_seconds") is not None
                    else job.get("max_run_seconds")
                ),
                "desktop_autonomy_mode": DesktopShellController._resolve_run_policy_value(job, "desktop_autonomy_mode"),
                "complex_task_planning": DesktopShellController._resolve_run_policy_value(job, "complex_task_planning"),
                "approval_policy": DesktopShellController._resolve_run_policy_value(job, "approval_policy"),
                "plan_review_policy": DesktopShellController._resolve_run_policy_value(job, "plan_review_policy"),
                "stage_review_policy": DesktopShellController._resolve_run_policy_value(job, "stage_review_policy"),
                "replan_on_recoverable_error": DesktopShellController._resolve_run_policy_value(
                    job, "replan_on_recoverable_error"
                ),
                "recoverable_error_retry_limit": DesktopShellController._resolve_run_policy_value(
                    job, "recoverable_error_retry_limit"
                ),
                "execution_budget": budget_summary,
                "execution_environment": environment_summary,
                **budget_summary,
                **environment_summary,
                "cancel_requested": _summary_bool(job.get("cancel_requested")),
                "cancelled": _bool_value(job.get("cancelled")) or _bool_value(result.get("cancelled")),
                "completed": _bool_value(result.get("completed")) or _bool_value(job.get("completed")),
                "error": result.get("error") if result.get("error") is not None else job.get("error"),
                "cancel_reason": (
                    result.get("cancel_reason") if result.get("cancel_reason") is not None else job.get("cancel_reason")
                ),
                "requires_human": (
                    _bool_value(job.get("requires_human"))
                    or _bool_value(result.get("requires_human"))
                    or pending_decision is not None
                ),
                "interruption_kind": job.get("interruption_kind") or result.get("interruption_kind"),
                "interruption_reason": job.get("interruption_reason") or result.get("interruption_reason"),
                "run_id": result.get("run_id") if isinstance(result, dict) else None,
                "result_started_at": result.get("started_at") if isinstance(result, dict) else None,
                "steps": result.get("steps") if isinstance(result, dict) else None,
                "run_finished_at": result.get("finished_at") if isinstance(result, dict) else None,
                "latest_summary": result.get("latest_summary") if isinstance(result, dict) else None,
                "current_goal": (
                    result.get("current_goal")
                    if isinstance(result, dict)
                    else None
                ) or (execution_state.get("current_goal") if isinstance(execution_state, dict) else None),
                "chosen_capability": (
                    result.get("chosen_capability")
                    if isinstance(result, dict)
                    else None
                ) or (execution_state.get("chosen_capability") if isinstance(execution_state, dict) else None),
                "verification_status": (
                    result.get("verification_status")
                    if isinstance(result, dict)
                    else None
                ) or (execution_state.get("verification_status") if isinstance(execution_state, dict) else None),
                "last_verification": DesktopShellController._summarize_verification(
                    execution_state.get("last_verification") if isinstance(execution_state.get("last_verification"), dict) else None
                ),
                "evidence_ledger": [
                    compact
                    for compact in (
                        DesktopShellController._summarize_evidence_item(item)
                        for item in (execution_state.get("evidence_ledger") if isinstance(execution_state.get("evidence_ledger"), list) else [])[-6:]
                    )
                    if compact is not None
                ],
                "orchestration_phase": (
                    result.get("orchestration_phase")
                    if isinstance(result, dict)
                    else None
                ) or (execution_state.get("orchestration_phase") if isinstance(execution_state, dict) else None),
                "active_specialist": (
                    result.get("active_specialist")
                    if isinstance(result, dict)
                    else None
                ) or (execution_state.get("active_specialist") if isinstance(execution_state, dict) else None),
                "current_surface_kind": (
                    result.get("current_surface_kind")
                    if isinstance(result, dict)
                    else None
                ) or (execution_state.get("current_surface_kind") if isinstance(execution_state, dict) else None),
                "last_progress_at": (
                    result.get("last_progress_at")
                    if isinstance(result, dict)
                    else None
                ) or (execution_state.get("last_progress_at") if isinstance(execution_state, dict) else None),
                "plan_review_status": (
                    result.get("plan_review_status")
                    if isinstance(result, dict)
                    else None
                )
                or (execution_state.get("plan_review_status") if isinstance(execution_state, dict) else None)
                or (execution_context.get("plan_review_status") if isinstance(execution_context, dict) else None),
                "stage_review_status": (
                    result.get("stage_review_status")
                    if isinstance(result, dict)
                    else None
                )
                or (execution_state.get("stage_review_status") if isinstance(execution_state, dict) else None)
                or (execution_context.get("stage_review_status") if isinstance(execution_context, dict) else None),
                "last_replan_reason": (
                    result.get("last_replan_reason")
                    if isinstance(result, dict)
                    else None
                ) or (execution_state.get("last_replan_reason") if isinstance(execution_state, dict) else None),
                "recovery_reason": (
                    result.get("recovery_reason")
                    if isinstance(result, dict)
                    else None
                ) or (execution_state.get("recovery_reason") if isinstance(execution_state, dict) else None),
                "handoff_state": DesktopShellController._summarize_handoff_state(execution_context),
                "repair_history": DesktopShellController._summarize_repair_history(repair_history),
                "capability_failures": DesktopShellController._summarize_capability_failures(capability_failures),
                "workspace_summary": DesktopShellController._summarize_workspace_summary(workspace_summary),
                "step_proposal": DesktopShellController._summarize_step_proposal(step_proposal),
                "plan_health": DesktopShellController._summarize_plan_health(
                    plan_health,
                    health_items,
                    include_remaining=True,
                ),
                "latest_screenshot": result.get("latest_screenshot") if isinstance(result, dict) else None,
                "latest_timings": DesktopShellController._summarize_timings(
                    result.get("latest_timings") if isinstance(result.get("latest_timings"), dict) else None
                ),
                "latest_actions": [
                    compact
                    for compact in (
                        DesktopShellController._summarize_action(action)
                        for action in (result.get("latest_actions") if isinstance(result.get("latest_actions"), list) else [])[:4]
                    )
                    if compact is not None
                ],
                "live_pointer": DesktopShellController._summarize_live_pointer(
                    result.get("live_pointer") if isinstance(result.get("live_pointer"), dict) else None
                ),
                "live_pointer_trail": [
                    compact
                    for compact in (
                        DesktopShellController._summarize_live_pointer(point)
                        for point in (result.get("live_pointer_trail") if isinstance(result.get("live_pointer_trail"), list) else [])[-6:]
                    )
                    if compact is not None
                ],
                "live_action": DesktopShellController._summarize_action(
                    result.get("live_action") if isinstance(result.get("live_action"), dict) else None
                ),
                "pending_decision": DesktopShellController._summarize_pending_decision(pending_decision),
            }

        @staticmethod
        def _summarize_workspace_summary(summary: dict[str, Any] | None) -> dict[str, Any] | None:
            if not isinstance(summary, dict):
                return None

            def _compact_items(value: Any) -> list[dict[str, Any]]:
                if not isinstance(value, list):
                    return []
                compacted: list[dict[str, Any]] = []
                for item in value[-4:]:
                    if not isinstance(item, dict):
                        continue
                    compacted.append(
                        {
                            "key": item.get("key"),
                            "title": item.get("title"),
                            "value": item.get("value"),
                            "url": item.get("url"),
                            "status": item.get("status"),
                            "specialist": item.get("specialist"),
                        }
                    )
                return compacted

            compact_summary = {
                "facts": _compact_items(summary.get("facts")),
                "sources": _compact_items(summary.get("sources")),
                "evidence": _compact_items(summary.get("evidence")),
                "notes": [
                    str(item)
                    for item in (summary.get("notes")[-4:] if isinstance(summary.get("notes"), list) else [])
                    if str(item).strip()
                ],
            }
            if not any(compact_summary.values()):
                return None
            return compact_summary

        @staticmethod
        def _summarize_action(action: Any) -> dict[str, Any] | None:
            if not isinstance(action, dict):
                return None
            compact: dict[str, Any] = {
                "type": action.get("type") or action.get("action"),
                "label": action.get("label") or action.get("text") or action.get("selector") or action.get("title") or action.get("app") or action.get("url"),
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
            return compact

        @staticmethod
        def _summarize_timings(timings: dict[str, Any] | None) -> dict[str, Any] | None:
            if not isinstance(timings, dict):
                return None
            compact: dict[str, Any] = {}
            for key in ("total", "capture_initial", "plan", "execute", "capture_after", "verify", "persist"):
                try:
                    value = float(timings.get(key))
                except (TypeError, ValueError):
                    continue
                compact[key] = round(value, 3)
            return compact or None

        @staticmethod
        def _summarize_live_pointer(point: dict[str, Any] | None) -> dict[str, Any] | None:
            if not isinstance(point, dict):
                return None
            compact: dict[str, Any] = {
                "phase": point.get("phase"),
                "status": point.get("status"),
            }
            for key in ("x", "y", "width", "height", "norm_x", "norm_y", "updated_at"):
                try:
                    value = float(point.get(key))
                except (TypeError, ValueError):
                    continue
                compact[key] = round(value, 4)
            return compact if any(value is not None for value in compact.values()) else None

        @staticmethod
        def _summarize_verification(verification: dict[str, Any] | None) -> dict[str, Any] | None:
            if not isinstance(verification, dict):
                return None
            evidence = verification.get("evidence") if isinstance(verification.get("evidence"), list) else []
            compact = {
                "success": _summary_bool(verification.get("success")),
                "status": verification.get("status"),
                "failure_kind": verification.get("failure_kind"),
                "message": verification.get("message"),
                "verified_at": verification.get("verified_at"),
                "evidence": [
                    item
                    for item in (DesktopShellController._summarize_evidence_item(entry) for entry in evidence[:4])
                    if item is not None
                ],
            }
            return {key: value for key, value in compact.items() if value not in (None, "", [], {})} or None

        @staticmethod
        def _summarize_evidence_item(item: Any) -> dict[str, Any] | None:
            if not isinstance(item, dict):
                return None
            compact = {
                "subgoal_id": item.get("subgoal_id"),
                "capability": item.get("capability"),
                "kind": item.get("kind"),
                "status": item.get("status"),
                "scope": item.get("scope"),
                "satisfied": _summary_bool(item.get("satisfied")),
                "title": item.get("title"),
                "value": item.get("value"),
                "message": item.get("message"),
                "detail": item.get("detail"),
                "selector": item.get("selector"),
                "url": item.get("url"),
                "verified_at": item.get("verified_at"),
            }
            if isinstance(item.get("evidence"), list):
                compact["evidence"] = [
                    nested
                    for nested in (
                        DesktopShellController._summarize_evidence_item(entry) for entry in item.get("evidence", [])[:3]
                    )
                    if nested is not None
                ]
            return {key: value for key, value in compact.items() if value not in (None, "", [], {})} or None

        @staticmethod
        def _summarize_pending_decision(decision: dict[str, Any] | None) -> dict[str, Any] | None:
            if not isinstance(decision, dict):
                return None
            actions = decision.get("actions") if isinstance(decision.get("actions"), list) else []
            return {
                "id": decision.get("id"),
                "decision_type": decision.get("decision_type"),
                "summary": decision.get("summary"),
                "reason": decision.get("reason"),
                "risk_level": decision.get("risk_level"),
                "actions": [
                    compact
                    for compact in (DesktopShellController._summarize_action(action) for action in actions[:4])
                    if compact is not None
                ],
            }

        @staticmethod
        def _summarize_step_proposal(proposal: dict[str, Any] | None) -> dict[str, Any] | None:
            if not isinstance(proposal, dict):
                return None
            actions = proposal.get("actions") if isinstance(proposal.get("actions"), list) else []
            return {
                "intent": proposal.get("intent"),
                "capability": proposal.get("capability"),
                "risk_level": proposal.get("risk_level"),
                "target_scope": proposal.get("target_scope"),
                "surface_kind": proposal.get("surface_kind"),
                "requires_approval": _summary_bool(proposal.get("requires_approval")),
                "completes_subgoal": _summary_bool(proposal.get("completes_subgoal")),
                "current_focus": proposal.get("current_focus"),
                "progress_signals": proposal.get("progress_signals")[:4] if isinstance(proposal.get("progress_signals"), list) else [],
                "repair_strategy": proposal.get("repair_strategy")[:4] if isinstance(proposal.get("repair_strategy"), list) else [],
                "remaining_steps": proposal.get("remaining_steps")[:4] if isinstance(proposal.get("remaining_steps"), list) else [],
                "actions": [
                    compact
                    for compact in (DesktopShellController._summarize_action(action) for action in actions[:4])
                    if compact is not None
                ],
            }

        @staticmethod
        def _summarize_repair_history(history: list[Any] | None) -> list[dict[str, Any]]:
            if not isinstance(history, list):
                return []
            compacted: list[dict[str, Any]] = []
            for item in history[-6:]:
                if not isinstance(item, dict):
                    continue
                compacted.append(
                    {
                        "mode": item.get("mode") or item.get("kind"),
                        "subgoal_id": item.get("subgoal_id"),
                        "failure_kind": item.get("failure_kind") or item.get("standard_failure_kind"),
                        "capability": item.get("capability"),
                        "message": item.get("message") or item.get("reason"),
                        "step": item.get("step"),
                    }
                )
            return compacted

        @staticmethod
        def _summarize_capability_failures(failures: dict[str, Any] | None) -> list[dict[str, Any]]:
            if not isinstance(failures, dict):
                return []
            compacted: list[dict[str, Any]] = []
            for target, values in sorted(failures.items())[:8]:
                if not isinstance(values, list):
                    continue
                recent = [str(item) for item in values[-4:] if str(item).strip()]
                if recent:
                    compacted.append({"target": target, "failures": recent})
            return compacted

        @staticmethod
        def _summarize_handoff_state(context: dict[str, Any] | None) -> dict[str, Any] | None:
            if not isinstance(context, dict):
                return None
            compact = {
                key: context.get(key)
                for key in (
                    "human_handoff_kind",
                    "human_handoff_summary",
                    "human_handoff_reason",
                    "manual_resume_status",
                    "manual_resume_reason",
                    "manual_resumed_at",
                    "standard_recovery_kind",
                    "recovery_reason",
                )
                if context.get(key) not in (None, "", [], {})
            }
            return compact or None

        @staticmethod
        def _summarize_run(run: dict[str, Any] | None) -> dict[str, Any] | None:
            if not isinstance(run, dict):
                return None
            state_payload = run.get("state") if isinstance(run.get("state"), dict) else {}
            execution_state = run.get("execution_state") if isinstance(run.get("execution_state"), dict) else {}
            state_context = (
                state_payload.get("app_context")
                if isinstance(state_payload.get("app_context"), dict)
                else execution_state.get("app_context")
                if isinstance(execution_state.get("app_context"), dict)
                else {}
            )
            task_graph = (
                state_payload.get("task_graph")
                if isinstance(state_payload.get("task_graph"), dict)
                else execution_state.get("task_graph")
                if isinstance(execution_state.get("task_graph"), dict)
                else run.get("task_graph")
                if isinstance(run.get("task_graph"), dict)
                else {}
            )
            plan_health = (
                state_payload.get("plan_health")
                if isinstance(state_payload.get("plan_health"), dict)
                else execution_state.get("plan_health")
                if isinstance(execution_state.get("plan_health"), dict)
                else {}
            )
            health_items = plan_health.get("items") if isinstance(plan_health.get("items"), list) else None
            state_subgoals = (
                state_payload.get("subgoals")
                if isinstance(state_payload.get("subgoals"), list)
                else execution_state.get("subgoals")
                if isinstance(execution_state.get("subgoals"), list)
                else None
            )
            graph_subgoals = task_graph.get("subgoals") if isinstance(task_graph.get("subgoals"), list) else []
            items = health_items if health_items is not None else state_subgoals if state_subgoals is not None else graph_subgoals
            repair_history = (
                state_payload.get("repair_history")
                if isinstance(state_payload.get("repair_history"), list)
                else execution_state.get("repair_history")
                if isinstance(execution_state.get("repair_history"), list)
                else None
            )
            capability_failures = (
                state_payload.get("capability_failures")
                if isinstance(state_payload.get("capability_failures"), dict)
                else execution_state.get("capability_failures")
                if isinstance(execution_state.get("capability_failures"), dict)
                else None
            )
            terminal_result = DesktopShellController._run_is_terminal_result(run)
            pending_decision = None if terminal_result else DesktopShellController._pending_decision_from_run(run)
            budget_summary = DesktopShellController._summarize_execution_budget(run)
            environment_summary = DesktopShellController._summarize_execution_environment(run)
            step_proposal = (
                run.get("step_proposal")
                if isinstance(run.get("step_proposal"), dict)
                else state_payload.get("step_proposal")
                if isinstance(state_payload.get("step_proposal"), dict)
                else execution_state.get("step_proposal")
                if isinstance(execution_state.get("step_proposal"), dict)
                else state_payload.get("last_step")
                if isinstance(state_payload.get("last_step"), dict)
                else execution_state.get("last_step")
                if isinstance(execution_state.get("last_step"), dict)
                else None
            )
            return {
                "id": run.get("id"),
                "steps": run.get("steps"),
                "dry_run": _summary_bool(run.get("dry_run")),
                "max_steps": run.get("max_steps"),
                "max_run_seconds": run.get("max_run_seconds"),
                "pause_after_action": run.get("pause_after_action"),
                "completed": _summary_bool(run.get("completed")),
                "cancelled": _summary_bool(run.get("cancelled")),
                "cancel_reason": run.get("cancel_reason"),
                "requires_human": False if terminal_result else _summary_bool(run.get("requires_human")),
                "can_resume": _summary_bool(run.get("can_resume")),
                "resume_mode": run.get("resume_mode"),
                "interruption_kind": run.get("interruption_kind"),
                "interruption_reason": run.get("interruption_reason"),
                "error": run.get("error"),
                "desktop_autonomy_mode": DesktopShellController._resolve_run_policy_value(run, "desktop_autonomy_mode"),
                "complex_task_planning": DesktopShellController._resolve_run_policy_value(run, "complex_task_planning"),
                "approval_policy": DesktopShellController._resolve_run_policy_value(run, "approval_policy"),
                "plan_review_policy": DesktopShellController._resolve_run_policy_value(run, "plan_review_policy"),
                "stage_review_policy": DesktopShellController._resolve_run_policy_value(run, "stage_review_policy"),
                "replan_on_recoverable_error": DesktopShellController._resolve_run_policy_value(
                    run, "replan_on_recoverable_error"
                ),
                "recoverable_error_retry_limit": DesktopShellController._resolve_run_policy_value(
                    run, "recoverable_error_retry_limit"
                ),
                "execution_budget": budget_summary,
                "execution_environment": environment_summary,
                **budget_summary,
                **environment_summary,
                "current_goal": run.get("current_goal") or state_payload.get("current_goal") or execution_state.get("current_goal"),
                "orchestration_phase": run.get("orchestration_phase") or state_payload.get("orchestration_phase") or execution_state.get("orchestration_phase"),
                "active_specialist": run.get("active_specialist") or state_payload.get("active_specialist") or execution_state.get("active_specialist"),
                "current_surface_kind": run.get("current_surface_kind") or state_payload.get("current_surface_kind") or execution_state.get("current_surface_kind"),
                "last_progress_at": run.get("last_progress_at") or state_payload.get("last_progress_at") or execution_state.get("last_progress_at"),
                "plan_review_status": run.get("plan_review_status") or state_payload.get("plan_review_status") or execution_state.get("plan_review_status") or state_context.get("plan_review_status"),
                "stage_review_status": run.get("stage_review_status") or state_payload.get("stage_review_status") or execution_state.get("stage_review_status") or state_context.get("stage_review_status"),
                "last_replan_reason": run.get("last_replan_reason") or state_payload.get("last_replan_reason") or execution_state.get("last_replan_reason"),
                "verification_status": run.get("verification_status") or state_payload.get("verification_status") or execution_state.get("verification_status"),
                "last_verification": DesktopShellController._summarize_verification(
                    state_payload.get("last_verification")
                    if isinstance(state_payload.get("last_verification"), dict)
                    else execution_state.get("last_verification")
                    if isinstance(execution_state.get("last_verification"), dict)
                    else None
                ),
                "evidence_ledger": [
                    compact
                    for compact in (
                        DesktopShellController._summarize_evidence_item(item)
                        for item in (
                            state_payload.get("evidence_ledger")
                            if isinstance(state_payload.get("evidence_ledger"), list)
                            else execution_state.get("evidence_ledger")
                            if isinstance(execution_state.get("evidence_ledger"), list)
                            else []
                        )[-6:]
                    )
                    if compact is not None
                ],
                "recovery_reason": run.get("recovery_reason") or state_payload.get("recovery_reason") or execution_state.get("recovery_reason"),
                "handoff_state": DesktopShellController._summarize_handoff_state(state_context),
                "repair_history": DesktopShellController._summarize_repair_history(repair_history),
                "capability_failures": DesktopShellController._summarize_capability_failures(capability_failures),
                "workspace_summary": DesktopShellController._summarize_workspace_summary(
                    run.get("workspace_summary")
                    if isinstance(run.get("workspace_summary"), dict)
                    else state_payload.get("workspace_summary")
                    if isinstance(state_payload.get("workspace_summary"), dict)
                    else execution_state.get("workspace_summary")
                    if isinstance(execution_state.get("workspace_summary"), dict)
                    else None
                ),
                "step_proposal": DesktopShellController._summarize_step_proposal(step_proposal),
                "pending_decision": DesktopShellController._summarize_pending_decision(pending_decision),
                "plan_health": DesktopShellController._summarize_plan_health(plan_health, items),
                "task_graph": {
                    "task": task_graph.get("task"),
                    "subgoals": [
                        {
                            "id": item.get("id"),
                            "title": item.get("title"),
                            "status": item.get("status"),
                            "ready": _summary_bool(item.get("ready")),
                            "is_next": _summary_bool(item.get("is_next")),
                        }
                        for item in graph_subgoals[:8]
                        if isinstance(item, dict)
                    ],
                },
                "started_at": run.get("started_at"),
                "finished_at": run.get("finished_at"),
                "details_updated_at": run.get("details_updated_at"),
            }

        @staticmethod
        def _run_is_terminal_result(run: dict[str, Any] | None) -> bool:
            if not isinstance(run, dict):
                return False
            status = str(run.get("status") or "").strip().lower()
            return bool(
                _bool_value(run.get("completed"))
                or _bool_value(run.get("cancelled"))
                or run.get("error")
                or status in {"completed", "failed", "cancelled"}
            )

        @staticmethod
        def _find_paused_resume_run(runs: object) -> dict[str, Any] | None:
            if not isinstance(runs, list):
                return None
            for run in runs:
                if not isinstance(run, dict):
                    continue
                if _optional_bool(run.get("can_resume")) is False:
                    continue
                terminal_result = DesktopShellController._run_is_terminal_result(run)
                resume_mode = str(run.get("resume_mode") or "").strip().lower()
                terminal_resumable = resume_mode in {"execution_state", "state", "plan"}
                if terminal_result and not terminal_resumable:
                    continue
                pending_decision = DesktopShellController._pending_decision_from_run(run)
                awaiting_approval = not terminal_result and _run_orchestration_phase(run) == "awaiting_approval"
                has_handoff = bool(
                    (pending_decision if not terminal_result else None)
                    or awaiting_approval
                    or _bool_value(run.get("requires_human"))
                    or resume_mode == "manual"
                    or terminal_resumable
                    or str(run.get("interruption_kind") or "").strip()
                    or str(run.get("interruption_reason") or "").strip()
                )
                if has_handoff:
                    return run
            return None

        @staticmethod
        def _pending_decision_from_run(run: dict[str, Any] | None) -> dict[str, Any] | None:
            if not isinstance(run, dict):
                return None
            pending_decision = run.get("pending_decision")
            if isinstance(pending_decision, dict) and pending_decision:
                return pending_decision
            state_payload = run.get("state") if isinstance(run.get("state"), dict) else {}
            pending_decision = state_payload.get("pending_decision") if isinstance(state_payload, dict) else None
            if isinstance(pending_decision, dict) and pending_decision:
                return pending_decision
            execution_state = run.get("execution_state") if isinstance(run.get("execution_state"), dict) else {}
            pending_decision = execution_state.get("pending_decision") if isinstance(execution_state, dict) else None
            return pending_decision if isinstance(pending_decision, dict) and pending_decision else None

        def _apply_overview_payload(self, payload: dict[str, Any]) -> None:
            active_job = payload.get("active_job")
            jobs = payload.get("jobs") or []
            runs = payload.get("runs") or []

            if active_job:
                self._clear_paused_run()
                self.current_active_job = active_job
                active_job_id = str(active_job.get("id") or "")
                if active_job_id and active_job_id != self.current_active_job_id:
                    self.current_active_job_id = active_job_id
                    self.auto_collapsed_for_current_job = True
                    self._hide_main_window_for_floating()
                elif self.main_window.isVisible():
                    self._hide_main_window_for_floating()
                else:
                    self.floating.update_active_job(active_job, self.follow_up_draft)
                return

            if self.current_active_job_id:
                finished_job = next(
                    (item for item in jobs if str(item.get("id") or "") == self.current_active_job_id),
                    None,
                )
                self._handle_finished_job(finished_job)
                self.current_active_job = None
                self.current_active_job_id = None

            if self.paused_run_id:
                if self.main_window.isVisible():
                    self._hide_main_window_for_floating()
                else:
                    self._show_paused_run_prompt()
                return

            paused_run = DesktopShellController._find_paused_resume_run(runs)
            if paused_run is not None:
                pending_decision = DesktopShellController._pending_decision_from_run(paused_run)
                waiting_for_approval = _run_orchestration_phase(paused_run) == "awaiting_approval"
                self.paused_run_id = str(paused_run.get("id") or "") or None
                self.paused_task = str(paused_run.get("task") or paused_run.get("current_goal") or "")
                self.paused_reason = str(
                    (pending_decision.get("summary") if isinstance(pending_decision, dict) else None)
                    or (pending_decision.get("reason") if isinstance(pending_decision, dict) else None)
                    or paused_run.get("interruption_reason")
                    or paused_run.get("recovery_reason")
                    or paused_run.get("cancel_reason")
                    or paused_run.get("error")
                    or ("Waiting for approval before continuing." if waiting_for_approval else "")
                    or "Waiting for manual handling."
                )
                if self.paused_run_id:
                    if self.main_window.isVisible():
                        self._hide_main_window_for_floating()
                    else:
                        self._show_paused_run_prompt()
                    return

            if self.follow_up_draft:
                if self.main_window.isVisible():
                    self._hide_main_window_for_floating()
                else:
                    self.floating.show_waiting_follow_up(self.follow_up_draft)
                return

            if self.success_feedback_deadline and time.time() < self.success_feedback_deadline:
                if self.main_window.isVisible():
                    self.floating.hide_floating()
                else:
                    self.floating.show_idle(status="任务完成")
                return

            self.success_feedback_deadline = 0
            if self.main_window.isVisible():
                self.floating.hide_floating()
            else:
                self.floating.show_idle()

        def _clear_paused_run(self) -> None:
            self.paused_run_id = None
            self.paused_task = ""
            self.paused_reason = ""

        def _show_paused_run_prompt(self) -> None:  # pragma: no cover - GUI runtime behavior
            if not self.paused_run_id:
                return
            self.floating.show_resume_prompt(
                run_id=self.paused_run_id,
                task=self.paused_task,
                reason=self.paused_reason,
            )

        def _handle_finished_job(self, job: dict[str, Any] | None) -> None:  # pragma: no cover - GUI runtime behavior
            result = job.get("result") if isinstance(job, dict) and isinstance(job.get("result"), dict) else {}
            run_id = result.get("run_id") if isinstance(result, dict) else None
            terminal_job = _job_is_terminal_result(job) if isinstance(job, dict) else False
            pending_decision = None if terminal_job else _pending_decision_from_job(job) if isinstance(job, dict) else None
            resume_mode = str(
                (
                    result.get("resume_mode")
                    if isinstance(result, dict) and result.get("resume_mode") is not None
                    else job.get("resume_mode")
                    if isinstance(job, dict)
                    else ""
                )
                or ""
            ).strip().lower()
            can_resume = _optional_bool(
                result.get("can_resume")
                if isinstance(result, dict) and result.get("can_resume") is not None
                else job.get("can_resume")
                if isinstance(job, dict)
                else None
            )
            terminal_resumable = terminal_job and resume_mode in {"execution_state", "state", "plan"} and can_resume is not False
            requires_human = bool(
                job
                and (
                    (
                        not terminal_job
                        and (
                            _bool_value(job.get("requires_human"))
                            or (isinstance(result, dict) and _bool_value(result.get("requires_human")))
                        )
                    )
                    or pending_decision
                    or terminal_resumable
                )
            )
            if job and requires_human:
                self.last_finished_run_id = str(run_id or "") or None
                self.paused_run_id = self.last_finished_run_id
                self.paused_task = str(job.get("task") or result.get("task") or "")
                self.paused_reason = str(
                    (pending_decision.get("summary") if isinstance(pending_decision, dict) else None)
                    or (pending_decision.get("reason") if isinstance(pending_decision, dict) else None)
                    or job.get("interruption_reason")
                    or result.get("interruption_reason")
                    or result.get("recovery_reason")
                    or result.get("cancel_reason")
                    or job.get("cancel_reason")
                    or result.get("error")
                    or ""
                )
                if self.main_window.isVisible():
                    self._hide_main_window_for_floating()
                else:
                    self._show_paused_run_prompt()
                return

            if job and job.get("status") in {"failed", "attention"}:
                self._clear_paused_run()
                self.last_finished_run_id = str(run_id or "") or None
                if self.main_window.isVisible():
                    self._hide_main_window_for_floating()
                else:
                    self.floating.show_idle(status="需要处理")
                return

            if job and (
                _bool_value(job.get("cancelled"))
                or job.get("status") == "cancelled"
                or (isinstance(result, dict) and _bool_value(result.get("cancelled")))
            ):
                self._clear_paused_run()
                self.last_finished_run_id = str(run_id or "") or self.last_finished_run_id
                self.success_feedback_deadline = time.time() + 3.0
                if not self.main_window.isVisible():
                    self.floating.show_idle(status="任务已停止")
                return

            if self.follow_up_draft:
                self._clear_paused_run()
                if not self.main_window.isVisible():
                    self.floating.show_waiting_follow_up(self.follow_up_draft, status="准备继续")
                return

            self._clear_paused_run()
            self.success_feedback_deadline = time.time() + 3.0
            if not self.main_window.isVisible():
                self.floating.show_idle(status="任务完成")

        def _build_tray(self):  # pragma: no cover - GUI runtime behavior
            tray = QSystemTrayIcon(QIcon(str(self.icons_root / "app-icon-64.png")), self.qt_app)
            tray.setToolTip(f"{APP_NAME} {APP_VERSION}")
            menu = QMenu()

            show_action = QAction("显示主窗口", menu)
            show_action.triggered.connect(self.show_main_window)
            menu.addAction(show_action)

            toggle_floating_action = QAction("显示悬浮窗", menu)
            toggle_floating_action.triggered.connect(self._toggle_floating_visibility)
            menu.addAction(toggle_floating_action)

            menu.addSeparator()

            exit_action = QAction("退出", menu)
            exit_action.triggered.connect(self._quit_application)
            menu.addAction(exit_action)

            menu.aboutToShow.connect(self._handle_tray_menu_about_to_show)
            menu.aboutToHide.connect(self._handle_tray_menu_about_to_hide)
            tray.activated.connect(self._handle_tray_activated)
            tray.setContextMenu(menu)
            return tray

        def _handle_tray_activated(self, reason) -> None:  # pragma: no cover - GUI runtime behavior
            if self.quitting or self.tray_menu_open or time.time() < self.ignore_tray_activation_until:
                return
            if reason == QSystemTrayIcon.ActivationReason.Trigger:
                self._toggle_main_window()

        def _handle_tray_menu_about_to_show(self) -> None:  # pragma: no cover - GUI runtime behavior
            self.tray_menu_open = True
            self.ignore_tray_activation_until = time.time() + 0.35

        def _handle_tray_menu_about_to_hide(self) -> None:  # pragma: no cover - GUI runtime behavior
            self.ignore_tray_activation_until = time.time() + 0.35
            QTimer.singleShot(250, self._clear_tray_menu_state)

        def _clear_tray_menu_state(self) -> None:  # pragma: no cover - GUI runtime behavior
            if time.time() < self.ignore_tray_activation_until:
                return
            self.tray_menu_open = False

        def _handle_main_window_hidden(self) -> None:  # pragma: no cover - GUI runtime behavior
            self._show_floating_for_current_state()

        def _show_floating_for_current_state(self) -> None:  # pragma: no cover - GUI runtime behavior
            if self.current_active_job:
                self.floating.update_active_job(self.current_active_job, self.follow_up_draft)
                return
            if self.paused_run_id:
                self._show_paused_run_prompt()
                return
            if self.follow_up_draft:
                self.floating.show_waiting_follow_up(self.follow_up_draft)
                return
            if self.success_feedback_deadline and time.time() < self.success_feedback_deadline:
                self.floating.show_idle(status="任务完成")
                return
            self.floating.show_idle()

        def _hide_main_window_for_floating(self) -> None:  # pragma: no cover - GUI runtime behavior
            if self.main_window.isVisible():
                self.main_window.hide()
            self._show_floating_for_current_state()

        def _toggle_floating_visibility(self) -> None:  # pragma: no cover - GUI runtime behavior
            if self.floating.isVisible():
                if not self.main_window.isVisible():
                    self.show_main_window(run_id=self.last_finished_run_id)
                else:
                    self.floating.hide_floating()
                return
            if self.main_window.isVisible():
                self._hide_main_window_for_floating()
                return
            self._show_floating_for_current_state()

        def _toggle_main_window(self) -> None:  # pragma: no cover - GUI runtime behavior
            if self.main_window.isVisible():
                self._hide_main_window_for_floating()
                return
            self.auto_collapsed_for_current_job = False
            self.show_main_window(run_id=self.last_finished_run_id)

        def show_main_window(self, run_id: str | None = None) -> None:  # pragma: no cover - GUI runtime behavior
            self.floating.hide_floating()
            self.main_window.show_and_focus()
            if run_id:
                QTimer.singleShot(260, lambda: self.main_window.open_run(run_id))

        def _quit_application(self) -> None:  # pragma: no cover - GUI runtime behavior
            self.quitting = True
            self.tray_menu_open = False
            self.ignore_tray_activation_until = time.time() + 1.0
            try:
                self.tray_icon.activated.disconnect(self._handle_tray_activated)
            except Exception:
                pass
            self.floating.hide_floating()
            self.tray_icon.hide()
            self.main_window.allow_close()
            self.qt_app.quit()

        def _read_runtime_preferences(self) -> dict[str, Any]:
            try:
                response = requests.get(f"{self.base_url}/api/runtime-preferences", timeout=1.5)
                payload = response.json() if response.ok else {}
            except Exception:
                payload = {}
            return payload.get("config_overrides") if isinstance(payload, dict) else {}

        def _capture_effective_environment(self):
            config_overrides = self._read_runtime_preferences()
            config = load_agent_config(self.dashboard_app.config_path, config_overrides=config_overrides)
            return capture_effective_desktop_environment(config)

        def _submit_task(self, task: str) -> bool:
            task_text = str(task or "").strip()
            if not task_text:
                return False
            try:
                response = requests.post(
                    f"{self.base_url}/api/tasks",
                    json={
                        "task": task_text,
                        "config_overrides": self._read_runtime_preferences(),
                    },
                    timeout=2.0,
                )
                return response.ok
            except Exception:
                return False

        def _resume_interrupted_run(self, run_id: str | None = None) -> bool:  # pragma: no cover - GUI runtime behavior
            target_run_id = str(run_id or self.paused_run_id or "").strip()
            if not target_run_id:
                return False
            try:
                response = requests.post(
                    f"{self.base_url}/api/runs/{target_run_id}/resume",
                    json={
                        "config_overrides": self._read_runtime_preferences(),
                    },
                    timeout=2.0,
                )
            except Exception:
                return False
            if not response.ok:
                return False
            payload = response.json() if response.content else {}
            if isinstance(payload, dict):
                self.current_active_job = payload
                self.current_active_job_id = str(payload.get("id") or "") or self.current_active_job_id
            self._clear_paused_run()
            self.success_feedback_deadline = 0
            self._hide_main_window_for_floating()
            return True

        def _decide_active_job(self, decision: str) -> bool:  # pragma: no cover - GUI runtime behavior
            active_job_id = str(self.current_active_job_id or (self.current_active_job or {}).get("id") or "").strip()
            if not active_job_id:
                return False
            try:
                response = requests.post(
                    f"{self.base_url}/api/jobs/{active_job_id}/decision",
                    json={"decision": str(decision or "").strip().lower()},
                    timeout=2.0,
                )
            except Exception:
                return False
            if not response.ok:
                return False
            payload = response.json() if response.content else {}
            if isinstance(payload, dict) and self.current_active_job:
                self.current_active_job = {**self.current_active_job, **payload}
            self._hide_main_window_for_floating()
            return True

        def _submit_or_stage_follow_up(self, text: str) -> bool:  # pragma: no cover - GUI runtime behavior
            text = str(text or "").strip()
            if not text:
                return False
            if self.current_active_job_id or self.follow_up_draft:
                self.follow_up_draft = text
                if not self.main_window.isVisible():
                    if self.current_active_job:
                        self.floating.update_active_job(self.current_active_job, self.follow_up_draft)
                    else:
                        self.floating.show_waiting_follow_up(self.follow_up_draft)
                return True
            if self._submit_task(text):
                self.follow_up_draft = ""
                self.success_feedback_deadline = 0
                self._hide_main_window_for_floating()
                return True
            return False

        def _continue_follow_up(self) -> bool:  # pragma: no cover - GUI runtime behavior
            if not self.follow_up_draft:
                return False
            if self._submit_task(self.follow_up_draft):
                self.follow_up_draft = ""
                self.success_feedback_deadline = 0
                self._hide_main_window_for_floating()
                return True
            return False

        def _stop_active_task(self) -> bool:  # pragma: no cover - GUI runtime behavior
            current_job = self.current_active_job
            try:
                response = requests.post(f"{self.base_url}/api/tasks/stop", json={}, timeout=1.5)
                if response.ok:
                    try:
                        payload = response.json() if getattr(response, "content", b"") else {}
                    except Exception:
                        payload = {}
                    if current_job:
                        self.current_active_job = {
                            **current_job,
                            **(payload if isinstance(payload, dict) else {}),
                            "cancel_requested": True,
                            "status": "stopping",
                        }
                        if not self.main_window.isVisible():
                            self.floating.update_active_job(self.current_active_job, self.follow_up_draft)
                    return True
                return False
            except Exception:
                return False


def launch_desktop_shell(
    *,
    host: str,
    port: int,
    config_path: str | Path | None = None,
) -> int:
    if _QT_IMPORT_ERROR is not None or QApplication is None:
        raise DesktopShellUnavailable(
            "PySide6 with QtWebEngine is not installed. Install dependencies from requirements.txt first."
        ) from _QT_IMPORT_ERROR

    app = DashboardApp(host=host, port=port, config_path=config_path)
    app.config = load_agent_config(config_path)
    server = app.create_server()
    server_thread = threading.Thread(target=server.serve_forever, daemon=True, name="desktop-agent-shell-server")
    server_thread.start()

    bound_host = _normalize_shell_host(host)
    actual_port = int(server.server_address[1])
    base_url = f"http://{bound_host}:{actual_port}"
    _wait_for_server(base_url)

    _configure_qtwebengine_environment()
    _configure_windows_app_identity(APP_ID)
    qt_app = QApplication.instance() or QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)
    qt_app.setApplicationName(APP_NAME)
    qt_app.setApplicationDisplayName(APP_NAME)
    qt_app.setWindowIcon(QIcon(str(app.ui_root / "icons" / "app-icon-64.png")))
    _configure_qtwebengine_profile_storage()

    controller = DesktopShellController(
        qt_app=qt_app,
        dashboard_app=app,
        server=server,
        base_url=base_url,
    )

    try:
        return qt_app.exec()
    finally:
        controller.shutdown()
