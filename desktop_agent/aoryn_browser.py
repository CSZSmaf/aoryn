from __future__ import annotations

import argparse
import html
import json
import os
import socket
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, quote_plus, urlparse

from desktop_agent.browser_chrome import BrowserTabStrip, BrowserTopChrome
from desktop_agent.browser_icons import browser_chrome_icon, browser_window_icon
from desktop_agent.browser_internal_pages import build_internal_page_html
from desktop_agent.browser_runtime import BrowserObservation, BrowserRuntimeError
from desktop_agent.browser_theme import BROWSER_CHROME_STYLESHEET
from desktop_agent.controller import discover_config_path, load_agent_config
from desktop_agent.runtime_paths import local_data_root, runtime_preferences_path_for
from desktop_agent.version import APP_ID, APP_NAME

DEFAULT_BROWSER_HOMEPAGE = "aoryn://home"
DEFAULT_BROWSER_SEARCH_URL = "https://www.google.com/search?q={query}"
INTERNAL_PAGE_TITLES = {
    "home": "Home",
    "runtime": "Runtime Overview",
    "setup": "Browser Setup",
    "history": "History",
    "bookmarks": "Bookmarks",
    "downloads": "Downloads",
    "permissions": "Review Queue",
}
SESSION_STATE_KEYS = (
    "bookmarks",
    "downloads",
    "history",
    "windows",
    "annotations",
    "permissions",
    "permission_requests",
    "handoffs",
    "auth_pause_reason",
)

try:  # pragma: no cover - GUI runtime availability depends on environment
    from PySide6.QtCore import QEventLoop, QObject, QSize, Qt, QTimer, QUrl, Signal, Slot
    from PySide6.QtGui import QAction, QCloseEvent, QColor, QIcon
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QDockWidget,
        QFormLayout,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMenu,
        QPushButton,
        QSizePolicy,
        QTabBar,
        QTabWidget,
        QTextEdit,
        QToolBar,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )
    from PySide6.QtWebEngineCore import QWebEngineDownloadRequest, QWebEnginePage, QWebEngineProfile
    from PySide6.QtWebEngineWidgets import QWebEngineView

    _QT_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - GUI runtime availability depends on environment
    QApplication = None  # type: ignore[assignment]
    QCheckBox = object  # type: ignore[assignment]
    QCloseEvent = object  # type: ignore[assignment]
    QComboBox = object  # type: ignore[assignment]
    QColor = object  # type: ignore[assignment]
    QDialog = object  # type: ignore[assignment]
    QDialogButtonBox = object  # type: ignore[assignment]
    QDockWidget = object  # type: ignore[assignment]
    QEventLoop = object  # type: ignore[assignment]
    QFormLayout = object  # type: ignore[assignment]
    QFrame = object  # type: ignore[assignment]
    QIcon = object  # type: ignore[assignment]
    QHBoxLayout = object  # type: ignore[assignment]
    QLabel = object  # type: ignore[assignment]
    QLineEdit = object  # type: ignore[assignment]
    QMainWindow = object  # type: ignore[assignment]
    QMenu = object  # type: ignore[assignment]
    QObject = object  # type: ignore[assignment]
    QPushButton = object  # type: ignore[assignment]
    QAction = object  # type: ignore[assignment]
    QSize = object  # type: ignore[assignment]
    QSizePolicy = object  # type: ignore[assignment]
    QTabBar = object  # type: ignore[assignment]
    QTabWidget = object  # type: ignore[assignment]
    QTextEdit = object  # type: ignore[assignment]
    QToolBar = object  # type: ignore[assignment]
    QToolButton = object  # type: ignore[assignment]
    QTimer = object  # type: ignore[assignment]
    Qt = object  # type: ignore[assignment]
    QUrl = object  # type: ignore[assignment]
    QVBoxLayout = object  # type: ignore[assignment]
    QWidget = object  # type: ignore[assignment]
    QWebEngineDownloadRequest = object  # type: ignore[assignment]
    QWebEnginePage = object  # type: ignore[assignment]
    QWebEngineProfile = object  # type: ignore[assignment]
    QWebEngineView = object  # type: ignore[assignment]
    Signal = object  # type: ignore[assignment]
    Slot = object  # type: ignore[assignment]
    _QT_IMPORT_ERROR = exc


def _empty_browser_state() -> dict[str, Any]:
    return {
        "bookmarks": [],
        "downloads": [],
        "history": [],
        "windows": [],
        "annotations": [],
        "permissions": [],
        "permission_requests": [],
        "handoffs": [],
        "auth_pause_reason": None,
    }


def browser_session_path(profile_root: Path) -> Path:
    return profile_root / "session.json"


def _internal_browser_page_name(target: str | None) -> str | None:
    if not target:
        return None
    text = str(target).strip()
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme.lower() != "aoryn":
        return None
    page = (parsed.netloc or parsed.path.lstrip("/")).strip().lower()
    return page or "home"


def is_internal_browser_url(target: str | None) -> bool:
    return _internal_browser_page_name(target) in INTERNAL_PAGE_TITLES


def _looks_like_browser_host(value: str) -> bool:
    token = _optional_str(value)
    if not token:
        return False
    first = token.split("/", 1)[0]
    if first.lower().startswith("localhost"):
        return True
    host, _, port = first.partition(":")
    if port and not port.isdigit():
        return False
    if host.replace(".", "").isdigit():
        return True
    return "." in host


def normalize_browser_target(
    target: str | None,
    *,
    homepage: str = DEFAULT_BROWSER_HOMEPAGE,
    search_url: str = DEFAULT_BROWSER_SEARCH_URL,
) -> str:
    text = str(target or "").strip()
    if not text:
        return homepage
    internal_page = _internal_browser_page_name(text)
    if internal_page in INTERNAL_PAGE_TITLES:
        return f"aoryn://{internal_page}"
    if _looks_like_browser_host(text):
        return f"https://{text}"
    parsed = urlparse(text)
    if parsed.scheme:
        return text
    return search_url.format(query=quote_plus(text))


def _collapse_browser_text(value: Any, *, limit: int = 2400) -> str:
    text = " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def build_browser_digest(snapshot: dict[str, Any] | None, *, mode: str = "summary") -> str:
    payload = snapshot or {}
    title = _optional_str(payload.get("title")) or "Current page"
    url = _optional_str(payload.get("url")) or "No page is open yet."
    text = _collapse_browser_text(payload.get("text"), limit=2800)
    sentences = [segment.strip() for segment in text.replace("!", ".").replace("?", ".").split(".") if segment.strip()]
    highlights = sentences[:3] if sentences else []
    if mode == "insights":
        lines = [
            f"{title}",
            url,
            "",
            "What stands out",
        ]
        if highlights:
            lines.extend(f"- {item}" for item in highlights)
        else:
            lines.append("- Open a page to generate quick insights.")
        lines.extend(
            [
                "",
                "Next actions",
                "- Ask Aoryn to summarize this page",
                "- Extract decisions or deadlines",
                "- Continue in the desktop app for agent execution",
            ]
        )
        return "\n".join(lines)
    if mode == "handoff":
        return "\n".join(
            [
                "Ready for agent handoff",
                title,
                url,
                "",
                _collapse_browser_text(text or "Open a page, then ask Aoryn to continue with full agent mode.", limit=420),
            ]
        )
    lines = [
        f"{title}",
        url,
        "",
        "Quick summary",
    ]
    if highlights:
        lines.extend(f"- {item}" for item in highlights)
    else:
        lines.append("- Open a page to generate a quick summary.")
    if text and len(sentences) > 3:
        lines.extend(["", _collapse_browser_text(" ".join(sentences[3:]), limit=500)])
    return "\n".join(lines)


def build_browser_assistant_user_message(snapshot: dict[str, Any] | None, prompt: str | None) -> str:
    payload = snapshot or {}
    title = _optional_str(payload.get("title")) or "Unknown page"
    url = _optional_str(payload.get("url")) or "No page is open."
    page_text = _collapse_browser_text(payload.get("text"), limit=5200)
    request = _optional_str(prompt) or "Summarize this page and suggest the next useful step."
    context_block = page_text or "No visible page text was captured."
    return "\n".join(
        [
            "You are helping inside Aoryn Browser.",
            "Use the visible page context below as the primary source of truth.",
            "If the page does not contain enough information, say so clearly.",
            "Answer in the same language as the user's request when that is clear.",
            "",
            f"Page title: {title}",
            f"Page URL: {url}",
            "Visible page text:",
            context_block,
            "",
            "User request:",
            request,
        ]
    )


def build_browser_ai_setup_summary(
    config: Any,
    *,
    provider_options: list[dict[str, Any]] | None = None,
    browser_channel_options: list[dict[str, Any]] | None = None,
    config_path: Path | None = None,
    runtime_preferences_path: Path | None = None,
) -> dict[str, Any]:
    provider_value = _optional_str(getattr(config, "model_provider", None)) or "lmstudio_local"
    provider_label = provider_value
    provider_requires_api_key = False
    for item in provider_options or []:
        if _optional_str(item.get("value")) == provider_value:
            provider_label = _optional_str(item.get("label")) or provider_value
            provider_requires_api_key = bool(item.get("api_key_required"))
            break

    model_name = _optional_str(getattr(config, "model_name", None)) or "auto"
    model_display = "Auto" if model_name.lower() in {"auto", "first"} else model_name
    base_url = _optional_str(getattr(config, "model_base_url", None))
    api_key_configured = bool(_optional_str(getattr(config, "model_api_key", None)))

    browser_channel = _optional_str(getattr(config, "browser_channel", None)) or ""
    browser_channel_label = "System default"
    for item in browser_channel_options or []:
        if _optional_str(item.get("value")) == browser_channel:
            browser_channel_label = _optional_str(item.get("label")) or browser_channel_label
            break
    if browser_channel and browser_channel_label == "System default":
        browser_channel_label = browser_channel

    browser_path = _optional_str(getattr(config, "browser_executable_path", None))
    browser_headless = bool(getattr(config, "browser_headless", False))

    status = "Ready"
    detail = f"{provider_label} will answer questions about the current page."
    if not base_url:
        status = "Setup needed"
        detail = "Add a Base URL before using the in-browser assistant."
    elif provider_requires_api_key and not api_key_configured:
        status = "API key needed"
        detail = f"{provider_label} requires an API key before the browser assistant can answer."

    badge_text = f"{provider_label} | {model_display}" if status == "Ready" else status
    return {
        "status": status,
        "detail": detail,
        "badge_text": badge_text,
        "provider_value": provider_value,
        "provider_label": provider_label,
        "model_name": model_name,
        "model_display": model_display,
        "base_url": base_url or "",
        "api_key_configured": api_key_configured,
        "browser_channel": browser_channel,
        "browser_channel_label": browser_channel_label,
        "browser_executable_path": browser_path or "",
        "browser_headless": browser_headless,
        "config_path": str(config_path) if config_path else None,
        "runtime_preferences_path": str(runtime_preferences_path) if runtime_preferences_path else None,
    }


def _browser_provider_options(config: Any) -> list[dict[str, Any]]:
    return [
        {
            "value": "lmstudio_local",
            "label": "Local LM Studio",
            "description": "Use your local LM Studio OpenAI-compatible server.",
            "base_url": "http://127.0.0.1:1234/v1",
            "api_key_required": False,
            "auto_discover": True,
            "supports_model_refresh": True,
            "supports_model_load": True,
        },
        {
            "value": "openai_api",
            "label": "OpenAI API",
            "description": "Use OpenAI's hosted API.",
            "base_url": "https://api.openai.com/v1",
            "api_key_required": True,
            "auto_discover": False,
            "supports_model_refresh": True,
            "supports_model_load": False,
        },
        {
            "value": "openai_compatible",
            "label": "OpenAI-Compatible API",
            "description": "Use a third-party API that follows the OpenAI chat format.",
            "base_url": "https://api.openai.com/v1",
            "api_key_required": True,
            "auto_discover": False,
            "supports_model_refresh": True,
            "supports_model_load": False,
        },
        {
            "value": "custom",
            "label": "Custom Provider",
            "description": "Bring your own endpoint and request settings.",
            "base_url": _optional_str(getattr(config, "model_base_url", None)) or "",
            "api_key_required": False,
            "auto_discover": bool(getattr(config, "model_auto_discover", False)),
            "supports_model_refresh": True,
            "supports_model_load": False,
        },
    ]


def _browser_channel_options() -> list[dict[str, Any]]:
    return [
        {"value": "", "label": "System default"},
        {"value": "msedge", "label": "Microsoft Edge"},
        {"value": "chrome", "label": "Google Chrome"},
        {"value": "firefox", "label": "Mozilla Firefox"},
    ]


def _load_browser_runtime_preferences(path: Path) -> dict[str, Any]:
    defaults = {
        "config_overrides": {},
        "ui_preferences": {"onboarding_completed": False},
        "updated_at": None,
    }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return defaults
    if not isinstance(payload, dict):
        return defaults
    config_overrides = payload.get("config_overrides")
    ui_preferences = payload.get("ui_preferences")
    return {
        "config_overrides": dict(config_overrides) if isinstance(config_overrides, dict) else {},
        "ui_preferences": dict(ui_preferences) if isinstance(ui_preferences, dict) else {"onboarding_completed": False},
        "updated_at": payload.get("updated_at"),
    }


def build_browser_assistant_setup_snapshot(config_path: Path | None) -> dict[str, Any]:
    resolved_config_path = discover_config_path(config_path)
    runtime_preferences_path = runtime_preferences_path_for(resolved_config_path)
    runtime_snapshot = _load_browser_runtime_preferences(runtime_preferences_path)
    runtime_overrides = runtime_snapshot.get("config_overrides") if isinstance(runtime_snapshot, dict) else {}
    config = load_agent_config(
        resolved_config_path,
        config_overrides=runtime_overrides if isinstance(runtime_overrides, dict) else {},
    )
    provider_options = _browser_provider_options(config)
    browser_channel_options = _browser_channel_options()
    summary = build_browser_ai_setup_summary(
        config,
        provider_options=provider_options,
        browser_channel_options=browser_channel_options,
        config_path=resolved_config_path,
        runtime_preferences_path=runtime_preferences_path,
    )
    return {
        "summary": summary,
        "config_path": str(resolved_config_path) if resolved_config_path else None,
        "runtime_preferences_path": str(runtime_preferences_path),
        "providers": provider_options,
        "browser_channels": browser_channel_options,
        "effective": {
            "model_provider": config.model_provider,
            "model_base_url": config.model_base_url,
            "model_name": config.model_name,
            "model_api_key": config.model_api_key or "",
            "model_auto_discover": config.model_auto_discover,
            "browser_channel": config.browser_channel or "",
            "browser_executable_path": config.browser_executable_path or "",
            "browser_headless": config.browser_headless,
        },
    }


def build_browser_service_summary(
    *,
    base_url: str,
    transport: str,
    status: str,
    window_count: int,
    tab_count: int,
    active_title: str | None = None,
    active_url: str | None = None,
    pending_permissions: int = 0,
    handoff_count: int = 0,
    annotation_count: int = 0,
    auth_pause_reason: str | None = None,
) -> dict[str, Any]:
    normalized_status = _optional_str(status) or "ready"
    badge_text = "Service ready" if normalized_status == "ready" else normalized_status.replace("_", " ").title()
    detail = (
        "Aoryn can inspect, navigate, query DOM, and perform browser actions through the managed runtime."
        if normalized_status == "ready"
        else f"Runtime state: {normalized_status.replace('_', ' ')}."
    )
    if auth_pause_reason:
        detail = f"{detail} Human review is blocking progress: {auth_pause_reason}"
    return {
        "badge_text": badge_text,
        "detail": detail,
        "runtime_role": "managed_browser_service",
        "transport": _optional_str(transport) or "local_http",
        "base_url": _optional_str(base_url) or "http://127.0.0.1",
        "status": normalized_status,
        "window_count": max(0, int(window_count or 0)),
        "tab_count": max(0, int(tab_count or 0)),
        "active_title": _optional_str(active_title),
        "active_url": _optional_str(active_url),
        "pending_permissions": max(0, int(pending_permissions or 0)),
        "handoff_count": max(0, int(handoff_count or 0)),
        "annotation_count": max(0, int(annotation_count or 0)),
        "auth_pause_reason": _optional_str(auth_pause_reason),
        "routes": [
            {"label": "Status", "path": "/status"},
            {"label": "Snapshot", "path": "/snapshot"},
            {"label": "DOM query", "path": "/query_dom"},
            {"label": "Action", "path": "/perform_action"},
            {"label": "Wait", "path": "/wait_for_state"},
            {"label": "Session", "path": "/get_session_state"},
        ],
    }


def build_browser_http_error_payload(exc: Exception) -> dict[str, Any]:
    message = _optional_str(str(exc)) or "Browser request failed."
    if isinstance(exc, BrowserRuntimeError):
        return {"ok": False, "error": message, "error_type": "runtime"}
    return {"ok": False, "error": message, "error_type": "server"}


def write_browser_json_response(handler: Any, payload: dict[str, Any], *, status: int = HTTPStatus.OK) -> bool:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(raw)))
        handler.end_headers()
        handler.wfile.write(raw)
        return True
    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError):
        return False


def load_browser_state(profile_root: Path) -> dict[str, Any]:
    path = browser_session_path(profile_root)
    if not path.exists():
        return _empty_browser_state()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _empty_browser_state()
    if not isinstance(payload, dict):
        return _empty_browser_state()
    state = _empty_browser_state()
    for key in SESSION_STATE_KEYS:
        value = payload.get(key)
        if key == "auth_pause_reason":
            state[key] = _optional_str(value)
            continue
        if isinstance(value, list):
            state[key] = [dict(item) for item in value if isinstance(item, dict)]
    return state


def save_browser_state(profile_root: Path, state: dict[str, Any]) -> Path:
    profile_root.mkdir(parents=True, exist_ok=True)
    path = browser_session_path(profile_root)
    payload = _empty_browser_state()
    for key in SESSION_STATE_KEYS:
        if key == "auth_pause_reason":
            payload[key] = _optional_str(state.get(key))
            continue
        payload[key] = [dict(item) for item in state.get(key, []) or [] if isinstance(item, dict)]
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)
    return path


def normalize_annotation_entries(entries: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    if not isinstance(entries, list):
        return normalized
    for item in entries:
        if not isinstance(item, dict):
            continue
        tab_id = _optional_str(item.get("tab_id"))
        annotation_id = _optional_str(item.get("annotation_id"))
        selector = _optional_str(item.get("selector"))
        if not tab_id or not annotation_id or not selector:
            continue
        normalized.append(
            {
                "tab_id": tab_id,
                "annotation_id": annotation_id,
                "selector": selector,
                "label": _optional_str(item.get("label")) or annotation_id,
                "created_at": float(item.get("created_at", time.time()) or time.time()),
            }
        )
    return normalized


def normalize_permission_entries(entries: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    if not isinstance(entries, list):
        return normalized
    for item in entries:
        if not isinstance(item, dict):
            continue
        origin = _optional_str(item.get("origin"))
        feature = _optional_str(item.get("feature"))
        decision = (_optional_str(item.get("decision")) or "prompt").lower()
        if not origin or not feature:
            continue
        normalized.append(
            {
                "origin": origin,
                "feature": feature,
                "decision": decision,
                "updated_at": float(item.get("updated_at", time.time()) or time.time()),
            }
        )
    return normalized


def normalize_permission_request_entries(entries: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    if not isinstance(entries, list):
        return normalized
    for item in entries:
        if not isinstance(item, dict):
            continue
        request_id = _optional_str(item.get("request_id"))
        origin = _optional_str(item.get("origin"))
        feature = _optional_str(item.get("feature"))
        if not request_id or not origin or not feature:
            continue
        normalized.append(
            {
                "request_id": request_id,
                "origin": origin,
                "feature": feature,
                "tab_id": _optional_str(item.get("tab_id")),
                "requested_at": float(item.get("requested_at", time.time()) or time.time()),
            }
        )
    return normalized


def normalize_handoff_entries(entries: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    if not isinstance(entries, list):
        return normalized
    for item in entries:
        if not isinstance(item, dict):
            continue
        kind = _optional_str(item.get("kind"))
        reason = _optional_str(item.get("reason"))
        if not kind or not reason:
            continue
        normalized.append(
            {
                "kind": kind,
                "reason": reason,
                "url": _optional_str(item.get("url")),
                "title": _optional_str(item.get("title")),
                "created_at": float(item.get("created_at", time.time()) or time.time()),
            }
        )
    return normalized


def detect_browser_handoff_reason(*, url: str | None, title: str | None, text: str | None = None) -> str | None:
    haystack = " ".join(
        part.lower()
        for part in (
            _optional_str(url),
            _optional_str(title),
            _optional_str(text),
        )
        if part
    )
    if not haystack:
        return None
    auth_terms = {
        "captcha": "CAPTCHA or bot verification requires human completion.",
        "cloudflare": "Cloudflare verification requires human completion.",
        "mfa": "Multi-factor authentication requires human completion.",
        "2fa": "Two-factor authentication requires human completion.",
        "passkey": "Passkey confirmation requires human completion.",
        "verify": "Verification step requires human confirmation.",
        "sign in": "Sign-in flow requires human review.",
        "login": "Login flow requires human review.",
        "authenticate": "Authentication step requires human review.",
    }
    for needle, reason in auth_terms.items():
        if needle in haystack:
            return reason
    return None


def normalize_browser_upload_paths(value: Any) -> list[str]:
    candidates: list[str] = []
    if isinstance(value, (list, tuple)):
        for item in value:
            text = _optional_str(item)
            if text:
                candidates.append(text)
    else:
        text = _optional_str(value)
        if text:
            candidates.append(text)
    normalized: list[str] = []
    for item in candidates:
        path = Path(item).expanduser()
        if path.exists():
            normalized.append(str(path.resolve()))
    return normalized


def normalize_download_state_name(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "requested"
    for source, target in (
        ("InProgress", " In Progress"),
        ("Completed", " Completed"),
        ("Cancelled", " Cancelled"),
        ("Interrupted", " Interrupted"),
        ("Requested", " Requested"),
    ):
        text = text.replace(source, target)
    text = text.replace("Download", "").replace("State", "").replace("_", " ").strip().lower()
    mapping = {
        "download requested": "requested",
        "requested": "requested",
        "download in progress": "in_progress",
        "in progress": "in_progress",
        "download completed": "completed",
        "completed": "completed",
        "download cancelled": "cancelled",
        "cancelled": "cancelled",
        "download interrupted": "failed",
        "interrupted": "failed",
    }
    return mapping.get(text, text.replace(" ", "_"))


def normalize_permission_feature_name(value: Any) -> str:
    raw = getattr(value, "name", None) or str(value or "")
    text = raw.replace("Feature.", "").replace("QWebEnginePage.", "").replace("_", " ").strip().lower()
    return text or "permission"


def normalize_permission_decision(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    mapping = {
        "allow": "allow",
        "remember_allow": "allow",
        "grant": "allow",
        "deny": "deny",
        "remember_deny": "deny",
        "block": "deny",
        "prompt": "prompt",
        "ask": "prompt",
        "ask_every_time": "prompt",
    }
    return mapping.get(text, "prompt")


def build_annotation_overlay_script(*, selector: str | None, label: str | None, annotation_id: str) -> str:
    return (
        """
        (() => {
          const selector = %SELECTOR%;
          const label = %LABEL%;
          const annotationId = %ANNOTATION_ID%;
          const node = selector ? document.querySelector(selector) : document.body;
          if (!node) {
            return { annotated: false, annotation_id: annotationId };
          }
          const previous = document.querySelector(`[data-aoryn-annotation-badge="${annotationId}"]`);
          if (previous) {
            previous.remove();
          }
          node.setAttribute('data-aoryn-annotation-id', annotationId);
          node.setAttribute('data-aoryn-annotation-label', label || annotationId);
          node.style.outline = '3px solid #0f8f73';
          node.style.outlineOffset = '2px';

          const badge = document.createElement('div');
          badge.setAttribute('data-aoryn-annotation-badge', annotationId);
          badge.textContent = label || annotationId;
          badge.style.position = 'absolute';
          badge.style.zIndex = '2147483647';
          badge.style.pointerEvents = 'none';
          badge.style.padding = '4px 8px';
          badge.style.borderRadius = '999px';
          badge.style.background = '#0f8f73';
          badge.style.color = '#ffffff';
          badge.style.font = '600 12px/1.2 Segoe UI, sans-serif';
          badge.style.boxShadow = '0 8px 20px rgba(15, 143, 115, 0.28)';

          const rect = node.getBoundingClientRect();
          const top = Math.max(window.scrollY + rect.top - 30, window.scrollY + 8);
          const left = Math.max(window.scrollX + rect.left, window.scrollX + 8);
          badge.style.top = `${top}px`;
          badge.style.left = `${left}px`;
          document.body.appendChild(badge);

          return {
            annotated: true,
            annotation_id: annotationId,
            label: label || annotationId,
            text: String(node.innerText || node.textContent || node.value || '').trim().slice(0, 200)
          };
        })();
        """
    ).replace("%SELECTOR%", json.dumps(selector)).replace("%LABEL%", json.dumps(label)).replace(
        "%ANNOTATION_ID%", json.dumps(annotation_id)
    )


def build_clear_annotations_script(*, annotation_id: str | None = None) -> str:
    return (
        """
        (() => {
          const annotationId = %ANNOTATION_ID%;
          const matches = annotationId
            ? Array.from(document.querySelectorAll(`[data-aoryn-annotation-id="${annotationId}"]`))
            : Array.from(document.querySelectorAll('[data-aoryn-annotation-id]'));
          matches.forEach((node) => {
            node.style.outline = '';
            node.style.outlineOffset = '';
            node.removeAttribute('data-aoryn-annotation-id');
            node.removeAttribute('data-aoryn-annotation-label');
          });
          const badges = annotationId
            ? Array.from(document.querySelectorAll(`[data-aoryn-annotation-badge="${annotationId}"]`))
            : Array.from(document.querySelectorAll('[data-aoryn-annotation-badge]'));
          badges.forEach((node) => node.remove());
          return { cleared: true, count: matches.length };
        })();
        """
    ).replace("%ANNOTATION_ID%", json.dumps(annotation_id))


def _configure_windows_app_identity(app_id: str) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        return


def _configure_qtwebengine_environment() -> None:
    existing_flags = (os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS") or "").strip()
    extra_flags = ["--no-sandbox"]
    if sys.platform == "win32":
        extra_flags.append("--single-process")
    merged_flags = existing_flags.split() if existing_flags else []
    for flag in extra_flags:
        if flag not in merged_flags:
            merged_flags.append(flag)
    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(merged_flags)


if QApplication is not None:

    class _UiDispatcher(QObject):
        execute_requested = Signal(object)

        def __init__(self) -> None:
            super().__init__()
            self.execute_requested.connect(self._execute, Qt.ConnectionType.QueuedConnection)

        def invoke(self, func: Callable[[], Any], *, timeout_seconds: float = 10.0) -> Any:
            if threading.current_thread() is threading.main_thread():
                return func()

            holder: dict[str, Any] = {}
            event = threading.Event()
            self.execute_requested.emit((func, holder, event))
            if not event.wait(timeout=max(0.5, timeout_seconds)):
                raise BrowserRuntimeError("Browser UI thread did not answer in time.")
            if "error" in holder:
                raise holder["error"]
            return holder.get("result")

        @Slot(object)
        def _execute(self, payload: object) -> None:
            try:
                func, holder, event = payload  # type: ignore[misc]
                holder["result"] = func()
            except Exception as exc:
                holder["error"] = exc
            finally:
                try:
                    event.set()
                except Exception:
                    pass


    @dataclass(slots=True)
    class _BrowserTab:
        tab_id: str
        view: QWebEngineView
        internal_page: str | None = None
        display_url: str | None = None


    class BrowserPage(QWebEnginePage):
        internal_navigation_requested = Signal(str)

        def __init__(self, profile, parent=None) -> None:
            super().__init__(profile, parent)
            self._pending_file_selection: list[str] = []
            set_background = getattr(self, "setBackgroundColor", None)
            if callable(set_background):
                try:
                    set_background(QColor("#eff3f7"))
                except Exception:
                    pass

        def acceptNavigationRequest(self, url, navigation_type, is_main_frame):  # type: ignore[override]
            parsed = urlparse(url.toString())
            if is_main_frame and parsed.scheme.lower() == "aoryn":
                self.internal_navigation_requested.emit(url.toString())
                return False
            return super().acceptNavigationRequest(url, navigation_type, is_main_frame)

        def prepare_file_selection(self, paths: list[str]) -> None:
            self._pending_file_selection = list(paths)

        def chooseFiles(self, mode, old_files, accepted_mime_types):  # type: ignore[override]
            if self._pending_file_selection:
                selected = list(self._pending_file_selection)
                self._pending_file_selection = []
                return selected
            return super().chooseFiles(mode, old_files, accepted_mime_types)


    class BrowserAssistantPanel(QWidget):
        quick_action_requested = Signal(str)
        ask_requested = Signal(str)
        handoff_requested = Signal(str)
        open_setup_requested = Signal()

        def __init__(self, parent=None) -> None:
            super().__init__(parent)
            self.setObjectName("AssistantPanel")
            layout = QVBoxLayout(self)
            layout.setContentsMargins(18, 18, 18, 18)
            layout.setSpacing(10)

            head = QHBoxLayout()
            head.setContentsMargins(0, 0, 0, 0)
            head.setSpacing(8)
            badge = QLabel("AI")
            badge.setObjectName("AssistantBadge")
            head.addWidget(badge)

            title_block = QVBoxLayout()
            title_block.setContentsMargins(0, 0, 0, 0)
            title_block.setSpacing(1)

            self.heading = QLabel("Page Assistant")
            self.heading.setObjectName("AssistantHeading")
            title_block.addWidget(self.heading)

            self.subheading = QLabel("Current tab only.")
            self.subheading.setWordWrap(True)
            self.subheading.setObjectName("AssistantSubheading")
            title_block.addWidget(self.subheading)
            head.addLayout(title_block, 1)

            self.setup_button = QPushButton("Setup", self)
            self.setup_button.setObjectName("AssistantSecondaryButton")
            self.setup_button.clicked.connect(lambda: self.open_setup_requested.emit())
            head.addWidget(self.setup_button)
            layout.addLayout(head)

            self.status = QLabel("Ready when opened.")
            self.status.setObjectName("AssistantStatus")
            self.status.setWordWrap(True)
            layout.addWidget(self.status)

            self.context_card = QFrame(self)
            self.context_card.setObjectName("AssistantContextCard")
            context_layout = QVBoxLayout(self.context_card)
            context_layout.setContentsMargins(14, 12, 14, 12)
            context_layout.setSpacing(3)
            self.context_title = QLabel("No page selected")
            self.context_title.setObjectName("AssistantContextTitle")
            self.context_title.setWordWrap(True)
            self.context_url = QLabel("Open a page to share context.")
            self.context_url.setObjectName("AssistantContextUrl")
            self.context_url.setWordWrap(True)
            context_layout.addWidget(self.context_title)
            context_layout.addWidget(self.context_url)
            layout.addWidget(self.context_card)

            chip_row = QHBoxLayout()
            chip_row.setContentsMargins(0, 0, 0, 0)
            chip_row.setSpacing(6)
            for label, mode in (
                ("Summarize", "summary"),
                ("Insights", "insights"),
                ("Handoff", "handoff"),
            ):
                button = QPushButton(label, self)
                button.setObjectName("AssistantChip")
                button.clicked.connect(lambda _checked=False, current_mode=mode: self.quick_action_requested.emit(current_mode))
                chip_row.addWidget(button)
            layout.addLayout(chip_row)

            self.prompt = QTextEdit(self)
            self.prompt.setObjectName("AssistantPrompt")
            self.prompt.setPlaceholderText("Ask or hand off.")
            self.prompt.setFixedHeight(92)
            layout.addWidget(self.prompt)

            action_row = QHBoxLayout()
            action_row.setContentsMargins(0, 0, 0, 0)
            action_row.setSpacing(8)
            self.ask_button = QPushButton("Ask", self)
            self.ask_button.setObjectName("AssistantPrimaryButton")
            self.ask_button.clicked.connect(lambda: self.ask_requested.emit(self.prompt.toPlainText().strip()))
            action_row.addWidget(self.ask_button, 1)
            self.handoff_button = QPushButton("Send to Agent", self)
            self.handoff_button.setObjectName("AssistantSecondaryButton")
            self.handoff_button.clicked.connect(lambda: self.handoff_requested.emit(self.prompt.toPlainText().strip()))
            action_row.addWidget(self.handoff_button, 1)
            layout.addLayout(action_row)

            self.response = QTextEdit(self)
            self.response.setObjectName("AssistantResponse")
            self.response.setReadOnly(True)
            self.response.setPlaceholderText("")
            layout.addWidget(self.response, 1)
            self._quick_action_buttons = self.findChildren(QPushButton, "AssistantChip")

        def update_context(self, snapshot: dict[str, Any] | None) -> None:
            payload = snapshot or {}
            self.context_title.setText(_optional_str(payload.get("title")) or "No page selected")
            self.context_url.setText(_optional_str(payload.get("url")) or "Open a page to share context.")

        def set_digest(self, text: str) -> None:
            self.response.setPlainText(str(text or "").strip())

        def set_prompt(self, text: str) -> None:
            self.prompt.setPlainText(text)
            self.prompt.setFocus()

        def set_status(self, text: str) -> None:
            self.status.setText(
                _optional_str(text)
                or "Ready when opened."
            )

        def set_busy(self, busy: bool, *, status_text: str | None = None) -> None:
            if status_text:
                self.set_status(status_text)
            self.prompt.setReadOnly(busy)
            self.ask_button.setDisabled(busy)
            self.handoff_button.setDisabled(busy)
            self.setup_button.setDisabled(busy)
            for button in self._quick_action_buttons:
                button.setDisabled(busy)


    class BrowserAssistantSetupDialog(QDialog):
        def __init__(self, runtime, parent=None) -> None:
            super().__init__(parent)
            self.runtime = runtime
            self.setWindowTitle("Aoryn Browser Setup")
            self.setModal(True)
            self.resize(620, 520)

            self._provider_defaults: dict[str, str] = {}

            layout = QVBoxLayout(self)
            layout.setContentsMargins(18, 18, 18, 18)
            layout.setSpacing(14)

            title = QLabel("Configure browser AI and the managed browser runtime.")
            title.setObjectName("AssistantSetupTitle")
            title.setWordWrap(True)
            layout.addWidget(title)

            self.subtitle = QLabel(
                "These settings are saved to runtime preferences and reused by the browser assistant plus the next Aoryn task that calls into the managed browser service."
            )
            self.subtitle.setObjectName("AssistantSetupSubtitle")
            self.subtitle.setWordWrap(True)
            layout.addWidget(self.subtitle)

            form = QFormLayout()
            form.setContentsMargins(0, 0, 0, 0)
            form.setSpacing(10)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
            form.setFormAlignment(Qt.AlignmentFlag.AlignTop)

            self.provider_combo = QComboBox(self)
            form.addRow("Provider", self.provider_combo)

            self.base_url_edit = QLineEdit(self)
            self.base_url_edit.setPlaceholderText("https://api.openai.com/v1")
            form.addRow("Base URL", self.base_url_edit)

            self.model_combo = QComboBox(self)
            self.model_combo.setEditable(True)
            self.model_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            form.addRow("Model", self.model_combo)

            self.auto_discover_checkbox = QCheckBox("Prefer automatic model selection when available.", self)
            form.addRow("", self.auto_discover_checkbox)

            self.api_key_edit = QLineEdit(self)
            self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.api_key_edit.setPlaceholderText("Optional for local providers")
            form.addRow("API key", self.api_key_edit)

            self.browser_channel_combo = QComboBox(self)
            form.addRow("Browser channel", self.browser_channel_combo)

            self.browser_path_edit = QLineEdit(self)
            self.browser_path_edit.setPlaceholderText("Optional explicit browser executable path")
            form.addRow("Browser path", self.browser_path_edit)

            self.browser_headless_checkbox = QCheckBox("Run the managed browser in headless mode.", self)
            form.addRow("", self.browser_headless_checkbox)

            layout.addLayout(form)

            action_row = QHBoxLayout()
            action_row.setContentsMargins(0, 0, 0, 0)
            action_row.setSpacing(8)
            self.refresh_models_button = QPushButton("Refresh models", self)
            self.refresh_models_button.setObjectName("AssistantSecondaryButton")
            self.refresh_models_button.clicked.connect(self._refresh_models)
            action_row.addWidget(self.refresh_models_button)
            action_row.addStretch(1)
            layout.addLayout(action_row)

            self.status_note = QLabel("Saved settings will be used by the in-browser assistant and the next Aoryn run.")
            self.status_note.setObjectName("AssistantSetupStatus")
            self.status_note.setWordWrap(True)
            layout.addWidget(self.status_note)

            self.paths_note = QLabel("")
            self.paths_note.setObjectName("AssistantSetupPaths")
            self.paths_note.setWordWrap(True)
            layout.addWidget(self.paths_note)

            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
                parent=self,
            )
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            layout.addWidget(buttons)

            self.provider_combo.currentIndexChanged.connect(self._handle_provider_changed)
            self._load_snapshot()

        def _load_snapshot(self) -> None:
            snapshot = self.runtime.assistant_setup_snapshot()
            providers = snapshot.get("providers") or []
            browser_channels = snapshot.get("browser_channels") or []
            effective = snapshot.get("effective") or {}
            summary = snapshot.get("summary") or {}

            self.provider_combo.blockSignals(True)
            self.provider_combo.clear()
            self._provider_defaults = {}
            current_provider = _optional_str(effective.get("model_provider")) or "lmstudio_local"
            provider_index = 0
            for index, item in enumerate(providers):
                value = _optional_str(item.get("value")) or ""
                label = _optional_str(item.get("label")) or value or "Provider"
                self.provider_combo.addItem(label, value)
                self._provider_defaults[value] = _optional_str(item.get("base_url")) or ""
                if value == current_provider:
                    provider_index = index
            if self.provider_combo.count() == 0:
                self.provider_combo.addItem(current_provider, current_provider)
            self.provider_combo.setCurrentIndex(provider_index)
            self.provider_combo.blockSignals(False)

            self.browser_channel_combo.clear()
            current_channel = _optional_str(effective.get("browser_channel")) or ""
            channel_index = 0
            for index, item in enumerate(browser_channels):
                value = _optional_str(item.get("value")) or ""
                label = _optional_str(item.get("label")) or value or "System default"
                self.browser_channel_combo.addItem(label, value)
                if value == current_channel:
                    channel_index = index
            if self.browser_channel_combo.count() == 0:
                self.browser_channel_combo.addItem("System default", "")
            self.browser_channel_combo.setCurrentIndex(channel_index)

            self.base_url_edit.setText(_optional_str(effective.get("model_base_url")) or "")
            self.api_key_edit.setText(_optional_str(effective.get("model_api_key")) or "")
            self.browser_path_edit.setText(_optional_str(effective.get("browser_executable_path")) or "")
            self.auto_discover_checkbox.setChecked(bool(effective.get("model_auto_discover", True)))
            self.browser_headless_checkbox.setChecked(bool(effective.get("browser_headless", False)))

            self.model_combo.clear()
            self.model_combo.addItem("auto")
            current_model = _optional_str(effective.get("model_name")) or "auto"
            if self.model_combo.findText(current_model) < 0:
                self.model_combo.addItem(current_model)
            self.model_combo.setCurrentText(current_model)

            self._set_status(
                f"{_optional_str(summary.get('status')) or 'Setup needed'}: {_optional_str(summary.get('detail')) or ''}".strip(": ")
            )
            self.paths_note.setText(
                "\n".join(
                    [
                        f"Runtime preferences: {_optional_str(snapshot.get('runtime_preferences_path')) or 'Unavailable'}",
                        f"Config file: {_optional_str(snapshot.get('config_path')) or 'Using defaults'}",
                    ]
                )
            )

        def _set_status(self, text: str) -> None:
            self.status_note.setText(_optional_str(text) or "Saved settings will be used by the in-browser assistant and the next Aoryn run.")

        def _handle_provider_changed(self) -> None:
            provider_value = _optional_str(self.provider_combo.currentData()) or ""
            current_base = _optional_str(self.base_url_edit.text())
            default_base = self._provider_defaults.get(provider_value, "")
            if not current_base or current_base in set(self._provider_defaults.values()):
                self.base_url_edit.setText(default_base)

        def _refresh_models(self) -> None:
            self._set_status("Refreshing provider connection and model catalog...")
            snapshot = self.runtime.assistant_provider_snapshot()
            if not snapshot.get("ok"):
                self._set_status(_optional_str(snapshot.get("error")) or "Unable to reach the configured provider.")
                return

            models = []
            for item in snapshot.get("catalog_models") or []:
                if not isinstance(item, dict):
                    continue
                model_id = _optional_str(item.get("model_id"))
                if model_id:
                    models.append(model_id)
            preferred_model = _optional_str(snapshot.get("preferred_chat_model")) or _optional_str(self.model_combo.currentText()) or "auto"

            self.model_combo.clear()
            self.model_combo.addItem("auto")
            for model_id in models:
                if self.model_combo.findText(model_id) < 0:
                    self.model_combo.addItem(model_id)
            if self.model_combo.findText(preferred_model) < 0:
                self.model_combo.addItem(preferred_model)
            self.model_combo.setCurrentText(preferred_model)
            self._set_status(
                f"Connected to {_optional_str(snapshot.get('provider')) or 'provider'} and found {len(models)} models."
            )

        def _collect_payload(self) -> dict[str, Any]:
            return {
                "model_provider": _optional_str(self.provider_combo.currentData()) or "",
                "model_base_url": _optional_str(self.base_url_edit.text()) or "",
                "model_name": _optional_str(self.model_combo.currentText()) or "auto",
                "model_api_key": _optional_str(self.api_key_edit.text()) or "",
                "model_auto_discover": self.auto_discover_checkbox.isChecked(),
                "browser_channel": _optional_str(self.browser_channel_combo.currentData()) or "",
                "browser_executable_path": _optional_str(self.browser_path_edit.text()) or "",
                "browser_headless": self.browser_headless_checkbox.isChecked(),
            }

        def accept(self) -> None:
            result = self.runtime.update_assistant_settings(self._collect_payload())
            if not result.get("ok"):
                self._set_status(_optional_str(result.get("error")) or "Unable to save browser AI settings.")
                return
            self._set_status("Saved. The browser assistant and next Aoryn task will use the updated settings.")
            super().accept()


    class BrowserWindow(QMainWindow):
        def __init__(
            self,
            *,
            profile: QWebEngineProfile,
            icon_path: Path,
            homepage_url: str,
            search_url: str,
        ) -> None:
            super().__init__()
            self.window_id = uuid.uuid4().hex[:8]
            self.profile = profile
            self.homepage_url = homepage_url
            self.search_url = search_url
            self._assistant_request_in_flight = False
            self.tabs = QTabWidget(self)
            self.tabs.currentChanged.connect(self._handle_current_tab_changed)
            self.tabs.tabBar().hide()
            self.setWindowTitle(f"{APP_NAME} Browser")
            window_icon = browser_window_icon()
            if window_icon.isNull():
                window_icon = QIcon(str(icon_path))
            self.setWindowIcon(window_icon)
            self.resize(1280, 900)
            self._tab_refs: list[_BrowserTab] = []
            self.address_bar = QLineEdit(self)
            self._build_chrome_shell()
            self._build_menu()
            self._build_assistant_dock()
            self._build_toolbar()
            self._build_tab_strip()
            self._apply_chrome_like_style()
            self.menuBar().hide()
            self._set_assistant_placeholder_state()
            QTimer.singleShot(0, self.refresh_assistant_setup_state)

        def _build_chrome_shell(self) -> None:
            self.chrome_root = QWidget(self)
            self.chrome_root.setObjectName("BrowserChromeRoot")
            root_layout = QVBoxLayout(self.chrome_root)
            root_layout.setContentsMargins(8, 6, 8, 8)
            root_layout.setSpacing(0)

            self.top_chrome = BrowserTopChrome(self.chrome_root)
            root_layout.addWidget(self.top_chrome)

            self.tab_strip_shell = QFrame(self.chrome_root)
            self.tab_strip_shell.setObjectName("BrowserTabStripShell")
            strip_layout = QVBoxLayout(self.tab_strip_shell)
            strip_layout.setContentsMargins(6, 2, 6, 0)
            strip_layout.setSpacing(0)
            root_layout.addWidget(self.tab_strip_shell)

            self.content_shell = QFrame(self.chrome_root)
            self.content_shell.setObjectName("BrowserContentShell")
            content_layout = QVBoxLayout(self.content_shell)
            content_layout.setContentsMargins(0, 0, 0, 0)
            content_layout.setSpacing(0)
            content_layout.addWidget(self.tabs)
            root_layout.addWidget(self.content_shell, 1)

            self.setCentralWidget(self.chrome_root)

        def _build_toolbar(self) -> None:
            self.back_button = self._create_toolbar_button(
                icon=browser_chrome_icon("back"),
                tooltip="Back",
                handler=self.go_back,
            )
            self.top_chrome.add_navigation_widget(self.back_button)

            self.forward_button = self._create_toolbar_button(
                icon=browser_chrome_icon("forward"),
                tooltip="Forward",
                handler=self.go_forward,
            )
            self.top_chrome.add_navigation_widget(self.forward_button)

            self.reload_button = self._create_toolbar_button(
                icon=browser_chrome_icon("reload"),
                tooltip="Reload",
                handler=self.reload_page,
            )
            self.top_chrome.add_navigation_widget(self.reload_button)

            self.home_button = self._create_toolbar_button(
                icon=browser_chrome_icon("home"),
                tooltip="Home",
                handler=self.open_home_page,
            )
            self.top_chrome.add_navigation_widget(self.home_button)

            self.address_bar.setClearButtonEnabled(True)
            self.address_bar.setPlaceholderText("Search or enter address")
            self.address_bar.setObjectName("AddressBar")
            self.address_bar.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.address_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.address_bar.returnPressed.connect(self._navigate_from_address_bar)
            self.top_chrome.set_address_widget(self.address_bar)

            self.new_tab_button = self._create_toolbar_button(
                icon=browser_chrome_icon("add"),
                tooltip="New tab",
                handler=lambda: self.open_tab(self.homepage_url),
                object_name="TabActionButton",
            )
            self.top_chrome.add_action_widget(self.new_tab_button)

            self.assistant_toggle_button = self._create_toolbar_button(
                text="AI",
                tooltip="Open browser help",
                handler=self._toggle_assistant_panel,
                object_name="AssistantToggleButton",
            )
            self.assistant_toggle_button.setCheckable(True)
            self.top_chrome.add_action_widget(self.assistant_toggle_button)

            self.menu_button = self._create_menu_button()
            self.top_chrome.add_action_widget(self.menu_button)

            self.assistant_status_chip = QLabel("Runtime starting", self)
            self.assistant_status_chip.setObjectName("AssistantStatusChip")
            self.assistant_status_chip.hide()

        def _build_menu(self) -> None:
            self._browser_menu = QMenu(self)
            new_tab = QAction("New Tab", self)
            new_tab.triggered.connect(lambda: self.open_tab(self.homepage_url))
            self._browser_menu.addAction(new_tab)
            bookmark_action = QAction("Bookmark Current Page", self)
            bookmark_action.triggered.connect(self._bookmark_current_page)
            self._browser_menu.addAction(bookmark_action)
            self._browser_menu.addSeparator()

            diagnostics_menu = self._browser_menu.addMenu("Diagnostics")
            setup_action = QAction("Browser Setup", self)
            setup_action.triggered.connect(self._open_assistant_setup)
            diagnostics_menu.addAction(setup_action)
            setup_page_action = QAction("Browser Setup", self)
            setup_page_action.triggered.connect(lambda: self.open_internal_page("setup"))
            diagnostics_menu.addAction(setup_page_action)
            runtime_action = QAction("Runtime Overview", self)
            runtime_action.triggered.connect(lambda: self.open_internal_page("runtime"))
            diagnostics_menu.addAction(runtime_action)
            history_action = QAction("History", self)
            history_action.triggered.connect(lambda: self.open_internal_page("history"))
            diagnostics_menu.addAction(history_action)
            bookmarks_action = QAction("Bookmarks", self)
            bookmarks_action.triggered.connect(lambda: self.open_internal_page("bookmarks"))
            diagnostics_menu.addAction(bookmarks_action)
            downloads_action = QAction("Downloads", self)
            downloads_action.triggered.connect(lambda: self.open_internal_page("downloads"))
            diagnostics_menu.addAction(downloads_action)
            permissions_action = QAction("Review Queue", self)
            permissions_action.triggered.connect(lambda: self.open_internal_page("permissions"))
            diagnostics_menu.addAction(permissions_action)

        def _build_assistant_dock(self) -> None:
            self.assistant_panel = BrowserAssistantPanel(self)
            self.assistant_panel.quick_action_requested.connect(self._handle_assistant_quick_action)
            self.assistant_panel.ask_requested.connect(self._handle_assistant_ask)
            self.assistant_panel.handoff_requested.connect(self._handle_assistant_handoff)
            self.assistant_panel.open_setup_requested.connect(self._open_assistant_setup)
            self.assistant_dock = QDockWidget("Aoryn", self)
            self.assistant_dock.setObjectName("AssistantDock")
            self.assistant_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
            self.assistant_dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
            self.assistant_dock.setTitleBarWidget(QWidget(self.assistant_dock))
            self.assistant_dock.setWidget(self.assistant_panel)
            self.assistant_dock.setMinimumWidth(320)
            self.assistant_dock.setMaximumWidth(360)
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.assistant_dock)
            visibility_signal = getattr(self.assistant_dock, "visibilityChanged", None)
            connect = getattr(visibility_signal, "connect", None)
            if callable(connect):
                connect(self._handle_assistant_dock_visibility_changed)
            self.assistant_dock.hide()

        def _build_tab_strip(self) -> None:
            self.tab_strip = BrowserTabStrip(self.tab_strip_shell)
            strip_layout = self.tab_strip_shell.layout()
            if strip_layout is not None:
                strip_layout.addWidget(self.tab_strip)
            self.tab_strip.currentChanged.connect(self._handle_tab_strip_changed)
            self.tab_strip.tabCloseRequested.connect(self._close_tab)
            self.tab_strip_shell.hide()
            self.tab_strip.hide()

        def _create_brand_widget(self) -> QWidget:
            brand = QWidget(self)
            brand.setObjectName("BrowserBrand")
            layout = QHBoxLayout(brand)
            layout.setContentsMargins(4, 0, 8, 0)
            layout.setSpacing(10)

            mark = QLabel("A", brand)
            mark.setObjectName("BrowserBrandMark")
            mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(mark)

            copy = QWidget(brand)
            copy.setObjectName("BrowserBrandCopy")
            copy_layout = QVBoxLayout(copy)
            copy_layout.setContentsMargins(0, 0, 0, 0)
            copy_layout.setSpacing(1)

            wordmark = QLabel("Aoryn", copy)
            wordmark.setObjectName("BrowserBrandWordmark")
            copy_layout.addWidget(wordmark)

            subline = QLabel("Browser", copy)
            subline.setObjectName("BrowserBrandSubline")
            copy_layout.addWidget(subline)

            layout.addWidget(copy)
            return brand

        def _create_toolbar_button(
            self,
            *,
            tooltip: str,
            handler: Callable[[], Any],
            icon: QIcon | None = None,
            text: str | None = None,
            object_name: str = "ChromeNavButton",
        ) -> QToolButton:
            button = QToolButton(self)
            button.setObjectName(object_name)
            button.setAutoRaise(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(tooltip)
            if icon is not None and not icon.isNull():
                button.setIcon(icon)
                button.setIconSize(QSize(18, 18))
            if text:
                button.setText(text)
            button.clicked.connect(handler)
            return button

        def _create_menu_button(self) -> QToolButton:
            button = QToolButton(self)
            button.setObjectName("BrowserMenuButton")
            button.setAutoRaise(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIcon(browser_chrome_icon("more"))
            button.setIconSize(QSize(18, 18))
            button.setToolTip("Browser menu")
            button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            button.setMenu(self._browser_menu)
            return button

        def _bookmark_current_page(self) -> None:
            runtime = self._browser_runtime()
            if runtime is not None:
                runtime.bookmark_page()

        def _open_assistant_setup(self) -> None:
            runtime = self._browser_runtime()
            if runtime is None:
                self.assistant_panel.set_status("Browser runtime is unavailable.")
                return
            dialog = BrowserAssistantSetupDialog(runtime, self)
            if dialog.exec():
                self.refresh_assistant_setup_state()
                self._refresh_assistant_context()

        def _toggle_assistant_panel(self) -> None:
            if self.assistant_dock.isVisible():
                self.assistant_dock.hide()
                return
            self.refresh_assistant_setup_state()
            self._refresh_assistant_context()
            self.assistant_dock.show()
            self.assistant_dock.raise_()

        def _handle_assistant_dock_visibility_changed(self, visible: bool) -> None:
            toggle_button = getattr(self, "assistant_toggle_button", None)
            if toggle_button is not None:
                toggle_button.setChecked(bool(visible))
            if visible:
                self.refresh_assistant_setup_state()

        def _handle_assistant_quick_action(self, mode: str) -> None:
            snapshot = self.snapshot()
            self.assistant_panel.update_context(snapshot)
            self.assistant_panel.set_digest(build_browser_digest(snapshot, mode=mode))
            if mode == "handoff":
                self.assistant_panel.set_prompt("Continue this browsing task in the desktop agent.")
                self.assistant_panel.set_status("Review the handoff preview, then send it to the desktop agent when ready.")
                return
            self.assistant_panel.set_status("Quick page digest generated from the visible page.")

        def _handle_assistant_ask(self, prompt: str) -> None:
            if self._assistant_request_in_flight:
                return
            snapshot = self.snapshot()
            runtime = self._browser_runtime()
            normalized_prompt = _optional_str(prompt) or "Summarize this page and tell me the next useful step."
            if runtime is None:
                self.assistant_panel.set_digest("Browser runtime is unavailable.")
                self.assistant_panel.set_status("Browser runtime is unavailable.")
                return

            self._assistant_request_in_flight = True
            self.assistant_panel.set_busy(True, status_text="Aoryn is reading the current page...")
            self.assistant_panel.set_digest("Working on a page-grounded answer...")

            def _worker() -> None:
                result = runtime.ask_assistant(prompt=normalized_prompt, snapshot=snapshot)
                runtime.dispatcher.invoke(
                    lambda: self._finish_assistant_request(
                        normalized_prompt,
                        snapshot,
                        result,
                    )
                )

            threading.Thread(target=_worker, name=f"browser-ai-{self.window_id}", daemon=True).start()

        def _finish_assistant_request(
            self,
            prompt: str,
            snapshot: dict[str, Any],
            result: dict[str, Any],
        ) -> None:
            self._assistant_request_in_flight = False
            self.assistant_panel.set_busy(False)
            if result.get("ok"):
                message = _optional_str(result.get("assistant_message")) or "The assistant returned an empty response."
                self.assistant_panel.set_digest(message)
                self.assistant_panel.set_status(
                    f"Answered from {_optional_str(snapshot.get('title')) or 'the current page'} using the configured provider."
                )
                return
            self.assistant_panel.set_digest(
                "\n".join(
                    [
                        "AI request failed",
                        _optional_str(result.get("error")) or "The configured provider could not answer.",
                    ]
                )
            )
            self.assistant_panel.set_status("Open Browser Setup to check the provider, Base URL, model, or API key.")

        def _handle_assistant_handoff(self, prompt: str) -> None:
            snapshot = self.snapshot()
            digest = build_browser_digest(snapshot, mode="handoff")
            normalized_prompt = _optional_str(prompt) or "Continue with the current page."
            runtime = self._browser_runtime()
            if runtime is not None:
                runtime.record_handoff(
                    kind="assistant_prompt",
                    reason=normalized_prompt,
                    url=_optional_str(snapshot.get("url")),
                    title=_optional_str(snapshot.get("title")),
                )
            self.assistant_panel.set_digest(
                "\n".join(
                    [
                        "Prompt queued for Aoryn",
                        normalized_prompt,
                        "",
                        digest,
                    ]
                )
            )
            self.assistant_panel.set_status("Handoff recorded. Continue the task in the desktop agent when ready.")

        def _set_assistant_placeholder_state(self) -> None:
            self.assistant_status_chip.setText("")
            self.assistant_status_chip.setToolTip("")
            toggle_button = getattr(self, "assistant_toggle_button", None)
            if toggle_button is not None:
                toggle_button.setToolTip("Open browser assistant")
            self.assistant_panel.set_status("Ready when opened.")

        def refresh_assistant_setup_state(self) -> None:
            runtime = self._browser_runtime()
            if runtime is None or not hasattr(runtime, "service_summary") or not hasattr(runtime, "assistant_setup_snapshot"):
                self.assistant_status_chip.setText("Runtime offline")
                self.assistant_status_chip.setToolTip("Browser runtime is unavailable.")
                toggle_button = getattr(self, "assistant_toggle_button", None)
                if toggle_button is not None:
                    toggle_button.setToolTip("Open browser assistant\nBrowser runtime is unavailable.")
                self.assistant_panel.set_status("Browser runtime is unavailable.")
                return
            service = runtime.service_summary()
            assistant = runtime.assistant_setup_snapshot().get("summary") or {}
            service_badge = _optional_str(service.get("badge_text")) or "Runtime starting"
            service_detail = _optional_str(service.get("detail")) or "Managed runtime state is unavailable."
            assistant_status = _optional_str(assistant.get("status")) or "Setup needed"
            assistant_detail = _optional_str(assistant.get("detail")) or "Open Browser Setup to configure browser AI."
            chip_text = f"{service_badge} | {'AI ready' if assistant_status == 'Ready' else assistant_status}"
            self.assistant_status_chip.setText(chip_text)
            self.assistant_status_chip.setToolTip("\n".join([service_detail, f"AI: {assistant_detail}"]).strip())
            toggle_button = getattr(self, "assistant_toggle_button", None)
            if toggle_button is not None:
                toggle_button.setToolTip(
                    "\n".join(
                        [
                            "Open browser assistant",
                            service_badge,
                            f"AI: {assistant_status}",
                            service_detail,
                            assistant_detail,
                        ]
                    ).strip()
                )
            self.assistant_panel.set_status(
                f"{service_badge}: {service_detail} AI: {assistant_status}. {assistant_detail}"
            )

        def _refresh_assistant_context(self) -> None:
            snapshot = self.snapshot()
            self.assistant_panel.update_context(snapshot)
            if not self.assistant_panel.response.toPlainText().strip():
                self.assistant_panel.set_digest(build_browser_digest(snapshot, mode="summary"))

        def _apply_chrome_like_style(self) -> None:
            self.setStyleSheet(BROWSER_CHROME_STYLESHEET)

        def open_tab(
            self,
            url: str | None = None,
            *,
            activate: bool = True,
            tab_id: str | None = None,
        ) -> dict[str, Any]:
            view = QWebEngineView(self)
            page = BrowserPage(self.profile, view)
            view.setPage(page)
            page.setWebChannel(None)
            item_tab_id = tab_id or uuid.uuid4().hex[:8]
            initial_url = url or self.homepage_url
            initial_internal_page = _internal_browser_page_name(initial_url)
            label = ""
            self._tab_refs.append(
                _BrowserTab(
                    tab_id=item_tab_id,
                    view=view,
                    internal_page=initial_internal_page,
                    display_url=initial_url,
                )
            )
            index = self.tabs.addTab(view, label)
            self._sync_tab_chrome()
            if activate:
                self.tabs.setCurrentIndex(index)
            view.titleChanged.connect(lambda title, current_tab_id=item_tab_id: self._update_tab_title(current_tab_id, title))
            view.urlChanged.connect(lambda changed_url, current_tab_id=item_tab_id: self._handle_url_changed(current_tab_id, changed_url))
            view.loadFinished.connect(lambda ok, current_tab_id=item_tab_id: self._handle_load_finished(current_tab_id, ok))
            icon_signal = getattr(view, "iconChanged", None)
            icon_connect = getattr(icon_signal, "connect", None)
            if callable(icon_connect):
                icon_connect(lambda _icon=None: self._sync_tab_chrome())
            page.internal_navigation_requested.connect(
                lambda target, current_tab_id=item_tab_id: self._open_internal_target(current_tab_id, target)
            )
            permission_signal = getattr(page, "featurePermissionRequested", None)
            connect = getattr(permission_signal, "connect", None)
            if callable(connect):
                connect(
                    lambda origin, feature, current_tab_id=item_tab_id, current_page=page: self._handle_permission_request(
                        current_tab_id,
                        current_page,
                        origin,
                        feature,
                    )
                )
            self.navigate(initial_url, tab_id=item_tab_id)
            return {"window_id": self.window_id, "tab_id": item_tab_id, "index": index}

        def active_tab(self) -> _BrowserTab | None:
            current = self.tabs.currentWidget()
            for item in self._tab_refs:
                if item.view is current:
                    return item
            return None

        def navigate(self, url: str, *, tab_id: str | None = None) -> dict[str, Any]:
            target = self._resolve_tab(tab_id)
            if target is None:
                payload = self.open_tab(url)
                return {**payload, "url": url}
            normalized = normalize_browser_target(url, homepage=self.homepage_url, search_url=self.search_url)
            target.display_url = normalized
            if is_internal_browser_url(normalized):
                return self._render_internal_page(target, normalized)
            target.internal_page = None
            self._update_tab_title(target.tab_id, self._fallback_tab_title(normalized))
            self._sync_tab_chrome()
            target.view.load(QUrl(normalized))
            self._sync_address_bar()
            self._refresh_assistant_context()
            return {"window_id": self.window_id, "tab_id": target.tab_id, "url": normalized}

        def open_internal_page(self, page_name: str, *, tab_id: str | None = None) -> dict[str, Any]:
            return self.navigate(f"aoryn://{(page_name or 'home').strip().lower()}", tab_id=tab_id)

        def switch_tab(self, tab_id: str) -> dict[str, Any]:
            target = self._resolve_tab(tab_id)
            if target is None:
                return {"ok": False, "error": "Unknown tab id."}
            index = self._tab_index(target)
            if index >= 0:
                self.tabs.setCurrentIndex(index)
            return {"ok": True, "window_id": self.window_id, "tab_id": target.tab_id, "index": index}

        def close_tab_by_id(self, tab_id: str | None = None) -> dict[str, Any]:
            target = self._resolve_tab(tab_id)
            if target is None:
                return {"ok": False, "error": "Unknown tab id."}
            index = self._tab_index(target)
            if index < 0:
                return {"ok": False, "error": "Unknown tab id."}
            self._close_tab(index)
            return {"ok": True, "tab_id": target.tab_id}

        def go_back(self) -> dict[str, Any]:
            tab = self.active_tab()
            if tab is None:
                return {"ok": False, "error": "No active tab."}
            if tab.internal_page:
                return self.open_home_page()
            tab.view.back()
            return {"ok": True, "tab_id": tab.tab_id, "action": "back"}

        def go_forward(self) -> dict[str, Any]:
            tab = self.active_tab()
            if tab is None:
                return {"ok": False, "error": "No active tab."}
            if tab.internal_page:
                return {"ok": False, "error": "Internal pages do not support forward navigation."}
            tab.view.forward()
            return {"ok": True, "tab_id": tab.tab_id, "action": "forward"}

        def reload_page(self) -> dict[str, Any]:
            tab = self.active_tab()
            if tab is None:
                return {"ok": False, "error": "No active tab."}
            if tab.internal_page:
                return self.open_internal_page(tab.internal_page, tab_id=tab.tab_id)
            tab.view.reload()
            return {"ok": True, "tab_id": tab.tab_id, "action": "reload"}

        def open_home_page(self) -> dict[str, Any]:
            return self.open_internal_page("home")

        def query_dom(self, *, selector: str | None = None, include_text: bool = True) -> dict[str, Any]:
            tab = self.active_tab()
            if tab is None:
                return {"url": None, "title": None, "text": None}
            page = tab.view.page()
            url = self._visible_url(tab)
            title = self._visible_title(tab)
            script = (
                """
                (() => {
                  const target = %SELECTOR%;
                  const node = target ? document.querySelector(target) : document.body;
                  if (!node) {
                    return { found: false, text: "", html: "", value: "" };
                  }
                  return {
                    found: true,
                    text: String(node.innerText || "").slice(0, 4000),
                    html: String(node.innerHTML || "").slice(0, 4000),
                    value: node.value !== undefined ? String(node.value || "") : ""
                  };
                })();
                """
            ).replace("%SELECTOR%", json.dumps(selector))
            payload = _run_js_sync(page, script)
            if not isinstance(payload, dict):
                payload = {"found": False, "text": "", "html": "", "value": ""}
            return {
                "url": url,
                "title": title,
                "text": payload.get("text") if include_text else None,
                "html": payload.get("html"),
                "value": payload.get("value"),
                "selector": selector,
                "found": bool(payload.get("found")),
                "tab_id": tab.tab_id,
            }

        def query_accessibility(self) -> dict[str, Any]:
            tab = self.active_tab()
            if tab is None:
                return {"items": []}
            script = """
                (() => Array.from(document.querySelectorAll('button, input, textarea, select, a, [role]'))
                  .slice(0, 100)
                  .map((node, index) => ({
                    index,
                    tag: node.tagName.toLowerCase(),
                    role: node.getAttribute('role') || '',
                    text: String(node.innerText || node.textContent || node.value || '').trim().slice(0, 200),
                    label: String(node.getAttribute('aria-label') || node.getAttribute('placeholder') || '').trim().slice(0, 200)
                  })))();
            """
            items = _run_js_sync(tab.view.page(), script)
            return {"items": items if isinstance(items, list) else [], "tab_id": tab.tab_id}

        def annotate_page(self, *, selector: str | None = None, label: str | None = None) -> dict[str, Any]:
            tab = self.active_tab()
            if tab is None:
                return {"annotated": False}
            runtime = self._browser_runtime()
            annotation_id = uuid.uuid4().hex[:8]
            script = build_annotation_overlay_script(
                selector=selector,
                label=label or annotation_id,
                annotation_id=annotation_id,
            )
            result = _run_js_sync(tab.view.page(), script)
            payload = result if isinstance(result, dict) else {"annotated": False}
            if payload.get("annotated") and runtime is not None:
                runtime.register_annotation(
                    {
                        "tab_id": tab.tab_id,
                        "annotation_id": annotation_id,
                        "selector": selector or "body",
                        "label": label or annotation_id,
                        "created_at": time.time(),
                    }
                )
            return {
                "annotated": bool(payload.get("annotated")),
                "annotation_id": annotation_id if payload.get("annotated") else None,
                "tab_id": tab.tab_id,
                "selector": selector,
                "label": label or annotation_id,
                "text": payload.get("text"),
            }

        def clear_annotations(self, *, tab_id: str | None = None, annotation_id: str | None = None) -> dict[str, Any]:
            tab = self._resolve_tab(tab_id)
            if tab is None:
                return {"ok": False, "error": "No active tab."}
            if tab.internal_page:
                return {"ok": False, "error": "Internal pages do not carry page annotations."}
            result = _run_js_sync(tab.view.page(), build_clear_annotations_script(annotation_id=annotation_id))
            runtime = self._browser_runtime()
            if runtime is not None:
                runtime.clear_registered_annotations(tab.tab_id, annotation_id=annotation_id)
            payload = result if isinstance(result, dict) else {"cleared": False, "count": 0}
            return {
                "ok": bool(payload.get("cleared")),
                "cleared": bool(payload.get("cleared")),
                "count": int(payload.get("count", 0) or 0),
                "tab_id": tab.tab_id,
            }

        def upload_files(
            self,
            *,
            selector: str | None = None,
            paths: list[str] | None = None,
            tab_id: str | None = None,
        ) -> dict[str, Any]:
            tab = self._resolve_tab(tab_id)
            if tab is None:
                return {"ok": False, "error": "No active tab."}
            if tab.internal_page:
                return {"ok": False, "error": "Internal pages do not support file uploads."}
            upload_paths = normalize_browser_upload_paths(paths or [])
            if not upload_paths:
                return {"ok": False, "error": "No valid upload file paths were provided."}
            page = tab.view.page()
            if hasattr(page, "prepare_file_selection"):
                page.prepare_file_selection(upload_paths)  # type: ignore[attr-defined]
            script = (
                "(() => {"
                f"const node = document.querySelector({json.dumps(selector)});"
                "if (!node || String(node.tagName || '').toLowerCase() !== 'input' || String(node.type || '').toLowerCase() !== 'file') return false;"
                "node.click();"
                "return true;"
                "})();"
            )
            result = _run_js_sync(page, script)
            return {
                "ok": bool(result),
                "tab_id": tab.tab_id,
                "action": "upload",
                "files": upload_paths,
                "selector": selector,
            }

        def perform_action(self, payload: dict[str, Any]) -> dict[str, Any]:
            tab = self._resolve_tab(payload.get("tab_id"))
            if tab is None:
                return {"ok": False, "error": "No active tab."}
            action = str(payload.get("action", "")).strip().lower()
            selector = str(payload.get("selector", "")).strip() or None
            value = str(payload.get("value", "")).strip() or None
            url = str(payload.get("url", "")).strip() or None
            raw_files = payload.get("files")
            upload_paths = normalize_browser_upload_paths(raw_files if raw_files is not None else payload.get("path") or value)
            if action == "navigate" and url:
                return self.navigate(url, tab_id=tab.tab_id)
            if action == "back":
                return self.go_back()
            if action == "forward":
                return self.go_forward()
            if action == "reload":
                return self.reload_page()
            if action == "home":
                return self.open_home_page()
            if action == "open_tab":
                return self.open_tab(url or self.homepage_url)
            if action == "switch_tab":
                return self.switch_tab(value or tab.tab_id)
            if action == "close_tab":
                return self.close_tab_by_id(tab.tab_id)
            if action == "open_internal_page":
                return self.open_internal_page(value or "home", tab_id=tab.tab_id)
            if action == "bookmark":
                runtime = self._browser_runtime()
                if runtime is None:
                    return {"ok": False, "error": "Browser runtime is unavailable."}
                return runtime.bookmark_page()
            if action == "resume_after_auth":
                runtime = self._browser_runtime()
                if runtime is None:
                    return {"ok": False, "error": "Browser runtime is unavailable."}
                return runtime.resume_after_auth()
            if action == "clear_annotations":
                return self.clear_annotations(tab_id=tab.tab_id, annotation_id=value)
            if action == "upload":
                return self.upload_files(selector=selector, paths=upload_paths, tab_id=tab.tab_id)
            if action == "decide_permission":
                runtime = self._browser_runtime()
                if runtime is None:
                    return {"ok": False, "error": "Browser runtime is unavailable."}
                origin = _optional_str(payload.get("origin")) or _optional_str(tab.view.url().host()) or _optional_str(tab.view.url().toString())
                feature = _optional_str(payload.get("feature"))
                if not origin or not feature:
                    return {"ok": False, "error": "Permission decision requires origin and feature."}
                return runtime.decide_permission(
                    {
                        "origin": origin,
                        "feature": feature,
                        "decision": value or "prompt",
                        "request_id": _optional_str(payload.get("request_id")),
                        "remember": bool(payload.get("remember", True)),
                    }
                )
            if action == "pause_for_auth":
                runtime = self._browser_runtime()
                if runtime is None:
                    return {"ok": False, "error": "Browser runtime is unavailable."}
                return runtime.pause_for_auth(value or "Authentication required.")
            if action == "scroll":
                script = "window.scrollBy({ top: 640, behavior: 'instant' }); true;"
            elif action == "click" and selector:
                script = f"(() => {{ const node = document.querySelector({json.dumps(selector)}); if (!node) return false; node.click(); return true; }})();"
            elif action == "fill" and selector:
                script = (
                    "(() => {"
                    f"const node = document.querySelector({json.dumps(selector)});"
                    "if (!node) return false;"
                    f"node.value = {json.dumps(value or '')};"
                    "node.dispatchEvent(new Event('input', { bubbles: true }));"
                    "node.dispatchEvent(new Event('change', { bubbles: true }));"
                    "return true;"
                    "})();"
                )
            elif action == "select" and selector:
                script = (
                    "(() => {"
                    f"const node = document.querySelector({json.dumps(selector)});"
                    "if (!node) return false;"
                    f"node.value = {json.dumps(value or '')};"
                    "node.dispatchEvent(new Event('change', { bubbles: true }));"
                    "return true;"
                    "})();"
                )
            else:
                return {"ok": False, "error": f"Unsupported browser action: {action}"}
            result = _run_js_sync(tab.view.page(), script)
            return {"ok": bool(result), "tab_id": tab.tab_id, "action": action}

        def wait_for_state(self, *, selector: str | None = None, text: str | None = None, timeout_seconds: float = 8.0) -> dict[str, Any]:
            deadline = time.time() + max(0.2, float(timeout_seconds or 0.0))
            needle = " ".join(str(text or "").strip().lower().split())
            while time.time() < deadline:
                snapshot = self.query_dom(selector=selector, include_text=True)
                haystack = " ".join(
                    str(snapshot.get(key) or "").strip().lower()
                    for key in ("text", "title", "url", "value")
                )
                if selector and snapshot.get("found"):
                    return {"ok": True, "matched": "selector", "snapshot": snapshot}
                if needle and needle in haystack:
                    return {"ok": True, "matched": "text", "snapshot": snapshot}
                QApplication.processEvents()
                time.sleep(0.1)
            return {"ok": False, "matched": None}

        def snapshot(self) -> dict[str, Any]:
            active_tab = self.active_tab()
            active_url = None
            if active_tab is not None:
                url_getter = getattr(active_tab.view, "url", None)
                if callable(url_getter):
                    try:
                        active_url = _optional_str(url_getter().toString())
                    except Exception:
                        active_url = None
            if active_tab is not None and (active_tab.internal_page or not active_url):
                dom = {
                    "url": self._visible_url(active_tab),
                    "title": self._visible_title(active_tab),
                    "text": None,
                }
            else:
                dom = self.query_dom(include_text=True)
            return {
                "runtime": "aoryn_browser",
                "status": "ready",
                "url": dom.get("url"),
                "title": dom.get("title"),
                "text": dom.get("text"),
                "active_tab_id": active_tab.tab_id if active_tab is not None else None,
                "tab_count": self.tabs.count(),
                "window_id": self.window_id,
                "current_internal_page": active_tab.internal_page if active_tab is not None else None,
                "tabs": self.serialize_tabs(),
                "annotations": self._annotation_snapshot(active_tab.tab_id if active_tab is not None else None),
            }

        def serialize_tabs(self) -> list[dict[str, Any]]:
            tabs: list[dict[str, Any]] = []
            active = self.active_tab()
            active_id = active.tab_id if active is not None else None
            runtime = self._browser_runtime()
            for item in self._tab_refs:
                tabs.append(
                    {
                        "tab_id": item.tab_id,
                        "url": self._visible_url(item),
                        "title": self._visible_title(item),
                        "internal_page": item.internal_page,
                        "is_active": item.tab_id == active_id,
                        "annotation_count": len(runtime.annotations_for_tab(item.tab_id)) if runtime is not None else 0,
                    }
                )
            return tabs

        def refresh_internal_tabs(self) -> None:
            active = self.active_tab()
            active_id = active.tab_id if active is not None else None
            for item in list(self._tab_refs):
                if item.internal_page:
                    self._render_internal_page(item, f"aoryn://{item.internal_page}")
            if active_id:
                self.switch_tab(active_id)

        def _resolve_tab(self, tab_id: str | None) -> _BrowserTab | None:
            if tab_id:
                for item in self._tab_refs:
                    if item.tab_id == tab_id:
                        return item
            return self.active_tab()

        def _close_tab(self, index: int) -> None:
            widget = self.tabs.widget(index)
            if widget is None:
                return
            self.tabs.removeTab(index)
            self._tab_refs = [item for item in self._tab_refs if item.view is not widget]
            widget.deleteLater()
            self._sync_tab_chrome()
            self._refresh_title()
            runtime = self._browser_runtime()
            if runtime is not None:
                runtime.schedule_persist_state()
            if self.tabs.count() == 0:
                self.open_tab(self.homepage_url)

        def _update_tab_title(self, tab_id: str, title: str) -> None:
            for index, item in enumerate(self._tab_refs):
                if item.tab_id == tab_id:
                    if item.internal_page:
                        self.tabs.setTabText(index, "" if item.internal_page == "home" else INTERNAL_PAGE_TITLES.get(item.internal_page, ""))
                    else:
                        self.tabs.setTabText(index, title or "")
                    break
            self._sync_tab_chrome()
            self._refresh_title()

        def _refresh_title(self) -> None:
            active = self.active_tab()
            title = self._visible_title(active) if active is not None else None
            self.setWindowTitle(f"{APP_NAME} Browser" + (f" - {title}" if _optional_str(title) else ""))

        def _handle_current_tab_changed(self, _index: int) -> None:
            self._sync_tab_strip_selection()
            self._refresh_title()
            self._sync_address_bar()
            self._refresh_assistant_context()

        def _handle_tab_strip_changed(self, index: int) -> None:
            if index < 0 or index == self.tabs.currentIndex():
                return
            self.tabs.setCurrentIndex(index)

        def _handle_url_changed(self, tab_id: str, url: QUrl) -> None:
            item = self._resolve_tab(tab_id)
            if item is None:
                return
            if not item.internal_page:
                item.display_url = url.toString() or item.display_url
            self._sync_address_bar()
            self._refresh_title()

        def _handle_load_finished(self, tab_id: str, ok: bool) -> None:
            item = self._resolve_tab(tab_id)
            if item is None or item.internal_page or not ok:
                return
            runtime = self._browser_runtime()
            if runtime is None:
                return
            runtime._record_history(
                url=_optional_str(item.view.url().toString()),
                title=_optional_str(item.view.title()),
            )
            runtime.maybe_pause_for_handoff(
                url=_optional_str(item.view.url().toString()),
                title=_optional_str(item.view.title()),
            )
            runtime.reapply_annotations(tab_id)
            runtime.schedule_persist_state()
            self._refresh_assistant_context()

        def _open_internal_target(self, tab_id: str, target: str) -> None:
            command = _internal_browser_page_name(target) or ""
            if command == "focus-address":
                parsed = urlparse(target)
                submitted = _optional_str((parse_qs(parsed.query).get("query") or [None])[0])
                if submitted:
                    self.address_bar.setText(submitted)
                    self._navigate_from_address_bar()
                    return
                self._focus_address_bar()
                return
            self.open_internal_page(_internal_browser_page_name(target) or "home", tab_id=tab_id)

        def _render_internal_page(self, tab: _BrowserTab, target_url: str) -> dict[str, Any]:
            page_name = _internal_browser_page_name(target_url) or "home"
            runtime = self._browser_runtime()
            if runtime is None:
                title, document = build_internal_page_html(page_name)
            else:
                title, document = runtime.render_internal_page(page_name)
            tab.internal_page = page_name
            tab.display_url = f"aoryn://{page_name}"
            tab.view.setHtml(document, QUrl("about:blank") if page_name == "home" else QUrl(tab.display_url))
            self._update_tab_title(tab.tab_id, title)
            self._sync_tab_chrome()
            self._sync_address_bar()
            self._refresh_title()
            if runtime is not None:
                runtime.schedule_persist_state()
            self._refresh_assistant_context()
            return {
                "window_id": self.window_id,
                "tab_id": tab.tab_id,
                "url": tab.display_url,
                "title": title,
                "internal_page": page_name,
            }

        def _sync_address_bar(self) -> None:
            active = self.active_tab()
            if active is None:
                self.address_bar.setText("")
                return
            self.address_bar.setText(self._visible_url(active) or "")

        def _navigate_from_address_bar(self) -> None:
            self.navigate(self.address_bar.text())

        def _focus_address_bar(self) -> None:
            self.address_bar.setFocus()
            self.address_bar.selectAll()

        def _tab_index(self, tab: _BrowserTab) -> int:
            for index, item in enumerate(self._tab_refs):
                if item.tab_id == tab.tab_id:
                    return index
            return -1

        def _visible_url(self, tab: _BrowserTab | None) -> str | None:
            if tab is None:
                return None
            if tab.internal_page:
                if tab.internal_page == "home":
                    return ""
                return tab.display_url or f"aoryn://{tab.internal_page}"
            url_getter = getattr(tab.view, "url", None)
            if callable(url_getter):
                try:
                    return _optional_str(url_getter().toString()) or tab.display_url
                except Exception:
                    return tab.display_url
            return tab.display_url

        def _visible_title(self, tab: _BrowserTab | None) -> str | None:
            if tab is None:
                return None
            if tab.internal_page:
                return "" if tab.internal_page == "home" else INTERNAL_PAGE_TITLES.get(tab.internal_page, "Page")
            title_getter = getattr(tab.view, "title", None)
            if callable(title_getter):
                try:
                    return _optional_str(title_getter()) or ""
                except Exception:
                    return ""
            return ""

        def _fallback_tab_title(self, normalized_url: str) -> str:
            parsed = urlparse(normalized_url or "")
            host = parsed.netloc.lower().removeprefix("www.")
            if host:
                return host
            if parsed.path:
                return parsed.path
            return normalized_url or ""

        def _tab_strip_label(self, item: _BrowserTab, index: int) -> str:
            if item.internal_page == "home":
                return "New Tab"
            title = self.tabs.tabText(index)
            if title:
                return title
            if item.internal_page:
                return INTERNAL_PAGE_TITLES.get(item.internal_page, "Page")
            return self._fallback_tab_title(_optional_str(item.display_url) or "")

        def _tab_strip_icon(self, item: _BrowserTab) -> QIcon:
            if item.internal_page == "home":
                return browser_chrome_icon("home", size=18)
            icon_getter = getattr(item.view, "icon", None)
            page_icon = icon_getter() if callable(icon_getter) else None
            if page_icon is not None and not page_icon.isNull():
                return page_icon
            return QIcon()

        def _sync_tab_strip_selection(self) -> None:
            current_index = self.tabs.currentIndex()
            if current_index < 0 or current_index == self.tab_strip.currentIndex():
                return
            self.tab_strip.blockSignals(True)
            self.tab_strip.setCurrentIndex(current_index)
            self.tab_strip.blockSignals(False)

        def _sync_tab_chrome(self) -> None:
            single_home = len(self._tab_refs) == 1 and self._tab_refs[0].internal_page == "home"
            self.tab_strip_shell.setVisible(not single_home)
            self.tab_strip.setVisible(not single_home)

            self.tab_strip.blockSignals(True)
            while self.tab_strip.count() > 0:
                self.tab_strip.removeTab(self.tab_strip.count() - 1)
            for index, item in enumerate(self._tab_refs):
                if index >= self.tabs.count():
                    break
                tab_index = self.tab_strip.addTab(self._tab_strip_icon(item), self._tab_strip_label(item, index))
                self.tab_strip.setTabToolTip(tab_index, self._visible_title(item) or item.display_url or "")
            self._sync_tab_strip_selection()
            self.tab_strip.blockSignals(False)

            if hasattr(QTabBar, "ButtonPosition"):
                button_position = QTabBar.ButtonPosition.RightSide
            else:
                button_position = QTabBar.RightSide
            for index, item in enumerate(self._tab_refs):
                if index >= self.tab_strip.count():
                    break
                close_button = self.tab_strip.tabButton(index, button_position)
                if close_button is not None:
                    close_button.setVisible(item.internal_page != "home")

        def _annotation_snapshot(self, tab_id: str | None) -> list[dict[str, Any]]:
            runtime = self._browser_runtime()
            if runtime is None or not tab_id:
                return []
            return runtime.annotations_for_tab(tab_id)

        def _handle_permission_request(self, tab_id: str, page, security_origin, feature) -> None:
            runtime = self._browser_runtime()
            if runtime is None:
                return
            runtime.register_permission_request(
                tab_id=tab_id,
                page=page,
                security_origin=security_origin,
                feature=feature,
            )

        def _browser_runtime(self):
            return getattr(self, "_browser_runtime_ref", None)

        def closeEvent(self, event: QCloseEvent) -> None:
            runtime = self._browser_runtime()
            if runtime is not None:
                runtime.unregister_window(self.window_id)
            super().closeEvent(event)


    class AorynBrowserRuntime:
        def __init__(self, *, profile_root: Path, port: int, icon_path: Path, config_path: Path | None = None) -> None:
            self.profile_root = profile_root
            self.port = port
            self.icon_path = icon_path
            self.config_path = discover_config_path(config_path)
            self.homepage_url = DEFAULT_BROWSER_HOMEPAGE
            self.search_url = DEFAULT_BROWSER_SEARCH_URL
            self.dispatcher = _UiDispatcher()
            self.profile = self._build_profile()
            self.windows: dict[str, BrowserWindow] = {}
            state = load_browser_state(self.profile_root)
            self.bookmarks: list[dict[str, Any]] = [dict(item) for item in state.get("bookmarks", [])]
            self.downloads: list[dict[str, Any]] = [dict(item) for item in state.get("downloads", [])]
            self.history: list[dict[str, Any]] = [dict(item) for item in state.get("history", [])]
            self.annotations: list[dict[str, Any]] = normalize_annotation_entries(state.get("annotations"))
            self.permissions: list[dict[str, Any]] = normalize_permission_entries(state.get("permissions"))
            self.permission_requests: list[dict[str, Any]] = normalize_permission_request_entries(state.get("permission_requests"))
            self.handoffs: list[dict[str, Any]] = normalize_handoff_entries(state.get("handoffs"))
            self.auth_pause_reason: str | None = _optional_str(state.get("auth_pause_reason"))
            self._live_permission_requests: dict[str, dict[str, Any]] = {}
            self._restored_windows: list[dict[str, Any]] = [dict(item) for item in state.get("windows", [])]
            self._assistant_setup_cache: dict[str, Any] | None = None
            self._persist_timer = QTimer()
            self._persist_timer.setSingleShot(True)
            self._persist_timer.timeout.connect(self._persist_state)
            self.profile.downloadRequested.connect(self.register_download)
            self.server = self._build_server()
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)

        def start(self, *, initial_url: str | None = None) -> None:
            restore_ok = False
            normalized = normalize_browser_target(initial_url, homepage=self.homepage_url, search_url=self.search_url)
            if normalized == self.homepage_url:
                restore_ok = self._restore_session()
            if not restore_ok:
                self.open_window(normalized)
            self.server_thread.start()

        def shutdown(self) -> None:
            self._persist_state()
            try:
                self.server.shutdown()
            except Exception:
                pass

        def _dashboard_app(self):
            from desktop_agent.dashboard import DashboardApp

            return DashboardApp(host="127.0.0.1", port=0, config_path=self.config_path)

        def assistant_setup_snapshot(self) -> dict[str, Any]:
            if self._assistant_setup_cache is None:
                self._assistant_setup_cache = build_browser_assistant_setup_snapshot(self.config_path)
            return dict(self._assistant_setup_cache)

        def assistant_provider_snapshot(self) -> dict[str, Any]:
            try:
                app = self._dashboard_app()
                payload = app.provider_models({})
                return {"ok": True, **payload}
            except Exception as exc:
                return {"ok": False, "error": str(exc)}

        def update_assistant_settings(self, payload: dict[str, Any] | None) -> dict[str, Any]:
            try:
                app = self._dashboard_app()
                runtime_snapshot = app.runtime_preferences.snapshot()
                current = dict(runtime_snapshot.get("config_overrides") or {}) if isinstance(runtime_snapshot, dict) else {}
                allowed_keys = {
                    "model_provider",
                    "model_base_url",
                    "model_name",
                    "model_api_key",
                    "model_auto_discover",
                    "browser_channel",
                    "browser_executable_path",
                    "browser_headless",
                }
                incoming = dict(payload or {})
                for key in allowed_keys:
                    if key not in incoming:
                        continue
                    value = incoming.get(key)
                    if isinstance(value, str):
                        value = value.strip()
                    if value in {None, ""} and key not in {"model_auto_discover", "browser_headless"}:
                        current.pop(key, None)
                        continue
                    current[key] = value
                app.runtime_preferences.update(config_overrides=current)
                self._assistant_setup_cache = None
                self.refresh_ai_surfaces()
                self.schedule_internal_page_refresh()
                return {"ok": True, "snapshot": self.assistant_setup_snapshot()}
            except Exception as exc:
                return {"ok": False, "error": str(exc)}

        def ask_assistant(self, *, prompt: str, snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
            try:
                app = self._dashboard_app()
                request_message = build_browser_assistant_user_message(snapshot, prompt)
                reply = app.chat_reply(
                    messages=[{"role": "user", "content": request_message}],
                    config_overrides={},
                    session_meta={"locale": "zh-CN" if any("\u4e00" <= char <= "\u9fff" for char in prompt) else "en-US"},
                )
                return {"ok": True, **reply}
            except Exception as exc:
                return {"ok": False, "error": str(exc)}

        def _resolved_transport(self) -> str:
            try:
                config = load_agent_config(self.config_path)
                return _optional_str(getattr(config, "browser_runtime_transport", None)) or "local_http"
            except Exception:
                return "local_http"

        def _service_summary_payload(self, *, transport: str) -> dict[str, Any]:
            window = self._active_window()
            snapshot = window.snapshot() if window is not None else {}
            runtime_status = "paused_for_auth" if self.auth_pause_reason else ("ready" if self.windows else "starting")
            return build_browser_service_summary(
                base_url=f"http://127.0.0.1:{self.port}",
                transport=transport,
                status=runtime_status,
                window_count=len(self.windows),
                tab_count=len(self._list_tabs()),
                active_title=_optional_str(snapshot.get("title")),
                active_url=_optional_str(snapshot.get("url")),
                pending_permissions=len(self.permission_requests),
                handoff_count=len(self.handoffs),
                annotation_count=len(self.annotations),
                auth_pause_reason=self.auth_pause_reason,
            )

        def service_summary(self) -> dict[str, Any]:
            transport = self._resolved_transport()
            return self.dispatcher.invoke(lambda: self._service_summary_payload(transport=transport))

        def refresh_ai_surfaces(self) -> None:
            def _refresh() -> None:
                for window in list(self.windows.values()):
                    try:
                        window.refresh_assistant_setup_state()
                    except Exception:
                        continue

            if threading.current_thread() is threading.main_thread():
                _refresh()
                return
            self.dispatcher.invoke(_refresh)

        def open_window(self, url: str | None = None) -> dict[str, Any]:
            def _create() -> dict[str, Any]:
                window = BrowserWindow(
                    profile=self.profile,
                    icon_path=self.icon_path,
                    homepage_url=self.homepage_url,
                    search_url=self.search_url,
                )
                window._browser_runtime_ref = self  # type: ignore[attr-defined]
                payload = window.open_tab(url or self.homepage_url)
                self.windows[window.window_id] = window
                window.show()
                self.schedule_persist_state()
                return {"window_id": window.window_id, **payload}

            return self.dispatcher.invoke(_create)

        def open_tab(self, url: str | None = None) -> dict[str, Any]:
            def _open() -> dict[str, Any]:
                window = self._active_window()
                if window is None:
                    return self.open_window(url)
                payload = window.open_tab(url or self.homepage_url)
                self.schedule_persist_state()
                return {"window_id": window.window_id, **payload}

            return self.dispatcher.invoke(_open)

        def open_internal_page(self, page_name: str) -> dict[str, Any]:
            return self.dispatcher.invoke(
                lambda: (self._active_window() or self._require_window()).open_internal_page(page_name)
            )

        def switch_tab(self, tab_id: str) -> dict[str, Any]:
            return self.dispatcher.invoke(lambda: (self._active_window() or self._require_window()).switch_tab(tab_id))

        def close_tab(self, tab_id: str | None = None) -> dict[str, Any]:
            def _close() -> dict[str, Any]:
                window = self._window_for_tab(tab_id) if tab_id else self._active_window()
                target = window or self._require_window()
                return target.close_tab_by_id(tab_id)

            return self.dispatcher.invoke(_close)

        def navigate(self, url: str, *, tab_id: str | None = None) -> dict[str, Any]:
            def _navigate() -> dict[str, Any]:
                window = self._window_for_tab(tab_id) if tab_id else self._active_window()
                if window is None:
                    return self.open_window(url)
                return window.navigate(url, tab_id=tab_id)

            return self.dispatcher.invoke(_navigate)

        def status(self) -> BrowserObservation:
            def _status() -> BrowserObservation:
                window = self._active_window()
                snapshot = window.snapshot() if window is not None else {}
                return BrowserObservation.from_dict(
                    {
                        **snapshot,
                        "status": "paused_for_auth" if self.auth_pause_reason else "ready",
                        "downloads": self.downloads[-20:],
                        "bookmarks": self.bookmarks[-20:],
                        "history": self.history[-50:],
                        "annotations": snapshot.get("annotations") or [],
                        "tabs": snapshot.get("tabs") or [],
                        "permissions": self.permissions[-40:],
                        "permission_requests": self.permission_requests[-20:],
                        "handoffs": self.handoffs[-20:],
                        "auth_pause_reason": self.auth_pause_reason,
                    }
                )

            return self.dispatcher.invoke(_status)

        def query_dom(self, payload: dict[str, Any]) -> dict[str, Any]:
            return self.dispatcher.invoke(
                lambda: (self._active_window() or self._require_window()).query_dom(
                    selector=_optional_str(payload.get("selector")),
                    include_text=bool(payload.get("include_text", True)),
                )
            )

        def query_accessibility(self) -> dict[str, Any]:
            return self.dispatcher.invoke(lambda: (self._active_window() or self._require_window()).query_accessibility())

        def annotate_page(self, payload: dict[str, Any]) -> dict[str, Any]:
            def _annotate() -> dict[str, Any]:
                tab_id = _optional_str(payload.get("tab_id"))
                window = self._window_for_tab(tab_id) if tab_id else self._active_window()
                target = window or self._require_window()
                return target.annotate_page(
                    selector=_optional_str(payload.get("selector")),
                    label=_optional_str(payload.get("label")),
                )

            return self.dispatcher.invoke(_annotate)

        def list_tabs(self) -> dict[str, Any]:
            return self.dispatcher.invoke(lambda: {"tabs": self._list_tabs()})

        def list_annotations(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
            request = payload or {}
            return {
                "annotations": self.annotations_for_tab(_optional_str(request.get("tab_id")))
                if _optional_str(request.get("tab_id"))
                else list(self.annotations)
            }

        def clear_annotations(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
            request = payload or {}
            def _clear() -> dict[str, Any]:
                tab_id = _optional_str(request.get("tab_id"))
                window = self._window_for_tab(tab_id) if tab_id else self._active_window()
                target = window or self._require_window()
                return target.clear_annotations(
                    tab_id=tab_id,
                    annotation_id=_optional_str(request.get("annotation_id")),
                )

            return self.dispatcher.invoke(_clear)

        def perform_action(self, payload: dict[str, Any]) -> dict[str, Any]:
            def _perform() -> dict[str, Any]:
                tab_id = _optional_str(payload.get("tab_id"))
                window = self._window_for_tab(tab_id) if tab_id else self._active_window()
                target = window or self._require_window()
                return target.perform_action(payload)

            return self.dispatcher.invoke(_perform)

        def wait_for_state(self, payload: dict[str, Any]) -> dict[str, Any]:
            return self.dispatcher.invoke(
                lambda: (self._active_window() or self._require_window()).wait_for_state(
                    selector=_optional_str(payload.get("selector")),
                    text=_optional_str(payload.get("text")),
                    timeout_seconds=float(payload.get("timeout_seconds", 8.0) or 8.0),
                )
            )

        def collect_downloads(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
            request = payload or {}
            state_filter = normalize_download_state_name(request.get("state")) if request.get("state") is not None else None
            downloads = [
                dict(item)
                for item in self.downloads
                if state_filter is None or normalize_download_state_name(item.get("state")) == state_filter
            ]
            return {"downloads": downloads}

        def wait_for_download(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
            request = payload or {}
            timeout_seconds = float(request.get("timeout_seconds", 12.0) or 12.0)
            expected_state = normalize_download_state_name(request.get("state") or "completed")
            deadline = time.time() + max(0.2, timeout_seconds)
            while time.time() < deadline:
                downloads = self.collect_downloads({"state": expected_state}).get("downloads", [])
                if downloads:
                    return {"ok": True, "download": downloads[-1], "state": expected_state}
                QApplication.processEvents()
                time.sleep(0.1)
            return {"ok": False, "download": None, "state": expected_state}

        def list_permissions(self) -> dict[str, Any]:
            return {"permissions": list(self.permissions)}

        def list_permission_requests(self) -> dict[str, Any]:
            return {"permission_requests": list(self.permission_requests)}

        def decide_permission(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
            request = payload or {}
            request_id = _optional_str(request.get("request_id"))
            origin = _optional_str(request.get("origin"))
            feature = _optional_str(request.get("feature"))
            decision = normalize_permission_decision(request.get("decision"))
            remember = bool(request.get("remember", True))
            if request_id:
                pending = next((item for item in self.permission_requests if item.get("request_id") == request_id), None)
                if pending is not None:
                    origin = origin or _optional_str(pending.get("origin"))
                    feature = feature or _optional_str(pending.get("feature"))
            if not origin or not feature:
                return {"ok": False, "error": "origin and feature are required."}
            entry = None
            if remember:
                entry = {
                    "origin": origin,
                    "feature": feature,
                    "decision": decision,
                    "updated_at": time.time(),
                }
                self.permissions = [
                    item
                    for item in self.permissions
                    if not (item.get("origin") == origin and item.get("feature") == feature)
                ]
                self.permissions.append(entry)
            self._resolve_permission_request(request_id=request_id, origin=origin, feature=feature, decision=decision)
            self.schedule_persist_state()
            self.schedule_internal_page_refresh()
            return {"ok": True, "entry": entry, "decision": decision}

        def bookmark_page(self) -> dict[str, Any]:
            def _bookmark() -> dict[str, Any]:
                window = self._active_window() or self._require_window()
                snapshot = window.snapshot()
                entry = {
                    "title": snapshot.get("title"),
                    "url": snapshot.get("url"),
                    "created_at": time.time(),
                }
                if entry["url"] and not any(bookmark.get("url") == entry["url"] for bookmark in self.bookmarks):
                    self.bookmarks.append(entry)
                    self.schedule_persist_state()
                    self.refresh_internal_pages()
                return {"bookmarked": bool(entry["url"]), "entry": entry, "ok": bool(entry["url"])}

            return self.dispatcher.invoke(_bookmark)

        def pause_for_auth(self, reason: str | None = None) -> dict[str, Any]:
            self.auth_pause_reason = _optional_str(reason) or "Authentication required."
            snapshot = self.dispatcher.invoke(
                lambda: (self._active_window() or self._require_window()).snapshot()
            )
            self.record_handoff(
                kind="auth_pause",
                reason=self.auth_pause_reason,
                url=_optional_str(snapshot.get("url")),
                title=_optional_str(snapshot.get("title")),
            )
            self.schedule_internal_page_refresh()
            self.schedule_persist_state()
            return {"paused": True, "reason": self.auth_pause_reason}

        def resume_after_auth(self) -> dict[str, Any]:
            self.auth_pause_reason = None
            self.schedule_internal_page_refresh()
            self.schedule_persist_state()
            return {"ok": True, "paused": False}

        def snapshot(self) -> dict[str, Any]:
            return self.status().to_dict()

        def session_state(self) -> dict[str, Any]:
            transport = self._resolved_transport()
            return self.dispatcher.invoke(
                lambda: {
                    "windows": self._serialize_windows(),
                    "tabs": self._list_tabs(),
                    "bookmarks": list(self.bookmarks),
                    "downloads": list(self.downloads),
                    "history": list(self.history),
                    "annotations": list(self.annotations),
                    "permissions": list(self.permissions),
                    "permission_requests": list(self.permission_requests),
                    "handoffs": list(self.handoffs),
                    "auth_pause_reason": self.auth_pause_reason,
                    "service": self._service_summary_payload(transport=transport),
                }
            )

        def register_download(self, item: QWebEngineDownloadRequest) -> None:
            entry = {
                "download_id": uuid.uuid4().hex[:8],
                "path": item.downloadDirectory() + "/" + item.downloadFileName(),
                "file_name": item.downloadFileName(),
                "url": item.url().toString(),
                "created_at": time.time(),
                "state": "requested",
                "received_bytes": 0,
                "total_bytes": 0,
            }
            self.downloads.append(entry)
            self._attach_download_observers(item, entry["download_id"])
            self.schedule_persist_state()
            self.schedule_internal_page_refresh()
            item.accept()

        def unregister_window(self, window_id: str) -> None:
            self.windows.pop(window_id, None)
            self.schedule_persist_state()

        def register_annotation(self, annotation: dict[str, Any]) -> None:
            tab_id = _optional_str(annotation.get("tab_id"))
            annotation_id = _optional_str(annotation.get("annotation_id"))
            selector = _optional_str(annotation.get("selector"))
            if not tab_id or not annotation_id or not selector:
                return
            self.clear_registered_annotations(tab_id, annotation_id=annotation_id, persist=False)
            self.annotations.append(
                {
                    "tab_id": tab_id,
                    "annotation_id": annotation_id,
                    "selector": selector,
                    "label": _optional_str(annotation.get("label")) or annotation_id,
                    "created_at": float(annotation.get("created_at", time.time()) or time.time()),
                }
            )
            self.schedule_persist_state()

        def register_permission_request(self, *, tab_id: str, page, security_origin, feature) -> None:
            origin = _optional_str(getattr(security_origin, "toString", lambda: None)()) or _optional_str(security_origin)
            feature_name = normalize_permission_feature_name(feature)
            if not origin:
                return
            stored = next(
                (
                    item
                    for item in self.permissions
                    if item.get("origin") == origin and item.get("feature") == feature_name
                ),
                None,
            )
            if stored is not None:
                self._apply_permission_to_page(page, security_origin, feature, stored.get("decision"))
                return
            request_id = uuid.uuid4().hex[:8]
            entry = {
                "request_id": request_id,
                "origin": origin,
                "feature": feature_name,
                "tab_id": tab_id,
                "requested_at": time.time(),
            }
            self.permission_requests.append(entry)
            del self.permission_requests[:-50]
            self._live_permission_requests[request_id] = {
                "page": page,
                "security_origin": security_origin,
                "feature": feature,
                "origin": origin,
                "feature_name": feature_name,
            }
            self.record_handoff(
                kind="permission_request",
                reason=f"{feature_name} permission requires review.",
                url=origin,
                title=None,
            )
            self.schedule_persist_state()
            self.schedule_internal_page_refresh()

        def record_handoff(self, *, kind: str, reason: str, url: str | None = None, title: str | None = None) -> None:
            self.handoffs.append(
                {
                    "kind": kind,
                    "reason": reason,
                    "url": _optional_str(url),
                    "title": _optional_str(title),
                    "created_at": time.time(),
                }
            )
            del self.handoffs[:-50]
            self.schedule_persist_state()
            self.schedule_internal_page_refresh()

        def maybe_pause_for_handoff(self, *, url: str | None, title: str | None, text: str | None = None) -> str | None:
            reason = detect_browser_handoff_reason(url=url, title=title, text=text)
            if not reason:
                return None
            if self.auth_pause_reason == reason:
                return reason
            self.auth_pause_reason = reason
            self.record_handoff(kind="detected_auth", reason=reason, url=url, title=title)
            return reason

        def clear_registered_annotations(self, tab_id: str, *, annotation_id: str | None = None, persist: bool = True) -> None:
            kept: list[dict[str, Any]] = []
            removed = False
            for item in self.annotations:
                if item.get("tab_id") != tab_id:
                    kept.append(item)
                    continue
                if annotation_id and item.get("annotation_id") != annotation_id:
                    kept.append(item)
                    continue
                removed = True
            self.annotations = kept
            if removed and persist:
                self.schedule_persist_state()

        def annotations_for_tab(self, tab_id: str | None) -> list[dict[str, Any]]:
            if not tab_id:
                return []
            return [dict(item) for item in self.annotations if item.get("tab_id") == tab_id]

        def reapply_annotations(self, tab_id: str) -> None:
            window = self._window_for_tab(tab_id)
            if window is None:
                return
            tab = window._resolve_tab(tab_id)
            if tab is None or tab.internal_page:
                return
            for annotation in self.annotations_for_tab(tab_id):
                _run_js_sync(
                    tab.view.page(),
                    build_annotation_overlay_script(
                        selector=_optional_str(annotation.get("selector")),
                        label=_optional_str(annotation.get("label")) or _optional_str(annotation.get("annotation_id")),
                        annotation_id=_optional_str(annotation.get("annotation_id")) or uuid.uuid4().hex[:8],
                    ),
                )

        def _resolve_permission_request(
            self,
            *,
            request_id: str | None,
            origin: str,
            feature: str,
            decision: str,
        ) -> None:
            matched_request_id = request_id
            if matched_request_id is None:
                matched = next(
                    (
                        item
                        for item in self.permission_requests
                        if item.get("origin") == origin and item.get("feature") == feature
                    ),
                    None,
                )
                matched_request_id = _optional_str(matched.get("request_id")) if matched is not None else None
            if matched_request_id:
                live = self._live_permission_requests.pop(matched_request_id, None)
                if live is not None:
                    self._apply_permission_to_page(
                        live.get("page"),
                        live.get("security_origin"),
                        live.get("feature"),
                        decision,
                    )
                self.permission_requests = [
                    item for item in self.permission_requests if item.get("request_id") != matched_request_id
                ]

        def _apply_permission_to_page(self, page, security_origin, feature, decision: Any) -> None:
            normalized = normalize_permission_decision(decision)
            policy = None
            enum_container = getattr(QWebEnginePage, "PermissionPolicy", None)
            name_map = {
                "allow": ("PermissionGrantedByUser", "GrantedByUser"),
                "deny": ("PermissionDeniedByUser", "DeniedByUser"),
                "prompt": ("PermissionUnknown", "AskEveryTime", "Unknown"),
            }
            for name in name_map.get(normalized, name_map["prompt"]):
                if enum_container is not None and hasattr(enum_container, name):
                    policy = getattr(enum_container, name)
                    break
                if hasattr(QWebEnginePage, name):
                    policy = getattr(QWebEnginePage, name)
                    break
            setter = getattr(page, "setFeaturePermission", None)
            if callable(setter) and policy is not None:
                try:
                    setter(security_origin, feature, policy)
                except Exception:
                    return

        def _attach_download_observers(self, item: QWebEngineDownloadRequest, download_id: str) -> None:
            def _safe_update(*_args) -> None:
                self._update_download_from_request(item, download_id)

            for signal_name in ("receivedBytesChanged", "totalBytesChanged", "stateChanged", "isFinishedChanged"):
                signal = getattr(item, signal_name, None)
                connect = getattr(signal, "connect", None)
                if callable(connect):
                    connect(_safe_update)

        def _update_download_from_request(self, item: QWebEngineDownloadRequest, download_id: str) -> None:
            state_name = "requested"
            state_value = getattr(item, "state", None)
            if callable(state_value):
                try:
                    raw_state = state_value()
                    state_name = getattr(raw_state, "name", None) or str(raw_state)
                except Exception:
                    state_name = "requested"
            updated = False
            for entry in self.downloads:
                if entry.get("download_id") != download_id:
                    continue
                entry["state"] = normalize_download_state_name(state_name)
                received = getattr(item, "receivedBytes", None)
                total = getattr(item, "totalBytes", None)
                entry["received_bytes"] = int(received() if callable(received) else entry.get("received_bytes", 0) or 0)
                entry["total_bytes"] = int(total() if callable(total) else entry.get("total_bytes", 0) or 0)
                updated = True
                break
            if updated:
                self.schedule_persist_state()
                self.schedule_internal_page_refresh()

        def _active_window(self) -> BrowserWindow | None:
            for window in self.windows.values():
                if window.isActiveWindow():
                    return window
            return next(iter(self.windows.values()), None)

        def _window_for_tab(self, tab_id: str | None) -> BrowserWindow | None:
            if not tab_id:
                return None
            for window in self.windows.values():
                if window._resolve_tab(tab_id) is not None:
                    return window
            return None

        def _require_window(self) -> BrowserWindow:
            window = self._active_window()
            if window is None:
                raise BrowserRuntimeError("No browser window is available.")
            return window

        def _record_history(self, *, url: str | None, title: str | None) -> None:
            if not url or is_internal_browser_url(url):
                return
            entry = {"url": url, "title": title, "visited_at": time.time()}
            if self.history and self.history[-1].get("url") == url:
                self.history[-1] = entry
                return
            self.history.append(entry)
            del self.history[:-200]
            self.schedule_internal_page_refresh()

        def _build_profile(self) -> QWebEngineProfile:
            self.profile_root.mkdir(parents=True, exist_ok=True)
            storage_path = self.profile_root / "storage"
            cache_path = self.profile_root / "cache"
            storage_path.mkdir(parents=True, exist_ok=True)
            cache_path.mkdir(parents=True, exist_ok=True)
            profile = QWebEngineProfile("AorynBrowser", QApplication.instance())
            profile.setPersistentStoragePath(str(storage_path))
            profile.setCachePath(str(cache_path))
            profile.setDownloadPath(str(self.profile_root / "downloads"))
            return profile

        def render_internal_page(self, page_name: str) -> tuple[str, str]:
            if (page_name or "").strip().lower() == "home":
                return build_internal_page_html("home")
            return build_internal_page_html(
                page_name,
                history=self.history,
                bookmarks=self.bookmarks,
                downloads=self.downloads,
                permissions=self.permissions,
                permission_requests=self.permission_requests,
                handoffs=self.handoffs,
                auth_pause_reason=self.auth_pause_reason,
                assistant_setup=self.assistant_setup_snapshot().get("summary"),
                service_summary=self.service_summary(),
            )

        def refresh_internal_pages(self) -> None:
            for window in list(self.windows.values()):
                window.refresh_internal_tabs()

        def schedule_internal_page_refresh(self) -> None:
            if threading.current_thread() is threading.main_thread():
                self.refresh_internal_pages()
                return
            self.dispatcher.invoke(self.refresh_internal_pages)

        def schedule_persist_state(self) -> None:
            if threading.current_thread() is threading.main_thread():
                self._persist_timer.start(200)
                return
            self.dispatcher.invoke(lambda: self._persist_timer.start(200))

        def _persist_state(self) -> None:
            save_browser_state(
                self.profile_root,
                {
                    "bookmarks": self.bookmarks,
                    "downloads": self.downloads,
                    "history": self.history,
                    "windows": self._serialize_windows(),
                    "annotations": self.annotations,
                    "permissions": self.permissions,
                    "permission_requests": self.permission_requests,
                    "handoffs": self.handoffs,
                    "auth_pause_reason": self.auth_pause_reason,
                },
            )

        def _serialize_windows(self) -> list[dict[str, Any]]:
            windows: list[dict[str, Any]] = []
            for window in self.windows.values():
                active_tab = window.active_tab()
                windows.append(
                    {
                        "window_id": window.window_id,
                        "tabs": window.serialize_tabs(),
                        "active_tab_id": active_tab.tab_id if active_tab is not None else None,
                    }
                )
            return windows

        def _list_tabs(self) -> list[dict[str, Any]]:
            tabs: list[dict[str, Any]] = []
            for window in self.windows.values():
                for item in window.serialize_tabs():
                    tabs.append({**item, "window_id": window.window_id})
            return tabs

        def _restore_session(self) -> bool:
            if not self._restored_windows:
                return False
            restored_any = False
            for window_state in self._restored_windows:
                tabs = [dict(item) for item in window_state.get("tabs", []) if isinstance(item, dict)]
                if not tabs:
                    continue
                window = BrowserWindow(
                    profile=self.profile,
                    icon_path=self.icon_path,
                    homepage_url=self.homepage_url,
                    search_url=self.search_url,
                )
                window._browser_runtime_ref = self  # type: ignore[attr-defined]
                self.windows[window.window_id] = window
                active_tab_id = _optional_str(window_state.get("active_tab_id"))
                active_index = 0
                for index, tab in enumerate(tabs):
                    payload = window.open_tab(
                        _optional_str(tab.get("url")) or self.homepage_url,
                        activate=False,
                        tab_id=_optional_str(tab.get("tab_id")),
                    )
                    if payload.get("tab_id") == active_tab_id:
                        active_index = index
                window.show()
                if window.tabs.count() > 0:
                    window.tabs.setCurrentIndex(active_index)
                restored_any = True
            return restored_any

        def _build_server(self) -> ThreadingHTTPServer:
            runtime = self

            class BrowserHandler(BaseHTTPRequestHandler):
                def do_GET(self) -> None:  # noqa: N802
                    try:
                        if self.path == "/status":
                            self._write_json(runtime.status().to_dict())
                            return
                        if self.path == "/snapshot":
                            self._write_json(runtime.snapshot())
                            return
                        self.send_error(HTTPStatus.NOT_FOUND)
                    except Exception as exc:
                        self._write_json(
                            build_browser_http_error_payload(exc),
                            status=HTTPStatus.SERVICE_UNAVAILABLE if isinstance(exc, BrowserRuntimeError) else HTTPStatus.INTERNAL_SERVER_ERROR,
                        )

                def do_POST(self) -> None:  # noqa: N802
                    try:
                        payload = self._read_json_body()
                        path = self.path
                        if path == "/open_window":
                            self._write_json(runtime.open_window(_optional_str(payload.get("url"))))
                            return
                        if path == "/open_tab":
                            self._write_json(runtime.open_tab(_optional_str(payload.get("url"))))
                            return
                        if path == "/open_internal_page":
                            self._write_json(runtime.open_internal_page(_optional_str(payload.get("page")) or "home"))
                            return
                        if path == "/switch_tab":
                            self._write_json(runtime.switch_tab(_optional_str(payload.get("tab_id")) or ""))
                            return
                        if path == "/close_tab":
                            self._write_json(runtime.close_tab(_optional_str(payload.get("tab_id"))))
                            return
                        if path == "/navigate":
                            self._write_json(runtime.navigate(str(payload.get("url", "")), tab_id=_optional_str(payload.get("tab_id"))))
                            return
                        if path == "/query_dom":
                            self._write_json(runtime.query_dom(payload))
                            return
                        if path == "/query_accessibility":
                            self._write_json(runtime.query_accessibility())
                            return
                        if path == "/annotate_page":
                            self._write_json(runtime.annotate_page(payload))
                            return
                        if path == "/list_tabs":
                            self._write_json(runtime.list_tabs())
                            return
                        if path == "/list_annotations":
                            self._write_json(runtime.list_annotations(payload))
                            return
                        if path == "/clear_annotations":
                            self._write_json(runtime.clear_annotations(payload))
                            return
                        if path == "/perform_action":
                            self._write_json(runtime.perform_action(payload))
                            return
                        if path == "/wait_for_state":
                            self._write_json(runtime.wait_for_state(payload))
                            return
                        if path == "/collect_downloads":
                            self._write_json(runtime.collect_downloads(payload))
                            return
                        if path == "/wait_for_download":
                            self._write_json(runtime.wait_for_download(payload))
                            return
                        if path == "/list_permissions":
                            self._write_json(runtime.list_permissions())
                            return
                        if path == "/list_permission_requests":
                            self._write_json(runtime.list_permission_requests())
                            return
                        if path == "/decide_permission":
                            self._write_json(runtime.decide_permission(payload))
                            return
                        if path == "/bookmark_page":
                            self._write_json(runtime.bookmark_page())
                            return
                        if path == "/pause_for_auth":
                            self._write_json(runtime.pause_for_auth(_optional_str(payload.get("reason"))))
                            return
                        if path == "/resume_after_auth":
                            self._write_json(runtime.resume_after_auth())
                            return
                        if path == "/get_session_state":
                            self._write_json(runtime.session_state())
                            return
                        self.send_error(HTTPStatus.NOT_FOUND)
                    except Exception as exc:
                        self._write_json(
                            build_browser_http_error_payload(exc),
                            status=HTTPStatus.SERVICE_UNAVAILABLE if isinstance(exc, BrowserRuntimeError) else HTTPStatus.INTERNAL_SERVER_ERROR,
                        )

                def log_message(self, format, *args) -> None:  # noqa: A003
                    return

                def _read_json_body(self) -> dict[str, Any]:
                    length = int(self.headers.get("Content-Length", "0") or 0)
                    if length <= 0:
                        return {}
                    raw = self.rfile.read(length)
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        return {}
                    return payload if isinstance(payload, dict) else {}

                def _write_json(self, payload: dict[str, Any], *, status: int = HTTPStatus.OK) -> None:
                    write_browser_json_response(self, payload, status=status)

            return ThreadingHTTPServer(("127.0.0.1", self.port), BrowserHandler)


def _run_js_sync(page, script: str, *, timeout_ms: int = 8000):
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    holder: dict[str, Any] = {}

    def _finish(result):
        holder["result"] = result
        if loop.isRunning():
            loop.quit()

    def _timeout():
        holder["timed_out"] = True
        if loop.isRunning():
            loop.quit()

    timer.timeout.connect(_timeout)
    page.runJavaScript(script, _finish)
    timer.start(timeout_ms)
    loop.exec()
    timer.stop()
    if holder.get("timed_out"):
        raise BrowserRuntimeError("Browser JavaScript execution timed out.")
    return holder.get("result")


def launch_aoryn_browser(
    *,
    port: int,
    profile_root: Path | None = None,
    initial_url: str | None = None,
    config_path: Path | None = None,
) -> int:
    if QApplication is None:
        raise BrowserRuntimeError(f"PySide6 QtWebEngine is unavailable: {_QT_IMPORT_ERROR}")

    _configure_windows_app_identity(f"{APP_ID}.Browser")
    _configure_qtwebengine_environment()

    app = QApplication(sys.argv[:1])
    icon_path = Path(__file__).resolve().parent / "dashboard_assets" / "icons" / "aoryn-browser.ico"
    profile = profile_root or (local_data_root() / "browser-runtime")
    runtime = AorynBrowserRuntime(profile_root=profile, port=port, icon_path=icon_path, config_path=config_path)
    runtime.start(initial_url=initial_url)
    app.aboutToQuit.connect(runtime.shutdown)
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} Browser")
    parser.add_argument("--port", type=int, default=38991)
    parser.add_argument("--profile-root", type=Path, default=None)
    parser.add_argument("--config-path", type=Path, default=None)
    parser.add_argument("--url", default=DEFAULT_BROWSER_HOMEPAGE)
    args = parser.parse_args(argv)
    return launch_aoryn_browser(
        port=args.port,
        profile_root=args.profile_root,
        initial_url=args.url,
        config_path=args.config_path,
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


# Delegate internal-page rendering to a dedicated module so UI templates stay
# maintainable and can evolve independently from the runtime control logic.
if __name__ == "__main__":  # pragma: no cover - manual runtime entrypoint
    raise SystemExit(main())

