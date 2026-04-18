from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from desktop_agent.actions import Action
from desktop_agent.config import AgentConfig


class SafetyError(RuntimeError):
    """Raised when an action violates safety constraints."""


@dataclass(slots=True)
class ActionGuard:
    config: AgentConfig

    def validate(self, action: Action, screen_width: int | None = None, screen_height: int | None = None) -> None:
        if action.type == "launch_app":
            if not _is_allowed_app_intent(action.app, self.config):
                raise SafetyError(f"App is not allowed: {action.app}")
        elif action.type == "open_app_if_needed":
            if not _is_allowed_app_intent(action.app, self.config):
                raise SafetyError(f"App is not allowed: {action.app}")
        elif action.type in {
            "focus_window",
            "minimize_window",
            "close_window",
            "dismiss_popup",
            "maximize_window",
            "wait_for_window",
        }:
            target = (action.title or action.text or "").strip()
            if not target:
                raise SafetyError(f"{action.type} requires a target window title.")
            if len(target) > 160:
                raise SafetyError("Window target exceeds safe length.")
        elif action.type == "move_resize_window":
            target = (action.title or action.text or "").strip()
            if not target:
                raise SafetyError("move_resize_window requires a target window title.")
            if None in {action.x, action.y, action.width, action.height}:
                raise SafetyError("move_resize_window requires x, y, width, and height.")
            if action.width <= 0 or action.height <= 0:
                raise SafetyError("move_resize_window dimensions must be positive.")
        elif action.type == "relative_click":
            target = (action.title or action.text or "").strip()
            if not target:
                raise SafetyError("relative_click requires a target window title.")
            if action.relative_x is None or action.relative_y is None:
                raise SafetyError("relative_click requires relative_x and relative_y.")
            if not (0.0 <= action.relative_x <= 1.0):
                raise SafetyError("relative_click.relative_x must be in [0, 1].")
            if not (0.0 <= action.relative_y <= 1.0):
                raise SafetyError("relative_click.relative_y must be in [0, 1].")
            if action.clicks < 1 or action.clicks > 3:
                raise SafetyError("clicks must be in [1, 3].")
        elif action.type == "hotkey":
            combo = tuple(key.lower() for key in action.keys)
            if combo not in self.config.hotkey_set():
                raise SafetyError(f"Hotkey is not allowed: {combo}")
        elif action.type in {"clipboard_copy", "clipboard_paste"}:
            return
        elif action.type == "press":
            if (action.key or "").lower() not in {
                "enter",
                "tab",
                "esc",
                "backspace",
                "space",
                "up",
                "down",
                "left",
                "right",
            }:
                raise SafetyError(f"Key is not allowed: {action.key}")
        elif action.type == "drag":
            if None in {action.x, action.y, action.end_x, action.end_y}:
                raise SafetyError("drag requires x, y, end_x, and end_y.")
            if screen_width is not None and not (0 <= int(action.x or -1) < screen_width):
                raise SafetyError("drag.x is out of bounds.")
            if screen_width is not None and not (0 <= int(action.end_x or -1) < screen_width):
                raise SafetyError("drag.end_x is out of bounds.")
            if screen_height is not None and not (0 <= int(action.y or -1) < screen_height):
                raise SafetyError("drag.y is out of bounds.")
            if screen_height is not None and not (0 <= int(action.end_y or -1) < screen_height):
                raise SafetyError("drag.end_y is out of bounds.")
        elif action.type == "type":
            if action.text is None:
                raise SafetyError("Missing text payload.")
            if len(action.text) > self.config.max_text_length:
                raise SafetyError("Typed text exceeds max_text_length.")
            lowered = action.text.lower()
            risky_keywords = ["format c:", "powershell", "cmd /c", "del /f", "rm -rf"]
            if any(keyword in lowered for keyword in risky_keywords):
                raise SafetyError("Text contains risky command-like content.")
            if _looks_like_action_literal(action.text):
                raise SafetyError("Text looks like an action literal instead of user content.")
        elif action.type == "browser_search":
            query = (action.text or "").strip()
            if not query:
                raise SafetyError("browser_search requires text.")
            if len(query) > self.config.max_text_length:
                raise SafetyError("Search query exceeds max_text_length.")
        elif action.type == "browser_open":
            target = (action.text or "").strip()
            if not target:
                raise SafetyError("browser_open requires text.")
            if len(target) > self.config.max_browser_target_length:
                raise SafetyError("Browser target exceeds max_browser_target_length.")
            if not _is_allowed_browser_target(target, self.config.allowed_browser_schemes):
                raise SafetyError(f"Browser target is not allowed: {target}")
        elif action.type == "browser_dom_click":
            text = (action.text or "").strip()
            selector = (action.selector or "").strip()
            if not text and not selector:
                raise SafetyError("browser_dom_click requires text or selector.")
            if len(text) > self.config.max_text_length:
                raise SafetyError("DOM click label exceeds max_text_length.")
            if len(selector) > 240:
                raise SafetyError("DOM selector exceeds safe length.")
            if selector and not _looks_like_safe_selector(selector):
                raise SafetyError(f"Unsafe DOM selector: {selector}")
        elif action.type in {"browser_dom_fill", "browser_dom_select"}:
            selector = (action.selector or "").strip()
            if not selector:
                raise SafetyError(f"{action.type} requires a selector.")
            if action.text is None:
                raise SafetyError(f"{action.type} requires text.")
            if len(action.text) > self.config.max_text_length:
                raise SafetyError("DOM input exceeds max_text_length.")
            if not _looks_like_safe_selector(selector):
                raise SafetyError(f"Unsafe DOM selector: {selector}")
        elif action.type in {"browser_dom_wait", "browser_dom_extract"}:
            selector = (action.selector or "").strip()
            text = (action.text or "").strip()
            if not selector and not text:
                raise SafetyError(f"{action.type} requires text or selector.")
            if selector and not _looks_like_safe_selector(selector):
                raise SafetyError(f"Unsafe DOM selector: {selector}")
            if action.seconds is not None and action.seconds > self.config.max_wait_seconds:
                raise SafetyError("browser_dom_wait.seconds exceeds limit.")
        elif action.type in {"uia_invoke", "uia_set_value", "uia_select", "uia_expand"}:
            selector = (action.selector or "").strip()
            text = (action.text or "").strip()
            if not selector and not text:
                raise SafetyError(f"{action.type} requires text or selector.")
            if len(selector) > 240:
                raise SafetyError("UIA selector exceeds safe length.")
            if action.type in {"uia_set_value", "uia_select"} and len(text) > self.config.max_text_length:
                raise SafetyError("UIA text exceeds max_text_length.")
        elif action.type == "shell_recipe_request":
            recipe = (action.recipe or "").strip()
            if not recipe:
                raise SafetyError("shell_recipe_request requires recipe.")
            if recipe not in self.config.shell_recipe_registry:
                raise SafetyError(f"Shell recipe is not allowed: {recipe}")
        elif action.type == "click":
            if action.clicks < 1 or action.clicks > 3:
                raise SafetyError("clicks must be in [1, 3].")
            if screen_width is not None and not (0 <= int(action.x or -1) < screen_width):
                raise SafetyError("click.x is out of bounds.")
            if screen_height is not None and not (0 <= int(action.y or -1) < screen_height):
                raise SafetyError("click.y is out of bounds.")
        elif action.type == "wait":
            if action.seconds is None or action.seconds < 0 or action.seconds > self.config.max_wait_seconds:
                raise SafetyError("wait.seconds exceeds limit.")
        elif action.type == "scroll":
            if action.amount is None or abs(action.amount) > self.config.max_scroll_amount:
                raise SafetyError("scroll.amount exceeds limit.")
        else:
            raise SafetyError(f"Unknown action type: {action.type}")

    def validate_many(
        self,
        actions: list[Action],
        screen_width: int | None = None,
        screen_height: int | None = None,
    ) -> list[Action]:
        for action in actions:
            self.validate(action, screen_width=screen_width, screen_height=screen_height)
        return actions


def _is_allowed_browser_target(target: str, allowed_schemes: list[str]) -> bool:
    parsed = urlparse(target)
    if parsed.scheme:
        return parsed.scheme.lower() in {scheme.lower() for scheme in allowed_schemes} and bool(parsed.netloc)
    return bool(
        re.match(
            r"^(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/[^\s]*)?$",
            target,
            re.I,
        )
    )


def _looks_like_action_literal(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if re.search(
        r"\b(?:launch_app|open_app_if_needed|browser_open|browser_search|focus_window|minimize_window|close_window|dismiss_popup|maximize_window|move_resize_window|wait_for_window|relative_click|hotkey|press|click|scroll|wait)\s*\(",
        stripped,
        re.I,
    ):
        return True
    return bool(re.search(r'"type"\s*:\s*"', stripped, re.I))


def _looks_like_safe_selector(selector: str) -> bool:
    lowered = selector.lower()
    if any(token in lowered for token in ("javascript:", "<", ">", "{", "}")):
        return False
    return bool(re.match(r"^[#.\[\]\w\s:=\-\*'\"(),>+~]+$", selector))


def _is_allowed_app_intent(app: str | None, config: AgentConfig) -> bool:
    cleaned = (app or "").strip().lower()
    if not cleaned:
        return False
    if cleaned in {item.lower() for item in config.allowed_apps}:
        return True
    if not config.generic_app_launch_enabled:
        return False
    return _looks_like_safe_app_intent(cleaned, config)


def _looks_like_safe_app_intent(app: str, config: AgentConfig) -> bool:
    blocked_terms = {item.lower() for item in config.blocked_app_launch_terms}
    normalized = re.sub(r"[^a-z0-9._ -]+", " ", app.lower())
    tokens = [token for token in re.split(r"[\s._-]+", normalized) if token]
    if any(token in blocked_terms for token in tokens):
        return False
    if any(term in normalized for term in blocked_terms):
        return False
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9._ -]{0,79}", app))
