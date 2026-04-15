import pytest

from desktop_agent.actions import Action
from desktop_agent.config import AgentConfig
from desktop_agent.safety import ActionGuard, SafetyError


def test_guard_rejects_hotkey_not_in_whitelist():
    guard = ActionGuard(AgentConfig())
    action = Action.from_dict({"type": "hotkey", "keys": ["ctrl", "shift", "esc"]})
    with pytest.raises(SafetyError):
        guard.validate(action)


def test_guard_rejects_out_of_bounds_click():
    guard = ActionGuard(AgentConfig())
    action = Action.from_dict({"type": "click", "x": 4000, "y": 10, "button": "left"})
    with pytest.raises(SafetyError):
        guard.validate(action, screen_width=1920, screen_height=1080)


def test_guard_rejects_risky_text():
    guard = ActionGuard(AgentConfig())
    action = Action.from_dict({"type": "type", "text": "powershell remove-item *"})
    with pytest.raises(SafetyError):
        guard.validate(action)


def test_guard_rejects_action_literal_text():
    guard = ActionGuard(AgentConfig())
    action = Action.from_dict({"type": "type", "text": "launch_app(browser)"})
    with pytest.raises(SafetyError):
        guard.validate(action)


def test_guard_rejects_disallowed_browser_scheme():
    guard = ActionGuard(AgentConfig())
    action = Action.from_dict({"type": "browser_open", "text": "file:///C:/Windows/System32"})
    with pytest.raises(SafetyError):
        guard.validate(action)


def test_guard_accepts_safe_dom_click_action():
    guard = ActionGuard(AgentConfig())
    action = Action.from_dict({"type": "browser_dom_click", "text": "Reject all"})

    guard.validate(action)


def test_guard_rejects_unsafe_dom_selector():
    guard = ActionGuard(AgentConfig())
    action = Action.from_dict({"type": "browser_dom_click", "selector": "javascript:alert(1)"})
    with pytest.raises(SafetyError):
        guard.validate(action)


def test_guard_accepts_focus_window_action():
    guard = ActionGuard(AgentConfig())
    action = Action.from_dict({"type": "focus_window", "title": "Calculator"})

    guard.validate(action)


def test_guard_accepts_minimize_window_action():
    guard = ActionGuard(AgentConfig())
    action = Action.from_dict({"type": "minimize_window", "title": "Chat"})

    guard.validate(action)


def test_guard_rejects_invalid_move_resize_dimensions():
    guard = ActionGuard(AgentConfig())
    action = Action.from_dict(
        {"type": "move_resize_window", "title": "Notepad", "x": 0, "y": 0, "width": 0, "height": 500}
    )
    with pytest.raises(SafetyError):
        guard.validate(action)


def test_guard_accepts_relative_click_action():
    guard = ActionGuard(AgentConfig())
    action = Action.from_dict(
        {"type": "relative_click", "title": "Calculator", "relative_x": 0.5, "relative_y": 0.4}
    )

    guard.validate(action)


def test_guard_rejects_out_of_range_relative_click():
    guard = ActionGuard(AgentConfig())
    action = Action.from_dict(
        {"type": "relative_click", "title": "Calculator", "relative_x": 1.2, "relative_y": 0.4}
    )
    with pytest.raises(SafetyError):
        guard.validate(action)


def test_guard_accepts_safe_generic_app_intent():
    guard = ActionGuard(AgentConfig())
    action = Action.from_dict({"type": "open_app_if_needed", "app": "snipping tool"})

    guard.validate(action)


def test_guard_rejects_blocked_generic_app_intent():
    guard = ActionGuard(AgentConfig())
    action = Action.from_dict({"type": "open_app_if_needed", "app": "powershell"})

    with pytest.raises(SafetyError):
        guard.validate(action)
