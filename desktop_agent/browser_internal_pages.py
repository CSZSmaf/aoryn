from __future__ import annotations

import html
from typing import Any

INTERNAL_PAGE_TITLES = {
    "home": "Home",
    "runtime": "Runtime",
    "setup": "AI Setup",
    "history": "History",
    "bookmarks": "Bookmarks",
    "downloads": "Downloads",
    "permissions": "Permissions",
}


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
    assistant_setup: dict[str, Any] | None = None,
    service_summary: dict[str, Any] | None = None,
) -> tuple[str, str]:
    page = (page_name or "home").strip().lower()
    title = INTERNAL_PAGE_TITLES.get(page, "Home")
    history = list(history or [])
    bookmarks = list(bookmarks or [])
    downloads = list(downloads or [])
    permissions = list(permissions or [])
    permission_requests = list(permission_requests or [])
    handoffs = list(handoffs or [])
    assistant_setup = dict(assistant_setup or {})
    service_summary = dict(service_summary or {})

    if page == "runtime":
        body = _build_runtime_page(service_summary, assistant_setup)
    elif page == "setup":
        body = _build_ai_setup_page(assistant_setup)
    elif page == "history":
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
        body = _build_home_page(
            service_summary,
            assistant_setup,
            history=history,
            bookmarks=bookmarks,
            downloads=downloads,
            permissions=permissions,
            permission_requests=permission_requests,
            handoffs=handoffs,
        )

    auth_banner = ""
    if auth_pause_reason:
        auth_banner = (
            '<div class="tblr-alert">'
            f"<strong>AI paused:</strong> {html.escape(auth_pause_reason)}"
            "</div>"
        )

    nav = "".join(
        f'<a href="aoryn://{name}" class="tblr-nav-link{" is-active" if name == page else ""}">{html.escape(label)}</a>'
        for name, label in INTERNAL_PAGE_TITLES.items()
    )
    setup_badge = html.escape(
        _optional_str(assistant_setup.get("badge_text"))
        or _optional_str(assistant_setup.get("status"))
        or "Setup needed"
    )
    service_badge = html.escape(
        _optional_str(service_summary.get("badge_text"))
        or _optional_str(service_summary.get("status"))
        or "Service starting"
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
            --bg: #f5f7fb;
            --surface: rgba(255, 255, 255, 0.95);
            --line: rgba(99, 117, 148, 0.25);
            --ink: #172534;
            --muted: #607289;
            --accent: #206bc4;
            --accent-soft: rgba(32, 107, 196, 0.12);
            --ok: #2fb344;
            --warn: #f59f00;
            --danger: #d63939;
            --shadow: 0 18px 44px rgba(17, 24, 39, 0.08);
            --radius: 14px;
          }}
          * {{ box-sizing: border-box; }}
          body {{
            margin: 0;
            min-height: 100vh;
            color: var(--ink);
            font-family: "Inter", "Segoe UI", "PingFang SC", sans-serif;
            background:
              radial-gradient(circle at left top, rgba(32, 107, 196, 0.1), transparent 30%),
              radial-gradient(circle at right top, rgba(47, 179, 68, 0.08), transparent 24%),
              linear-gradient(180deg, #ffffff 0%, var(--bg) 100%);
            padding: 22px;
          }}
          a {{ color: inherit; text-decoration: none; }}
          .tblr-shell {{
            max-width: 1120px;
            margin: 0 auto;
          }}
          .tblr-head {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            margin-bottom: 14px;
            padding: 14px 16px;
            border-radius: var(--radius);
            border: 1px solid var(--line);
            background: var(--surface);
            box-shadow: var(--shadow);
          }}
          .tblr-brand {{
            display: flex;
            align-items: center;
            gap: 10px;
          }}
          .tblr-logo {{
            width: 38px;
            height: 38px;
            border-radius: 10px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(145deg, #1f4e8c 0%, #1a6bd6 100%);
            color: #ffffff;
            font-weight: 700;
          }}
          .tblr-brand h1 {{
            margin: 0;
            font-size: 1rem;
          }}
          .tblr-brand p {{
            margin: 2px 0 0;
            color: var(--muted);
            font-size: 12px;
          }}
          .tblr-badges {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
          }}
          .tblr-badge {{
            padding: 5px 10px;
            border-radius: 999px;
            border: 1px solid var(--line);
            background: rgba(255, 255, 255, 0.8);
            color: var(--muted);
            font-size: 12px;
            font-weight: 600;
          }}
          .tblr-badge strong {{
            color: var(--ink);
            margin-right: 6px;
          }}
          .tblr-nav {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            margin-bottom: 14px;
            padding: 10px;
            border-radius: var(--radius);
            border: 1px solid var(--line);
            background: var(--surface);
          }}
          .tblr-nav-link {{
            padding: 8px 12px;
            border-radius: 10px;
            border: 1px solid var(--line);
            background: #ffffff;
            color: var(--ink);
            font-size: 13px;
            font-weight: 600;
          }}
          .tblr-nav-link.is-active {{
            border-color: rgba(32, 107, 196, 0.5);
            background: var(--accent-soft);
            color: var(--accent);
          }}
          .tblr-alert {{
            margin-bottom: 14px;
            padding: 12px;
            border-radius: 12px;
            border: 1px solid rgba(214, 57, 57, 0.35);
            background: rgba(214, 57, 57, 0.08);
            color: #7f1d1d;
          }}
          .tblr-hero,
          .tblr-list {{
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 16px;
            padding: 18px;
            box-shadow: var(--shadow);
          }}
          .tblr-hero h2 {{
            margin: 0 0 8px;
            font-size: 1.5rem;
          }}
          .tblr-hero p {{
            margin: 0 0 14px;
            color: var(--muted);
          }}
          .tblr-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
            gap: 10px;
          }}
          .tblr-card {{
            padding: 12px;
            border-radius: 12px;
            border: 1px solid var(--line);
            background: #ffffff;
          }}
          .tblr-card strong {{
            display: block;
            margin-bottom: 4px;
          }}
          .tblr-card span,
          .tblr-meta {{
            color: var(--muted);
            font-size: 13px;
          }}
          .tblr-links {{
            margin-top: 12px;
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
          }}
          .tblr-chip {{
            display: inline-flex;
            padding: 7px 10px;
            border-radius: 999px;
            border: 1px solid var(--line);
            background: #ffffff;
            font-size: 12px;
            font-weight: 600;
          }}
          .tblr-list {{
            margin-top: 14px;
          }}
          .tblr-entry {{
            padding: 10px 0;
            border-top: 1px solid var(--line);
          }}
          .tblr-entry:first-child {{
            border-top: 0;
            padding-top: 0;
          }}
          .tblr-entry a {{
            color: var(--accent);
          }}
          .tblr-empty {{
            margin: 0;
            color: var(--muted);
          }}
          .tblr-route-grid {{
            margin-top: 12px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 10px;
          }}
          .tblr-route-path {{
            font-family: "Cascadia Mono", Consolas, monospace;
            color: var(--accent);
            font-size: 12px;
            word-break: break-all;
          }}
          @media (max-width: 760px) {{
            body {{ padding: 12px; }}
            .tblr-head {{
              flex-direction: column;
              align-items: flex-start;
            }}
          }}
        </style>
      </head>
      <body>
        <main class="tblr-shell">
          <header class="tblr-head">
            <div class="tblr-brand">
              <div class="tblr-logo">A</div>
              <div>
                <h1>Aoryn Browser</h1>
                <p>Managed browser runtime tuned to the desktop app</p>
              </div>
            </div>
            <div class="tblr-badges">
              <div class="tblr-badge"><strong>Service</strong>{service_badge}</div>
              <div class="tblr-badge"><strong>AI</strong>{setup_badge}</div>
            </div>
          </header>
          <nav class="tblr-nav">{nav}</nav>
          {auth_banner}
          {body}
        </main>
      </body>
    </html>
    """
    return title, document


def _build_service_metric_card(*, label: str, value: str, detail: str | None = None) -> str:
    detail_markup = ""
    if _optional_str(detail):
        detail_markup = f'<div class="tblr-meta">{html.escape(_optional_str(detail) or "")}</div>'
    return (
        '<div class="tblr-card">'
        f"<strong>{html.escape(label)}</strong>"
        f"<span>{html.escape(_optional_str(value) or 'Unavailable')}</span>"
        f"{detail_markup}"
        "</div>"
    )


def _build_service_routes_markup(service_summary: dict[str, Any] | None) -> str:
    payload = service_summary or {}
    routes = payload.get("routes") or []
    if not routes:
        return '<section class="tblr-list"><p class="tblr-empty">No runtime routes registered yet.</p></section>'
    base_url = (_optional_str(payload.get("base_url")) or "http://127.0.0.1").rstrip("/")
    cards: list[str] = []
    for route in routes:
        label = _optional_str(route.get("label")) or "Route"
        path = _optional_str(route.get("path")) or "/"
        full_url = f"{base_url}{path}" if path.startswith("/") else f"{base_url}/{path}"
        cards.append(
            '<article class="tblr-card">'
            f"<strong>{html.escape(label)}</strong>"
            f'<div class="tblr-route-path">{html.escape(path)}</div>'
            f'<div class="tblr-meta">{html.escape(full_url)}</div>'
            "</article>"
        )
    return (
        '<section class="tblr-list">'
        '<article class="tblr-entry">'
        "<strong>Runtime routes</strong>"
        '<div class="tblr-meta">These local endpoints are what the desktop app calls when it drives browsing, DOM inspection, waiting, downloads, and handoff checks.</div>'
        "</article>"
        f'<div class="tblr-route-grid">{"".join(cards)}</div>'
        "</section>"
    )


def _build_home_page(
    service_summary: dict[str, Any] | None,
    assistant_setup: dict[str, Any] | None,
    *,
    history: list[dict[str, Any]],
    bookmarks: list[dict[str, Any]],
    downloads: list[dict[str, Any]],
    permissions: list[dict[str, Any]],
    permission_requests: list[dict[str, Any]],
    handoffs: list[dict[str, Any]],
) -> str:
    service = service_summary or {}
    assistant = assistant_setup or {}
    active_title = _optional_str(service.get("active_title")) or "No active page yet"
    active_url = _optional_str(service.get("active_url")) or "The desktop app can open a page on demand."
    review_detail = _optional_str(service.get("auth_pause_reason")) or "No auth or permission blockers are waiting."
    working_set_value = f"{int(service.get('window_count') or 0)} windows | {int(service.get('tab_count') or 0)} tabs"
    working_set_detail = f"{len(history)} visits | {len(bookmarks)} bookmarks | {len(downloads)} downloads"
    handoff_detail = f"{int(service.get('handoff_count') or 0)} recorded handoffs | {int(service.get('annotation_count') or 0)} annotations"
    ai_value = _optional_str(assistant.get("status")) or "Setup needed"
    ai_detail = (
        f"{_optional_str(assistant.get('provider_label')) or 'Provider not set'} | "
        f"{_optional_str(assistant.get('model_display')) or 'Auto'}"
    )
    return (
        """
        <section class="tblr-hero">
          <h2>Managed browser runtime for Aoryn tasks.</h2>
          <p>This browser is primarily the desktop app's control surface: Aoryn can navigate pages, inspect DOM, wait for UI state, and pause here when a human needs to step in.</p>
        """
        + f"""
          <div class="tblr-grid">
            {_build_service_metric_card(label='Runtime status', value=_optional_str(service.get('status')) or 'starting', detail=_optional_str(service.get('detail')))}
            {_build_service_metric_card(label='Active page', value=active_title, detail=active_url)}
            {_build_service_metric_card(label='Human review', value=f"{int(service.get('pending_permissions') or 0)} pending permissions", detail=review_detail)}
            {_build_service_metric_card(label='AI setup', value=ai_value, detail=ai_detail)}
            {_build_service_metric_card(label='Working set', value=working_set_value, detail=working_set_detail)}
            {_build_service_metric_card(label='Handoffs', value=f"{len(handoffs)} recorded events", detail=handoff_detail)}
          </div>
          <div class="tblr-links">
            <a class="tblr-chip" href="aoryn://runtime">Runtime console</a>
            <a class="tblr-chip" href="aoryn://setup">Model + browser setup</a>
            <a class="tblr-chip" href="aoryn://history">Research trail</a>
            <a class="tblr-chip" href="aoryn://permissions">Human review queue</a>
            <a class="tblr-chip" href="aoryn://downloads">Downloads</a>
          </div>
        </section>
        """
        + _build_service_routes_markup(service)
        + f"""
        <section class="tblr-list">
          <article class="tblr-entry">
            <strong>Saved permissions</strong>
            <div class="tblr-meta">{len(permissions)} remembered site decisions are available to speed up repeated task runs.</div>
          </article>
          <article class="tblr-entry">
            <strong>Pending requests</strong>
            <div class="tblr-meta">{len(permission_requests)} permission prompts are waiting for operator choice.</div>
          </article>
        </section>
        """
    )


def _build_runtime_page(service_summary: dict[str, Any] | None, assistant_setup: dict[str, Any] | None) -> str:
    service = service_summary or {}
    assistant = assistant_setup or {}
    active_value = _optional_str(service.get("active_title")) or "No page is active"
    active_detail = _optional_str(service.get("active_url")) or "Aoryn will open or restore pages when a task needs them."
    return (
        """
        <section class="tblr-hero">
          <h2>Control surface for the desktop app.</h2>
          <p>The desktop executor talks to this browser over local HTTP. These metrics show whether the managed runtime is ready for navigation, DOM inspection, downloads, and human-review pauses.</p>
        """
        + f"""
          <div class="tblr-grid">
            {_build_service_metric_card(label='Service state', value=_optional_str(service.get('badge_text')) or 'Service starting', detail=_optional_str(service.get('detail')))}
            {_build_service_metric_card(label='Base URL', value=_optional_str(service.get('base_url')) or 'http://127.0.0.1', detail=_optional_str(service.get('transport')) or 'local_http')}
            {_build_service_metric_card(label='Runtime role', value=_optional_str(service.get('runtime_role')) or 'managed_browser_service', detail='Primary browser runtime exposed to Aoryn tasks')}
            {_build_service_metric_card(label='Active page', value=active_value, detail=active_detail)}
            {_build_service_metric_card(label='Window + tab count', value=f"{int(service.get('window_count') or 0)} windows | {int(service.get('tab_count') or 0)} tabs", detail='Live UI surfaces currently attached to the runtime')}
            {_build_service_metric_card(label='Review pressure', value=f"{int(service.get('pending_permissions') or 0)} permission prompts", detail=_optional_str(service.get('auth_pause_reason')) or 'No auth pause is currently blocking automation')}
            {_build_service_metric_card(label='Handoffs', value=f"{int(service.get('handoff_count') or 0)} handoffs", detail='Recorded operator checkpoints and auth pauses')}
            {_build_service_metric_card(label='Annotations', value=f"{int(service.get('annotation_count') or 0)} page markers", detail='Visual anchors preserved for the current session')}
            {_build_service_metric_card(label='AI provider', value=_optional_str(assistant.get('provider_label')) or 'Not configured', detail=_optional_str(assistant.get('status')) or 'Setup needed')}
          </div>
        </section>
        """
        + _build_service_routes_markup(service)
    )


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
        return f'<section class="tblr-list"><p class="tblr-empty">{html.escape(empty_message)}</p></section>'
    rows: list[str] = []
    for entry in reversed(entries[-60:]):
        primary = _optional_str(entry.get(primary_key)) or _optional_str(entry.get(secondary_key)) or "Untitled"
        secondary = _optional_str(entry.get(secondary_key))
        tertiary = _optional_str(entry.get(tertiary_key)) if tertiary_key else None
        meta_parts = [_format_timestamp(entry.get(timestamp_key))]
        if secondary:
            safe_secondary = html.escape(secondary)
            secondary_markup = f'<a href="{safe_secondary}">{safe_secondary}</a>' if secondary.startswith(("http://", "https://")) else safe_secondary
            meta_parts.append(secondary_markup)
        if tertiary:
            meta_parts.append(html.escape(tertiary))
        rows.append(
            '<article class="tblr-entry">'
            f"<strong>{html.escape(primary)}</strong>"
            f"<div class=\"tblr-meta\">{'<br/>'.join(part for part in meta_parts if part)}</div>"
            "</article>"
        )
    return f'<section class="tblr-list">{"".join(rows)}</section>'


def _build_ai_setup_page(assistant_setup: dict[str, Any] | None) -> str:
    payload = assistant_setup or {}
    status = html.escape(_optional_str(payload.get("status")) or "Setup needed")
    detail = html.escape(_optional_str(payload.get("detail")) or "Open the Setup button in the toolbar to configure browser AI.")
    provider_label = html.escape(_optional_str(payload.get("provider_label")) or "Not selected")
    model_display = html.escape(_optional_str(payload.get("model_display")) or "Auto")
    base_url = html.escape(_optional_str(payload.get("base_url")) or "Not set")
    browser_channel = html.escape(_optional_str(payload.get("browser_channel_label")) or "System default")
    browser_path = html.escape(_optional_str(payload.get("browser_executable_path")) or "System default")
    headless_label = "On" if bool(payload.get("browser_headless")) else "Off"
    runtime_preferences_path = html.escape(_optional_str(payload.get("runtime_preferences_path")) or "Unavailable")
    config_path = html.escape(_optional_str(payload.get("config_path")) or "Using defaults")
    api_key_state = "Configured" if bool(payload.get("api_key_configured")) else "Not configured"
    return f"""
        <section class="tblr-hero">
          <h2>Configure the browser assistant and execution browser in one place.</h2>
          <p>The toolbar Setup button writes to the same runtime preferences used by Aoryn tasks, so browser AI and desktop runs stay aligned.</p>
          <div class="tblr-grid">
            <div class="tblr-card"><strong>Status</strong><span>{status}</span><div class="tblr-meta">{detail}</div></div>
            <div class="tblr-card"><strong>Provider</strong><span>{provider_label}</span></div>
            <div class="tblr-card"><strong>Model</strong><span>{model_display}</span></div>
            <div class="tblr-card"><strong>API key</strong><span>{api_key_state}</span></div>
            <div class="tblr-card"><strong>Browser channel</strong><span>{browser_channel}</span></div>
          </div>
        </section>
        <section class="tblr-list">
          <article class="tblr-entry"><strong>Base URL</strong><div class="tblr-meta">{base_url}</div></article>
          <article class="tblr-entry"><strong>Browser executable path</strong><div class="tblr-meta">{browser_path}</div></article>
          <article class="tblr-entry"><strong>Headless mode</strong><div class="tblr-meta">{headless_label}</div></article>
          <article class="tblr-entry"><strong>Runtime preferences file</strong><div class="tblr-meta">{runtime_preferences_path}</div></article>
          <article class="tblr-entry"><strong>Config file</strong><div class="tblr-meta">{config_path}</div></article>
        </section>
    """


def _build_permission_entries(
    permissions: list[dict[str, Any]],
    permission_requests: list[dict[str, Any]],
    handoffs: list[dict[str, Any]],
) -> str:
    pending_rows: list[str] = []
    for entry in reversed(permission_requests[-20:]):
        pending_rows.append(
            '<article class="tblr-entry">'
            f"<strong>{html.escape(_optional_str(entry.get('origin')) or 'Unknown origin')}</strong>"
            f"<div class=\"tblr-meta\">{html.escape(_optional_str(entry.get('feature')) or 'permission')}<br/>{html.escape(_optional_str(entry.get('request_id')) or '')}<br/>{html.escape(_format_timestamp(entry.get('requested_at')))}</div>"
            "</article>"
        )
    permission_rows: list[str] = []
    for entry in reversed(permissions[-40:]):
        origin = _optional_str(entry.get("origin")) or "Unknown origin"
        feature = _optional_str(entry.get("feature")) or "permission"
        decision = (_optional_str(entry.get("decision")) or "prompt").replace("_", " ")
        permission_rows.append(
            '<article class="tblr-entry">'
            f"<strong>{html.escape(origin)}</strong>"
            f"<div class=\"tblr-meta\">{html.escape(feature)}<br/>{html.escape(decision.title())}<br/>{html.escape(_format_timestamp(entry.get('updated_at')))}</div>"
            "</article>"
        )
    handoff_rows: list[str] = []
    for entry in reversed(handoffs[-20:]):
        handoff_rows.append(
            '<article class="tblr-entry">'
            f"<strong>{html.escape(_optional_str(entry.get('kind')) or 'handoff')}</strong>"
            f"<div class=\"tblr-meta\">{html.escape(_optional_str(entry.get('reason')) or 'Manual review required')}<br/>{html.escape(_optional_str(entry.get('url')) or '')}<br/>{html.escape(_format_timestamp(entry.get('created_at')))}</div>"
            "</article>"
        )
    permissions_markup = "".join(permission_rows) or '<p class="tblr-empty">No saved permission decisions yet.</p>'
    pending_markup = "".join(pending_rows) or '<p class="tblr-empty">No pending permission requests.</p>'
    handoffs_markup = "".join(handoff_rows) or '<p class="tblr-empty">No recent auth or human handoffs.</p>'
    return (
        '<section class="tblr-list">'
        "<article class=\"tblr-entry\"><strong>Pending Requests</strong></article>"
        f"{pending_markup}"
        "</section>"
        '<section class="tblr-list">'
        "<article class=\"tblr-entry\"><strong>Permission Decisions</strong></article>"
        f"{permissions_markup}"
        "</section>"
        '<section class="tblr-list">'
        "<article class=\"tblr-entry\"><strong>Recent Handoffs</strong></article>"
        f"{handoffs_markup}"
        "</section>"
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _format_timestamp(value: Any) -> str:
    if value in {None, ""}:
        return ""
    try:
        import datetime as _dt

        ts = float(value)
        if ts <= 0:
            return ""
        dt = _dt.datetime.fromtimestamp(ts)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value)
