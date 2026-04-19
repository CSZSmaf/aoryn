from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import uuid4

from desktop_agent import aoryn_browser as browser_module
from desktop_agent.browser_runtime import BrowserRuntimeError
from desktop_agent.config import AgentConfig
from desktop_agent.aoryn_browser import (
    DEFAULT_BROWSER_HOMEPAGE,
    build_browser_assistant_setup_snapshot,
    build_browser_ai_setup_summary,
    build_internal_page_html,
    build_browser_assistant_user_message,
    build_browser_digest,
    build_browser_http_error_payload,
    build_browser_service_summary,
    browser_session_path,
    detect_browser_handoff_reason,
    load_browser_state,
    normalize_annotation_entries,
    normalize_browser_upload_paths,
    normalize_handoff_entries,
    normalize_browser_target,
    normalize_download_state_name,
    normalize_permission_entries,
    normalize_permission_request_entries,
    save_browser_state,
    write_browser_json_response,
)
from desktop_agent.runtime_paths import runtime_preferences_path_for


def test_normalize_browser_target_supports_internal_urls_hosts_and_search_queries():
    assert normalize_browser_target(None) == DEFAULT_BROWSER_HOMEPAGE
    assert normalize_browser_target("aoryn://history") == "aoryn://history"
    assert normalize_browser_target("example.com/docs") == "https://example.com/docs"
    assert normalize_browser_target("localhost:3000") == "https://localhost:3000"
    assert normalize_browser_target("latest ai browser") == "https://www.google.com/search?q=latest+ai+browser"


def test_save_and_load_browser_state_round_trip():
    temp_root = Path("test_artifacts") / f"aoryn_browser_state_{uuid4().hex}"
    try:
        state = {
            "bookmarks": [{"title": "Aoryn", "url": "https://aoryn.org", "created_at": 1.0}],
            "downloads": [{"file_name": "aoryn.exe", "url": "https://downloads.aoryn.org/a.exe", "created_at": 2.0}],
            "history": [{"title": "Docs", "url": "https://docs.aoryn.org", "visited_at": 3.0}],
            "windows": [{"window_id": "abc", "tabs": [{"tab_id": "tab1", "url": "aoryn://home"}], "active_tab_id": "tab1"}],
            "annotations": [
                {
                    "tab_id": "tab1",
                    "annotation_id": "ann-1",
                    "selector": "#hero",
                    "label": "Hero",
                    "created_at": 4.0,
                }
            ],
            "permissions": [
                {
                    "origin": "https://example.com",
                    "feature": "notifications",
                    "decision": "allow",
                    "updated_at": 5.0,
                }
            ],
            "permission_requests": [
                {
                    "request_id": "req-1",
                    "origin": "https://example.com",
                    "feature": "camera",
                    "tab_id": "tab1",
                    "requested_at": 5.5,
                }
            ],
            "handoffs": [
                {
                    "kind": "detected_auth",
                    "reason": "Login flow requires human review.",
                    "url": "https://example.com/login",
                    "title": "Sign in",
                    "created_at": 6.0,
                }
            ],
            "auth_pause_reason": "Captcha pending",
        }

        path = save_browser_state(temp_root, state)
        restored = load_browser_state(temp_root)

        assert path == browser_session_path(temp_root)
        assert restored == state
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_build_internal_page_html_renders_home_and_download_entries():
    title, document = build_internal_page_html(
        "downloads",
        downloads=[
            {
                "file_name": "AorynBrowser-Setup.exe",
                "url": "https://downloads.aoryn.org/AorynBrowser-Setup.exe",
                "path": "C:/Downloads/AorynBrowser-Setup.exe",
                "created_at": 1710000000.0,
            }
        ],
        auth_pause_reason="User must complete login",
    )

    assert title == "Downloads"
    assert "AorynBrowser-Setup.exe" in document
    assert "User must complete login" in document
    assert "aoryn://history" in document


def test_build_internal_page_html_home_is_blank():
    title, document = build_internal_page_html(
        "home",
        assistant_setup={"status": "Ready", "provider_label": "Local LM Studio", "model_display": "auto"},
        service_summary=build_browser_service_summary(
            base_url="http://127.0.0.1:38991",
            transport="local_http",
            status="ready",
            window_count=1,
            tab_count=2,
            active_title="Aoryn Docs",
            active_url="https://docs.aoryn.org/browser",
            pending_permissions=0,
            handoff_count=3,
            annotation_count=1,
        ),
    )

    assert title == ""
    assert 'id="new-tab-search"' in document
    assert 'id="new-tab-search-input"' in document
    assert 'name="query"' in document
    assert 'action="aoryn://focus-address"' in document
    assert 'window.location.href = "aoryn://focus-address?query="' in document
    assert "Managed browser runtime for Aoryn tasks." not in document
    assert "Runtime Overview" not in document
    assert "aoryn://history" not in document
    assert "tblr-home-stage" not in document


def test_build_internal_page_html_runtime_renders_service_console():
    title, document = build_internal_page_html(
        "runtime",
        assistant_setup={"status": "Ready", "provider_label": "OpenAI API"},
        service_summary=build_browser_service_summary(
            base_url="http://127.0.0.1:38991",
            transport="local_http",
            status="paused_for_auth",
            window_count=1,
            tab_count=4,
            active_title="Sign in",
            active_url="https://example.com/login",
            pending_permissions=2,
            handoff_count=4,
            annotation_count=2,
            auth_pause_reason="CAPTCHA or bot verification requires human completion.",
        ),
    )

    assert title == "Runtime Overview"
    assert "Browser runtime for the desktop workbench." in document
    assert "http://127.0.0.1:38991" in document
    assert "/get_session_state" in document
    assert "paused for auth" in document.lower()


def test_build_internal_page_html_setup_renders_effective_ai_configuration():
    title, document = build_internal_page_html(
        "setup",
        assistant_setup={
            "status": "Ready",
            "detail": "Local LM Studio will answer questions about the current page.",
            "provider_label": "Local LM Studio",
            "model_display": "qwen/qwen3-14b",
            "base_url": "http://127.0.0.1:1234/v1",
            "api_key_configured": False,
            "browser_channel_label": "Microsoft Edge",
            "browser_executable_path": "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
            "browser_headless": False,
            "runtime_preferences_path": "C:/Users/demo/AppData/Roaming/Aoryn/runtime-preferences.json",
            "config_path": "C:/Users/demo/AppData/Roaming/Aoryn/config.yaml",
        },
    )

    assert title == "Browser Setup"
    assert "Local LM Studio" in document
    assert "runtime-preferences.json" in document
    assert "qwen/qwen3-14b" in document


def test_normalize_annotation_entries_filters_invalid_rows():
    entries = normalize_annotation_entries(
        [
            {"tab_id": "tab1", "annotation_id": "ann-1", "selector": "#main", "label": "Main"},
            {"tab_id": "", "annotation_id": "ann-2", "selector": "#skip"},
            {"annotation_id": "ann-3", "selector": "#skip"},
            "invalid",
        ]
    )

    assert entries == [
        {
            "tab_id": "tab1",
            "annotation_id": "ann-1",
            "selector": "#main",
            "label": "Main",
            "created_at": entries[0]["created_at"],
        }
    ]


def test_normalize_permission_and_handoff_entries_filter_invalid_rows():
    permissions = normalize_permission_entries(
        [
            {"origin": "https://example.com", "feature": "notifications", "decision": "allow"},
            {"origin": "", "feature": "camera", "decision": "deny"},
            "invalid",
        ]
    )
    handoffs = normalize_handoff_entries(
        [
            {"kind": "detected_auth", "reason": "Login flow requires human review.", "url": "https://example.com/login"},
            {"kind": "", "reason": "skip"},
        ]
    )
    permission_requests = normalize_permission_request_entries(
        [
            {"request_id": "req-1", "origin": "https://example.com", "feature": "camera", "tab_id": "tab-1"},
            {"request_id": "", "origin": "https://example.com", "feature": "camera"},
        ]
    )

    assert permissions == [
        {
            "origin": "https://example.com",
            "feature": "notifications",
            "decision": "allow",
            "updated_at": permissions[0]["updated_at"],
        }
    ]
    assert handoffs == [
        {
            "kind": "detected_auth",
            "reason": "Login flow requires human review.",
            "url": "https://example.com/login",
            "title": None,
            "created_at": handoffs[0]["created_at"],
        }
    ]
    assert permission_requests == [
        {
            "request_id": "req-1",
            "origin": "https://example.com",
            "feature": "camera",
            "tab_id": "tab-1",
            "requested_at": permission_requests[0]["requested_at"],
        }
    ]


def test_detect_browser_handoff_reason_handles_login_and_captcha_terms():
    assert detect_browser_handoff_reason(url="https://example.com/login", title="Sign in") == "Sign-in flow requires human review."
    assert detect_browser_handoff_reason(url="https://example.com", title="Please complete CAPTCHA") == "CAPTCHA or bot verification requires human completion."
    assert detect_browser_handoff_reason(url="https://example.com/docs", title="Documentation") is None


def test_build_browser_digest_returns_summary_and_handoff_variants():
    snapshot = {
        "title": "Aoryn Docs",
        "url": "https://docs.aoryn.org/browser",
        "text": "Aoryn Browser keeps a clean chrome. It opens an AI side panel. It supports page handoff into the desktop agent.",
    }

    summary = build_browser_digest(snapshot, mode="summary")
    handoff = build_browser_digest(snapshot, mode="handoff")

    assert "Quick summary" in summary
    assert "Ready for agent handoff" in handoff
    assert "Aoryn Docs" in summary


def test_build_browser_assistant_user_message_grounds_prompt_in_page_context():
    message = build_browser_assistant_user_message(
        {
            "title": "Aoryn Docs",
            "url": "https://docs.aoryn.org/browser",
            "text": "Aoryn Browser supports browsing, summaries, and agent handoff.",
        },
        "用中文总结这一页的重点",
    )

    assert "Page title: Aoryn Docs" in message
    assert "https://docs.aoryn.org/browser" in message
    assert "用中文总结这一页的重点" in message
    assert "Visible page text" in message


def test_build_browser_ai_setup_summary_reports_missing_api_key_for_hosted_provider():
    summary = build_browser_ai_setup_summary(
        AgentConfig(
            model_provider="openai_api",
            model_base_url="https://api.openai.com/v1",
            model_name="gpt-5.4-mini",
            model_api_key=None,
            browser_channel="msedge",
            browser_executable_path="",
            browser_headless=False,
        ),
        provider_options=[
            {"value": "openai_api", "label": "OpenAI API", "api_key_required": True},
        ],
        browser_channel_options=[
            {"value": "msedge", "label": "Microsoft Edge"},
        ],
        config_path=Path("config.yaml"),
        runtime_preferences_path=Path("runtime-preferences.json"),
    )

    assert summary["status"] == "API key needed"
    assert summary["provider_label"] == "OpenAI API"
    assert summary["browser_channel_label"] == "Microsoft Edge"


def test_build_browser_assistant_setup_snapshot_avoids_dashboard_meta_and_runtime_probe(monkeypatch):
    import desktop_agent.dashboard as dashboard_module

    temp_root = Path("test_artifacts") / f"aoryn_browser_setup_snapshot_{uuid4().hex}"
    prefs_path = None
    try:
        temp_root.mkdir(parents=True)
        config_path = temp_root / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "model_provider: lmstudio_local",
                    "model_base_url: http://127.0.0.1:1234/v1",
                    "model_name: auto",
                    "browser_headless: false",
                ]
            ),
            encoding="utf-8",
        )
        prefs_path = runtime_preferences_path_for(config_path)
        prefs_path.write_text(
            json.dumps({"config_overrides": {"browser_channel": "msedge"}, "ui_preferences": {"onboarding_completed": False}}),
            encoding="utf-8",
        )

        monkeypatch.setattr(
            dashboard_module.DashboardApp,
            "meta",
            lambda self: (_ for _ in ()).throw(AssertionError("browser setup snapshot should not call DashboardApp.meta")),
        )
        monkeypatch.setattr(
            dashboard_module,
            "browser_runtime_status",
            lambda config: (_ for _ in ()).throw(AssertionError("browser setup snapshot should not probe browser runtime status")),
        )

        snapshot = build_browser_assistant_setup_snapshot(config_path)

        assert snapshot["summary"]["provider_label"] == "Local LM Studio"
        assert snapshot["effective"]["browser_channel"] == "msedge"
        assert snapshot["runtime_preferences_path"] == str(prefs_path)
    finally:
        if prefs_path is not None:
            prefs_path.unlink(missing_ok=True)
        shutil.rmtree(temp_root, ignore_errors=True)


def test_build_browser_service_summary_exposes_runtime_routes_and_counts():
    summary = build_browser_service_summary(
        base_url="http://127.0.0.1:38991",
        transport="local_http",
        status="ready",
        window_count=2,
        tab_count=5,
        active_title="Aoryn Docs",
        active_url="https://docs.aoryn.org/browser",
        pending_permissions=1,
        handoff_count=3,
        annotation_count=2,
    )

    assert summary["badge_text"] == "Service ready"
    assert summary["window_count"] == 2
    assert summary["tab_count"] == 5
    assert summary["routes"][-1]["path"] == "/get_session_state"


def test_build_browser_http_error_payload_marks_runtime_failures():
    payload = build_browser_http_error_payload(BrowserRuntimeError("UI thread timeout"))

    assert payload == {
        "ok": False,
        "error": "UI thread timeout",
        "error_type": "runtime",
    }


def test_write_browser_json_response_ignores_client_disconnects():
    class _BrokenWriter:
        def write(self, _raw):
            raise ConnectionAbortedError("socket closed")

    class _FakeHandler:
        def __init__(self):
            self.headers = []
            self.wfile = _BrokenWriter()

        def send_response(self, status):
            self.status = status

        def send_header(self, name, value):
            self.headers.append((name, value))

        def end_headers(self):
            self.ended = True

    handler = _FakeHandler()

    assert write_browser_json_response(handler, {"ok": True}) is False


def test_normalize_browser_upload_paths_and_download_state_name():
    temp_root = Path("test_artifacts") / f"aoryn_browser_upload_{uuid4().hex}"
    try:
        temp_root.mkdir(parents=True)
        upload_file = temp_root / "sample.txt"
        upload_file.write_text("hello", encoding="utf-8")

        paths = normalize_browser_upload_paths([str(upload_file), str(temp_root / "missing.txt")])

        assert paths == [str(upload_file.resolve())]
        assert normalize_download_state_name("DownloadInProgress") == "in_progress"
        assert normalize_download_state_name("DownloadCompleted") == "completed"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_browser_window_runtime_accessor_survives_runtime_reference_assignment():
    if browser_module.QApplication is None:
        return

    app = browser_module.QApplication.instance() or browser_module.QApplication([])
    temp_root = Path("test_artifacts") / f"aoryn_browser_window_{uuid4().hex}"
    window = None
    try:
        temp_root.mkdir(parents=True)
        profile = browser_module.QWebEngineProfile(f"test-{uuid4().hex}", app)
        profile.setPersistentStoragePath(str(temp_root / "storage"))
        profile.setCachePath(str(temp_root / "cache"))
        window = browser_module.BrowserWindow(
            profile=profile,
            icon_path=Path("desktop_agent") / "dashboard_assets" / "icons" / "aoryn-browser.ico",
            homepage_url=DEFAULT_BROWSER_HOMEPAGE,
            search_url="https://www.google.com/search?q={query}",
        )
        runtime_ref = object()
        window._browser_runtime_ref = runtime_ref  # type: ignore[attr-defined]

        assert window._browser_runtime() is runtime_ref  # type: ignore[attr-defined]
    finally:
        try:
            if window is not None:
                window.close()
        except Exception:
            pass
        shutil.rmtree(temp_root, ignore_errors=True)


def test_browser_window_assistant_dock_toggle_smoke():
    if browser_module.QApplication is None:
        return

    app = browser_module.QApplication.instance() or browser_module.QApplication([])
    temp_root = Path("test_artifacts") / f"aoryn_browser_window_toggle_{uuid4().hex}"
    window = None
    try:
        temp_root.mkdir(parents=True)
        profile = browser_module.QWebEngineProfile(f"test-{uuid4().hex}", app)
        profile.setPersistentStoragePath(str(temp_root / "storage"))
        profile.setCachePath(str(temp_root / "cache"))
        window = browser_module.BrowserWindow(
            profile=profile,
            icon_path=Path("desktop_agent") / "dashboard_assets" / "icons" / "aoryn-browser.ico",
            homepage_url=DEFAULT_BROWSER_HOMEPAGE,
            search_url="https://www.google.com/search?q={query}",
        )
        window.show()
        home_view = browser_module.QWidget(window)
        tab_id = "home-tab"
        window._tab_refs.append(  # type: ignore[attr-defined]
            browser_module._BrowserTab(  # type: ignore[attr-defined]
                tab_id=tab_id,
                view=home_view,
                internal_page="home",
                display_url=DEFAULT_BROWSER_HOMEPAGE,
            )
        )
        index = window.tabs.addTab(home_view, "")
        window.tabs.setCurrentIndex(index)
        window._update_tab_title(tab_id, "")
        window._sync_address_bar()
        app.processEvents()

        assert window.address_bar.placeholderText() == "Search or enter address"
        assert window.address_bar.text() == ""
        assert bool(window.address_bar.alignment() & browser_module.Qt.AlignmentFlag.AlignVCenter)
        assert window.tabs.tabText(0) == ""
        assert not window.tabs.tabBar().isVisible()
        assert not window.tab_strip.isVisible()
        assert window.windowTitle() == f"{browser_module.APP_NAME} Browser"
        assert not window.windowIcon().isNull()
        assert not window.back_button.icon().isNull()
        assert not window.forward_button.icon().isNull()
        assert not window.reload_button.icon().isNull()
        assert not window.home_button.icon().isNull()
        assert not window.new_tab_button.icon().isNull()
        assert not window.menu_button.icon().isNull()
        assert window.assistant_dock.isHidden()
        assert not window.assistant_toggle_button.isChecked()

        second_view = browser_module.QWidget(window)
        second_tab_id = "docs-tab"
        window._tab_refs.append(  # type: ignore[attr-defined]
            browser_module._BrowserTab(  # type: ignore[attr-defined]
                tab_id=second_tab_id,
                view=second_view,
                internal_page=None,
                display_url="https://docs.aoryn.org/browser",
            )
        )
        window.tabs.addTab(second_view, "docs.aoryn.org")
        window._update_tab_title(second_tab_id, "docs.aoryn.org")
        window._sync_tab_chrome()
        app.processEvents()

        assert window.tab_strip.isVisible()
        assert window.tab_strip.count() == 2
        assert window.tab_strip.tabText(0) == "New Tab"
        assert window.tab_strip.tabText(1) == "docs.aoryn.org"

        diagnostics_action = next((action for action in window._browser_menu.actions() if action.menu() and action.text() == "Diagnostics"), None)
        assert diagnostics_action is not None
        diagnostics_menu = diagnostics_action.menu()
        assert diagnostics_menu is not None
        diagnostics_labels = [action.text() for action in diagnostics_menu.actions()]
        assert "Browser Setup" in diagnostics_labels
        assert "Runtime Overview" in diagnostics_labels

        captured: dict[str, str | None] = {}

        def _capture_navigate(url: str, *, tab_id: str | None = None):
            captured["url"] = url
            captured["tab_id"] = tab_id
            return {"url": url, "tab_id": tab_id}

        window.navigate = _capture_navigate  # type: ignore[method-assign]
        window._open_internal_target(tab_id, "aoryn://focus-address?query=docs.aoryn.org")

        assert window.address_bar.text() == "docs.aoryn.org"
        assert captured == {"url": "docs.aoryn.org", "tab_id": None}

        window._toggle_assistant_panel()
        app.processEvents()

        assert not window.assistant_dock.isHidden()
        assert window.assistant_toggle_button.isChecked()

        window._toggle_assistant_panel()
        app.processEvents()

        assert window.assistant_dock.isHidden()
        assert not window.assistant_toggle_button.isChecked()
    finally:
        try:
            if window is not None:
                window.close()
        except Exception:
            pass
        shutil.rmtree(temp_root, ignore_errors=True)
