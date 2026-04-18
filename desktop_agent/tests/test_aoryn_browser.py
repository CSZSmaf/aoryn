from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from desktop_agent.aoryn_browser import (
    DEFAULT_BROWSER_HOMEPAGE,
    build_internal_page_html,
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
)


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
