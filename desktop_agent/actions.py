from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


class ActionValidationError(ValueError):
    """Raised when action payload is invalid."""


@dataclass(slots=True)
class Action:
    """Single executable action."""

    type: str
    app: str | None = None
    keys: list[str] = field(default_factory=list)
    key: str | None = None
    text: str | None = None
    selector: str | None = None
    title: str | None = None
    x: int | None = None
    y: int | None = None
    width: int | None = None
    height: int | None = None
    relative_x: float | None = None
    relative_y: float | None = None
    button: str = "left"
    clicks: int = 1
    seconds: float | None = None
    amount: int | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Action":
        if not isinstance(payload, dict):
            raise ActionValidationError("Action must be a dictionary.")
        action_type = str(payload.get("type", "")).strip().lower()
        if not action_type:
            raise ActionValidationError("Action.type is required.")
        action = cls(
            type=action_type,
            app=_optional_str(payload.get("app")),
            keys=_as_key_list(payload.get("keys")),
            key=_optional_str(payload.get("key")),
            text=_optional_str(payload.get("text")),
            selector=_optional_str(payload.get("selector")),
            title=_optional_str(payload.get("title")),
            x=_optional_int(payload.get("x")),
            y=_optional_int(payload.get("y")),
            width=_optional_int(payload.get("width")),
            height=_optional_int(payload.get("height")),
            relative_x=_optional_float(payload.get("relative_x")),
            relative_y=_optional_float(payload.get("relative_y")),
            button=str(payload.get("button", "left")).strip().lower() or "left",
            clicks=int(payload.get("clicks", 1) or 1),
            seconds=_optional_float(payload.get("seconds")),
            amount=_optional_int(payload.get("amount")),
        )
        action.validate()
        return action

    def validate(self) -> None:
        if self.type == "launch_app":
            if not self.app:
                raise ActionValidationError("launch_app requires app.")
        elif self.type == "open_app_if_needed":
            if not self.app:
                raise ActionValidationError("open_app_if_needed requires app.")
        elif self.type in {
            "focus_window",
            "minimize_window",
            "close_window",
            "dismiss_popup",
            "maximize_window",
            "wait_for_window",
        }:
            if not ((self.title or "").strip() or (self.text or "").strip()):
                raise ActionValidationError(f"{self.type} requires title or text.")
        elif self.type == "move_resize_window":
            if not ((self.title or "").strip() or (self.text or "").strip()):
                raise ActionValidationError("move_resize_window requires title or text.")
            if None in {self.x, self.y, self.width, self.height}:
                raise ActionValidationError("move_resize_window requires x, y, width, and height.")
        elif self.type == "relative_click":
            if not ((self.title or "").strip() or (self.text or "").strip()):
                raise ActionValidationError("relative_click requires title or text.")
            if self.relative_x is None or self.relative_y is None:
                raise ActionValidationError("relative_click requires relative_x and relative_y.")
            if self.button not in {"left", "right", "middle"}:
                raise ActionValidationError("relative_click.button must be left/right/middle.")
        elif self.type == "hotkey":
            if not self.keys:
                raise ActionValidationError("hotkey requires keys.")
        elif self.type == "press":
            if not self.key:
                raise ActionValidationError("press requires key.")
        elif self.type == "type":
            if self.text is None:
                raise ActionValidationError("type requires text.")
        elif self.type in {"browser_open", "browser_search"}:
            if not (self.text or "").strip():
                raise ActionValidationError(f"{self.type} requires text.")
        elif self.type == "browser_dom_click":
            if not ((self.text or "").strip() or (self.selector or "").strip()):
                raise ActionValidationError(
                    "browser_dom_click requires text or selector."
                )
        elif self.type == "click":
            if self.x is None or self.y is None:
                raise ActionValidationError("click requires x and y.")
            if self.button not in {"left", "right", "middle"}:
                raise ActionValidationError("click.button must be left/right/middle.")
        elif self.type == "wait":
            if self.seconds is None:
                raise ActionValidationError("wait requires seconds.")
        elif self.type == "scroll":
            if self.amount is None:
                raise ActionValidationError("scroll requires amount.")
        else:
            raise ActionValidationError(f"Unsupported action type: {self.type}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "app": self.app,
            "keys": self.keys,
            "key": self.key,
            "text": self.text,
            "selector": self.selector,
            "title": self.title,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "relative_x": self.relative_x,
            "relative_y": self.relative_y,
            "button": self.button,
            "clicks": self.clicks,
            "seconds": self.seconds,
            "amount": self.amount,
        }


@dataclass(slots=True)
class PlanResult:
    """Planner output for one decision round."""

    status_summary: str
    done: bool
    actions: list[Action] = field(default_factory=list)
    current_focus: str | None = None
    reasoning: str | None = None
    remaining_steps: list[str] = field(default_factory=list)
    raw_response: str | None = None

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        raw_response: str | None = None,
    ) -> "PlanResult":
        if not isinstance(payload, dict):
            raise ActionValidationError("Plan payload must be a dictionary.")
        status_summary = (
            str(payload.get("status_summary", "")).strip()
            or "No status summary provided."
        )
        done = bool(payload.get("done", False))
        raw_actions = payload.get("actions", [])
        if raw_actions is None:
            raw_actions = []
        if not isinstance(raw_actions, list):
            raise ActionValidationError("Plan.actions must be a list.")
        actions = [Action.from_dict(item) for item in raw_actions]
        return cls(
            status_summary=status_summary,
            done=done,
            actions=actions,
            current_focus=_optional_compact_str(payload.get("current_focus")),
            reasoning=_optional_compact_str(payload.get("reasoning")),
            remaining_steps=_as_string_list(payload.get("remaining_steps")),
            raw_response=raw_response,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status_summary": self.status_summary,
            "done": self.done,
            "actions": [action.to_dict() for action in self.actions],
            "current_focus": self.current_focus,
            "reasoning": self.reasoning,
            "remaining_steps": self.remaining_steps,
            "raw_response": self.raw_response,
        }


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _optional_compact_str(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _as_key_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip().lower()] if value.strip() else []
    if isinstance(value, Iterable):
        keys: list[str] = []
        for item in value:
            text = str(item).strip().lower()
            if text:
                keys.append(text)
        return keys
    raise ActionValidationError("keys must be a list[str] or str.")


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = _optional_compact_str(value)
        return [text] if text else []
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
        items: list[str] = []
        for item in value:
            text = _optional_compact_str(item)
            if text:
                items.append(text)
        return items
    raise ActionValidationError("remaining_steps must be a list[str] or str.")
