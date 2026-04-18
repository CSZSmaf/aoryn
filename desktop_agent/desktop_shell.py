from __future__ import annotations

import os
import socket
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import requests

from desktop_agent.dashboard import DashboardApp
from desktop_agent.controller import load_agent_config
from desktop_agent.runtime_paths import default_cache_root, local_data_root
from desktop_agent.version import APP_ASSET_VERSION, APP_ID, APP_NAME, APP_VERSION

try:  # pragma: no cover - import availability depends on runtime environment
    from PySide6.QtCore import QEvent, QPoint, QRectF, QSize, QTimer, Qt, QUrl
    from PySide6.QtGui import QAction, QCloseEvent, QIcon, QPainterPath, QRegion
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
    QIcon = object  # type: ignore[assignment]
    QPoint = object  # type: ignore[assignment]
    QSize = object  # type: ignore[assignment]
    QEvent = object  # type: ignore[assignment]
    QRectF = object  # type: ignore[assignment]
    Qt = object  # type: ignore[assignment]
    QPainterPath = object  # type: ignore[assignment]
    QRegion = object  # type: ignore[assignment]
    QWebEngineProfile = object  # type: ignore[assignment]
    QWebEngineView = object  # type: ignore[assignment]
    _QT_IMPORT_ERROR = exc

from desktop_agent.windows_env import capture_effective_desktop_environment, preferred_work_area


class DesktopShellUnavailable(RuntimeError):
    """Raised when the native desktop shell cannot be launched."""


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
    if sys.platform == "win32":
        # This shell only hosts the local dashboard, so single-process mode is a
        # practical tradeoff to avoid renderer startup crashes on locked-down PCs.
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


    class FloatingExecutionWindow(QWidget):
        _IDLE_WIDTH = 236
        _ACTIVE_WIDTH = 486
        _WINDOW_HEIGHT = 54
        _WINDOW_RADIUS = 18

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
            self.setWindowTitle(f"{APP_NAME} Floating")
            self.setWindowIcon(QIcon(str(icon_path)))

            self._allow_close = False
            self._active_job: dict[str, Any] | None = None
            self._follow_up_draft = ""
            self._resume_run_id: str | None = None
            self._resume_task = ""
            self._resume_reason = ""
            self._waiting_status = ""
            self._started_at: float | None = None
            self._drag_global: QPoint | None = None
            self._drag_origin: QPoint | None = None
            self._dragging = False
            self._on_toggle_main = on_toggle_main
            self._on_stop_task = on_stop_task
            self._on_submit_text = on_submit_text
            self._on_continue_follow_up = on_continue_follow_up
            self._on_resume_run = on_resume_run
            self._on_decide_job = on_decide_job

            self._timer = QTimer(self)
            self._timer.setInterval(1000)
            self._timer.timeout.connect(self._refresh_timer_label)

            root = QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)

            self.card = QFrame(self)
            self.card.setObjectName("floatingShellCard")
            card_layout = QHBoxLayout(self.card)
            card_layout.setContentsMargins(6, 6, 7, 6)
            card_layout.setSpacing(7)

            self.logo_button = QPushButton(self.card)
            self.logo_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.logo_button.setFixedSize(30, 30)
            self.logo_button.setIcon(QIcon(str(icon_path)))
            self.logo_button.setIconSize(QSize(16, 16))
            self.logo_button.setObjectName("floatingLogoButton")
            self.logo_button.clicked.connect(self._on_toggle_main)
            card_layout.addWidget(self.logo_button, 0, Qt.AlignmentFlag.AlignVCenter)

            self.task_label = QLabel(f"{APP_NAME} 就绪", self.card)
            self.task_label.setObjectName("floatingTaskLabel")
            self.task_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            card_layout.addWidget(self.task_label, 1)

            self.timer_label = QLabel("--", self.card)
            self.timer_label.setObjectName("floatingTimerLabel")
            card_layout.addWidget(self.timer_label, 0, Qt.AlignmentFlag.AlignRight)

            self.input_line = QLineEdit(self.card)
            self.input_line.setObjectName("floatingInputLine")
            self.input_line.setPlaceholderText("输入下一条任务…")
            self.input_line.returnPressed.connect(self._handle_submit)
            self.input_line.setClearButtonEnabled(True)
            card_layout.addWidget(self.input_line, 1)

            self.submit_button = QPushButton("排队", self.card)
            self.submit_button.setObjectName("floatingPrimaryButton")
            self.submit_button.clicked.connect(self._handle_submit)
            card_layout.addWidget(self.submit_button)

            self.continue_button = QPushButton("继续", self.card)
            self.continue_button.setObjectName("floatingPrimaryButton")
            self.continue_button.clicked.connect(self._handle_continue_follow_up)
            card_layout.addWidget(self.continue_button)

            self.stop_button = QPushButton("停止", self.card)
            self.stop_button.setObjectName("floatingDangerButton")
            self.stop_button.clicked.connect(self._handle_stop_action)
            card_layout.addWidget(self.stop_button, 0, Qt.AlignmentFlag.AlignRight)

            self.open_button = QPushButton("打开", self.card)
            self.open_button.setObjectName("floatingGhostButton")
            self.open_button.clicked.connect(self._on_toggle_main)
            card_layout.addWidget(self.open_button, 0, Qt.AlignmentFlag.AlignRight)
            root.addWidget(self.card)

            self.setStyleSheet(
                """
                QWidget#floatingShellWindow {
                  background: transparent;
                }
                #floatingShellCard {
                  background: rgba(252, 253, 251, 0.96);
                  border: 1px solid rgba(22, 33, 29, 0.1);
                  border-radius: 20px;
                  box-shadow: 0 18px 42px rgba(22, 33, 29, 0.14);
                }
                #floatingLogoButton {
                  border: 1px solid rgba(22, 33, 29, 0.08);
                  border-radius: 15px;
                  background: rgba(244, 247, 243, 0.98);
                  padding: 0;
                }
                #floatingTaskLabel {
                  color: #16211d;
                  font-size: 12px;
                  font-weight: 700;
                }
                #floatingTimerLabel {
                  color: #0f8f73;
                  font-size: 10px;
                  font-weight: 700;
                  padding: 2px 6px;
                  background: rgba(15, 143, 115, 0.12);
                  border-radius: 999px;
                }
                #floatingInputLine {
                  min-height: 26px;
                  padding: 0 9px;
                  border-radius: 13px;
                  border: 1px solid rgba(22, 33, 29, 0.1);
                  background: rgba(246, 249, 245, 0.98);
                  color: #16211d;
                  selection-background-color: rgba(15, 143, 115, 0.2);
                }
                #floatingGhostButton, #floatingDangerButton, #floatingPrimaryButton {
                  min-height: 26px;
                  padding: 0 9px;
                  border-radius: 13px;
                  font-weight: 600;
                  font-size: 11px;
                }
                #floatingGhostButton {
                  border: 1px solid rgba(22, 33, 29, 0.1);
                  background: rgba(244, 247, 243, 0.96);
                  color: #4d5f59;
                }
                #floatingDangerButton {
                  border: 1px solid rgba(185, 28, 28, 0.12);
                  background: rgba(254, 242, 242, 0.96);
                  color: #b91c1c;
                }
                #floatingPrimaryButton {
                  border: 1px solid rgba(15, 143, 115, 0.14);
                  background: rgba(230, 247, 241, 0.96);
                  color: #0f8f73;
                }
                """
            )

            self._drag_surfaces = (
                self,
                self.card,
                self.task_label,
                self.timer_label,
            )
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
            self._on_toggle_main()

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
            self._follow_up_draft = ""
            self._resume_run_id = None
            self._resume_task = ""
            self._resume_reason = ""
            self._waiting_status = status
            self._started_at = None
            self._timer.stop()
            self.timer_label.setText("--")
            self.input_line.clear()
            self._apply_layout_state()
            self.show()
            self.raise_()

        def hide_floating(self) -> None:  # pragma: no cover - GUI runtime behavior
            self._timer.stop()
            self.hide()

        def show_waiting_follow_up(self, draft: str, *, status: str = "下一条任务已排队") -> None:  # pragma: no cover
            self._active_job = None
            self._follow_up_draft = draft
            self._resume_run_id = None
            self._resume_task = ""
            self._resume_reason = ""
            self._waiting_status = status
            self._started_at = None
            self._timer.stop()
            self.timer_label.setText("--")
            self.input_line.setText(draft)
            self._apply_layout_state()
            self.show()
            self.raise_()

        def show_resume_prompt(
            self,
            *,
            run_id: str,
            task: str,
            reason: str = "",
            status: str = "Resume when the manual check is done.",
        ) -> None:  # pragma: no cover - GUI runtime behavior
            self._active_job = None
            self._follow_up_draft = ""
            self._resume_run_id = str(run_id or "").strip() or None
            self._resume_task = str(task or "").strip()
            self._resume_reason = str(reason or "").strip()
            self._waiting_status = status
            self._started_at = None
            self._timer.stop()
            self.timer_label.setText("--")
            self.input_line.clear()
            self._apply_layout_state()
            self.show()
            self.raise_()

        def update_active_job(self, active_job: dict[str, Any] | None, follow_up_draft: str) -> None:  # pragma: no cover
            self._active_job = active_job
            self._follow_up_draft = follow_up_draft
            self._resume_run_id = None
            self._resume_task = ""
            self._resume_reason = ""
            self._waiting_status = ""
            result = active_job.get("result") if isinstance(active_job, dict) else {}
            started_at = result.get("started_at") or active_job.get("started_at") if isinstance(result, dict) else active_job.get("started_at")
            self._started_at = float(started_at) if isinstance(started_at, (int, float)) else None
            if self._started_at is not None:
                self._timer.start()
            else:
                self._timer.stop()
                self.timer_label.setText("--")
            self._refresh_timer_label()
            self._apply_layout_state()
            self.show()
            self.raise_()

        def _handle_submit(self) -> None:  # pragma: no cover - GUI runtime behavior
            text = self.input_line.text().strip()
            if not text:
                return
            self._on_submit_text(text)
            self.input_line.clear()

        def _handle_continue_follow_up(self) -> None:  # pragma: no cover - GUI runtime behavior
            if self._is_approval_job():
                self._on_decide_job("approve")
                return
            if self._resume_run_id:
                self._on_resume_run(self._resume_run_id)
                return
            self._on_continue_follow_up()

        def _handle_stop_action(self) -> None:  # pragma: no cover - GUI runtime behavior
            if self._is_approval_job():
                self._on_decide_job("reject")
                return
            self._on_stop_task()

        def _is_approval_job(self) -> bool:
            active = self._active_job or {}
            if not active:
                return False
            if str(active.get("status") or "").strip().lower() == "approval":
                return True
            result = active.get("result") if isinstance(active, dict) else {}
            pending_decision = result.get("pending_decision") if isinstance(result, dict) else None
            return isinstance(pending_decision, dict) and bool(pending_decision)

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

        def _apply_window_shape(self) -> None:
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), self._WINDOW_RADIUS, self._WINDOW_RADIUS)
            self.setMask(QRegion(path.toFillPolygon().toPolygon()))

        def _apply_layout_state(self) -> None:  # pragma: no cover - GUI runtime behavior
            active = self._active_job or {}
            has_job = bool(self._active_job)
            has_follow_up = bool(self._follow_up_draft)
            has_resume_prompt = bool(self._resume_run_id)
            stop_requested = bool(active.get("cancel_requested")) if has_job else False
            show_input = has_job or has_follow_up

            width = self._ACTIVE_WIDTH if (show_input or has_resume_prompt) else self._IDLE_WIDTH
            self.setFixedSize(width, self._WINDOW_HEIGHT)
            self.card.setFixedSize(width, self._WINDOW_HEIGHT)
            self._apply_window_shape()

            if has_job:
                title = str(active.get("task") or "正在执行任务")
                if stop_requested:
                    title = f"正在停止 · {title}"
            elif has_resume_prompt:
                title = self._resume_reason or self._waiting_status or "Manual verification paused"
                if self._resume_task:
                    title = f"Resume: {self._resume_task}"
            elif has_resume_prompt:
                self.input_line.clear()
                self.continue_button.setText("Resume")
            elif has_follow_up:
                title = self._waiting_status or "下一条任务已排队"
            else:
                title = self._waiting_status or f"{APP_NAME} 就绪"
            self.task_label.setText(title[:42])

            self.timer_label.setVisible(has_job)
            self.stop_button.setVisible(has_job)
            self.stop_button.setEnabled(has_job and not stop_requested)
            self.stop_button.setText("停止中…" if stop_requested else "停止")
            self.continue_button.setVisible((not has_job and has_follow_up) or has_resume_prompt)
            self.input_line.setVisible(show_input)
            self.submit_button.setVisible(show_input)

            if has_job:
                self.submit_button.setText("排队")
                self.input_line.setPlaceholderText("输入下一条任务…")
            elif has_follow_up:
                self.submit_button.setText("更新")
                self.input_line.setPlaceholderText("更新已排队的任务…")
                if not self.input_line.text().strip():
                    self.input_line.setText(self._follow_up_draft)
            else:
                self.input_line.clear()
                self.input_line.setPlaceholderText("输入任务…")


        def _apply_layout_state(self) -> None:  # pragma: no cover - GUI runtime behavior
            active = self._active_job or {}
            has_job = bool(self._active_job)
            has_follow_up = bool(self._follow_up_draft)
            has_resume_prompt = bool(self._resume_run_id)
            is_approval = self._is_approval_job()
            stop_requested = bool(active.get("cancel_requested")) if has_job else False
            show_input = (has_job and not is_approval) or has_follow_up

            width = self._ACTIVE_WIDTH if (show_input or has_resume_prompt) else self._IDLE_WIDTH
            self.setFixedSize(width, self._WINDOW_HEIGHT)
            self.card.setFixedSize(width, self._WINDOW_HEIGHT)
            self._apply_window_shape()

            if is_approval:
                result = active.get("result") if isinstance(active, dict) else {}
                pending_decision = result.get("pending_decision") if isinstance(result, dict) else None
                title = "Approval needed"
                if isinstance(pending_decision, dict):
                    title = str(pending_decision.get("summary") or pending_decision.get("reason") or title)
            elif has_job:
                title = str(active.get("task") or "Running task")
                if stop_requested:
                    title = f"Stopping | {title}"
            elif has_resume_prompt:
                title = self._resume_reason or self._waiting_status or "Manual verification paused"
                if self._resume_task:
                    title = f"Resume: {self._resume_task}"
            elif has_follow_up:
                title = self._waiting_status or "Queued follow-up task"
            else:
                title = self._waiting_status or f"{APP_NAME} ready"
            self.task_label.setText(title[:42])

            self.timer_label.setVisible(has_job and not is_approval)
            self.stop_button.setVisible(has_job)
            self.stop_button.setEnabled(has_job and not stop_requested)
            self.stop_button.setText("Reject" if is_approval else ("Stopping" if stop_requested else "Stop"))
            self.continue_button.setVisible(is_approval or (not has_job and has_follow_up) or has_resume_prompt)
            self.input_line.setVisible(show_input)
            self.submit_button.setVisible(show_input)

            if is_approval:
                self.input_line.clear()
                self.continue_button.setText("Approve")
            elif has_job:
                self.submit_button.setText("Queue")
                self.input_line.setPlaceholderText("Add the next task")
                self.continue_button.setText("Continue")
            elif has_resume_prompt:
                self.input_line.clear()
                self.continue_button.setText("Resume")
            elif has_follow_up:
                self.submit_button.setText("Update")
                self.input_line.setPlaceholderText("Update the queued follow-up")
                self.continue_button.setText("Continue")
                if not self.input_line.text().strip():
                    self.input_line.setText(self._follow_up_draft)
            else:
                self.input_line.clear()
                self.input_line.setPlaceholderText("Enter a task")
                self.continue_button.setText("Continue")


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

    def refresh_overview(self) -> None:  # pragma: no cover - exercised through runtime UI
        try:
            payload = requests.get(f"{self.base_url}/api/overview", timeout=1.5).json()
        except Exception:
            if self.success_feedback_deadline and time.time() >= self.success_feedback_deadline:
                self.success_feedback_deadline = 0
                if self.main_window.isVisible():
                    self.floating.hide_floating()
                else:
                    self.floating.show_idle()
            return

        active_job = payload.get("active_job")
        jobs = payload.get("jobs") or []

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
            finished_job = next((item for item in jobs if str(item.get("id") or "") == self.current_active_job_id), None)
            self._handle_finished_job(finished_job)
            self.current_active_job = None
            self.current_active_job_id = None

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

    def _handle_finished_job(self, job: dict[str, Any] | None) -> None:  # pragma: no cover - GUI runtime behavior
        result = job.get("result") if isinstance(job, dict) else {}
        run_id = result.get("run_id") if isinstance(result, dict) else None
        if job and (job.get("requires_human") or job.get("status") in {"failed", "attention"}):
            self.last_finished_run_id = str(run_id or "") or None
            self.show_main_window(run_id=self.last_finished_run_id)
            return

        if job and (job.get("cancelled") or job.get("status") == "cancelled" or (isinstance(result, dict) and result.get("cancelled"))):
            self.last_finished_run_id = str(run_id or "") or self.last_finished_run_id
            self.success_feedback_deadline = time.time() + 3.0
            if not self.main_window.isVisible():
                self.floating.show_idle(status="任务已停止")
            return

        if self.follow_up_draft:
            if not self.main_window.isVisible():
                self.floating.show_waiting_follow_up(self.follow_up_draft, status="准备继续")
            return

        self.success_feedback_deadline = time.time() + 3.0
        if not self.main_window.isVisible():
            self.floating.show_idle(status="任务完成")

    def _handle_finished_job(self, job: dict[str, Any] | None) -> None:  # pragma: no cover - GUI runtime behavior
        result = job.get("result") if isinstance(job, dict) else {}
        run_id = result.get("run_id") if isinstance(result, dict) else None
        if job and job.get("requires_human"):
            self.last_finished_run_id = str(run_id or "") or None
            self.paused_run_id = self.last_finished_run_id
            self.paused_task = str(job.get("task") or result.get("task") or "")
            self.paused_reason = str(job.get("interruption_reason") or result.get("interruption_reason") or "")
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
                self.floating.show_idle(status="Task needs review")
            return

        if job and (job.get("cancelled") or job.get("status") == "cancelled" or (isinstance(result, dict) and result.get("cancelled"))):
            self._clear_paused_run()
            self.last_finished_run_id = str(run_id or "") or self.last_finished_run_id
            self.success_feedback_deadline = time.time() + 3.0
            if not self.main_window.isVisible():
                self.floating.show_idle(status="Task stopped")
            return

        if self.follow_up_draft:
            self._clear_paused_run()
            if not self.main_window.isVisible():
                self.floating.show_waiting_follow_up(self.follow_up_draft, status="Ready to continue")
            return

        self._clear_paused_run()
        self.success_feedback_deadline = time.time() + 3.0
        if not self.main_window.isVisible():
            self.floating.show_idle(status="Task complete")

    def _build_tray(self):  # pragma: no cover - GUI runtime behavior
        tray = QSystemTrayIcon(QIcon(str(self.icons_root / "app-icon-64.png")), self.qt_app)
        tray.setToolTip(f"{APP_NAME} {APP_VERSION}")
        menu = QMenu()

        show_action = QAction("显示主窗口", menu)
        show_action.triggered.connect(self.show_main_window)
        menu.addAction(show_action)

        toggle_floating_action = QAction("显示悬浮条", menu)
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
        if self.follow_up_draft:
            self.floating.show_waiting_follow_up(self.follow_up_draft)
            return
        if self.success_feedback_deadline and time.time() < self.success_feedback_deadline:
            self.floating.show_idle(status="任务完成")
            return
        self.floating.show_idle()

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
            self.floating.show_idle(status="Task complete")
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

    def _submit_or_stage_follow_up(self, text: str) -> None:  # pragma: no cover - GUI runtime behavior
        if self.current_active_job_id:
            self.follow_up_draft = text
            if not self.main_window.isVisible():
                self.floating.update_active_job(self.current_active_job, self.follow_up_draft)
            return
        if self._submit_task(text):
            self.follow_up_draft = ""
            self.success_feedback_deadline = 0
            self._hide_main_window_for_floating()

    def _continue_follow_up(self) -> None:  # pragma: no cover - GUI runtime behavior
        if not self.follow_up_draft:
            return
        if self._submit_task(self.follow_up_draft):
            self.follow_up_draft = ""
            self.success_feedback_deadline = 0
            self._hide_main_window_for_floating()

    def _stop_active_task(self) -> None:  # pragma: no cover - GUI runtime behavior
        if self.current_active_job and not self.current_active_job.get("cancel_requested"):
            self.current_active_job = {
                **self.current_active_job,
                "cancel_requested": True,
                "status": "stopping",
            }
            if not self.main_window.isVisible():
                self.floating.update_active_job(self.current_active_job, self.follow_up_draft)
        try:
            response = requests.post(f"{self.base_url}/api/tasks/stop", json={}, timeout=1.5)
            if response.ok:
                payload = response.json()
                if isinstance(payload, dict) and self.current_active_job:
                    self.current_active_job = {
                        **self.current_active_job,
                        **payload,
                        "cancel_requested": True,
                        "status": "stopping",
                    }
                    if not self.main_window.isVisible():
                        self.floating.update_active_job(self.current_active_job, self.follow_up_draft)
        except Exception:
            return


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
