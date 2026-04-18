from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Any

from desktop_agent.config import AgentConfig
from desktop_agent.windows_env import DesktopEnvironment

SURFACE_KINDS = frozenset(
    {
        "current_user_desktop",
        "managed_aoryn_browser",
        "external_browser_attach",
        "safe_mode_desktop",
    }
)


def normalize_surface_kind(value: str | None, *, default: str = "current_user_desktop") -> str:
    normalized = str(value or "").strip().lower()
    if normalized in SURFACE_KINDS:
        return normalized
    return default


@dataclass(slots=True)
class TargetAnchor:
    kind: str
    value: str
    detail: str | None = None
    confidence: float = 1.0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TargetAnchor":
        return cls(
            kind=str(payload.get("kind", "")).strip() or "text",
            value=str(payload.get("value", "")).strip(),
            detail=_optional_str(payload.get("detail")),
            confidence=float(payload.get("confidence", 1.0) or 1.0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": self.value,
            "detail": self.detail,
            "confidence": self.confidence,
        }


@dataclass(slots=True)
class SurfacePolicy:
    default_surface_policy: str = "current_user_desktop"
    managed_browser_enabled: bool = True
    external_browser_attach_enabled: bool = True
    safe_mode_enabled: bool = False

    @classmethod
    def from_config(cls, config: AgentConfig) -> "SurfacePolicy":
        return cls(
            default_surface_policy=normalize_surface_kind(
                getattr(config, "default_surface_policy", "current_user_desktop")
            ),
            managed_browser_enabled=bool(getattr(config, "managed_browser_enabled", True)),
            external_browser_attach_enabled=bool(getattr(config, "external_browser_attach_enabled", True)),
            safe_mode_enabled=bool(getattr(config, "safe_mode_enabled", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "default_surface_policy": self.default_surface_policy,
            "managed_browser_enabled": self.managed_browser_enabled,
            "external_browser_attach_enabled": self.external_browser_attach_enabled,
            "safe_mode_enabled": self.safe_mode_enabled,
        }


@dataclass(slots=True)
class UserDesktopSession:
    session_id: str
    surface_kind: str = "current_user_desktop"
    foreground_window_handle: int | None = None
    foreground_window_title: str | None = None
    visible_window_titles: list[str] = field(default_factory=list)
    focused_control: str | None = None
    cursor_x: int | None = None
    cursor_y: int | None = None
    last_input_tick_ms: int | None = None
    last_input_age_seconds: float | None = None
    captured_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "surface_kind": self.surface_kind,
            "foreground_window_handle": self.foreground_window_handle,
            "foreground_window_title": self.foreground_window_title,
            "visible_window_titles": list(self.visible_window_titles),
            "focused_control": self.focused_control,
            "cursor_x": self.cursor_x,
            "cursor_y": self.cursor_y,
            "last_input_tick_ms": self.last_input_tick_ms,
            "last_input_age_seconds": self.last_input_age_seconds,
            "captured_at": self.captured_at,
        }


def capture_user_desktop_session(
    *,
    environment: DesktopEnvironment | None,
    focused_control: str | None = None,
) -> UserDesktopSession:
    foreground = environment.foreground_window if environment is not None else None
    cursor_x, cursor_y = _cursor_position()
    last_tick, last_age = _last_input_age()
    visible_titles: list[str] = []
    if environment is not None:
        for window in environment.visible_windows[:10]:
            title = str(window.title or "").strip()
            if title:
                visible_titles.append(title)
    return UserDesktopSession(
        session_id="user-desktop",
        surface_kind="current_user_desktop",
        foreground_window_handle=getattr(foreground, "handle", None),
        foreground_window_title=getattr(foreground, "title", None),
        visible_window_titles=visible_titles,
        focused_control=_optional_str(focused_control),
        cursor_x=cursor_x,
        cursor_y=cursor_y,
        last_input_tick_ms=last_tick,
        last_input_age_seconds=last_age,
    )


def choose_surface_kind(
    *,
    config: AgentConfig,
    active_app: str | None,
    browser_snapshot: dict[str, Any] | None,
    goal_type: str | None,
    subgoal_text: str | None = None,
) -> str:
    policy = SurfacePolicy.from_config(config)
    active = " ".join(str(active_app or "").strip().lower().split())
    goal = " ".join(str(goal_type or "").strip().lower().split())
    task_text = " ".join(str(subgoal_text or "").strip().lower().split())
    browser_like = any(
        token in task_text
        for token in (
            "browser",
            "website",
            "web",
            "search",
            "visit",
            "bookmark",
            "link",
            "login",
            "网页",
            "网站",
            "搜索",
            "访问",
        )
    )
    if policy.managed_browser_enabled and (
        bool(browser_snapshot and str(browser_snapshot.get("managed_by") or "").strip().lower() == "aoryn_browser")
        or browser_like
        or (active == "browser" and (browser_snapshot or goal in {"navigate", "read", "extract", "fill", "confirm"}))
    ):
        return "managed_aoryn_browser"
    if policy.external_browser_attach_enabled and (active == "browser" or browser_snapshot):
        return "external_browser_attach"
    if policy.safe_mode_enabled and policy.default_surface_policy == "safe_mode_desktop":
        return "safe_mode_desktop"
    return "current_user_desktop"


def detect_user_input_preemption(
    *,
    config: AgentConfig,
    execution_context: dict[str, Any] | None,
    session: UserDesktopSession | None,
    threshold_seconds: float = 1.5,
) -> bool:
    if str(getattr(config, "user_input_preemption_policy", "")).strip().lower() != "pause_and_resume":
        return False
    if session is None or session.last_input_age_seconds is None:
        return False
    last_agent_action_at = _optional_float((execution_context or {}).get("last_agent_action_at"))
    if last_agent_action_at is None:
        return False
    if time.time() - last_agent_action_at <= 0.75:
        return False
    return session.last_input_age_seconds <= max(0.25, float(threshold_seconds))


def _cursor_position() -> tuple[int | None, int | None]:
    if os.name != "nt":
        return None, None
    user32 = getattr(ctypes, "windll", None)
    if user32 is None:
        return None, None

    class POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    point = POINT()
    try:
        if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
            return None, None
        return int(point.x), int(point.y)
    except Exception:
        return None, None


def _last_input_age() -> tuple[int | None, float | None]:
    if os.name != "nt":
        return None, None

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    try:
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return None, None
        tick_now = ctypes.windll.kernel32.GetTickCount()
        age_ms = max(0, int(tick_now - int(info.dwTime)))
        return int(info.dwTime), round(age_ms / 1000.0, 3)
    except Exception:
        return None, None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
