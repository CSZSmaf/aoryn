from __future__ import annotations

import html
from typing import Any

INTERNAL_PAGE_TITLES = {
    "home": "Home",
    "runtime": "Runtime Overview",
    "setup": "Browser Setup",
    "history": "History",
    "bookmarks": "Bookmarks",
    "downloads": "Downloads",
    "permissions": "Review Queue",
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
    if page == "home":
        return "", _build_blank_home_document()
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
        body = _build_collection_page(
            title="History",
            summary="Recent pages visited by the managed browser runtime.",
            count_text=f"{len(history)} saved visits",
            content=_build_internal_entries(
                history,
                empty_message="No browsing history yet.",
                primary_key="title",
                secondary_key="url",
                timestamp_key="visited_at",
            ),
        )
    elif page == "bookmarks":
        body = _build_collection_page(
            title="Bookmarks",
            summary="Saved pages collected from the browser menu and current tab.",
            count_text=f"{len(bookmarks)} saved bookmarks",
            content=_build_internal_entries(
                bookmarks,
                empty_message="No bookmarks yet.",
                primary_key="title",
                secondary_key="url",
                timestamp_key="created_at",
            ),
        )
    elif page == "downloads":
        body = _build_collection_page(
            title="Downloads",
            summary="Files downloaded through the managed browsing session.",
            count_text=f"{len(downloads)} recorded downloads",
            content=_build_internal_entries(
                downloads,
                empty_message="No downloads yet.",
                primary_key="file_name",
                secondary_key="url",
                timestamp_key="created_at",
                tertiary_key="path",
            ),
        )
    elif page == "permissions":
        body = _build_collection_page(
            title="Permissions",
            summary="Review decisions, prompts, and recent handoffs in one place.",
            count_text=(
                f"{len(permission_requests)} pending | "
                f"{len(permissions)} saved decisions | "
                f"{len(handoffs)} handoffs"
            ),
            content=_build_permission_entries(permissions, permission_requests, handoffs),
        )
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
            --bg: #edf2f7;
            --surface: rgba(255, 255, 255, 0.94);
            --surface-strong: rgba(255, 255, 255, 0.99);
            --surface-muted: #f4f7fb;
            --surface-ink: linear-gradient(135deg, #12233b 0%, #1b3252 58%, #244468 100%);
            --line: rgba(15, 23, 42, 0.08);
            --line-strong: rgba(15, 23, 42, 0.14);
            --ink: #0f172a;
            --muted: #607089;
            --accent: #2563eb;
            --accent-soft: rgba(37, 99, 235, 0.1);
            --accent-strong: #1749b5;
            --danger: #d63939;
            --shadow-soft: 0 18px 46px rgba(15, 23, 42, 0.08);
            --shadow-tight: 0 10px 24px rgba(15, 23, 42, 0.04);
            --radius-xl: 28px;
            --radius-lg: 22px;
            --radius-md: 16px;
          }}
          * {{ box-sizing: border-box; }}
          html {{
            background: var(--bg);
          }}
          body {{
            margin: 0;
            min-height: 100vh;
            color: var(--ink);
            font-family: "Segoe UI Variable Display", "Aptos", "PingFang SC", sans-serif;
            background:
              radial-gradient(circle at top, rgba(37, 99, 235, 0.12), transparent 34%),
              linear-gradient(180deg, #f9fbfe 0%, var(--bg) 48%, #e9eef5 100%);
            padding: 28px clamp(20px, 3vw, 42px) 72px;
          }}
          body::before {{
            content: "";
            position: fixed;
            inset: 0;
            pointer-events: none;
            background:
              linear-gradient(90deg, rgba(255, 255, 255, 0.2) 0, rgba(255, 255, 255, 0.2) 1px, transparent 1px, transparent 72px),
              linear-gradient(rgba(255, 255, 255, 0.16) 0, rgba(255, 255, 255, 0.16) 1px, transparent 1px, transparent 72px);
            opacity: 0.24;
            mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.52), transparent 82%);
          }}
          a {{ color: inherit; text-decoration: none; }}
          .tblr-shell {{
            position: relative;
            max-width: 1220px;
            margin: 0 auto;
          }}
          .tblr-head {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            margin-bottom: 14px;
            padding: 14px 16px;
            border-radius: var(--radius-lg);
            border: 1px solid var(--line);
            background: rgba(255, 255, 255, 0.72);
            backdrop-filter: blur(18px);
            box-shadow: var(--shadow-tight);
          }}
          .tblr-brand {{
            display: flex;
            align-items: center;
            gap: 12px;
          }}
          .tblr-logo {{
            width: 42px;
            height: 42px;
            border-radius: 14px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border: 1px solid rgba(255, 255, 255, 0.18);
            background: var(--surface-ink);
            color: #f8fbff;
            font-weight: 700;
            font-size: 16px;
            box-shadow: 0 14px 28px rgba(18, 35, 59, 0.24);
          }}
          .tblr-brand h1 {{
            margin: 0;
            font-family: "Bahnschrift SemiBold", "Segoe UI Variable Display", sans-serif;
            font-size: 1.1rem;
            letter-spacing: -0.02em;
          }}
          .tblr-brand p {{
            margin: 3px 0 0;
            color: var(--muted);
            font-size: 12.5px;
          }}
          .tblr-badges {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            justify-content: flex-end;
          }}
          .tblr-badge {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            min-height: 34px;
            padding: 6px 12px;
            border-radius: 999px;
            border: 1px solid var(--line);
            background: rgba(255, 255, 255, 0.82);
            color: var(--muted);
            font-size: 12px;
            font-weight: 600;
          }}
          .tblr-badge strong {{
            color: var(--ink);
          }}
          .tblr-nav {{
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
            margin-bottom: 14px;
            padding: 7px;
            border-radius: 999px;
            border: 1px solid var(--line);
            background: rgba(255, 255, 255, 0.72);
            backdrop-filter: blur(18px);
            box-shadow: var(--shadow-tight);
          }}
          .tblr-nav-link {{
            padding: 9px 14px;
            border-radius: 999px;
            border: 1px solid transparent;
            background: transparent;
            color: var(--muted);
            font-size: 13px;
            font-weight: 600;
            transition: background 160ms ease, color 160ms ease, border-color 160ms ease;
          }}
          .tblr-nav-link:hover {{
            color: var(--ink);
            background: rgba(255, 255, 255, 0.82);
            border-color: var(--line);
          }}
          .tblr-nav-link.is-active {{
            border-color: rgba(37, 99, 235, 0.16);
            background: rgba(255, 255, 255, 0.96);
            color: var(--accent);
            box-shadow: inset 0 0 0 1px rgba(37, 99, 235, 0.05);
          }}
          .tblr-alert {{
            margin-bottom: 14px;
            padding: 14px 16px;
            border-radius: var(--radius-md);
            border: 1px solid rgba(214, 57, 57, 0.35);
            background: rgba(214, 57, 57, 0.08);
            color: #7f1d1d;
          }}
          .tblr-hero,
          .tblr-list {{
            position: relative;
            border: 1px solid var(--line);
            border-radius: var(--radius-xl);
            padding: 24px;
            box-shadow: var(--shadow-soft);
            overflow: hidden;
          }}
          .tblr-hero {{
            background: var(--surface-ink);
            color: #f8fbff;
            border-color: rgba(255, 255, 255, 0.08);
          }}
          .tblr-hero::after {{
            content: "";
            position: absolute;
            inset: auto -60px -90px auto;
            width: 280px;
            height: 280px;
            border-radius: 999px;
            background: radial-gradient(circle, rgba(255, 255, 255, 0.16), transparent 68%);
            pointer-events: none;
          }}
          .tblr-hero--compact {{
            background: rgba(255, 255, 255, 0.8);
            color: var(--ink);
            border-color: var(--line);
            padding-bottom: 18px;
          }}
          .tblr-hero h2 {{
            margin: 0 0 10px;
            font-family: "Bahnschrift SemiBold", "Segoe UI Variable Display", sans-serif;
            font-size: clamp(1.8rem, 2vw, 2.35rem);
            letter-spacing: -0.02em;
            line-height: 1.08;
          }}
          .tblr-hero p {{
            max-width: 860px;
            margin: 0;
            color: rgba(226, 232, 240, 0.88);
            line-height: 1.62;
            font-size: 1.02rem;
          }}
          .tblr-hero--compact h2 {{
            font-size: clamp(1.55rem, 1.7vw, 1.9rem);
            color: var(--ink);
          }}
          .tblr-hero--compact p {{
            color: var(--muted);
            font-size: 0.99rem;
          }}
          .tblr-inline-stat {{
            display: inline-flex;
            align-items: center;
            min-height: 34px;
            margin-top: 16px;
            padding: 6px 12px;
            border-radius: 999px;
            border: 1px solid var(--line);
            background: rgba(255, 255, 255, 0.84);
            color: var(--accent-strong);
            font-size: 12px;
            font-weight: 600;
          }}
          .tblr-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(196px, 1fr));
            gap: 14px;
            margin-top: 22px;
          }}
          .tblr-card {{
            padding: 16px;
            border-radius: var(--radius-md);
            border: 1px solid rgba(255, 255, 255, 0.08);
            background: rgba(255, 255, 255, 0.09);
            backdrop-filter: blur(10px);
          }}
          .tblr-card strong {{
            display: block;
            margin-bottom: 8px;
            color: rgba(226, 232, 240, 0.82);
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.08em;
          }}
          .tblr-card > span {{
            display: block;
            color: #ffffff;
            font-size: 1.18rem;
            font-weight: 700;
            line-height: 1.2;
          }}
          .tblr-card .tblr-meta,
          .tblr-meta {{
            color: var(--muted);
            font-size: 13px;
          }}
          .tblr-card .tblr-meta {{
            margin-top: 8px;
            color: rgba(226, 232, 240, 0.74);
            line-height: 1.55;
          }}
          .tblr-hero--compact .tblr-card,
          .tblr-list .tblr-card {{
            background: var(--surface-muted);
            border-color: var(--line);
            backdrop-filter: none;
          }}
          .tblr-hero--compact .tblr-card strong,
          .tblr-list .tblr-card strong {{
            color: var(--muted);
          }}
          .tblr-hero--compact .tblr-card > span,
          .tblr-list .tblr-card > span {{
            color: var(--ink);
          }}
          .tblr-hero--compact .tblr-card .tblr-meta,
          .tblr-list .tblr-card .tblr-meta {{
            color: var(--muted);
          }}
          .tblr-links {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 22px;
          }}
          .tblr-chip {{
            display: inline-flex;
            align-items: center;
            min-height: 34px;
            padding: 7px 12px;
            border-radius: 999px;
            border: 1px solid rgba(255, 255, 255, 0.14);
            background: rgba(255, 255, 255, 0.1);
            color: #f8fbff;
            font-size: 12px;
            font-weight: 600;
            transition: transform 160ms ease, background 160ms ease;
          }}
          .tblr-chip:hover {{
            transform: translateY(-1px);
            background: rgba(255, 255, 255, 0.16);
          }}
          .tblr-list {{
            margin-top: 16px;
            background: var(--surface);
          }}
          .tblr-entry {{
            padding: 16px 18px;
            border: 1px solid var(--line);
            border-radius: 18px;
            background: var(--surface-muted);
            margin-top: 12px;
          }}
          .tblr-entry:first-child {{
            margin-top: 0;
          }}
          .tblr-entry strong {{
            display: block;
            margin-bottom: 8px;
            font-size: 1rem;
            letter-spacing: -0.01em;
          }}
          .tblr-entry a {{
            color: var(--accent);
          }}
          .tblr-entry a:hover {{
            color: var(--accent-strong);
          }}
          .tblr-empty {{
            margin: 0;
            color: var(--muted);
            padding: 18px 0 2px;
          }}
          .tblr-section-head {{
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 16px;
            margin-bottom: 16px;
          }}
          .tblr-section-kicker {{
            margin-bottom: 8px;
            color: var(--accent-strong);
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.12em;
            text-transform: uppercase;
          }}
          .tblr-section-title {{
            margin: 0;
            font-family: "Bahnschrift SemiBold", "Segoe UI Variable Display", sans-serif;
            font-size: 1.35rem;
            letter-spacing: -0.02em;
          }}
          .tblr-section-copy {{
            max-width: 760px;
            margin: 8px 0 0;
            color: var(--muted);
            line-height: 1.56;
          }}
          .tblr-meta-pills {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
          }}
          .tblr-meta-pill {{
            display: inline-flex;
            align-items: center;
            min-height: 30px;
            padding: 6px 10px;
            border-radius: 999px;
            background: var(--surface-strong);
            border: 1px solid var(--line);
            color: var(--muted);
            font-size: 12px;
            line-height: 1.2;
          }}
          .tblr-route-grid {{
            margin-top: 18px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 14px;
          }}
          .tblr-route-path {{
            display: inline-flex;
            margin-top: 8px;
            padding: 5px 9px;
            border-radius: 999px;
            background: var(--accent-soft);
            font-family: "Cascadia Mono", Consolas, monospace;
            color: var(--accent);
            font-size: 12px;
            word-break: break-all;
          }}
          @media (max-width: 760px) {{
            body {{ padding: 18px 14px 48px; }}
            .tblr-head {{
              flex-direction: column;
              align-items: flex-start;
            }}
            .tblr-badges {{
              justify-content: flex-start;
            }}
            .tblr-section-head {{
              flex-direction: column;
            }}
            .tblr-hero,
            .tblr-list {{
              padding: 20px;
              border-radius: 24px;
            }}
          }}
        </style>
      </head>
      <body class="tblr-page tblr-page--{html.escape(page)}">
        <main class="tblr-shell">
          <header class="tblr-head">
            <div class="tblr-brand">
              <div class="tblr-logo">A</div>
              <div>
                <h1>Aoryn Browser</h1>
                <p>Managed browser surface for the desktop app</p>
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


def _build_blank_home_document() -> str:
    return """
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title></title>
        <style>
          :root {
            color-scheme: light;
            --page-bg: #ffffff;
            --wordmark: #1f3d70;
            --wordmark-soft: #5b7fb6;
            --search-bg: #ffffff;
            --search-border: #dfe1e5;
            --search-border-hover: #d2d6dc;
            --search-shadow: 0 1px 6px rgba(32, 33, 36, 0.18);
            --text-soft: #6f7782;
          }
          * {
            box-sizing: border-box;
          }
          html, body {
            margin: 0;
            min-height: 100%;
          }
          body {
            display: flex;
            align-items: flex-start;
            justify-content: center;
            width: 100%;
            padding-top: min(16vh, 132px);
            background: var(--page-bg);
            font-family: Arial, "Segoe UI", sans-serif;
          }
          .tblr-home-shell {
            width: min(760px, calc(100vw - 64px));
            display: grid;
            gap: 28px;
            justify-items: center;
            position: relative;
          }
          .tblr-wordmark {
            display: inline-flex;
            align-items: baseline;
            justify-content: center;
            gap: 2px;
            font-size: clamp(54px, 9vw, 86px);
            font-weight: 700;
            letter-spacing: -0.06em;
            line-height: 1;
            user-select: none;
          }
          .tblr-wordmark-main {
            color: var(--wordmark);
          }
          .tblr-wordmark-accent {
            color: var(--wordmark-soft);
          }
          .tblr-search-shell {
            width: min(640px, calc(100vw - 72px));
            display: flex;
            align-items: center;
            padding: 0 18px;
            height: 50px;
            border-radius: 999px;
            border: 1px solid var(--search-border);
            background: var(--search-bg);
            cursor: text;
          }
          .tblr-search-shell:hover {
            border-color: var(--search-border-hover);
            box-shadow: var(--search-shadow);
          }
          .tblr-search-main {
            display: flex;
            align-items: center;
            gap: 14px;
            min-width: 0;
            flex: 1;
          }
          .tblr-search-icon {
            position: relative;
            width: 16px;
            height: 16px;
            border: 2px solid #9aa0a6;
            border-radius: 999px;
            flex: none;
          }
          .tblr-search-icon::after {
            content: "";
            position: absolute;
            right: -6px;
            bottom: -4px;
            width: 8px;
            height: 2px;
            border-radius: 999px;
            background: #9aa0a6;
            transform: rotate(45deg);
            transform-origin: center;
          }
          .tblr-search-label {
            appearance: none;
            border: 0;
            outline: 0;
            background: transparent;
            width: 100%;
            min-width: 0;
            color: var(--text-soft);
            font-size: 16px;
            line-height: 1;
            padding: 0;
            margin: 0;
            font-family: Arial, "Segoe UI", sans-serif;
          }
          .tblr-search-label::placeholder {
            color: var(--text-soft);
          }
          @media (max-width: 720px) {
            .tblr-home-shell {
              width: calc(100vw - 28px);
            }
            .tblr-search-shell {
              width: calc(100vw - 40px);
            }
            body {
              padding-top: 90px;
            }
          }
        </style>
      </head>
      <body>
        <main class="tblr-home-shell">
          <div class="tblr-wordmark" aria-hidden="true">
            <span class="tblr-wordmark-main">Aoryn</span><span class="tblr-wordmark-accent">.</span>
          </div>
          <form id="new-tab-search" class="tblr-search-shell" action="aoryn://focus-address" method="get" autocomplete="off">
            <div class="tblr-search-main">
              <div class="tblr-search-icon" aria-hidden="true"></div>
              <input
                id="new-tab-search-input"
                class="tblr-search-label"
                type="text"
                name="query"
                placeholder="Search or enter address"
                autocomplete="off"
                autocapitalize="off"
                spellcheck="false"
              />
            </div>
          </form>
        </main>
        <script>
          (() => {
            const form = document.getElementById("new-tab-search");
            const input = document.getElementById("new-tab-search-input");
            if (!form || !input) return;

            const submit = () => {
              const value = String(input.value || "").trim();
              if (!value) {
                input.focus();
                return;
              }
              window.location.href = "aoryn://focus-address?query=" + encodeURIComponent(value);
            };

            form.addEventListener("submit", (event) => {
              event.preventDefault();
              submit();
            });

            form.addEventListener("click", () => input.focus());

            window.addEventListener("keydown", (event) => {
              const active = document.activeElement;
              if (active === input || event.ctrlKey || event.metaKey || event.altKey) return;
              if (event.key === "/" || (event.key.length === 1 && !event.repeat)) {
                input.focus();
                if (event.key.length === 1 && event.key !== "/") {
                  input.value = event.key;
                }
                event.preventDefault();
              }
            });

            window.addEventListener("load", () => input.focus());
          })();
        </script>
      </body>
    </html>
    """


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


def _build_collection_page(*, title: str, summary: str, count_text: str, content: str) -> str:
    return (
        '<section class="tblr-hero tblr-hero--compact">'
        f"<h2>{html.escape(title)}</h2>"
        f"<p>{html.escape(summary)}</p>"
        f'<div class="tblr-inline-stat">{html.escape(count_text)}</div>'
        "</section>"
        f"{content}"
    )


def _build_section_card(*, kicker: str, title: str, summary: str, content: str, aside: str | None = None) -> str:
    aside_markup = ""
    if _optional_str(aside):
        aside_markup = f'<div class="tblr-inline-stat">{html.escape(_optional_str(aside) or "")}</div>'
    return (
        '<section class="tblr-list">'
        '<div class="tblr-section-head">'
        "<div>"
        f'<div class="tblr-section-kicker">{html.escape(kicker)}</div>'
        f'<h3 class="tblr-section-title">{html.escape(title)}</h3>'
        f'<p class="tblr-section-copy">{html.escape(summary)}</p>'
        "</div>"
        f"{aside_markup}"
        "</div>"
        f"{content}"
        "</section>"
    )


def _render_meta_pills(parts: list[str]) -> str:
    items = [part for part in parts if _optional_str(part)]
    if not items:
        return ""
    return '<div class="tblr-meta-pills">' + "".join(f'<span class="tblr-meta-pill">{item}</span>' for item in items) + "</div>"


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
    return _build_section_card(
        kicker="Runtime",
        title="Runtime routes",
        summary="These local endpoints are what the desktop app calls when it drives browsing, DOM inspection, waiting, downloads, and handoff checks.",
        aside=_optional_str(payload.get("transport")) or "local_http",
        content=f'<div class="tblr-route-grid">{"".join(cards)}</div>',
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
          <p>This browser is the desktop app's control surface. Aoryn can navigate, inspect the DOM, wait for UI state, and pause here when human review is needed.</p>
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
            <a class="tblr-chip" href="aoryn://runtime">Runtime overview</a>
            <a class="tblr-chip" href="aoryn://setup">Model and browser setup</a>
            <a class="tblr-chip" href="aoryn://history">Research trail</a>
            <a class="tblr-chip" href="aoryn://permissions">Review queue</a>
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
          <h2>Browser runtime for the desktop workbench.</h2>
          <p>The desktop executor talks to this browser over local HTTP. These metrics show whether the managed runtime is ready for navigation, DOM inspection, downloads, and review pauses.</p>
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
            f"{_render_meta_pills(meta_parts)}"
            "</article>"
        )
    return f'<section class="tblr-list">{"".join(rows)}</section>'


def _build_ai_setup_page(assistant_setup: dict[str, Any] | None) -> str:
    payload = assistant_setup or {}
    status = html.escape(_optional_str(payload.get("status")) or "Setup needed")
    detail = html.escape(_optional_str(payload.get("detail")) or "Open Setup in the toolbar to connect browser AI.")
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
          <h2>Configure browser AI and the execution browser in one place.</h2>
          <p>Setup writes to the same local runtime preferences used by Aoryn tasks, so browser AI and desktop runs stay aligned.</p>
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
            f"{_render_meta_pills([html.escape(_optional_str(entry.get('feature')) or 'permission'), html.escape(_optional_str(entry.get('request_id')) or ''), html.escape(_format_timestamp(entry.get('requested_at')))])}"
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
            f"{_render_meta_pills([html.escape(feature), html.escape(decision.title()), html.escape(_format_timestamp(entry.get('updated_at')))])}"
            "</article>"
        )
    handoff_rows: list[str] = []
    for entry in reversed(handoffs[-20:]):
        handoff_rows.append(
            '<article class="tblr-entry">'
            f"<strong>{html.escape(_optional_str(entry.get('kind')) or 'handoff')}</strong>"
            f"{_render_meta_pills([html.escape(_optional_str(entry.get('reason')) or 'Manual review required'), html.escape(_optional_str(entry.get('url')) or ''), html.escape(_format_timestamp(entry.get('created_at')))])}"
            "</article>"
        )
    permissions_markup = "".join(permission_rows) or '<p class="tblr-empty">No saved permission decisions yet.</p>'
    pending_markup = "".join(pending_rows) or '<p class="tblr-empty">No pending permission requests.</p>'
    handoffs_markup = "".join(handoff_rows) or '<p class="tblr-empty">No recent auth or human handoffs.</p>'
    return (
        _build_section_card(
            kicker="Review",
            title="Pending Requests",
            summary="Prompts waiting for a human decision before the managed browser can continue.",
            aside=f"{len(permission_requests)} open",
            content=pending_markup,
        )
        + _build_section_card(
            kicker="Review",
            title="Permission Decisions",
            summary="Saved allow, deny, and prompt decisions that speed up repeat browsing tasks.",
            aside=f"{len(permissions)} saved",
            content=permissions_markup,
        )
        + _build_section_card(
            kicker="Review",
            title="Recent Handoffs",
            summary="Authentication pauses and operator checkpoints captured during recent runs.",
            aside=f"{len(handoffs)} events",
            content=handoffs_markup,
        )
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
