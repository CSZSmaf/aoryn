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
from urllib.parse import quote_plus, urlparse

from desktop_agent.browser_runtime import BrowserObservation, BrowserRuntimeError
from desktop_agent.runtime_paths import local_data_root
from desktop_agent.version import APP_ID, APP_NAME

DEFAULT_BROWSER_HOMEPAGE = "aoryn://home"
DEFAULT_BROWSER_SEARCH_URL = "https://www.google.com/search?q={query}"
INTERNAL_PAGE_TITLES = {
    "home": "Home",
    "history": "History",
    "bookmarks": "Bookmarks",
    "downloads": "Downloads",
    "permissions": "Permissions",
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
    from PySide6.QtCore import QEventLoop, QObject, Qt, QTimer, QUrl, Signal, Slot
    from PySide6.QtGui import QAction, QCloseEvent, QIcon
    from PySide6.QtWidgets import QApplication, QLineEdit, QMainWindow, QTabWidget, QToolBar
    from PySide6.QtWebEngineCore import QWebEngineDownloadRequest, QWebEnginePage, QWebEngineProfile
    from PySide6.QtWebEngineWidgets import QWebEngineView

    _QT_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - GUI runtime availability depends on environment
    QApplication = None  # type: ignore[assignment]
    QCloseEvent = object  # type: ignore[assignment]
    QEventLoop = object  # type: ignore[assignment]
    QIcon = object  # type: ignore[assignment]
    QLineEdit = object  # type: ignore[assignment]
    QMainWindow = object  # type: ignore[assignment]
    QObject = object  # type: ignore[assignment]
    QAction = object  # type: ignore[assignment]
    QTabWidget = object  # type: ignore[assignment]
    QToolBar = object  # type: ignore[assignment]
    QTimer = object  # type: ignore[assignment]
    Qt = object  # type: ignore[assignment]
    QUrl = object  # type: ignore[assignment]
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


def build_internal_page_html(
    page_name: str,
    *,
    history: list[dict[str, Any]] | None = None,
    bookmarks: list[dict[str, Any]] | None = None,
    downloads: list[dict[str, Any]] | None = None,
    permissions: list[dict[str, Any]] | None = None,
    permission_requests: list[dict[str, Any]] | None = None,
    handoffs: list[dict[str, Any]] | None = None,
    auth_pause_reason: str | None = None,
) -> tuple[str, str]:
    page = (page_name or "home").strip().lower()
    title = INTERNAL_PAGE_TITLES.get(page, "Home")
    history = list(history or [])
    bookmarks = list(bookmarks or [])
    downloads = list(downloads or [])
    permissions = list(permissions or [])
    permission_requests = list(permission_requests or [])
    handoffs = list(handoffs or [])

    if page == "history":
        body = _build_internal_entries(
            history,
            empty_message="No browsing history yet.",
            primary_key="title",
            secondary_key="url",
            timestamp_key="visited_at",
        )
    elif page == "bookmarks":
        body = _build_internal_entries(
            bookmarks,
            empty_message="No bookmarks yet.",
            primary_key="title",
            secondary_key="url",
            timestamp_key="created_at",
        )
    elif page == "downloads":
        body = _build_internal_entries(
            downloads,
            empty_message="No downloads yet.",
            primary_key="file_name",
            secondary_key="url",
            timestamp_key="created_at",
            tertiary_key="path",
        )
    elif page == "permissions":
        body = _build_permission_entries(permissions, permission_requests, handoffs)
    else:
        title = INTERNAL_PAGE_TITLES["home"]
        body = f"""
        <section class="hero">
          <h1>{html.escape(APP_NAME)} Browser</h1>
          <p>A Chromium-powered browser surface for day-to-day browsing and agent-assisted work.</p>
          <div class="grid">
            <a class="card" href="aoryn://history"><strong>History</strong><span>{len(history)} recent visits</span></a>
            <a class="card" href="aoryn://bookmarks"><strong>Bookmarks</strong><span>{len(bookmarks)} saved pages</span></a>
            <a class="card" href="aoryn://downloads"><strong>Downloads</strong><span>{len(downloads)} tracked files</span></a>
            <a class="card" href="aoryn://permissions"><strong>Permissions</strong><span>{len(permission_requests)} pending, {len(permissions)} saved</span></a>
          </div>
          <div class="hint">
            <strong>Tip:</strong> Type a URL, hostname, or search query in the address bar.
          </div>
        </section>
        """

    auth_banner = ""
    if auth_pause_reason:
        auth_banner = (
            '<div class="banner">'
            f"<strong>AI paused:</strong> {html.escape(auth_pause_reason)}"
            "</div>"
        )

    nav = "".join(
        f'<a href="aoryn://{name}" class="nav-link{" active" if name == page else ""}">{html.escape(label)}</a>'
        for name, label in INTERNAL_PAGE_TITLES.items()
    )
    document = f"""
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>{html.escape(title)}</title>
        <style>
          :root {{
            color-scheme: light;
            --bg: #f6f8fb;
            --card: #ffffff;
            --line: #d7dce5;
            --ink: #172033;
            --muted: #5b6578;
            --accent: #0f8f73;
            --accent-soft: rgba(15, 143, 115, 0.12);
          }}
          * {{ box-sizing: border-box; }}
          body {{
            margin: 0;
            padding: 24px;
            font-family: "Segoe UI", "PingFang SC", sans-serif;
            color: var(--ink);
            background: radial-gradient(circle at top right, #edf8f4 0, var(--bg) 45%);
          }}
          .shell {{
            max-width: 1040px;
            margin: 0 auto;
          }}
          .nav {{
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-bottom: 18px;
          }}
          .nav-link {{
            color: var(--ink);
            text-decoration: none;
            background: var(--card);
            border: 1px solid var(--line);
            border-radius: 999px;
            padding: 10px 16px;
            font-weight: 600;
          }}
          .nav-link.active {{
            border-color: var(--accent);
            background: var(--accent-soft);
            color: var(--accent);
          }}
          .banner {{
            margin-bottom: 18px;
            border: 1px solid #f2c98f;
            background: #fff7ec;
            color: #865d16;
            border-radius: 14px;
            padding: 14px 16px;
          }}
          .hero, .list {{
            background: var(--card);
            border: 1px solid rgba(23, 32, 51, 0.08);
            border-radius: 20px;
            padding: 22px;
            box-shadow: 0 10px 28px rgba(23, 32, 51, 0.06);
          }}
          .hero h1 {{
            margin: 0 0 8px;
            font-size: 34px;
          }}
          .hero p {{
            margin: 0 0 18px;
            color: var(--muted);
            font-size: 16px;
          }}
          .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 14px;
            margin-bottom: 18px;
          }}
          .card {{
            display: block;
            background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
            border: 1px solid var(--line);
            border-radius: 16px;
            padding: 16px;
            color: var(--ink);
            text-decoration: none;
          }}
          .card strong {{
            display: block;
            margin-bottom: 6px;
            font-size: 18px;
          }}
          .card span, .hint, .meta {{
            color: var(--muted);
          }}
          .entry {{
            padding: 14px 0;
            border-top: 1px solid rgba(23, 32, 51, 0.08);
          }}
          .entry:first-child {{
            border-top: 0;
            padding-top: 0;
          }}
          .entry a {{
            color: var(--accent);
            text-decoration: none;
            font-weight: 600;
          }}
          .entry .meta {{
            margin-top: 6px;
            font-size: 13px;
            word-break: break-all;
          }}
          .empty {{
            margin: 0;
            color: var(--muted);
          }}
        </style>
      </head>
      <body>
        <main class="shell">
          <nav class="nav">{nav}</nav>
          {auth_banner}
          {body}
        </main>
      </body>
    </html>
    """
    return title, document


def _build_internal_entries(
    entries: list[dict[str, Any]],
    *,
    empty_message: str,
    primary_key: str,
    secondary_key: str,
    timestamp_key: str,
    tertiary_key: str | None = None,
) -> str:
    if not entries:
        return f'<section class="list"><p class="empty">{html.escape(empty_message)}</p></section>'
    rows: list[str] = []
    for entry in reversed(entries[-60:]):
        primary = _optional_str(entry.get(primary_key)) or _optional_str(entry.get(secondary_key)) or "Untitled"
        secondary = _optional_str(entry.get(secondary_key))
        tertiary = _optional_str(entry.get(tertiary_key)) if tertiary_key else None
        meta_parts = [_format_timestamp(entry.get(timestamp_key))]
        if secondary:
            safe_secondary = html.escape(secondary)
            if secondary.startswith(("http://", "https://")):
                secondary_markup = f'<a href="{safe_secondary}">{safe_secondary}</a>'
            else:
                secondary_markup = safe_secondary
            meta_parts.append(secondary_markup)
        if tertiary:
            meta_parts.append(html.escape(tertiary))
        rows.append(
            '<article class="entry">'
            f"<strong>{html.escape(primary)}</strong>"
            f"<div class=\"meta\">{'<br/>'.join(part for part in meta_parts if part)}</div>"
            "</article>"
        )
    return f'<section class="list">{"".join(rows)}</section>'


def _build_permission_entries(
    permissions: list[dict[str, Any]],
    permission_requests: list[dict[str, Any]],
    handoffs: list[dict[str, Any]],
) -> str:
    pending_rows: list[str] = []
    for entry in reversed(permission_requests[-20:]):
        pending_rows.append(
            '<article class="entry">'
            f"<strong>{html.escape(_optional_str(entry.get('origin')) or 'Unknown origin')}</strong>"
            f"<div class=\"meta\">{html.escape(_optional_str(entry.get('feature')) or 'permission')}<br/>{html.escape(_optional_str(entry.get('request_id')) or '')}<br/>{html.escape(_format_timestamp(entry.get('requested_at')))}</div>"
            "</article>"
        )
    permission_rows: list[str] = []
    for entry in reversed(permissions[-40:]):
        origin = _optional_str(entry.get("origin")) or "Unknown origin"
        feature = _optional_str(entry.get("feature")) or "permission"
        decision = (_optional_str(entry.get("decision")) or "prompt").replace("_", " ")
        permission_rows.append(
            '<article class="entry">'
            f"<strong>{html.escape(origin)}</strong>"
            f"<div class=\"meta\">{html.escape(feature)}<br/>{html.escape(decision.title())}<br/>{html.escape(_format_timestamp(entry.get('updated_at')))}</div>"
            "</article>"
        )
    handoff_rows: list[str] = []
    for entry in reversed(handoffs[-20:]):
        handoff_rows.append(
            '<article class="entry">'
            f"<strong>{html.escape(_optional_str(entry.get('kind')) or 'handoff')}</strong>"
            f"<div class=\"meta\">{html.escape(_optional_str(entry.get('reason')) or 'Manual review required')}<br/>{html.escape(_optional_str(entry.get('url')) or '')}<br/>{html.escape(_format_timestamp(entry.get('created_at')))}</div>"
            "</article>"
        )
    permissions_markup = "".join(permission_rows) or '<p class="empty">No saved permission decisions yet.</p>'
    pending_markup = "".join(pending_rows) or '<p class="empty">No pending permission requests.</p>'
    handoffs_markup = "".join(handoff_rows) or '<p class="empty">No recent auth or human handoffs.</p>'
    return (
        '<section class="list">'
        '<h2>Pending Requests</h2>'
        f"{pending_markup}"
        "</section>"
        '<section class="list" style="margin-top:16px;">'
        '<h2>Permission Decisions</h2>'
        f"{permissions_markup}"
        "</section>"
        '<section class="list" style="margin-top:16px;">'
        '<h2>Recent Handoffs</h2>'
        f"{handoffs_markup}"
        "</section>"
    )


def _looks_like_browser_host(target: str) -> bool:
    token = str(target or "").strip()
    if not token or " " in token:
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


def _format_timestamp(value: Any) -> str:
    try:
        instant = float(value)
    except (TypeError, ValueError):
        return ""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(instant))


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

        def acceptNavigationRequest(self, url, navigation_type, is_main_frame):  # type: ignore[override]
            if is_main_frame and is_internal_browser_url(url.toString()):
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
            self.tabs = QTabWidget(self)
            self.tabs.setDocumentMode(True)
            self.tabs.setTabsClosable(True)
            self.tabs.tabCloseRequested.connect(self._close_tab)
            self.tabs.currentChanged.connect(self._handle_current_tab_changed)
            self.setCentralWidget(self.tabs)
            self.setWindowTitle(f"{APP_NAME} Browser")
            self.setWindowIcon(QIcon(str(icon_path)))
            self.resize(1280, 900)
            self._tab_refs: list[_BrowserTab] = []
            self.address_bar = QLineEdit(self)
            self._build_toolbar()
            self._build_menu()

        def _build_toolbar(self) -> None:
            toolbar = QToolBar("Navigation", self)
            toolbar.setMovable(False)
            self.addToolBar(toolbar)

            back_action = QAction("Back", self)
            back_action.triggered.connect(self.go_back)
            toolbar.addAction(back_action)

            forward_action = QAction("Forward", self)
            forward_action.triggered.connect(self.go_forward)
            toolbar.addAction(forward_action)

            reload_action = QAction("Reload", self)
            reload_action.triggered.connect(self.reload_page)
            toolbar.addAction(reload_action)

            home_action = QAction("Home", self)
            home_action.triggered.connect(self.open_home_page)
            toolbar.addAction(home_action)

            new_tab_action = QAction("New Tab", self)
            new_tab_action.triggered.connect(lambda: self.open_tab(self.homepage_url))
            toolbar.addAction(new_tab_action)

            toolbar.addSeparator()
            self.address_bar.setClearButtonEnabled(True)
            self.address_bar.setPlaceholderText("Search or enter address")
            self.address_bar.returnPressed.connect(self._navigate_from_address_bar)
            toolbar.addWidget(self.address_bar)

        def _build_menu(self) -> None:
            file_menu = self.menuBar().addMenu("File")
            new_tab = QAction("New Tab", self)
            new_tab.triggered.connect(lambda: self.open_tab(self.homepage_url))
            file_menu.addAction(new_tab)

            view_menu = self.menuBar().addMenu("View")
            history_action = QAction("History", self)
            history_action.triggered.connect(lambda: self.open_internal_page("history"))
            view_menu.addAction(history_action)
            bookmarks_action = QAction("Bookmarks", self)
            bookmarks_action.triggered.connect(lambda: self.open_internal_page("bookmarks"))
            view_menu.addAction(bookmarks_action)
            downloads_action = QAction("Downloads", self)
            downloads_action.triggered.connect(lambda: self.open_internal_page("downloads"))
            view_menu.addAction(downloads_action)

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
            label = "New Tab"
            self._tab_refs.append(_BrowserTab(tab_id=item_tab_id, view=view, display_url=self.homepage_url))
            index = self.tabs.addTab(view, label)
            if activate:
                self.tabs.setCurrentIndex(index)
            view.titleChanged.connect(lambda title, current_tab_id=item_tab_id: self._update_tab_title(current_tab_id, title))
            view.urlChanged.connect(lambda changed_url, current_tab_id=item_tab_id: self._handle_url_changed(current_tab_id, changed_url))
            view.loadFinished.connect(lambda ok, current_tab_id=item_tab_id: self._handle_load_finished(current_tab_id, ok))
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
            self.navigate(url or self.homepage_url, tab_id=item_tab_id)
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
            target.view.load(QUrl(normalized))
            self._sync_address_bar()
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
            runtime = self._runtime()
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
            runtime = self._runtime()
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
                runtime = self._runtime()
                if runtime is None:
                    return {"ok": False, "error": "Browser runtime is unavailable."}
                return runtime.bookmark_page()
            if action == "resume_after_auth":
                runtime = self._runtime()
                if runtime is None:
                    return {"ok": False, "error": "Browser runtime is unavailable."}
                return runtime.resume_after_auth()
            if action == "clear_annotations":
                return self.clear_annotations(tab_id=tab.tab_id, annotation_id=value)
            if action == "upload":
                return self.upload_files(selector=selector, paths=upload_paths, tab_id=tab.tab_id)
            if action == "decide_permission":
                runtime = self._runtime()
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
                runtime = self._runtime()
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
            dom = self.query_dom(include_text=True)
            active_tab = self.active_tab()
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
            runtime = self._runtime()
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
            self._refresh_title()
            runtime = self._runtime()
            if runtime is not None:
                runtime.schedule_persist_state()
            if self.tabs.count() == 0:
                self.open_tab(self.homepage_url)

        def _update_tab_title(self, tab_id: str, title: str) -> None:
            for index, item in enumerate(self._tab_refs):
                if item.tab_id == tab_id:
                    if item.internal_page:
                        self.tabs.setTabText(index, INTERNAL_PAGE_TITLES.get(item.internal_page, "New Tab"))
                    else:
                        self.tabs.setTabText(index, title or "New Tab")
                    break
            self._refresh_title()

        def _refresh_title(self) -> None:
            active = self.active_tab()
            title = self._visible_title(active) if active is not None else "New Tab"
            self.setWindowTitle(f"{APP_NAME} Browser - {title or 'New Tab'}")

        def _handle_current_tab_changed(self, _index: int) -> None:
            self._refresh_title()
            self._sync_address_bar()

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
            runtime = self._runtime()
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

        def _open_internal_target(self, tab_id: str, target: str) -> None:
            self.open_internal_page(_internal_browser_page_name(target) or "home", tab_id=tab_id)

        def _render_internal_page(self, tab: _BrowserTab, target_url: str) -> dict[str, Any]:
            page_name = _internal_browser_page_name(target_url) or "home"
            runtime = self._runtime()
            if runtime is None:
                title, document = build_internal_page_html(page_name)
            else:
                title, document = runtime.render_internal_page(page_name)
            tab.internal_page = page_name
            tab.display_url = f"aoryn://{page_name}"
            tab.view.setHtml(document, QUrl(tab.display_url))
            self._update_tab_title(tab.tab_id, title)
            self._sync_address_bar()
            self._refresh_title()
            if runtime is not None:
                runtime.schedule_persist_state()
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

        def _tab_index(self, tab: _BrowserTab) -> int:
            for index, item in enumerate(self._tab_refs):
                if item.tab_id == tab.tab_id:
                    return index
            return -1

        def _visible_url(self, tab: _BrowserTab | None) -> str | None:
            if tab is None:
                return None
            if tab.internal_page:
                return tab.display_url or f"aoryn://{tab.internal_page}"
            return _optional_str(tab.view.url().toString()) or tab.display_url

        def _visible_title(self, tab: _BrowserTab | None) -> str | None:
            if tab is None:
                return None
            if tab.internal_page:
                return INTERNAL_PAGE_TITLES.get(tab.internal_page, "Page")
            return _optional_str(tab.view.title()) or "New Tab"

        def _annotation_snapshot(self, tab_id: str | None) -> list[dict[str, Any]]:
            runtime = self._runtime()
            if runtime is None or not tab_id:
                return []
            return runtime.annotations_for_tab(tab_id)

        def _handle_permission_request(self, tab_id: str, page, security_origin, feature) -> None:
            runtime = self._runtime()
            if runtime is None:
                return
            runtime.register_permission_request(
                tab_id=tab_id,
                page=page,
                security_origin=security_origin,
                feature=feature,
            )

        def _runtime(self):
            return getattr(self, "_runtime", None)

        def closeEvent(self, event: QCloseEvent) -> None:
            runtime = self._runtime()
            if runtime is not None:
                runtime.unregister_window(self.window_id)
            super().closeEvent(event)


    class AorynBrowserRuntime:
        def __init__(self, *, profile_root: Path, port: int, icon_path: Path) -> None:
            self.profile_root = profile_root
            self.port = port
            self.icon_path = icon_path
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

        def open_window(self, url: str | None = None) -> dict[str, Any]:
            def _create() -> dict[str, Any]:
                window = BrowserWindow(
                    profile=self.profile,
                    icon_path=self.icon_path,
                    homepage_url=self.homepage_url,
                    search_url=self.search_url,
                )
                window._runtime = self  # type: ignore[attr-defined]
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
            return build_internal_page_html(
                page_name,
                history=self.history,
                bookmarks=self.bookmarks,
                downloads=self.downloads,
                permissions=self.permissions,
                permission_requests=self.permission_requests,
                handoffs=self.handoffs,
                auth_pause_reason=self.auth_pause_reason,
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
                window._runtime = self  # type: ignore[attr-defined]
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
                    if self.path == "/status":
                        self._write_json(runtime.status().to_dict())
                        return
                    if self.path == "/snapshot":
                        self._write_json(runtime.snapshot())
                        return
                    self.send_error(HTTPStatus.NOT_FOUND)

                def do_POST(self) -> None:  # noqa: N802
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

                def _write_json(self, payload: dict[str, Any]) -> None:
                    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)

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
) -> int:
    if QApplication is None:
        raise BrowserRuntimeError(f"PySide6 QtWebEngine is unavailable: {_QT_IMPORT_ERROR}")

    _configure_windows_app_identity(f"{APP_ID}.Browser")
    _configure_qtwebengine_environment()

    app = QApplication(sys.argv[:1])
    icon_path = Path(__file__).resolve().parent / "dashboard_assets" / "icons" / "aoryn-app.ico"
    profile = profile_root or (local_data_root() / "browser-runtime")
    runtime = AorynBrowserRuntime(profile_root=profile, port=port, icon_path=icon_path)
    runtime.start(initial_url=initial_url)
    app.aboutToQuit.connect(runtime.shutdown)
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} Browser")
    parser.add_argument("--port", type=int, default=38991)
    parser.add_argument("--profile-root", type=Path, default=None)
    parser.add_argument("--url", default=DEFAULT_BROWSER_HOMEPAGE)
    args = parser.parse_args(argv)
    return launch_aoryn_browser(port=args.port, profile_root=args.profile_root, initial_url=args.url)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


if __name__ == "__main__":  # pragma: no cover - manual runtime entrypoint
    raise SystemExit(main())
