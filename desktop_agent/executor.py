from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from desktop_agent.actions import Action
from desktop_agent.browser_runtime import BrowserRuntimeBridge, BrowserRuntimeError
from desktop_agent.browser_dom import BrowserDOMError, PlaywrightBrowserSession, dom_backend_status
from desktop_agent.capabilities import CapabilityExecutor
from desktop_agent.config import AgentConfig
from desktop_agent.windows_env import (
    DesktopEnvironment,
    Rect,
    WindowSnapshot,
    capture_effective_desktop_environment,
    close_window,
    find_window,
    focus_window,
    launch_app_by_name,
    maximize_window,
    minimize_window,
    move_resize_window,
    wait_for_window,
)


class ExecutionError(RuntimeError):
    """Raised when action execution fails."""


class ExecutionCancelled(ExecutionError):
    """Raised when the user stops execution mid-run."""

    def __init__(self, message: str = "Stopped by user.", *, executed_actions: list[Action] | None = None) -> None:
        super().__init__(message)
        self.executed_actions = list(executed_actions or [])


class BaseExecutor:
    def __init__(self) -> None:
        self.current_environment: DesktopEnvironment | None = None
        self._active_stop_requested: Callable[[], bool] | None = None

    def execute(self, action: Action) -> None:
        raise NotImplementedError

    def update_environment(self, environment: DesktopEnvironment | None) -> None:
        self.current_environment = environment

    def execute_many(
        self,
        actions: list[Action],
        pause_after_action: float,
        stop_requested: Callable[[], bool] | None = None,
    ) -> None:
        previous_stop_requested = self._active_stop_requested
        self._active_stop_requested = stop_requested
        executed_actions: list[Action] = []
        try:
            for action in actions:
                self._ensure_not_stopped()
                try:
                    self.execute(action)
                except ExecutionCancelled as exc:
                    if not exc.executed_actions:
                        exc.executed_actions = list(executed_actions)
                    raise
                executed_actions.append(action)
                self._ensure_not_stopped(executed_actions=executed_actions)
                if pause_after_action > 0:
                    try:
                        self._sleep_interruptibly(pause_after_action)
                    except ExecutionCancelled as exc:
                        if not exc.executed_actions:
                            exc.executed_actions = list(executed_actions)
                        raise
        finally:
            self._active_stop_requested = previous_stop_requested

    def _stop_requested(self) -> bool:
        if self._active_stop_requested is None:
            return False
        try:
            return bool(self._active_stop_requested())
        except Exception:
            return False

    def _ensure_not_stopped(self, *, executed_actions: list[Action] | None = None) -> None:
        if self._stop_requested():
            raise ExecutionCancelled(executed_actions=executed_actions)

    def _sleep_interruptibly(self, seconds: float, *, poll_interval: float = 0.05) -> None:
        remaining = max(0.0, float(seconds or 0.0))
        while remaining > 0:
            self._ensure_not_stopped()
            chunk = min(remaining, poll_interval)
            time.sleep(chunk)
            remaining -= chunk

    def browser_snapshot(self) -> dict[str, str | None] | None:
        return None


class ActionExecutor(BaseExecutor):
    """Low-level guarded action executor."""


class RealDesktopExecutor(ActionExecutor):
    """Real desktop executor based on pyautogui."""

    def __init__(self, config: AgentConfig):
        super().__init__()
        self.config = config
        self.dom_session = None
        self.managed_browser = BrowserRuntimeBridge(config) if config.managed_browser_enabled else None
        self._last_dom_extract: str | None = None

    def execute(self, action: Action) -> None:
        try:
            if action.type == "launch_app":
                self._launch_app(action.app or "")
            elif action.type == "open_app_if_needed":
                self._open_app_if_needed(action.app or "")
            elif action.type == "focus_window":
                self._focus_window(action.title or action.text or "")
            elif action.type == "minimize_window":
                self._minimize_window(action.title or action.text or "")
            elif action.type == "close_window":
                self._close_window(action.title or action.text or "")
            elif action.type == "dismiss_popup":
                self._dismiss_popup(action.title or action.text or "")
            elif action.type == "maximize_window":
                self._maximize_window(action.title or action.text or "")
            elif action.type == "move_resize_window":
                self._move_resize_window(
                    action.title or action.text or "",
                    Rect(
                        int(action.x or 0),
                        int(action.y or 0),
                        int(action.x or 0) + int(action.width or 0),
                        int(action.y or 0) + int(action.height or 0),
                    ),
                )
            elif action.type == "wait_for_window":
                self._wait_for_window(action.title or action.text or "", action.seconds)
            elif action.type == "relative_click":
                self._relative_click(
                    action.title or action.text or "",
                    float(action.relative_x or 0.0),
                    float(action.relative_y or 0.0),
                    button=action.button,
                    clicks=action.clicks,
                )
            elif action.type == "browser_open":
                self._open_browser_target(action.text or "", target_scope=action.target_scope)
            elif action.type == "browser_search":
                self._search_in_browser(action.text or "", target_scope=action.target_scope)
            elif action.type == "browser_dom_click":
                self._dom_click(text=action.text, selector=action.selector, target_scope=action.target_scope)
            elif action.type == "browser_dom_fill":
                self._dom_fill(
                    value=action.text or "",
                    selector=action.selector,
                    label=action.target_scope,
                    target_scope=action.target_scope,
                )
            elif action.type == "browser_dom_select":
                self._dom_select(
                    value=action.text or "",
                    selector=action.selector,
                    label=action.target_scope,
                    target_scope=action.target_scope,
                )
            elif action.type == "browser_dom_wait":
                self._dom_wait(
                    text=action.text,
                    selector=action.selector,
                    seconds=action.seconds,
                    target_scope=action.target_scope,
                )
            elif action.type == "browser_dom_extract":
                self._dom_extract(text=action.text, selector=action.selector, target_scope=action.target_scope)
            elif action.type == "uia_invoke":
                self._uia_invoke(title=action.title, selector=action.selector, text=action.text)
            elif action.type == "uia_set_value":
                self._uia_set_value(title=action.title, selector=action.selector, text=action.text or "")
            elif action.type == "uia_select":
                self._uia_select(title=action.title, selector=action.selector, text=action.text or "")
            elif action.type == "uia_expand":
                self._uia_expand(title=action.title, selector=action.selector, text=action.text)
            elif action.type == "hotkey":
                gui = _load_pyautogui()
                gui.hotkey(*action.keys)
            elif action.type == "clipboard_copy":
                gui = _load_pyautogui()
                gui.hotkey("ctrl", "c")
            elif action.type == "clipboard_paste":
                gui = _load_pyautogui()
                gui.hotkey("ctrl", "v")
            elif action.type == "press":
                gui = _load_pyautogui()
                gui.press(action.key or "")
            elif action.type == "type":
                gui = _load_pyautogui()
                gui.write(action.text or "", interval=0.02)
            elif action.type == "drag":
                gui = _load_pyautogui()
                gui.moveTo(action.x, action.y)
                gui.dragTo(action.end_x, action.end_y, duration=0.2, button=action.button)
            elif action.type == "click":
                gui = _load_pyautogui()
                gui.click(action.x, action.y, clicks=action.clicks, button=action.button)
            elif action.type == "scroll":
                gui = _load_pyautogui()
                gui.scroll(action.amount or 0)
            elif action.type == "shell_recipe_request":
                self._run_shell_recipe(recipe=action.recipe or "", arguments=action.text or "")
            elif action.type == "wait":
                self._sleep_interruptibly(float(action.seconds or 0))
            else:  # pragma: no cover
                raise ExecutionError(f"Unsupported action type: {action.type}")
        except ExecutionCancelled:
            raise
        except Exception as exc:  # pragma: no cover - depends on runtime environment
            raise ExecutionError(str(exc)) from exc

    def _launch_app(self, app: str) -> None:
        resolved_app = (app or "").strip()
        if not resolved_app:
            raise ExecutionError("Missing app name.")
        alias = resolved_app.lower()
        target = self.config.app_launch_map.get(alias) or self.config.app_launch_map.get(resolved_app)
        if alias == "browser":
            if self._attempt_dom_navigation(lambda session: session.open_url("about:blank")):
                return
            self._open_browser_with_fallback(target)
            return
        if target:
            subprocess.Popen([target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        if self.config.generic_app_launch_enabled and launch_app_by_name(resolved_app):
            return
        raise ExecutionError(f"Unknown or unavailable app: {resolved_app}")

    def _open_app_if_needed(self, app: str) -> None:
        resolved_app = (app or "").strip()
        if not resolved_app:
            raise ExecutionError("Missing app name.")
        self._refresh_environment()
        match = _find_existing_app_window(self.current_environment, resolved_app)
        if match is not None:
            if not focus_window(match.handle):
                raise ExecutionError(f"Could not focus window: {resolved_app}")
            return
        self._launch_app(resolved_app)
        wait_query = _default_window_hint(resolved_app) or resolved_app
        if not (resolved_app.lower() == "browser" and self._prefers_dom_navigation()):
            self._wait_for_window(wait_query, self.config.window_match_timeout)

    def _open_browser_target(self, target: str, *, target_scope: str | None = None) -> None:
        if (target_scope or "").strip().lower() != "managed_aoryn_browser":
            self._prepare_for_browser_task()
        normalized = self.config.normalize_browser_url(target)
        if self._attempt_managed_browser(
            lambda bridge: bridge.navigate(normalized),
            action_scope=target_scope,
        ):
            return
        if self._attempt_dom_navigation(lambda session: session.open_url(normalized)):
            return
        browser_target = self.config.app_launch_map.get("browser")
        self._open_browser_with_fallback(browser_target, normalized)

    def _open_browser_with_fallback(self, binary: str | None, target: str | None = None) -> None:
        resolved_binary = _resolve_browser_binary(binary)
        if resolved_binary:
            try:
                self._spawn_browser_process(resolved_binary, target)
                return
            except Exception:
                pass

        fallback_target = target or "about:blank"
        if webbrowser.open(fallback_target):
            return
        raise ExecutionError(f"Failed to open browser target: {fallback_target}")

    def _search_in_browser(self, query: str, *, target_scope: str | None = None) -> None:
        if (target_scope or "").strip().lower() != "managed_aoryn_browser":
            self._prepare_for_browser_task()
        if self._attempt_managed_browser(
            lambda bridge: bridge.navigate(self.config.build_browser_search_url(query)),
            action_scope=target_scope,
        ):
            return
        if self._attempt_dom_navigation(lambda session: session.search(query)):
            return
        self._open_browser_target(self.config.build_browser_search_url(query))

    def _dom_click(self, *, text: str | None, selector: str | None, target_scope: str | None = None) -> None:
        if (target_scope or "").strip().lower() != "managed_aoryn_browser":
            self._prepare_for_browser_task()
        if selector and self._attempt_managed_browser(
            lambda bridge: bridge.perform_action({"action": "click", "selector": selector}),
            action_scope=target_scope,
        ):
            return
        session = self._get_dom_session(required=True)
        session.click(text=text, selector=selector)

    def _dom_fill(
        self,
        *,
        value: str,
        selector: str | None,
        label: str | None,
        target_scope: str | None = None,
    ) -> None:
        if (target_scope or "").strip().lower() != "managed_aoryn_browser":
            self._prepare_for_browser_task()
        if selector and self._attempt_managed_browser(
            lambda bridge: bridge.perform_action({"action": "fill", "selector": selector, "value": value}),
            action_scope=target_scope,
        ):
            return
        session = self._get_dom_session(required=True)
        session.fill(value=value, text=label, selector=selector)

    def _dom_select(
        self,
        *,
        value: str,
        selector: str | None,
        label: str | None,
        target_scope: str | None = None,
    ) -> None:
        if (target_scope or "").strip().lower() != "managed_aoryn_browser":
            self._prepare_for_browser_task()
        if selector and self._attempt_managed_browser(
            lambda bridge: bridge.perform_action({"action": "select", "selector": selector, "value": value}),
            action_scope=target_scope,
        ):
            return
        session = self._get_dom_session(required=True)
        session.select(value=value, text=label, selector=selector)

    def _dom_wait(
        self,
        *,
        text: str | None,
        selector: str | None,
        seconds: float | None,
        target_scope: str | None = None,
    ) -> None:
        if (target_scope or "").strip().lower() != "managed_aoryn_browser":
            self._prepare_for_browser_task()
        if self._attempt_managed_browser(
            lambda bridge: bridge.wait_for_state(
                selector=selector,
                text=text,
                timeout_seconds=seconds or self.config.browser_dom_timeout,
            ),
            action_scope=target_scope,
            selector=selector,
        ):
            return
        session = self._get_dom_session(required=True)
        session.wait_for(text=text, selector=selector, timeout_seconds=seconds)

    def _dom_extract(
        self,
        *,
        text: str | None,
        selector: str | None,
        target_scope: str | None = None,
    ) -> None:
        if (target_scope or "").strip().lower() != "managed_aoryn_browser":
            self._prepare_for_browser_task()
        if self._attempt_managed_browser_query(selector=selector, action_scope=target_scope):
            payload = self.managed_browser.query_dom(selector=selector, include_text=True) if self.managed_browser else {}
            self._last_dom_extract = str(payload.get("text") or payload.get("value") or "").strip() or None
            return
        session = self._get_dom_session(required=True)
        extracted = session.extract(text=text, selector=selector)
        self._last_dom_extract = extracted

    def _uia_invoke(self, *, title: str | None, selector: str | None, text: str | None) -> None:
        element = _resolve_uia_element(title=title, selector=selector, text=text)
        if hasattr(element, "invoke"):
            element.invoke()
            return
        element.click_input()

    def _uia_set_value(self, *, title: str | None, selector: str | None, text: str) -> None:
        element = _resolve_uia_element(title=title, selector=selector, text=None)
        if hasattr(element, "set_edit_text"):
            element.set_edit_text(text)
            return
        if hasattr(element, "set_text"):
            element.set_text(text)
            return
        element.click_input()
        gui = _load_pyautogui()
        gui.write(text, interval=0.02)

    def _uia_select(self, *, title: str | None, selector: str | None, text: str) -> None:
        element = _resolve_uia_element(title=title, selector=selector, text=None)
        if hasattr(element, "select"):
            try:
                element.select(text)
                return
            except Exception:
                pass
        element.expand() if hasattr(element, "expand") else element.click_input()
        option = _resolve_uia_element(title=title, selector=None, text=text)
        option.click_input()

    def _uia_expand(self, *, title: str | None, selector: str | None, text: str | None) -> None:
        element = _resolve_uia_element(title=title, selector=selector, text=text)
        if hasattr(element, "expand"):
            element.expand()
            return
        element.click_input()

    def _run_shell_recipe(self, *, recipe: str, arguments: str) -> None:
        policy = (self.config.shell_recipe_policy or "approval_required").strip().lower()
        if policy == "disabled":
            raise ExecutionError("Shell recipes are disabled by policy.")

        command = list(self.config.shell_recipe_registry.get(recipe) or [])
        if not command:
            raise ExecutionError(f"Unknown shell recipe: {recipe}")

        if recipe == "pip_install":
            package_names = re.findall(r"[A-Za-z0-9._\-]+", arguments)
            if not package_names:
                raise ExecutionError("pip_install requires at least one safe package name.")
            command.extend(package_names[:5])

        subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=max(15, int(self.config.model_request_timeout)),
            shell=False,
        )

    def _prepare_for_browser_task(self) -> None:
        self._refresh_environment()
        browser_window = _find_existing_browser_window(self.current_environment)
        self._dismiss_known_blockers()
        self._minimize_browser_conflicts(browser_window)
        if browser_window is not None:
            focus_window(browser_window.handle)

    def _focus_window(self, title: str) -> None:
        self._refresh_environment()
        match = find_window(self.current_environment, title)
        if match is None or not focus_window(match.handle):
            raise ExecutionError(f"Could not focus window: {title}")

    def _close_window(self, title: str) -> None:
        self._refresh_environment()
        match = find_window(self.current_environment, title)
        if match is None or not close_window(match.handle):
            raise ExecutionError(f"Could not close window: {title}")

    def _dismiss_popup(self, title: str) -> None:
        self._close_window(title)

    def _minimize_window(self, title: str) -> None:
        self._refresh_environment()
        match = find_window(self.current_environment, title)
        if match is None or not minimize_window(match.handle):
            raise ExecutionError(f"Could not minimize window: {title}")

    def _maximize_window(self, title: str) -> None:
        self._refresh_environment()
        match = find_window(self.current_environment, title)
        if match is None or not maximize_window(match.handle):
            raise ExecutionError(f"Could not maximize window: {title}")

    def _move_resize_window(self, title: str, rect: Rect) -> None:
        self._refresh_environment()
        match = find_window(self.current_environment, title)
        if match is None or not move_resize_window(match.handle, rect):
            raise ExecutionError(f"Could not move or resize window: {title}")

    def _wait_for_window(self, title: str, timeout_seconds: float | None = None) -> None:
        match = wait_for_window(
            title,
            timeout_seconds=float(timeout_seconds or self.config.window_match_timeout),
            stop_requested=self._stop_requested,
        )
        self.current_environment = capture_effective_desktop_environment(self.config)
        if match is None:
            self._ensure_not_stopped()
            raise ExecutionError(f"Timed out waiting for window: {title}")

    def _relative_click(
        self,
        title: str,
        relative_x: float,
        relative_y: float,
        *,
        button: str,
        clicks: int,
    ) -> None:
        self._refresh_environment()
        match = find_window(self.current_environment, title)
        if match is None or match.rect is None:
            raise ExecutionError(f"Could not find target window for relative click: {title}")
        focus_window(match.handle)
        rect = match.rect
        click_x = rect.left + _resolve_relative_axis(relative_x, rect.width)
        click_y = rect.top + _resolve_relative_axis(relative_y, rect.height)
        gui = _load_pyautogui()
        gui.click(click_x, click_y, clicks=clicks, button=button)

    def _dismiss_known_blockers(self) -> None:
        mode = self.config.desktop_autonomy_mode.lower().strip()
        if mode not in {"conservative", "balanced", "aggressive"}:
            return
        if self.current_environment is None:
            return
        for blocker in _find_known_blockers(self.current_environment, mode=mode):
            close_window(blocker.handle)

    def _minimize_browser_conflicts(self, browser_window: WindowSnapshot | None) -> None:
        if self.current_environment is None:
            return
        if (self.config.window_conflict_policy or "").strip().lower() != "minimize_first":
            return
        foreground = self.current_environment.foreground_window
        if foreground is None or foreground.handle == 0:
            return
        if browser_window is not None and foreground.handle == browser_window.handle:
            return
        if foreground.is_minimized or not foreground.is_visible:
            return
        if _is_known_blocker_window(foreground):
            return
        if _is_browser_window(foreground):
            return
        if _is_protected_window(foreground):
            return
        minimize_window(foreground.handle)

    def _refresh_environment(self) -> None:
        self.current_environment = capture_effective_desktop_environment(self.config)

    def _get_dom_session(self, *, required: bool = False):
        status = dom_backend_status(self.config.browser_dom_backend)
        if not status.available:
            if required or self.config.browser_control_mode == "dom":
                raise ExecutionError(
                    f"{status.detail} Install Playwright and browser binaries to enable DOM mode."
                )
            return None

        if self.dom_session is None:
            try:
                self.dom_session = PlaywrightBrowserSession(self.config)
            except BrowserDOMError as exc:
                raise ExecutionError(str(exc)) from exc
        return self.dom_session

    def _prefers_dom_navigation(self) -> bool:
        return self.config.browser_control_mode.lower().strip() in {"dom", "hybrid"}

    def _requires_dom_navigation(self) -> bool:
        return self.config.browser_control_mode.lower().strip() == "dom"

    def _attempt_dom_navigation(self, operation) -> bool:
        if not self._prefers_dom_navigation():
            return False

        try:
            session = self._get_dom_session(required=self._requires_dom_navigation())
            if session is None:
                return False
            operation(session)
            return True
        except Exception as exc:
            self._reset_dom_session()
            if self._requires_dom_navigation():
                if isinstance(exc, ExecutionError):
                    raise
                raise ExecutionError(str(exc)) from exc
            return False

    def _attempt_managed_browser(self, operation, *, action_scope: str | None, selector: str | None = None) -> bool:
        if self.managed_browser is None:
            return False
        if (action_scope or "").strip().lower() != "managed_aoryn_browser":
            return False
        if selector is not None and not selector.strip():
            return False
        try:
            self.managed_browser.ensure_running()
            operation(self.managed_browser)
            return True
        except BrowserRuntimeError:
            return False

    def _attempt_managed_browser_query(self, *, selector: str | None = None, action_scope: str | None = None) -> bool:
        if self.managed_browser is None:
            return False
        if (action_scope or "").strip().lower() != "managed_aoryn_browser":
            return False
        if selector is None or not selector.strip():
            return False
        try:
            self.managed_browser.ensure_running()
            return True
        except BrowserRuntimeError:
            return False

    def _reset_dom_session(self) -> None:
        if self.dom_session is not None:
            try:
                self.dom_session.close()
            except Exception:
                pass
        self.dom_session = None

    def browser_snapshot(self) -> dict[str, str | None] | None:
        if self.managed_browser is not None:
            try:
                snapshot = self.managed_browser.snapshot()
            except BrowserRuntimeError:
                snapshot = None
            if isinstance(snapshot, dict) and any(str(snapshot.get(key) or "").strip() for key in ("url", "title", "text")):
                return snapshot
        if self.dom_session is None:
            return None
        snapshot = getattr(self.dom_session, "snapshot", None)
        if snapshot is None:
            return None
        try:
            return snapshot()
        except Exception:
            return None

    @staticmethod
    def _spawn_browser_process(binary: str, target: str | None = None) -> None:
        command = [binary]
        if target:
            command.append(target)
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@dataclass(slots=True)
class MockDesktopState:
    open_apps: set[str] = field(default_factory=set)
    active_app: str | None = None
    text_buffers: dict[str, str] = field(default_factory=dict)
    browser_queries: list[str] = field(default_factory=list)
    browser_history: list[str] = field(default_factory=list)
    browser_dom_clicks: list[str] = field(default_factory=list)
    current_url: str | None = None
    address_bar_active: bool = False
    clipboard_text: str | None = None
    last_extracted_text: str | None = None


class MockExecutor(ActionExecutor):
    """Mock executor for tests and dry-run mode."""

    def __init__(self, config: AgentConfig | None = None) -> None:
        super().__init__()
        self.config = config or AgentConfig()
        self.state = MockDesktopState()
        self.executed: list[dict] = []

    def execute(self, action: Action) -> None:
        self.executed.append(action.to_dict())
        if action.type == "launch_app":
            app = action.app or ""
            self.state.open_apps.add(app)
            self.state.active_app = app
            self.state.text_buffers.setdefault(app, "")
            self.state.address_bar_active = False
            return
        if action.type == "open_app_if_needed":
            app = action.app or ""
            self.state.open_apps.add(app)
            self.state.active_app = app
            self.state.text_buffers.setdefault(app, "")
            return
        if action.type in {"focus_window", "minimize_window", "maximize_window", "wait_for_window"}:
            target = (action.title or action.text or "").strip().lower()
            if target:
                self.state.active_app = _infer_mock_app_from_title(target) or self.state.active_app
            return
        if action.type in {"close_window", "dismiss_popup"}:
            target = (action.title or action.text or "").strip().lower()
            app = _infer_mock_app_from_title(target)
            if app and app in self.state.open_apps:
                self.state.open_apps.discard(app)
                if self.state.active_app == app:
                    self.state.active_app = next(iter(self.state.open_apps), None)
            return
        if action.type in {"move_resize_window", "relative_click"}:
            target = (action.title or action.text or "").strip().lower()
            if target:
                self.state.active_app = _infer_mock_app_from_title(target) or self.state.active_app
            return
        if action.type == "browser_open":
            self._open_browser_target(action.text or "")
            return
        if action.type == "browser_search":
            self._search_in_browser(action.text or "")
            return
        if action.type == "browser_dom_click":
            label = (action.text or action.selector or "").strip()
            if label:
                self.state.browser_dom_clicks.append(label)
            self._ensure_browser_context()
            return
        if action.type in {"browser_dom_fill", "browser_dom_select"}:
            self._ensure_browser_context()
            self.state.text_buffers["browser"] = action.text or ""
            return
        if action.type == "browser_dom_wait":
            self._ensure_browser_context()
            return
        if action.type == "browser_dom_extract":
            self._ensure_browser_context()
            self.state.last_extracted_text = self.state.text_buffers.get("browser")
            return
        if action.type in {"uia_invoke", "uia_set_value", "uia_select", "uia_expand"}:
            if action.title:
                self.state.active_app = _infer_mock_app_from_title(action.title.lower()) or self.state.active_app
            if action.type == "uia_set_value" and self.state.active_app:
                self.state.text_buffers[self.state.active_app] = action.text or ""
            return
        if action.type == "clipboard_copy":
            if self.state.active_app:
                self.state.clipboard_text = self.state.text_buffers.get(self.state.active_app, "")
            return
        if action.type == "clipboard_paste":
            if self.state.active_app:
                current = self.state.text_buffers.get(self.state.active_app, "")
                self.state.text_buffers[self.state.active_app] = current + (self.state.clipboard_text or "")
            return
        if action.type == "type":
            if self.state.active_app:
                if self.state.active_app == "browser" and self.state.address_bar_active:
                    self.state.text_buffers["browser"] = action.text or ""
                else:
                    current = self.state.text_buffers.get(self.state.active_app, "")
                    self.state.text_buffers[self.state.active_app] = current + (action.text or "")
            return
        if action.type == "drag":
            return
        if action.type == "hotkey":
            combo = tuple(action.keys)
            if combo == ("ctrl", "l") and self.state.active_app == "browser":
                self.state.address_bar_active = True
                return
            if combo == ("ctrl", "t") and self.state.active_app == "browser":
                self.state.address_bar_active = True
                self.state.text_buffers["browser"] = ""
                self.state.current_url = "about:blank"
                return
            if combo == ("alt", "tab") and self.state.open_apps:
                self.state.active_app = self.state.active_app or next(iter(self.state.open_apps))
                return
            return
        if action.type == "press":
            if action.key == "enter" and self.state.active_app == "browser" and self.state.address_bar_active:
                self._commit_browser_address_bar()
            return
        if action.type == "shell_recipe_request":
            return
        if action.type in {"wait", "click", "scroll"}:
            return

    def _commit_browser_address_bar(self) -> None:
        raw_value = (self.state.text_buffers.get("browser") or "").strip()
        if raw_value:
            if _looks_like_browser_target(raw_value):
                self._open_browser_target(raw_value)
            else:
                self._search_in_browser(raw_value)
        self.state.address_bar_active = False

    def _ensure_browser_context(self) -> None:
        self.state.open_apps.add("browser")
        self.state.active_app = "browser"
        self.state.text_buffers.setdefault("browser", "")

    def _open_browser_target(self, target: str) -> None:
        self._ensure_browser_context()
        normalized = self.config.normalize_browser_url(target)
        self.state.current_url = normalized
        self.state.browser_history.append(normalized)
        self.state.text_buffers["browser"] = normalized
        self.state.address_bar_active = False

    def _search_in_browser(self, query: str) -> None:
        self._ensure_browser_context()
        clean_query = query.strip()
        self.state.browser_queries.append(clean_query)
        self.state.current_url = self.config.build_browser_search_url(clean_query)
        self.state.browser_history.append(self.state.current_url)
        self.state.text_buffers["browser"] = clean_query
        self.state.address_bar_active = False

    def browser_snapshot(self) -> dict[str, str | None] | None:
        if not self.state.current_url:
            return None
        return {
            "url": self.state.current_url,
            "title": None,
            "text": self.state.text_buffers.get("browser"),
        }


def _looks_like_browser_target(value: str) -> bool:
    if re.match(r"^https?://\S+$", value, re.I):
        return True
    return bool(
        re.match(
            r"^(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/[^\s]*)?$",
            value,
            re.I,
        )
    )


def _load_pyautogui():
    import pyautogui  # imported lazily

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.1
    return pyautogui


def _resolve_uia_element(*, title: str | None, selector: str | None, text: str | None):
    try:
        from pywinauto import Desktop
    except ModuleNotFoundError as exc:
        raise ExecutionError("pywinauto is required for Windows UI Automation actions.") from exc

    desktop = Desktop(backend="uia")
    window = None
    if (title or "").strip():
        window = desktop.window(title_re=re.escape(str(title).strip()))
    else:
        try:
            window = desktop.active()
        except Exception as exc:  # pragma: no cover - runtime dependent
            raise ExecutionError("Could not resolve the active desktop window for UI Automation.") from exc

    query = _parse_uia_selector(selector)
    if text and "title_re" not in query and "best_match" not in query and "name" not in query:
        query["title_re"] = re.escape(text.strip())
    try:
        if query:
            return window.child_window(**query).wrapper_object()
        return window.wrapper_object()
    except Exception as exc:  # pragma: no cover - runtime dependent
        raise ExecutionError(
            f"Could not resolve a UI Automation element for selector={selector!r} text={text!r}."
        ) from exc


def _parse_uia_selector(selector: str | None) -> dict[str, str]:
    normalized = str(selector or "").strip()
    if not normalized:
        return {}
    query: dict[str, str] = {}
    for segment in normalized.split(";"):
        if "=" not in segment:
            continue
        key, value = segment.split("=", 1)
        cleaned_key = key.strip().lower()
        cleaned_value = value.strip()
        if not cleaned_key or not cleaned_value:
            continue
        if cleaned_key in {"name", "title"}:
            query["title_re"] = re.escape(cleaned_value)
        elif cleaned_key in {"auto_id", "automation_id"}:
            query["auto_id"] = cleaned_value
        elif cleaned_key in {"control_type", "type"}:
            query["control_type"] = cleaned_value
        elif cleaned_key == "class_name":
            query["class_name"] = cleaned_value
        elif cleaned_key == "best_match":
            query["best_match"] = cleaned_value
    return query


def _resolve_browser_binary(binary: str | None) -> str | None:
    candidate = (binary or "").strip()
    if candidate:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
        candidate_path = Path(candidate)
        if candidate_path.is_file():
            return str(candidate_path)

    for path in _browser_installation_candidates():
        if Path(path).is_file():
            return path
    return None


def _browser_installation_candidates() -> list[str]:
    if os.name != "nt":
        return []

    roots = [
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("ProgramFiles"),
        os.environ.get("LocalAppData"),
    ]
    templates = [
        ("Microsoft", "Edge", "Application", "msedge.exe"),
        ("Google", "Chrome", "Application", "chrome.exe"),
        ("Mozilla Firefox", "firefox.exe"),
        ("Chromium", "Application", "chrome.exe"),
    ]

    candidates: list[str] = []
    for root in roots:
        if not root:
            continue
        for parts in templates:
            candidates.append(str(Path(root, *parts)))
    return candidates


_BLOCKER_TITLE_PATTERNS = (
    re.compile(r"\btranslate\b", re.I),
    re.compile(r"\bsave (?:your )?password\b", re.I),
    re.compile(r"\bremember password\b", re.I),
    re.compile(r"\bcookie(?:s)?\b", re.I),
    re.compile(r"\bconsent\b", re.I),
    re.compile(r"\bprivacy choices\b", re.I),
    re.compile(r"\bnotification(?:s)?(?: permission| request| prompt)?\b", re.I),
    re.compile(r"\bupdate available\b", re.I),
    re.compile(r"\buse recommended browser settings\b", re.I),
    re.compile(r"\bsign in prompt\b", re.I),
    re.compile(r"\bnot now\b", re.I),
    re.compile(r"翻译"),
    re.compile(r"保存密码"),
    re.compile(r"cookie", re.I),
    re.compile(r"同意"),
    re.compile(r"隐私"),
    re.compile(r"通知权限"),
    re.compile(r"权限请求"),
)
_BLOCKER_EXCLUDED_TITLE_PATTERNS = (
    re.compile(r"visual studio code", re.I),
    re.compile(r"\bcursor\b", re.I),
    re.compile(r"\bpycharm\b", re.I),
    re.compile(r"\bwebstorm\b", re.I),
    re.compile(r"\bdwm notification window\b", re.I),
)
_BLOCKER_EXCLUDED_CLASS_NAMES = {
    "dwm",
}


def _default_window_hint(app: str) -> str | None:
    normalized = (app or "").strip().lower()
    hints = {
        "browser": "edge",
        "notepad": "notepad",
        "calculator": "calculator",
        "explorer": "file explorer",
    }
    return hints.get(normalized) or normalized or None


def _infer_mock_app_from_title(title: str) -> str | None:
    if "edge" in title or "chrome" in title or "browser" in title:
        return "browser"
    if "notepad" in title:
        return "notepad"
    if "calculator" in title or "calc" in title:
        return "calculator"
    if "explorer" in title or "file" in title:
        return "explorer"
    return None


def _find_existing_browser_window(environment: DesktopEnvironment | None) -> WindowSnapshot | None:
    if environment is None:
        return None
    for query in ("edge", "chrome", "firefox", "msedge.exe", "chrome.exe", "firefox.exe"):
        match = find_window(environment, query)
        if match is not None:
            return match
    return None


def _find_existing_app_window(environment: DesktopEnvironment | None, app: str) -> WindowSnapshot | None:
    if environment is None:
        return None
    normalized = (app or "").strip().lower()
    if normalized == "browser":
        return _find_existing_browser_window(environment)
    queries = []
    default_hint = _default_window_hint(normalized)
    if default_hint:
        queries.append(default_hint)
    queries.append(normalized)
    mapped = normalized.replace(" ", "")
    if mapped and mapped not in queries:
        queries.append(mapped)
    for query in queries:
        match = find_window(environment, query)
        if match is not None:
            return match
    return None


def _is_browser_window(window: WindowSnapshot) -> bool:
    haystacks = [
        (window.title or "").lower(),
        (window.class_name or "").lower(),
        (window.process_name or "").lower(),
    ]
    return any(token in item for item in haystacks for token in ("edge", "chrome", "firefox", "msedge.exe", "chrome.exe", "firefox.exe"))


def _is_protected_window(window: WindowSnapshot) -> bool:
    title = (window.title or "").strip().lower()
    class_name = (window.class_name or "").strip().lower()
    process_name = (window.process_name or "").strip().lower()
    if not title and class_name in {"shell_traywnd", "progman"}:
        return True
    protected_patterns = (
        "visual studio code",
        "cursor",
        "pycharm",
        "webstorm",
        "dwm notification window",
        "task switching",
    )
    if any(pattern in title for pattern in protected_patterns):
        return True
    return process_name in {"code.exe", "cursor.exe"} or class_name in {"dwm"}


def _is_known_blocker_window(window: WindowSnapshot) -> bool:
    environment = DesktopEnvironment(
        platform="windows",
        virtual_bounds=Rect(0, 0, 0, 0),
        visible_windows=[window],
    )
    return bool(_find_known_blockers(environment))


def _find_known_blockers(
    environment: DesktopEnvironment,
    *,
    mode: str = "conservative",
) -> list[WindowSnapshot]:
    blockers: list[WindowSnapshot] = []
    normalized_mode = (mode or "conservative").strip().lower()
    for window in environment.visible_windows:
        title = (window.title or "").strip()
        class_name = (window.class_name or "").strip().lower()
        if not title:
            continue
        if any(pattern.search(title) for pattern in _BLOCKER_EXCLUDED_TITLE_PATTERNS):
            continue
        if class_name in _BLOCKER_EXCLUDED_CLASS_NAMES:
            continue
        if any(pattern.search(title) for pattern in _BLOCKER_TITLE_PATTERNS):
            blockers.append(window)
            continue
        if normalized_mode in {"balanced", "aggressive"}:
            # Reserved for future broader popup handling, but never class-only in conservative mode.
            continue
    return blockers


def _resolve_relative_axis(ratio: float, span: int) -> int:
    if span <= 0:
        return 0
    clamped = min(max(ratio, 0.0), 1.0)
    return max(0, min(span - 1, int(round((span - 1) * clamped))))
