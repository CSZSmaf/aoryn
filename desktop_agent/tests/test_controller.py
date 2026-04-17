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


def test_desktop_agent_stops_repeated_identical_plans():
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
        assert "same plan repeatedly" in (result.error or "")
        assert executor.executed_batches == 2
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

        assert '"environment"' in step_payload
        assert '"effective"' in step_payload
        assert '"detected"' in step_payload
        assert '"dpi_scale"' in step_payload
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


def test_desktop_agent_replans_after_recoverable_execution_error():
    scratch_root = Path("test_artifacts") / f"controller_recover_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)

    class _FlakyExecutor(_ExecutorStub):
        def execute_many(self, actions, pause_after_action, stop_requested=None):
            super().execute_many(actions, pause_after_action, stop_requested=stop_requested)
            if self.executed_batches == 1:
                raise ExecutionError("Could not focus window: Calculator")

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
        )

        result = agent.run("recover from a missing calculator window")

        assert result.completed is True
        assert result.error is None
        assert result.steps == 2
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


def test_configure_qtwebengine_environment_enables_single_process_on_windows(monkeypatch):
    import desktop_agent.desktop_shell as desktop_shell

    monkeypatch.delenv("QTWEBENGINE_CHROMIUM_FLAGS", raising=False)
    monkeypatch.delenv("QTWEBENGINE_DISABLE_SANDBOX", raising=False)
    monkeypatch.setattr(desktop_shell.sys, "platform", "win32")

    desktop_shell._configure_qtwebengine_environment()

    flags = set((os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS") or "").split())
    assert "--no-sandbox" in flags
    assert "--single-process" in flags
    assert os.environ.get("QTWEBENGINE_DISABLE_SANDBOX") == "1"
