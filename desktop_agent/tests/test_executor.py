import pytest

from desktop_agent.actions import Action
from desktop_agent.config import AgentConfig
from desktop_agent.executor import (
    BaseExecutor,
    ExecutionCancelled,
    ExecutionError,
    RealDesktopExecutor,
    _find_known_blockers,
    _resolve_browser_binary,
)
from desktop_agent.windows_env import DesktopEnvironment, MonitorSnapshot, Rect, WindowSnapshot


def test_launch_browser_falls_back_to_default_browser(monkeypatch):
    executor = RealDesktopExecutor(AgentConfig(dry_run=False))
    opened: list[str] = []

    def fake_popen(*args, **kwargs):
        raise FileNotFoundError("missing browser binary")

    def fake_open(url: str) -> bool:
        opened.append(url)
        return True

    monkeypatch.setattr("desktop_agent.executor.subprocess.Popen", fake_popen)
    monkeypatch.setattr("desktop_agent.executor.webbrowser.open", fake_open)

    executor.execute(Action.from_dict({"type": "launch_app", "app": "browser"}))

    assert opened == ["about:blank"]


def test_browser_open_falls_back_to_default_browser(monkeypatch):
    executor = RealDesktopExecutor(AgentConfig(dry_run=False))
    opened: list[str] = []

    def fake_popen(*args, **kwargs):
        raise FileNotFoundError("missing browser binary")

    def fake_open(url: str) -> bool:
        opened.append(url)
        return True

    monkeypatch.setattr("desktop_agent.executor.subprocess.Popen", fake_popen)
    monkeypatch.setattr("desktop_agent.executor.webbrowser.open", fake_open)

    executor.execute(Action.from_dict({"type": "browser_open", "text": "openai.com"}))

    assert opened == ["https://openai.com"]


def test_launch_browser_raises_if_no_fallback_available(monkeypatch):
    executor = RealDesktopExecutor(AgentConfig(dry_run=False))

    def fake_popen(*args, **kwargs):
        raise FileNotFoundError("missing browser binary")

    monkeypatch.setattr("desktop_agent.executor.subprocess.Popen", fake_popen)
    monkeypatch.setattr("desktop_agent.executor.webbrowser.open", lambda url: False)

    with pytest.raises(ExecutionError, match="Failed to open browser target: about:blank"):
        executor.execute(Action.from_dict({"type": "launch_app", "app": "browser"}))


def test_resolve_browser_binary_uses_known_installation_path(monkeypatch):
    known_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

    monkeypatch.setattr("desktop_agent.executor.shutil.which", lambda binary: None)
    monkeypatch.setattr("desktop_agent.executor._browser_installation_candidates", lambda: [known_path])
    monkeypatch.setattr("desktop_agent.executor.Path.is_file", lambda self: str(self) == known_path)

    assert _resolve_browser_binary("msedge.exe") == known_path


def test_browser_open_uses_dom_session_in_hybrid_mode(monkeypatch):
    events: list[tuple[str, str]] = []

    class FakeSession:
        def __init__(self, config):
            events.append(("init", config.browser_dom_backend))

        def open_url(self, target: str) -> None:
            events.append(("open", target))

        def search(self, query: str) -> None:
            events.append(("search", query))

        def click(self, *, text=None, selector=None) -> None:
            events.append(("click", text or selector or ""))

    monkeypatch.setattr(
        "desktop_agent.executor.dom_backend_status",
        lambda backend: type("Status", (), {"available": True, "detail": "ok"})(),
    )
    monkeypatch.setattr("desktop_agent.executor.PlaywrightBrowserSession", FakeSession)

    executor = RealDesktopExecutor(AgentConfig(dry_run=False, browser_control_mode="hybrid"))
    executor.execute(Action.from_dict({"type": "browser_open", "text": "openai.com"}))
    executor.execute(Action.from_dict({"type": "browser_dom_click", "text": "Log in"}))

    assert ("open", "https://openai.com") in events
    assert ("click", "Log in") in events


def test_browser_open_uses_managed_browser_when_surface_requests_it(monkeypatch):
    executor = RealDesktopExecutor(AgentConfig(dry_run=False))
    events: list[tuple[str, str]] = []

    class FakeBridge:
        def ensure_running(self):
            events.append(("ensure", "ready"))

        def navigate(self, target: str):
            events.append(("navigate", target))

        def snapshot(self):
            return {"url": "https://openai.com", "title": "OpenAI", "text": "Docs", "managed_by": "aoryn_browser"}

    executor.managed_browser = FakeBridge()
    monkeypatch.setattr(
        "desktop_agent.executor.dom_backend_status",
        lambda backend: type("Status", (), {"available": False, "detail": "Playwright missing"})(),
    )
    monkeypatch.setattr("desktop_agent.executor.webbrowser.open", lambda url: (_ for _ in ()).throw(AssertionError("unexpected browser fallback")))

    executor.execute(
        Action.from_dict(
            {"type": "browser_open", "text": "openai.com", "target_scope": "managed_aoryn_browser"}
        )
    )

    assert ("navigate", "https://openai.com") in events


def test_browser_snapshot_prefers_managed_browser_runtime():
    executor = RealDesktopExecutor(AgentConfig(dry_run=False))

    class FakeBridge:
        def snapshot(self):
            return {"url": "https://aoryn.org", "title": "Aoryn", "text": "Browser", "managed_by": "aoryn_browser"}

    executor.managed_browser = FakeBridge()

    snapshot = executor.browser_snapshot()

    assert snapshot["managed_by"] == "aoryn_browser"


def test_browser_open_falls_back_to_gui_when_dom_backend_is_unavailable_in_hybrid_mode(monkeypatch):
    opened: list[str] = []

    monkeypatch.setattr(
        "desktop_agent.executor.dom_backend_status",
        lambda backend: type("Status", (), {"available": False, "detail": "Playwright missing"})(),
    )
    monkeypatch.setattr("desktop_agent.executor._resolve_browser_binary", lambda binary: None)
    monkeypatch.setattr("desktop_agent.executor.webbrowser.open", lambda url: opened.append(url) or True)

    executor = RealDesktopExecutor(AgentConfig(dry_run=False, browser_control_mode="hybrid"))
    executor.execute(Action.from_dict({"type": "browser_open", "text": "openai.com"}))

    assert opened == ["https://openai.com"]


def test_browser_dom_click_requires_available_dom_backend(monkeypatch):
    monkeypatch.setattr(
        "desktop_agent.executor.dom_backend_status",
        lambda backend: type("Status", (), {"available": False, "detail": "Playwright missing"})(),
    )
    executor = RealDesktopExecutor(AgentConfig(dry_run=False, browser_control_mode="dom"))

    with pytest.raises(ExecutionError, match="Playwright missing"):
        executor.execute(Action.from_dict({"type": "browser_dom_click", "text": "Reject all"}))


def test_open_app_if_needed_reuses_existing_window(monkeypatch):
    events: list[tuple[str, object]] = []
    environment = DesktopEnvironment(
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
        visible_windows=[
            WindowSnapshot(handle=101, title="Calculator", class_name="ApplicationFrameWindow"),
        ],
    )

    monkeypatch.setattr(
        "desktop_agent.executor.capture_effective_desktop_environment",
        lambda config=None: environment,
    )
    monkeypatch.setattr("desktop_agent.executor.find_window", lambda env, query: env.visible_windows[0])
    monkeypatch.setattr("desktop_agent.executor.focus_window", lambda handle: events.append(("focus", handle)) or True)
    monkeypatch.setattr(
        "desktop_agent.executor.subprocess.Popen",
        lambda *args, **kwargs: events.append(("spawn", args[0])) or None,
    )

    executor = RealDesktopExecutor(AgentConfig(dry_run=False))
    executor.update_environment(environment)
    executor.execute(Action.from_dict({"type": "open_app_if_needed", "app": "calculator"}))

    assert events == [("focus", 101)]


def test_browser_open_attempts_to_dismiss_known_blockers(monkeypatch):
    events: list[tuple[str, object]] = []
    environment = DesktopEnvironment(
        platform="windows",
        virtual_bounds=Rect(0, 0, 1920, 1080),
        monitors=[],
        foreground_window=WindowSnapshot(handle=14, title="Chat", class_name="ApplicationFrameWindow"),
        visible_windows=[
            WindowSnapshot(handle=11, title="Save password"),
            WindowSnapshot(
                handle=13,
                title="run_agent.py - desktop_agent_project - Visual Studio Code",
                class_name="Chrome_WidgetWin_1",
            ),
            WindowSnapshot(handle=14, title="Chat", class_name="ApplicationFrameWindow"),
            WindowSnapshot(handle=12, title="Microsoft Edge"),
        ],
    )

    monkeypatch.setattr(
        "desktop_agent.executor.capture_effective_desktop_environment",
        lambda config=None: environment,
    )
    monkeypatch.setattr(
        "desktop_agent.executor.find_window",
        lambda env, query: next((item for item in env.visible_windows if query.lower() in item.title.lower()), None),
    )
    monkeypatch.setattr("desktop_agent.executor.close_window", lambda handle: events.append(("close", handle)) or True)
    monkeypatch.setattr("desktop_agent.executor.minimize_window", lambda handle: events.append(("minimize", handle)) or True)
    monkeypatch.setattr("desktop_agent.executor.focus_window", lambda handle: events.append(("focus", handle)) or True)
    monkeypatch.setattr(
        "desktop_agent.executor.dom_backend_status",
        lambda backend: type("Status", (), {"available": False, "detail": "Playwright missing"})(),
    )
    monkeypatch.setattr("desktop_agent.executor._resolve_browser_binary", lambda binary: None)
    monkeypatch.setattr("desktop_agent.executor.webbrowser.open", lambda url: events.append(("open", url)) or True)

    executor = RealDesktopExecutor(AgentConfig(dry_run=False, browser_control_mode="hybrid"))
    executor.execute(Action.from_dict({"type": "browser_open", "text": "openai.com"}))

    assert ("close", 11) in events
    assert ("minimize", 14) in events
    assert ("focus", 12) in events
    assert ("open", "https://openai.com") in events
    assert ("close", 13) not in events


def test_launch_app_uses_generic_windows_launcher_for_safe_unknown_app(monkeypatch):
    events: list[tuple[str, object]] = []

    monkeypatch.setattr("desktop_agent.executor.launch_app_by_name", lambda app: events.append(("launch", app)) or True)

    executor = RealDesktopExecutor(AgentConfig(dry_run=False))
    executor.execute(Action.from_dict({"type": "launch_app", "app": "snipping tool"}))

    assert events == [("launch", "snipping tool")]


def test_relative_click_targets_window_rect(monkeypatch):
    events: list[tuple[str, object]] = []
    environment = DesktopEnvironment(
        platform="windows",
        virtual_bounds=Rect(0, 0, 1920, 1080),
        monitors=[],
        visible_windows=[
            WindowSnapshot(handle=21, title="Calculator", rect=Rect(100, 200, 500, 800)),
        ],
    )

    class FakeGui:
        def click(self, x, y, clicks=1, button="left"):
            events.append(("click", (x, y, clicks, button)))

    monkeypatch.setattr(
        "desktop_agent.executor.capture_effective_desktop_environment",
        lambda config=None: environment,
    )
    monkeypatch.setattr(
        "desktop_agent.executor.find_window",
        lambda env, query: next((item for item in env.visible_windows if query.lower() in item.title.lower()), None),
    )
    monkeypatch.setattr("desktop_agent.executor.focus_window", lambda handle: events.append(("focus", handle)) or True)
    monkeypatch.setattr("desktop_agent.executor._load_pyautogui", lambda: FakeGui())

    executor = RealDesktopExecutor(AgentConfig(dry_run=False))
    executor.execute(
        Action.from_dict(
            {
                "type": "relative_click",
                "title": "Calculator",
                "relative_x": 0.5,
                "relative_y": 0.25,
                "clicks": 2,
            }
        )
    )

    assert ("focus", 21) in events
    assert ("click", (300, 350, 2, "left")) in events


def test_find_known_blockers_ignores_vscode_main_window():
    environment = DesktopEnvironment(
        platform="windows",
        virtual_bounds=Rect(0, 0, 1920, 1080),
        visible_windows=[
            WindowSnapshot(
                handle=1,
                title="run_agent.py - desktop_agent_project - Visual Studio Code",
                class_name="Chrome_WidgetWin_1",
            ),
            WindowSnapshot(handle=2, title="Save password", class_name="Chrome_WidgetWin_1"),
        ],
    )

    blockers = _find_known_blockers(environment)

    assert [item.title for item in blockers] == ["Save password"]


def test_find_known_blockers_ignores_dwm_notification_window():
    environment = DesktopEnvironment(
        platform="windows",
        virtual_bounds=Rect(0, 0, 1920, 1080),
        visible_windows=[
            WindowSnapshot(handle=1, title="DWM Notification Window", class_name="Dwm"),
            WindowSnapshot(handle=2, title="Translate", class_name="#32770"),
        ],
    )

    blockers = _find_known_blockers(environment)

    assert [item.title for item in blockers] == ["Translate"]


def test_execute_many_stops_during_pause_after_action(monkeypatch):
    class _Executor(BaseExecutor):
        def __init__(self) -> None:
            super().__init__()
            self.executed: list[str] = []

        def execute(self, action: Action) -> None:
            self.executed.append(action.type)

    stop_state = {"checks": 0}

    def stop_requested() -> bool:
        stop_state["checks"] += 1
        return stop_state["checks"] >= 3

    monkeypatch.setattr("desktop_agent.executor.time.sleep", lambda seconds: None)

    executor = _Executor()
    action = Action.from_dict({"type": "wait", "seconds": 0.1})

    with pytest.raises(ExecutionCancelled) as exc:
        executor.execute_many([action], pause_after_action=0.2, stop_requested=stop_requested)

    assert executor.executed == ["wait"]
    assert exc.value.executed_actions == [action]


def test_wait_action_stops_quickly(monkeypatch):
    sleep_calls: list[float] = []
    stop_state = {"checks": 0}

    def stop_requested() -> bool:
        stop_state["checks"] += 1
        return stop_state["checks"] >= 3

    monkeypatch.setattr("desktop_agent.executor.time.sleep", lambda seconds: sleep_calls.append(seconds))

    executor = RealDesktopExecutor(AgentConfig(dry_run=False))
    action = Action.from_dict({"type": "wait", "seconds": 0.2})

    with pytest.raises(ExecutionCancelled) as exc:
        executor.execute_many([action], pause_after_action=0, stop_requested=stop_requested)

    assert exc.value.executed_actions == []
    assert sleep_calls


def test_wait_for_window_action_stops_quickly(monkeypatch):
    stop_state = {"checks": 0}
    wait_callbacks: list[bool] = []

    def stop_requested() -> bool:
        stop_state["checks"] += 1
        return stop_state["checks"] >= 3

    def fake_wait_for_window(query, *, timeout_seconds=2.5, poll_interval=0.1, stop_requested=None):
        assert query == "Calculator"
        assert stop_requested is not None
        wait_callbacks.append(bool(stop_requested()))
        wait_callbacks.append(bool(stop_requested()))
        return None

    monkeypatch.setattr("desktop_agent.executor.wait_for_window", fake_wait_for_window)
    monkeypatch.setattr(
        "desktop_agent.executor.capture_effective_desktop_environment",
        lambda config=None: DesktopEnvironment(platform="windows", virtual_bounds=Rect(0, 0, 1920, 1080)),
    )

    executor = RealDesktopExecutor(AgentConfig(dry_run=False))

    with pytest.raises(ExecutionCancelled) as exc:
        executor.execute_many(
            [Action.from_dict({"type": "wait_for_window", "title": "Calculator", "seconds": 1.0})],
            pause_after_action=0,
            stop_requested=stop_requested,
        )

    assert exc.value.executed_actions == []
    assert wait_callbacks == [False, True]


def test_find_known_blockers_matches_explicit_cookie_and_password_titles():
    environment = DesktopEnvironment(
        platform="windows",
        virtual_bounds=Rect(0, 0, 1920, 1080),
        visible_windows=[
            WindowSnapshot(handle=1, title="Cookie consent", class_name="Chrome_WidgetWin_1"),
            WindowSnapshot(handle=2, title="Save your password", class_name="Chrome_WidgetWin_1"),
            WindowSnapshot(handle=3, title="Microsoft Edge", class_name="Chrome_WidgetWin_1"),
        ],
    )

    blockers = _find_known_blockers(environment)

    assert [item.title for item in blockers] == ["Cookie consent", "Save your password"]
