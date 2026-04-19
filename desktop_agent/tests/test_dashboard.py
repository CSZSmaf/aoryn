import json
import re
import shutil
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

import desktop_agent.dashboard as dashboard
import pytest
from desktop_agent.dashboard import DashboardApp, DashboardJob, TaskQueue, _clean_config_overrides
from desktop_agent.controller import load_agent_config
from desktop_agent.provider_tools import ProviderModelEntry, ProviderSnapshot
from desktop_agent.version import APP_ASSET_VERSION, APP_VERSION


def test_clean_config_overrides_accepts_model_browser_and_display_fields():
    raw = {
        "model_provider": "openai_compatible",
        "model_base_url": "https://api.example.com/v1",
        "model_name": "gpt-test",
        "model_api_key": "  secret \n",
        "model_auto_discover": False,
        "model_structured_output": "json_object",
        "browser_control_mode": "dom",
        "browser_dom_backend": "playwright",
        "browser_dom_timeout": "12.5",
        "browser_headless": "true",
        "browser_channel": "chrome",
        "browser_executable_path": "C:/Apps/chrome.exe",
        "display_override_enabled": "true",
        "display_override_monitor_device_name": "DISPLAY2",
        "display_override_dpi_scale": "1.5",
        "display_override_work_area_left": "1920",
        "display_override_work_area_top": "10",
        "display_override_work_area_width": "1600",
        "display_override_work_area_height": "900",
        "ignored": "value",
    }

    cleaned = _clean_config_overrides(raw)

    assert cleaned == {
        "model_provider": "openai_compatible",
        "model_base_url": "https://api.example.com/v1",
        "model_name": "gpt-test",
        "model_api_key": "secret",
        "model_auto_discover": False,
        "model_structured_output": "json_object",
        "browser_control_mode": "dom",
        "browser_dom_backend": "playwright",
        "browser_dom_timeout": 12.5,
        "browser_headless": True,
        "browser_channel": "chrome",
        "browser_executable_path": "C:/Apps/chrome.exe",
        "display_override_enabled": True,
        "display_override_monitor_device_name": "DISPLAY2",
        "display_override_dpi_scale": 1.5,
        "display_override_work_area_left": 1920,
        "display_override_work_area_top": 10,
        "display_override_work_area_width": 1600,
        "display_override_work_area_height": 900,
    }


def test_dashboard_meta_exposes_dom_and_model_defaults(monkeypatch):
    monkeypatch.setattr(
        "desktop_agent.dashboard.dom_backend_status",
        lambda backend: type(
            "Status",
            (),
            {"available": False, "backend": backend, "detail": "Playwright missing"},
        )(),
    )

    temp_root = Path("test_artifacts") / f"dashboard_meta_{uuid4().hex}"
    temp_root.mkdir(parents=True, exist_ok=True)
    try:
        config_path = temp_root / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "planner_mode: vlm",
                    "dry_run: true",
                    "model_provider: lmstudio_local",
                    "model_base_url: http://127.0.0.1:1234/v1",
                    "model_name: auto",
                    "browser_control_mode: hybrid",
                    "browser_dom_backend: playwright",
                    "browser_dom_timeout: 8",
                ]
            ),
            encoding="utf-8",
        )

        app = DashboardApp(host="127.0.0.1", port=8765, config_path=config_path)
        meta = app.meta()

        assert meta["default_locale"] == "zh-CN"
        assert isinstance(meta["chat_launch_id"], str)
        assert len(meta["chat_launch_id"]) >= 8
        assert any(item["value"] == "zh-CN" for item in meta["ui_languages"])
        assert meta["defaults"]["planner_mode"] == "auto"
        assert meta["defaults"]["dry_run"] is False
        assert meta["defaults"]["model_provider"] == "lmstudio_local"
        assert meta["defaults"]["browser_control_mode"] == "hybrid"
        assert meta["dom_status"]["detail"] == "Playwright missing"
        assert any(item["value"] == "openai_api" for item in meta["model_providers"])
        assert any(item["value"] == "openai_compatible" for item in meta["model_providers"])
        assert meta["browser_control_modes"] == [{"value": "hybrid", "label": "Hybrid GUI + DOM"}]
        assert meta["browser_dom_backends"] == [{"value": "playwright", "label": "Playwright"}]
        assert meta["browser_channels"] == [
            {"value": "", "label": "System default"},
            {"value": "msedge", "label": "Microsoft Edge"},
            {"value": "chrome", "label": "Google Chrome"},
            {"value": "firefox", "label": "Mozilla Firefox"},
        ]
        assert any(item["id"] == "visit_docs" for item in meta["presets"])
        assert any(item["id"] == "ordered_browser_task" for item in meta["workflow_recipes"])
        assert any(item["id"] == "shopping_refine" for item in meta["workflow_recipes"])
        assert any(item["id"] == "provider_check" for item in meta["workflow_recipes"])
        assert any(item["id"] == "openai_overview" for item in meta["documentation_links"])
    finally:
        if config_path.exists():
            config_path.unlink()
        temp_root.rmdir()


def test_open_browser_uses_windows_fallback_when_webbrowser_fails(monkeypatch):
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(dashboard, "_try_webbrowser_open", lambda url: False)
    monkeypatch.setattr(dashboard.sys, "platform", "win32")
    monkeypatch.setattr(
        dashboard,
        "_open_with_windows_startfile",
        lambda url: calls.append(("startfile", url)) or True,
    )
    monkeypatch.setattr(
        dashboard,
        "_spawn_open_command",
        lambda command: calls.append(("spawn", " ".join(command))) or False,
    )

    dashboard._open_browser("http://127.0.0.1:8765")

    assert calls == [("startfile", "http://127.0.0.1:8765")]


def test_open_browser_waits_for_local_server_before_launch(monkeypatch):
    attempts = {"count": 0}
    opened: list[str] = []

    class _Connection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_connect(address, timeout):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise OSError("not ready")
        return _Connection()

    monkeypatch.setattr(dashboard.socket, "create_connection", fake_connect)
    monkeypatch.setattr(dashboard.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(dashboard, "_open_browser", lambda url: opened.append(url))

    dashboard._open_browser_when_ready("http://127.0.0.1:8765", attempts=5, delay_seconds=0.01)

    assert attempts["count"] == 3
    assert opened == ["http://127.0.0.1:8765"]


def test_load_agent_config_allows_dashboard_to_disable_dry_run():
    temp_root = Path("test_artifacts") / f"dashboard_dry_run_{uuid4().hex}"
    temp_root.mkdir(parents=True, exist_ok=True)
    try:
        config_path = temp_root / "config.yaml"
        config_path.write_text("dry_run: true\n", encoding="utf-8")

        config = load_agent_config(config_path, dry_run=False)

        assert config.dry_run is False
    finally:
        if config_path.exists():
            config_path.unlink()
        temp_root.rmdir()


def test_dashboard_resolve_chat_model_uses_loaded_vision_only_model_in_compat_mode_for_lmstudio_auto(
    monkeypatch,
):
    monkeypatch.setattr(
        dashboard,
        "load_agent_config",
        lambda *args, **kwargs: type(
            "Config",
            (),
            {
                "model_name": "auto",
                "model_provider": "lmstudio_local",
                "model_base_url": "http://127.0.0.1:1234/v1",
                "model_api_key": "",
                "model_request_timeout": 15.0,
                "run_root": Path("runs"),
            },
        )(),
    )
    monkeypatch.setattr(
        dashboard,
        "fetch_provider_snapshot",
        lambda **kwargs: ProviderSnapshot(
            ok=True,
            provider="lmstudio_local",
            api_base="http://127.0.0.1:1234/v1",
            root_base="http://127.0.0.1:1234",
            loaded_models=["qwen/qwen3-vl-30b"],
            catalog_models=[
                ProviderModelEntry(model_id="qwen/qwen3-vl-30b", label="Qwen 3 VL", kind="vlm", loaded=True),
                ProviderModelEntry(
                    model_id="text-embedding-nomic-embed-text-v1.5",
                    label="Embedding",
                    kind="embedding",
                    loaded=False,
                ),
                ProviderModelEntry(
                    model_id="qwen/qwen3.5-35b-a3b",
                    label="Qwen 3.5 35B",
                    kind="llm",
                    loaded=False,
                ),
            ],
            error=None,
        ),
    )

    app = DashboardApp(host="127.0.0.1", port=8765, config_path=None)

    assert app._resolve_chat_model(config_overrides={}) == "qwen/qwen3-vl-30b"
    assert app._resolve_chat_model_selection(config_overrides={}) == ("qwen/qwen3-vl-30b", True)


def test_dashboard_resolve_chat_model_prefers_loaded_text_models_for_lmstudio_auto(monkeypatch):
    monkeypatch.setattr(
        dashboard,
        "load_agent_config",
        lambda *args, **kwargs: type(
            "Config",
            (),
            {
                "model_name": "auto",
                "model_provider": "lmstudio_local",
                "model_base_url": "http://127.0.0.1:1234/v1",
                "model_api_key": "",
                "model_request_timeout": 15.0,
                "run_root": Path("runs"),
            },
        )(),
    )
    monkeypatch.setattr(
        dashboard,
        "fetch_provider_snapshot",
        lambda **kwargs: ProviderSnapshot(
            ok=True,
            provider="lmstudio_local",
            api_base="http://127.0.0.1:1234/v1",
            root_base="http://127.0.0.1:1234",
            loaded_models=["qwen/qwen3-vl-30b", "qwen/qwen3-14b"],
            catalog_models=[
                ProviderModelEntry(model_id="qwen/qwen3-vl-30b", label="Qwen 3 VL", kind="vlm", loaded=True),
                ProviderModelEntry(model_id="qwen/qwen3-14b", label="Qwen 3 14B", kind="llm", loaded=True),
            ],
            error=None,
        ),
    )

    app = DashboardApp(host="127.0.0.1", port=8765, config_path=None)

    assert app._resolve_chat_model(config_overrides={}) == "qwen/qwen3-14b"
    assert app._resolve_chat_model_selection(config_overrides={}) == ("qwen/qwen3-14b", False)


def test_dashboard_resolve_chat_model_prefers_text_models_when_none_are_loaded(monkeypatch):
    monkeypatch.setattr(
        dashboard,
        "load_agent_config",
        lambda *args, **kwargs: type(
            "Config",
            (),
            {
                "model_name": "auto",
                "model_provider": "lmstudio_local",
                "model_base_url": "http://127.0.0.1:1234/v1",
                "model_api_key": "",
                "model_request_timeout": 15.0,
                "run_root": Path("runs"),
            },
        )(),
    )
    monkeypatch.setattr(
        dashboard,
        "fetch_provider_snapshot",
        lambda **kwargs: ProviderSnapshot(
            ok=True,
            provider="lmstudio_local",
            api_base="http://127.0.0.1:1234/v1",
            root_base="http://127.0.0.1:1234",
            loaded_models=[],
            catalog_models=[
                ProviderModelEntry(model_id="qwen/qwen3-vl-30b", label="Qwen 3 VL", kind="vlm", loaded=False),
                ProviderModelEntry(
                    model_id="text-embedding-nomic-embed-text-v1.5",
                    label="Embedding",
                    kind="embedding",
                    loaded=False,
                ),
                ProviderModelEntry(
                    model_id="qwen/qwen3.5-35b-a3b",
                    label="Qwen 3.5 35B",
                    kind="llm",
                    loaded=False,
                ),
            ],
            error=None,
        ),
    )

    app = DashboardApp(host="127.0.0.1", port=8765, config_path=None)

    assert app._resolve_chat_model(config_overrides={}) == "qwen/qwen3.5-35b-a3b"


def test_dashboard_resolve_chat_model_avoids_oversized_or_specialized_text_models(monkeypatch):
    monkeypatch.setattr(
        dashboard,
        "load_agent_config",
        lambda *args, **kwargs: type(
            "Config",
            (),
            {
                "model_name": "auto",
                "model_provider": "lmstudio_local",
                "model_base_url": "http://127.0.0.1:1234/v1",
                "model_api_key": "",
                "model_request_timeout": 15.0,
                "run_root": Path("runs"),
            },
        )(),
    )
    monkeypatch.setattr(
        dashboard,
        "fetch_provider_snapshot",
        lambda **kwargs: ProviderSnapshot(
            ok=True,
            provider="lmstudio_local",
            api_base="http://127.0.0.1:1234/v1",
            root_base="http://127.0.0.1:1234",
            loaded_models=["qwen/qwen3.5-35b-a3b", "qwen/qwen3.5-9b", "qwen/qwen3-coder-30b"],
            catalog_models=[
                ProviderModelEntry(
                    model_id="qwen/qwen3.5-35b-a3b",
                    label="Qwen 3.5 35B",
                    kind="llm",
                    loaded=True,
                ),
                ProviderModelEntry(model_id="qwen/qwen3.5-9b", label="Qwen 3.5 9B", kind="llm", loaded=True),
                ProviderModelEntry(
                    model_id="qwen/qwen3-coder-30b",
                    label="Qwen 3 Coder",
                    kind="llm",
                    loaded=True,
                ),
            ],
            error=None,
        ),
    )

    app = DashboardApp(host="127.0.0.1", port=8765, config_path=None)

    assert app._resolve_chat_model(config_overrides={}) == "qwen/qwen3.5-9b"


def test_dashboard_provider_models_exposes_preferred_chat_model_and_sorts_catalog(monkeypatch):
    monkeypatch.setattr(
        dashboard,
        "load_agent_config",
        lambda *args, **kwargs: type(
            "Config",
            (),
            {
                "model_name": "auto",
                "model_provider": "lmstudio_local",
                "model_base_url": "http://127.0.0.1:1234/v1",
                "model_api_key": "",
                "model_request_timeout": 15.0,
                "run_root": Path("runs"),
            },
        )(),
    )
    monkeypatch.setattr(
        dashboard,
        "fetch_provider_snapshot",
        lambda **kwargs: ProviderSnapshot(
            ok=True,
            provider="lmstudio_local",
            api_base="http://127.0.0.1:1234/v1",
            root_base="http://127.0.0.1:1234",
            loaded_models=["qwen/qwen3-vl-30b"],
            catalog_models=[
                ProviderModelEntry(
                    model_id="qwen/qwen3.5-35b-a3b",
                    label="qwen/qwen3.5-35b-a3b",
                    kind="llm",
                    loaded=False,
                ),
                ProviderModelEntry(
                    model_id="qwen/qwen3-vl-30b",
                    label="qwen/qwen3-vl-30b",
                    kind="vlm",
                    loaded=True,
                ),
                ProviderModelEntry(
                    model_id="qwen/qwen3-14b",
                    label="qwen/qwen3-14b",
                    kind="llm",
                    loaded=False,
                ),
            ],
            error=None,
        ),
    )

    app = DashboardApp(host="127.0.0.1", port=8765, config_path=None)
    payload = app.provider_models({})

    assert payload["preferred_chat_model"] == "qwen/qwen3-vl-30b"
    assert payload["preferred_chat_compatibility_mode"] is True
    assert payload["catalog_models"][0]["id"] == "qwen/qwen3-vl-30b"


def test_dashboard_provider_load_model_can_unload_loaded_instances_before_loading(monkeypatch):
    monkeypatch.setattr(
        dashboard,
        "load_agent_config",
        lambda *args, **kwargs: type(
            "Config",
            (),
            {
                "model_provider": "lmstudio_local",
                "model_base_url": "http://127.0.0.1:1234/v1",
                "model_api_key": "",
                "model_request_timeout": 15.0,
                "run_root": Path("runs"),
            },
        )(),
    )
    monkeypatch.setattr(
        dashboard,
        "fetch_provider_snapshot",
        lambda **kwargs: ProviderSnapshot(
            ok=True,
            provider="lmstudio_local",
            api_base="http://127.0.0.1:1234/v1",
            root_base="http://127.0.0.1:1234",
            loaded_models=["qwen/qwen3-vl-30b"],
            catalog_models=[
                ProviderModelEntry(
                    model_id="qwen/qwen3-vl-30b",
                    label="qwen/qwen3-vl-30b",
                    kind="vlm",
                    loaded=True,
                    loaded_instance_ids=["qwen/qwen3-vl-30b"],
                ),
            ],
            error=None,
        ),
    )
    unload_calls = []
    load_calls = []
    monkeypatch.setattr(
        dashboard,
        "unload_lmstudio_model_instances",
        lambda **kwargs: unload_calls.append(kwargs) or {"ok": True, "unloaded_instance_ids": ["qwen/qwen3-vl-30b"]},
    )
    monkeypatch.setattr(
        dashboard,
        "load_lmstudio_model",
        lambda **kwargs: load_calls.append(kwargs) or {"ok": True, "model_id": "qwen/qwen3-14b"},
    )

    app = DashboardApp(host="127.0.0.1", port=8765, config_path=None)
    payload = app.provider_load_model(
        config_overrides={},
        model_id="qwen/qwen3-14b",
        unload_first=True,
    )

    assert unload_calls
    assert unload_calls[0]["instance_ids"] == ["qwen/qwen3-vl-30b"]
    assert load_calls
    assert load_calls[0]["model_id"] == "qwen/qwen3-14b"
    assert payload["unloaded_instance_ids"] == ["qwen/qwen3-vl-30b"]


def test_dashboard_job_serializes_manual_handoff_state():
    job = DashboardJob(
        job_id="job123",
        task="search for OpenAI desktop agent",
        planner_mode="auto",
        dry_run=False,
        max_steps=6,
        pause_after_action=0.4,
        status="attention",
        requires_human=True,
        interruption_kind="recaptcha",
        interruption_reason="A reCAPTCHA challenge is on screen.",
    )

    payload = job.to_dict()

    assert payload["status"] == "attention"
    assert payload["requires_human"] is True
    assert payload["interruption_kind"] == "recaptcha"
    assert payload["started_at"] is None
    assert payload["finished_at"] is None


def test_task_queue_cancel_active_marks_job_stopping():
    queue = TaskQueue(config_path=None)
    job = DashboardJob(
        job_id="job123",
        task="open calculator",
        planner_mode="auto",
        dry_run=False,
        max_steps=6,
        pause_after_action=0.4,
        status="running",
    )
    queue.jobs[job.job_id] = job
    queue.cancel_events[job.job_id] = threading.Event()
    queue.active_job_id = job.job_id

    payload = queue.cancel_active()

    assert payload["status"] == "stopping"
    assert payload["cancel_requested"] is True
    assert queue.cancel_events[job.job_id].is_set() is True


def test_dashboard_serves_shell_without_pwa_install_routes():
    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(f"{base_url}/index.html") as response:
            payload = response.read().decode("utf-8")
            assert response.status == 200
            assert f'/assets/vendor/tabler.min.css?v={APP_ASSET_VERSION}' in payload
            assert f'/assets/vendor/tabler-icons-subset.css?v={APP_ASSET_VERSION}' in payload
            assert f'/assets/vendor/desktop-markdown.js?v={APP_ASSET_VERSION}' in payload
            assert f'/assets/vendor/tabler.min.js?v={APP_ASSET_VERSION}' in payload
            assert f'/assets/locales/zh-CN.js?v={APP_ASSET_VERSION}' in payload
            assert f'/assets/locales/en-US.js?v={APP_ASSET_VERSION}' in payload
            assert f'/assets/app.js?v={APP_ASSET_VERSION}' in payload
            assert "manifest.webmanifest" not in payload
            assert 'id="installActionButton"' not in payload
            assert "v__APP_VERSION__" not in payload
            assert f"v{APP_VERSION}" in payload

        with pytest.raises(urllib.error.HTTPError) as manifest_error:
            urllib.request.urlopen(f"{base_url}/manifest.webmanifest")
        assert manifest_error.value.code == 404

        with pytest.raises(urllib.error.HTTPError) as worker_error:
            urllib.request.urlopen(f"{base_url}/service-worker.js")
        assert worker_error.value.code == 404

        with urllib.request.urlopen(f"{base_url}/assets/icons/app-icon-192.png") as response:
            assert response.status == 200
            assert "image/png" in response.headers.get("Content-Type", "")
            assert response.headers.get("Cache-Control") == "no-store"
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_assets_remove_browser_install_entry_points():
    index_html = (Path("desktop_agent") / "dashboard_assets" / "index.html").read_text(encoding="utf-8")
    app_js = (Path("desktop_agent") / "dashboard_assets" / "app.js").read_text(encoding="utf-8")

    assert "manifest.webmanifest" not in index_html
    assert "install-card" not in index_html
    assert 'id="installActionButton"' not in index_html
    assert 'id="displaySettingsSection"' in index_html
    assert 'id="accountSettingsSection"' not in index_html
    assert 'id="authRegisterButton"' not in index_html
    assert 'id="authLoginButton"' not in index_html
    assert 'id="authLogoutButton"' not in index_html
    assert 'id="authGateOverlay"' not in index_html
    assert 'id="displayOverrideEnabled"' in index_html
    assert 'id="displayDetectionJsonView"' in index_html
    assert 'id="closeAboutButton"' in index_html
    assert ">脳<" not in index_html
    assert 'id="closeAboutButton" type="button" data-i18n="common.close"' in index_html
    assert "beforeinstallprompt" not in app_js
    assert "serviceWorker.register" not in app_js
    assert "handleInstallApp" not in app_js
    assert "getInstallState" not in app_js
    assert "cancel_reason" in app_js
    assert '"/api/system/display-detection"' in app_js or "'/api/system/display-detection'" in app_js
    assert "renderDisplayDetection" in app_js
    dom_ready_section = app_js[
        app_js.find('document.addEventListener("DOMContentLoaded", async () => {') :
        app_js.find("function bindEvents()")
    ]
    render_section = app_js[app_js.find("function renderAll()") : app_js.find("function applyShellState()")]
    assert 'loadAuthSession({ silent: true })' not in dom_ready_section
    assert "renderAuthGate();" not in render_section


def test_dashboard_chinese_copy_integrity_and_no_known_mojibake_tokens():
    index_html = (Path("desktop_agent") / "dashboard_assets" / "index.html").read_text(encoding="utf-8")
    app_js = (Path("desktop_agent") / "dashboard_assets" / "app.js").read_text(encoding="utf-8")
    zh_locale = (Path("desktop_agent") / "dashboard_assets" / "locales" / "zh-CN.js").read_text(encoding="utf-8")

    assert "开始一个任务" in index_html
    assert "输入目标后，执行过程和截图会出现在对话里。" in index_html
    assert "语言" in zh_locale
    assert "任务" in zh_locale
    assert "设置" in zh_locale
    assert "关闭" in zh_locale

    known_mojibake_tokens = [
        "鏂板缓",
        "鍘嗗彶",
        "浠诲姟",
        "鍏充簬涓庢棩蹇?",
        "脳",
    ]
    for token in known_mojibake_tokens:
        assert token not in index_html
        assert token not in zh_locale
        assert token not in app_js


def test_dashboard_app_js_has_no_duplicate_function_declarations():
    app_js = (Path("desktop_agent") / "dashboard_assets" / "app.js").read_text(encoding="utf-8")
    names = re.findall(r"^function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(", app_js, flags=re.MULTILINE)
    duplicates = sorted({name for name in names if names.count(name) > 1})
    assert not duplicates, f"Duplicate function declarations found: {duplicates}"


def test_dashboard_runtime_preferences_roundtrip():
    temp_root = Path(__file__).resolve().parents[2] / ".pytest-local" / f"aoryn-dashboard-runtime-{uuid4().hex}"
    temp_root.mkdir(parents=True, exist_ok=True)
    config_path = temp_root / "config.yaml"
    config_path.write_text("{}", encoding="utf-8")
    app = DashboardApp(host="127.0.0.1", port=0, config_path=config_path)
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(f"{base_url}/api/runtime-preferences") as response:
            initial = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert initial["ui_preferences"]["onboarding_completed"] is False

        payload = json.dumps(
            {
                "config_overrides": {
                    "model_provider": "openai_compatible",
                    "model_base_url": " https://api.example.com/v1 ",
                    "model_api_key": " secret \n",
                    "browser_headless": True,
                },
                "ui_preferences": {
                    "onboarding_completed": True,
                },
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            f"{base_url}/api/runtime-preferences",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            snapshot = json.loads(response.read().decode("utf-8"))
            assert response.status == 202
            assert snapshot["config_overrides"] == {
                "model_provider": "openai_compatible",
                "model_base_url": "https://api.example.com/v1",
                "model_api_key": "secret",
                "browser_headless": True,
            }
            assert snapshot["ui_preferences"]["onboarding_completed"] is True

        with urllib.request.urlopen(f"{base_url}/api/runtime-preferences") as response:
            persisted = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert persisted["config_overrides"]["model_provider"] == "openai_compatible"
            assert persisted["config_overrides"]["model_api_key"] == "secret"
            assert persisted["ui_preferences"]["onboarding_completed"] is True
            assert isinstance(persisted["updated_at"], float)
    finally:
        server.shutdown()
        server.server_close()
        shutil.rmtree(temp_root, ignore_errors=True)


def test_dashboard_provider_models_uses_runtime_preferences_when_request_overrides_are_empty(monkeypatch):
    temp_root = Path(__file__).resolve().parents[2] / ".pytest-local" / f"aoryn-dashboard-provider-runtime-{uuid4().hex}"
    temp_root.mkdir(parents=True, exist_ok=True)
    config_path = temp_root / "config.yaml"
    config_path.write_text("{}", encoding="utf-8")
    app = DashboardApp(host="127.0.0.1", port=0, config_path=config_path)
    app.runtime_preferences.update(
        config_overrides={
            "model_provider": "openai_compatible",
            "model_base_url": "https://runtime.example.com/v1",
            "model_api_key": "runtime-secret",
            "model_name": "runtime-model",
        }
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        dashboard,
        "fetch_provider_snapshot",
        lambda **kwargs: captured.update(kwargs)
        or ProviderSnapshot(
            ok=True,
            provider="openai_compatible",
            api_base="https://runtime.example.com/v1",
            root_base="https://runtime.example.com",
            loaded_models=[],
            catalog_models=[],
            error=None,
        ),
    )
    monkeypatch.setattr(DashboardApp, "_resolve_chat_model_selection", lambda self, **kwargs: ("runtime-model", False))

    try:
        payload = app.provider_models({})
        assert payload["provider"] == "openai_compatible"
        assert captured == {
            "provider": "openai_compatible",
            "base_url": "https://runtime.example.com/v1",
            "api_key": "runtime-secret",
            "timeout": 15.0,
        }
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_dashboard_chat_reply_uses_runtime_preferences_when_request_overrides_are_empty(monkeypatch):
    temp_root = Path(__file__).resolve().parents[2] / ".pytest-local" / f"aoryn-dashboard-chat-runtime-{uuid4().hex}"
    temp_root.mkdir(parents=True, exist_ok=True)
    config_path = temp_root / "config.yaml"
    config_path.write_text("{}", encoding="utf-8")
    app = DashboardApp(host="127.0.0.1", port=0, config_path=config_path)
    app.runtime_preferences.update(
        config_overrides={
            "model_provider": "openai_compatible",
            "model_base_url": "https://runtime.example.com/v1",
            "model_api_key": "runtime-secret",
            "model_name": "runtime-model",
        }
    )
    captured: dict[str, object] = {}

    class _FakeResponse:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "runtime reply"}}]}

    class _FakeRequests:
        class RequestException(Exception):
            pass

        @staticmethod
        def post(url, **kwargs):
            captured["url"] = url
            captured.update(kwargs)
            return _FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", _FakeRequests)
    monkeypatch.setattr(DashboardApp, "_resolve_chat_model", lambda self, **kwargs: "runtime-model")
    monkeypatch.setattr(dashboard, "build_chat_system_prompt", lambda **kwargs: "runtime-system")

    try:
        payload = app.chat_reply(
            messages=[{"role": "user", "content": "hello"}],
            config_overrides={},
            session_meta={"locale": "en-US"},
        )
        assert payload["assistant_message"] == "runtime reply"
        assert captured["url"] == "https://runtime.example.com/v1/chat/completions"
        assert captured["headers"]["Authorization"] == "Bearer runtime-secret"
        assert captured["json"]["model"] == "runtime-model"
        assert captured["json"]["messages"][0] == {"role": "system", "content": "runtime-system"}
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_dashboard_task_route_merges_runtime_preferences_with_request_overrides(monkeypatch):
    temp_root = Path(__file__).resolve().parents[2] / ".pytest-local" / f"aoryn-dashboard-task-runtime-{uuid4().hex}"
    temp_root.mkdir(parents=True, exist_ok=True)
    config_path = temp_root / "config.yaml"
    config_path.write_text("{}", encoding="utf-8")
    app = DashboardApp(host="127.0.0.1", port=0, config_path=config_path)
    app.runtime_preferences.update(
        config_overrides={
            "model_provider": "openai_compatible",
            "model_base_url": "https://runtime.example.com/v1",
            "model_api_key": "runtime-secret",
        }
    )
    captured: dict[str, object] = {}

    def _submit(**kwargs):
        captured.update(kwargs)
        return DashboardJob(
            job_id="job-runtime",
            task=kwargs["task"],
            planner_mode=kwargs.get("planner_mode") or "auto",
            dry_run=bool(kwargs.get("dry_run")),
            max_steps=kwargs.get("max_steps"),
            pause_after_action=kwargs.get("pause_after_action"),
            config_overrides=dict(kwargs.get("config_overrides") or {}),
        )

    monkeypatch.setattr(app.queue, "submit", _submit)

    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/tasks",
            data=json.dumps(
                {
                    "task": "visit openai.com and click login",
                    "config_overrides": {
                        "model_base_url": " https://override.example.com/v1 ",
                    },
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 202
            assert payload["id"] == "job-runtime"

        assert captured["config_overrides"] == {
            "model_provider": "openai_compatible",
            "model_base_url": "https://override.example.com/v1",
            "model_api_key": "runtime-secret",
        }
    finally:
        server.shutdown()
        server.server_close()
        shutil.rmtree(temp_root, ignore_errors=True)


def test_dashboard_resume_route_merges_runtime_preferences_with_request_overrides(monkeypatch):
    temp_root = Path(__file__).resolve().parents[2] / ".pytest-local" / f"aoryn-dashboard-resume-runtime-{uuid4().hex}"
    temp_root.mkdir(parents=True, exist_ok=True)
    config_path = temp_root / "config.yaml"
    config_path.write_text("{}", encoding="utf-8")
    app = DashboardApp(host="127.0.0.1", port=0, config_path=config_path)
    app.runtime_preferences.update(
        config_overrides={
            "model_provider": "openai_compatible",
            "model_base_url": "https://runtime.example.com/v1",
        }
    )
    captured: dict[str, object] = {}

    def _resume(**kwargs):
        captured.update(kwargs)
        return DashboardJob(
            job_id="job-resume",
            task="resume the interrupted browser task",
            planner_mode="auto",
            dry_run=False,
            max_steps=None,
            pause_after_action=None,
            resume_run_id=kwargs["run_id"],
            config_overrides=dict(kwargs.get("config_overrides") or {}),
        )

    monkeypatch.setattr(app.queue, "resume", _resume)

    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/runs/run-human-1/resume",
            data=json.dumps(
                {
                    "config_overrides": {
                        "model_base_url": " https://override.example.com/v1 ",
                    },
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 202
            assert payload["id"] == "job-resume"
            assert payload["resume_run_id"] == "run-human-1"

        assert captured["run_id"] == "run-human-1"
        assert captured["config_overrides"] == {
            "model_provider": "openai_compatible",
            "model_base_url": "https://override.example.com/v1",
        }
    finally:
        server.shutdown()
        server.server_close()
        shutil.rmtree(temp_root, ignore_errors=True)


def test_dashboard_system_paths_and_open_path(monkeypatch):
    temp_root = Path(__file__).resolve().parents[2] / ".pytest-local" / f"aoryn-dashboard-paths-{uuid4().hex}"
    temp_root.mkdir(parents=True, exist_ok=True)
    config_path = temp_root / "config.yaml"
    config_path.write_text("{}", encoding="utf-8")
    app = DashboardApp(host="127.0.0.1", port=0, config_path=config_path)
    opened: dict[str, str] = {}

    monkeypatch.setattr(
        dashboard,
        "_open_path_in_file_manager",
        lambda path: opened.setdefault("path", str(path)),
    )
    app.system_paths = lambda: {
        "config_dir": str(temp_root / "config"),
        "data_dir": str(temp_root / "data"),
        "run_root": str(temp_root / "runs"),
        "cache_dir": str(temp_root / "cache"),
        "install_dir": str(temp_root / "install"),
    }

    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(f"{base_url}/api/system/paths") as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert payload["config_dir"].endswith("config")
            assert payload["data_dir"].endswith("data")
            assert payload["run_root"].endswith("runs")
            assert payload["cache_dir"].endswith("cache")
            assert payload["install_dir"].endswith("install")
            assert "auth_session_file" not in payload

        request = urllib.request.Request(
            f"{base_url}/api/system/open-path",
            data=json.dumps({"key": "run_root"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 202
            assert payload["ok"] is True
            assert payload["key"] == "run_root"
            assert payload["path"].endswith("runs")
            assert opened["path"].endswith("runs")
    finally:
        server.shutdown()
        server.server_close()
        shutil.rmtree(temp_root, ignore_errors=True)


def test_dashboard_auth_routes_are_removed_and_core_routes_stay_available(monkeypatch):
    temp_root = Path(__file__).resolve().parents[2] / ".pytest-local" / f"aoryn-dashboard-authless-{uuid4().hex}"
    temp_root.mkdir(parents=True, exist_ok=True)
    config_path = temp_root / "config.yaml"
    config_path.write_text("{}", encoding="utf-8")
    app = DashboardApp(host="127.0.0.1", port=0, config_path=config_path)

    monkeypatch.setattr(
        app.queue,
        "submit",
        lambda **kwargs: DashboardJob(
            job_id="job123",
            task=kwargs["task"],
            planner_mode=kwargs.get("planner_mode") or "auto",
            dry_run=bool(kwargs.get("dry_run")),
            max_steps=kwargs.get("max_steps"),
            pause_after_action=kwargs.get("pause_after_action"),
            config_overrides=dict(kwargs.get("config_overrides") or {}),
        ),
    )
    monkeypatch.setattr(
        DashboardApp,
        "chat_reply",
        lambda self, **kwargs: {
            "assistant_message": "No desktop sign-in required.",
            "agent_handoff": None,
            "session_meta": kwargs.get("session_meta"),
        },
    )
    monkeypatch.setattr(
        DashboardApp,
        "provider_models",
        lambda self, *_args, **_kwargs: {
            "provider": "lmstudio_local",
            "models": [],
            "preferred_chat_model": "auto",
        },
    )

    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        task_request = urllib.request.Request(
            f"{base_url}/api/tasks",
            data=json.dumps(
                {
                    "task": "visit openai.com and click login",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(task_request) as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 202
            assert payload["id"] == "job123"
            assert payload["task"] == "visit openai.com and click login"

        chat_request = urllib.request.Request(
            f"{base_url}/api/chat",
            data=json.dumps(
                {
                    "messages": [{"role": "user", "content": "Can I use the workspace without signing in?"}],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(chat_request) as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert payload["assistant_message"] == "No desktop sign-in required."

        provider_request = urllib.request.Request(
            f"{base_url}/api/provider/models",
            data=json.dumps({"config_overrides": {}}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(provider_request) as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert payload["provider"] == "lmstudio_local"

        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"{base_url}/api/auth/session")
        assert exc_info.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        shutil.rmtree(temp_root, ignore_errors=True)


def test_dashboard_environment_check_reports_missing_api_key(monkeypatch):
    monkeypatch.setattr(
        dashboard,
        "dom_backend_status",
        lambda backend: type(
            "Status",
            (),
            {"available": True, "backend": backend, "detail": "Playwright ready"},
        )(),
    )
    monkeypatch.setattr(
        dashboard,
        "load_agent_config",
        lambda *args, **kwargs: type(
            "Config",
            (),
            {
                "model_provider": "openai_compatible",
                "model_base_url": "https://api.example.com/v1",
                "model_name": "gpt-test",
                "model_api_key": "",
                "model_auto_discover": False,
                "model_request_timeout": 15.0,
                "browser_dom_backend": "playwright",
                "browser_channel": "chrome",
                "browser_executable_path": "",
                "run_root": Path("runs"),
            },
        )(),
    )
    monkeypatch.setattr(
        dashboard,
        "detect_display_environment",
        lambda config: type(
            "DisplayDetection",
            (),
            {
                "override": type(
                    "Override",
                    (),
                    {"status": "override", "warnings": [], "editable": True},
                )(),
            },
        )(),
    )

    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)
    payload = app.environment_check()

    assert [item["id"] for item in payload["items"]] == [
        "browser_execution",
        "display_detection",
        "model_provider",
        "model_selection",
        "provider_connection",
    ]
    assert payload["items"][0]["status"] == "Ready"
    assert payload["items"][1]["status"] == "Ready"
    assert payload["items"][2]["status"] == "Ready"
    assert payload["items"][3]["status"] == "Ready"
    assert payload["items"][4]["status"] == "Needs setup"
    assert "API key" in payload["items"][4]["detail"]


def test_dashboard_environment_check_route_returns_items(monkeypatch):
    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)
    monkeypatch.setattr(
        app,
        "environment_check",
        lambda: {
            "items": [
                {
                    "id": "browser_execution",
                    "label": "Browser execution",
                    "status": "Ready",
                    "detail": "Using browser channel: msedge.",
                    "action": "open_settings",
                }
            ],
            "checked_at": 123.0,
        },
    )
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(f"{base_url}/api/system/environment-check") as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert payload["items"][0]["id"] == "browser_execution"
            assert payload["items"][0]["status"] == "Ready"
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_display_detection_uses_runtime_overrides(monkeypatch):
    monkeypatch.setattr(
        dashboard,
        "load_agent_config",
        lambda *args, **kwargs: type(
            "Config",
            (),
            {
                "run_root": Path("runs"),
                "display_override_enabled": True,
                "display_override_monitor_device_name": "DISPLAY2",
                "display_override_dpi_scale": 1.5,
                "display_override_work_area_left": 2000,
                "display_override_work_area_top": 20,
                "display_override_work_area_width": 1600,
                "display_override_work_area_height": 900,
            },
        )(),
    )
    monkeypatch.setattr(
        dashboard,
        "detect_display_environment",
        lambda config: type(
            "DisplayDetection",
            (),
            {
                "to_dict": lambda self: {
                    "detected": {"platform": "windows"},
                    "effective": {"platform": "windows", "dpi_scale": 1.5},
                    "override": {"status": "override", "enabled": True},
                    "checked_at": 123.0,
                }
            },
        )(),
    )

    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)
    app.runtime_preferences.update(
        config_overrides={
            "display_override_enabled": True,
            "display_override_monitor_device_name": "DISPLAY2",
        }
    )

    payload = app.display_detection()

    assert payload["effective"]["dpi_scale"] == 1.5
    assert payload["override"]["status"] == "override"
    assert payload["checked_at"] == 123.0


def test_dashboard_display_detection_route_returns_snapshot(monkeypatch):
    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)
    monkeypatch.setattr(
        app,
        "display_detection",
        lambda: {
            "detected": {"platform": "windows"},
            "effective": {"platform": "windows"},
            "override": {"status": "auto"},
            "checked_at": 456.0,
        },
    )
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(f"{base_url}/api/system/display-detection") as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert payload["override"]["status"] == "auto"
            assert payload["checked_at"] == 456.0
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_serves_help_route():
    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(f"{base_url}/api/help?locale=zh-CN") as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert payload["title"] == "帮助中心"
            assert payload["locale"] == "zh-CN"
            assert payload["audience"] == "user"
            assert "第一次使用" in payload["markdown"]
            assert "本地优先" in payload["markdown"]

        with urllib.request.urlopen(f"{base_url}/api/help?locale=en-US") as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert payload["title"] == "Help Center"
            assert payload["locale"] == "en-US"
            assert payload["audience"] == "user"
            assert "First run" in payload["markdown"]
            assert "Advanced Docs" in payload["markdown"]

        with urllib.request.urlopen(f"{base_url}/api/help?locale=en-US&audience=developer") as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert payload["title"] == "Advanced Docs"
            assert payload["locale"] == "en-US"
            assert payload["audience"] == "developer"
            assert "Developer Guide" in payload["markdown"]
    finally:
        server.shutdown()
        server.server_close()


def test_chat_frontend_assets_include_avatar_timer_and_katex_hooks():
    assets_root = Path(__file__).resolve().parents[1] / "dashboard_assets"
    app_source = (assets_root / "app.js").read_text(encoding="utf-8")
    styles_source = (assets_root / "styles.css").read_text(encoding="utf-8")

    assert "assistant-shell" in app_source
    assert "chatPendingBadgeTimer" in app_source
    assert 'return renderAssistantMessageShell(`' in app_source
    assert "onboardingSection" in app_source
    assert "renderOnboardingGuide" in app_source
    assert "aboutOverlay" in app_source
    assert '"/api/system/open-path"' in app_source or "'/api/system/open-path'" in app_source
    assert '"/api/system/environment-check"' in app_source or "'/api/system/environment-check'" in app_source
    assert "environment-check-grid" in app_source
    assert "openDeveloperDocsButton" in app_source
    assert "Help Center" in app_source
    assert "Run starter task" in app_source
    assert "Finish one successful run in four steps." in app_source
    assert "assistant-pending-badge" in styles_source
    assert "assistant-avatar" in styles_source
    assert "assistant-math--katex" in styles_source
    assert "border-bottom: none;" in styles_source
    assert "onboarding-card" in styles_source
    assert "about-modal" in styles_source
    assert "environment-check-grid" in styles_source
    assert "--text-primary: var(--ink);" in styles_source
    assert "Desktop polish pass" in styles_source


def test_dashboard_chat_reply_stream_prefers_real_stream_for_lmstudio(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.headers = {"Content-Type": "text/event-stream"}
            self.closed = False

        def iter_lines(self, decode_unicode: bool = False):
            assert decode_unicode is False
            yield b'data: {"choices":[{"delta":{"content":"hello "}}]}'
            yield b'data: {"choices":[{"delta":{"content":"world"}}]}'
            yield b"data: [DONE]"

        def close(self) -> None:
            self.closed = True

    class _FakeRequests:
        class RequestException(Exception):
            pass

        @staticmethod
        def post(*args, **kwargs):
            captured.update(kwargs)
            return fake_response

    fake_response = _FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", _FakeRequests)
    monkeypatch.setattr(
        dashboard,
        "load_agent_config",
        lambda *args, **kwargs: type(
            "Config",
            (),
            {
                "model_provider": "lmstudio_local",
                "model_base_url": "http://127.0.0.1:1234/v1",
                "model_request_timeout": 30.0,
                "model_api_key": "",
                "run_root": Path("runs"),
            },
        )(),
    )
    monkeypatch.setattr(DashboardApp, "_resolve_chat_model", lambda self, **kwargs: "qwen/qwen3-vl-30b")
    monkeypatch.setattr(dashboard, "build_chat_system_prompt", lambda **kwargs: "compat-system")
    monkeypatch.setattr(
        dashboard,
        "build_agent_handoff",
        lambda message, locale="zh-CN": {"suggested_task": message, "reason": locale},
    )

    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)
    events = list(
        app.chat_reply_stream(
            messages=[{"role": "user", "content": "hello"}],
            config_overrides={},
            session_meta={"locale": "en-US"},
        )
    )

    assert events == [
        ("start", {"session_meta": {"locale": "en-US"}}),
        ("delta", {"content_delta": "hello "}),
        ("delta", {"content_delta": "world"}),
        (
            "done",
            {
                "assistant_message": "hello world",
                "agent_handoff": {"suggested_task": "hello", "reason": "en-US"},
                "session_meta": {"locale": "en-US"},
            },
        ),
    ]
    assert captured["stream"] is True
    assert captured["json"]["model"] == "qwen/qwen3-vl-30b"
    assert fake_response.closed is True


def test_dashboard_chat_reply_stream_falls_back_to_non_stream_for_lmstudio(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeResponse:
        status_code = 200
        headers = {"Content-Type": "application/json"}
        closed = False

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "hello from fallback"}}]}

        def close(self) -> None:
            self.closed = True

    class _FakeRequests:
        class RequestException(Exception):
            pass

        @staticmethod
        def post(*args, **kwargs):
            captured.update(kwargs)
            return fake_response

    fake_response = _FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", _FakeRequests)
    monkeypatch.setattr(
        dashboard,
        "load_agent_config",
        lambda *args, **kwargs: type(
            "Config",
            (),
            {
                "model_provider": "lmstudio_local",
                "model_base_url": "http://127.0.0.1:1234/v1",
                "model_request_timeout": 30.0,
                "model_api_key": "",
                "run_root": Path("runs"),
            },
        )(),
    )
    monkeypatch.setattr(DashboardApp, "_resolve_chat_model", lambda self, **kwargs: "qwen/qwen3-vl-30b")
    monkeypatch.setattr(dashboard, "build_chat_system_prompt", lambda **kwargs: "compat-system")
    monkeypatch.setattr(
        dashboard,
        "build_agent_handoff",
        lambda message, locale="zh-CN": {"suggested_task": message, "reason": locale},
    )

    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)
    events = list(
        app.chat_reply_stream(
            messages=[{"role": "user", "content": "hello"}],
            config_overrides={},
            session_meta={"locale": "en-US"},
        )
    )

    assert events == [
        ("start", {"session_meta": {"locale": "en-US"}}),
        ("delta", {"content_delta": "hello from fallback"}),
        (
            "done",
            {
                "assistant_message": "hello from fallback",
                "agent_handoff": {"suggested_task": "hello", "reason": "en-US"},
                "session_meta": {"locale": "en-US"},
            },
        ),
    ]
    assert captured["stream"] is True
    assert fake_response.closed is True


def test_dashboard_chat_reply_returns_math_recovery_payload_for_vision_formula_failure(monkeypatch):
    class _FakeResponse:
        status_code = 400
        text = r"Failed to parse input at pos 0: $$ \nabla \times \mathbf{E} = -\frac{\partial B}{\partial t} $$ \ufffd"

        def json(self):
            return {"error": {"message": self.text}}

    class _FakeRequests:
        class RequestException(Exception):
            pass

        @staticmethod
        def post(*args, **kwargs):
            return _FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", _FakeRequests)
    monkeypatch.setattr(
        dashboard,
        "load_agent_config",
        lambda *args, **kwargs: type(
            "Config",
            (),
            {
                "model_provider": "lmstudio_local",
                "model_base_url": "http://127.0.0.1:1234/v1",
                "model_request_timeout": 30.0,
                "model_api_key": "",
                "run_root": Path("runs"),
            },
        )(),
    )
    monkeypatch.setattr(DashboardApp, "_resolve_chat_model", lambda self, **kwargs: "qwen/qwen3-vl-30b")
    monkeypatch.setattr(
        DashboardApp,
        "_suggest_text_chat_model",
        lambda self, **kwargs: "qwen/qwen3-14b",
    )

    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)

    with pytest.raises(dashboard.ChatUIError) as exc_info:
        app.chat_reply(
            messages=[{"role": "user", "content": r"Explain Maxwell equations with \nabla and \epsilon_0."}],
            config_overrides={},
            session_meta={"locale": "en-US"},
        )

    payload = exc_info.value.payload
    assert payload["error_code"] == "math_formula_unstable"
    assert payload["recovery_action"] == "switch_text_model_retry"
    assert payload["retry_context"]["suggested_text_model"] == "qwen/qwen3-14b"
    assert payload["retry_context"]["previous_model"] == "qwen/qwen3-vl-30b"
    assert payload["retry_context"]["restore_to_model"] == "qwen/qwen3-vl-30b"
    assert payload["retry_context"]["messages"][-1]["role"] == "user"


def test_math_formula_output_health_check_accepts_valid_formula_markup():
    assert (
        dashboard._looks_like_math_formula_output_unstable(
            r"$$\nabla \cdot \mathbf{E} = \frac{\rho}{\epsilon_0}$$"
        )
        is False
    )


def test_math_formula_output_health_check_rejects_damaged_formula_markup():
    assert (
        dashboard._looks_like_math_formula_output_unstable(
            r"$$\nabla \cdot \mathbf{E} = \frac{\rho}{\epsilon_0}$"
        )
        is True
    )
    assert dashboard._looks_like_math_formula_output_unstable(r"Here is a broken token <|im_end|>") is True


def test_math_provider_failure_check_requires_explicit_parse_or_damage_signals():
    assert dashboard._looks_like_math_provider_failure(r"Failed to parse input at pos 0: $$\nabla \times E = 0") is True
    assert dashboard._looks_like_math_provider_failure(r"Provider detail: $$\nabla \times E = 0$$") is False


def test_dashboard_chat_reply_can_temporarily_switch_to_text_model_and_restore(monkeypatch):
    captured: dict[str, object] = {}
    load_calls: list[dict[str, object]] = []

    class _FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "Recovered answer"}}]}

    class _FakeRequests:
        class RequestException(Exception):
            pass

        @staticmethod
        def post(*args, **kwargs):
            captured.update(kwargs)
            return _FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", _FakeRequests)
    monkeypatch.setattr(
        dashboard,
        "load_agent_config",
        lambda *args, **kwargs: type(
            "Config",
            (),
            {
                "model_provider": "lmstudio_local",
                "model_base_url": "http://127.0.0.1:1234/v1",
                "model_request_timeout": 30.0,
                "model_api_key": "",
                "run_root": Path("runs"),
            },
        )(),
    )
    monkeypatch.setattr(
        DashboardApp,
        "_resolve_chat_model",
        lambda self, *, config_overrides: config_overrides.get("model_name", "qwen/qwen3-vl-30b"),
    )
    monkeypatch.setattr(
        DashboardApp,
        "provider_load_model",
        lambda self, **kwargs: load_calls.append(kwargs) or {"ok": True, "model_id": kwargs["model_id"]},
    )

    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)
    payload = app.chat_reply(
        messages=[{"role": "user", "content": "Retry this answer with a safer text model."}],
        config_overrides={},
        session_meta={"locale": "en-US"},
        recovery_context={
            "previous_model": "qwen/qwen3-vl-30b",
            "suggested_text_model": "qwen/qwen3-14b",
            "restore_to_model": "qwen/qwen3-vl-30b",
        },
    )

    assert payload["assistant_message"] == "Recovered answer"
    assert captured["json"]["model"] == "qwen/qwen3-14b"
    assert [call["model_id"] for call in load_calls] == ["qwen/qwen3-14b", "qwen/qwen3-vl-30b"]
    assert all(call["unload_first"] is True for call in load_calls)


def test_dashboard_chat_route_returns_structured_math_recovery_payload(monkeypatch):
    def _raise_error(self, **kwargs):
        raise dashboard.ChatUIError(
            "Formula-heavy reply was unstable upstream.",
            payload={
                "error_code": "math_formula_unstable",
                "recovery_action": "switch_text_model_retry",
                "recovery_label": "Retry with a text model",
                "retry_context": {
                    "messages": [{"role": "user", "content": "Explain Maxwell equations"}],
                    "previous_model": "qwen/qwen3-vl-30b",
                    "suggested_text_model": "qwen/qwen3-14b",
                    "restore_to_model": "qwen/qwen3-vl-30b",
                },
            },
        )

    monkeypatch.setattr(DashboardApp, "chat_reply", _raise_error)

    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)
    app.auth_session_snapshot = lambda: {"authenticated": True, "profile": {"email": "user@example.com"}}
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/chat",
            data=json.dumps({"messages": [{"role": "user", "content": "Explain Maxwell equations"}]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(request)

        assert exc_info.value.code == 400
        payload = json.loads(exc_info.value.read().decode("utf-8"))
        assert payload["error_code"] == "math_formula_unstable"
        assert payload["recovery_action"] == "switch_text_model_retry"
        assert payload["retry_context"]["suggested_text_model"] == "qwen/qwen3-14b"
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_chat_stream_route_returns_structured_math_recovery_event(monkeypatch):
    def _stream_reply(self, **kwargs):
        yield "start", {"session_meta": {"locale": "en-US"}}
        yield "error", {
            "error": "Formula-heavy reply was unstable upstream.",
            "error_code": "math_formula_unstable",
            "recovery_action": "switch_text_model_retry",
            "recovery_label": "Retry with a text model",
            "retry_context": {
                "messages": [{"role": "user", "content": "Explain Maxwell equations"}],
                "previous_model": "qwen/qwen3-vl-30b",
                "suggested_text_model": "qwen/qwen3-14b",
                "restore_to_model": "qwen/qwen3-vl-30b",
            },
        }

    monkeypatch.setattr(DashboardApp, "chat_reply_stream", _stream_reply)

    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)
    app.auth_session_snapshot = lambda: {"authenticated": True, "profile": {"email": "user@example.com"}}
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/chat/stream",
            data=json.dumps({"messages": [{"role": "user", "content": "Explain Maxwell equations"}]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            payload = response.read().decode("utf-8")
            assert response.status == 200
            assert "event: error" in payload
            assert '"error_code": "math_formula_unstable"' in payload
            assert '"recovery_action": "switch_text_model_retry"' in payload
            assert '"suggested_text_model": "qwen/qwen3-14b"' in payload
    finally:
        server.shutdown()
        server.server_close()


def test_chat_ui_source_contains_copy_retry_and_stopped_state_hooks():
    source = (Path(__file__).resolve().parents[1] / "dashboard_assets" / "app.js").read_text(encoding="utf-8")
    render_tail = source[source.rfind("function renderNormalAssistantMessage") :]
    request_tail = source[source.rfind("async function requestChatReply") :]

    assert "data-copy-chat-message" in source
    assert "data-retry-chat-message" in source
    assert "data-recover-chat-message" in source
    assert "switch_text_model_retry" in source
    assert "countMathRecoveryFailures" in source
    assert "isStoppedPlaceholderChatMessage" in source
    assert 'draft.status = "stopped"' in source
    assert "message-action-icon-button" in source
    assert "renderChatActionIconButton" in render_tail
    assert 'draft.content += delta;' in request_tail
    assert 'draft.targetContent = draft.content;' in request_tail
    assert "ensureChatStreamReveal();" not in request_tail
    assert 'elements.modelBaseUrl?.addEventListener("input", handleModelBaseUrlInput);' in source
    assert "updateModelBaseUrlAutofillState()" in source
    assert "handleProviderChange({ force: firstHydration });" in source


def test_dashboard_chat_route_returns_reply(monkeypatch):
    monkeypatch.setattr(
        DashboardApp,
        "chat_reply",
        lambda self, **kwargs: {
            "assistant_message": "Use Agent mode when you need execution.",
            "agent_handoff": {"suggested_task": "visit openai.com and click login", "reason": "Browser actions required."},
            "session_meta": None,
        },
    )

    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)
    app.auth_session_snapshot = lambda: {"authenticated": True, "profile": {"email": "user@example.com"}}
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/chat",
            data=json.dumps({"messages": [{"role": "user", "content": "How do I use Agent mode?"}]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert payload["assistant_message"] == "Use Agent mode when you need execution."
            assert payload["agent_handoff"]["suggested_task"] == "visit openai.com and click login"
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_chat_route_passes_locale_session_meta(monkeypatch):
    captured: dict[str, object] = {}

    def _chat_reply(self, **kwargs):
        captured.update(kwargs)
        return {
            "assistant_message": "Hello from English docs.",
            "agent_handoff": None,
            "session_meta": kwargs.get("session_meta"),
        }

    monkeypatch.setattr(DashboardApp, "chat_reply", _chat_reply)

    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)
    app.auth_session_snapshot = lambda: {"authenticated": True, "profile": {"email": "user@example.com"}}
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/chat",
            data=json.dumps(
                {
                    "messages": [{"role": "user", "content": "How do I use Agent mode?"}],
                    "session_meta": {"locale": "en-US"},
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert payload["assistant_message"] == "Hello from English docs."
            assert payload["session_meta"]["locale"] == "en-US"
            assert captured["session_meta"] == {"locale": "en-US"}
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_chat_reply_limits_completion_tokens(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "Hello"}}]}

    class _FakeRequests:
        class RequestException(Exception):
            pass

        @staticmethod
        def post(*args, **kwargs):
            captured.update(kwargs)
            return _FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", _FakeRequests)
    monkeypatch.setattr(
        dashboard,
        "load_agent_config",
        lambda *args, **kwargs: type(
            "Config",
            (),
            {
                "model_provider": "openai_compatible",
                "model_base_url": "http://127.0.0.1:1234/v1",
                "model_request_timeout": 30.0,
                "model_api_key": "",
                "run_root": Path("runs"),
            },
        )(),
    )
    monkeypatch.setattr(DashboardApp, "_resolve_chat_model", lambda self, **kwargs: "test-model")

    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)
    payload = app.chat_reply(
        messages=[{"role": "user", "content": "hello"}],
        config_overrides={},
        session_meta={"locale": "en-US"},
    )

    assert payload["assistant_message"] == "Hello"
    assert "max_tokens" not in captured["json"]


def test_dashboard_chat_reply_rejects_placeholder_slash_output(monkeypatch):
    class _FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "////////////////////////////"}}]}

    class _FakeRequests:
        class RequestException(Exception):
            pass

        @staticmethod
        def post(*args, **kwargs):
            return _FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", _FakeRequests)
    monkeypatch.setattr(
        dashboard,
        "load_agent_config",
        lambda *args, **kwargs: type(
            "Config",
            (),
            {
                "model_provider": "openai_compatible",
                "model_base_url": "http://127.0.0.1:1234/v1",
                "model_request_timeout": 30.0,
                "model_api_key": "",
                "run_root": Path("runs"),
            },
        )(),
    )
    monkeypatch.setattr(DashboardApp, "_resolve_chat_model", lambda self, **kwargs: "test-model")

    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)

    with pytest.raises(dashboard.ProviderToolError) as exc_info:
        app.chat_reply(
            messages=[{"role": "user", "content": "hello"}],
            config_overrides={},
            session_meta={"locale": "en-US"},
        )

    assert "placeholder output" in str(exc_info.value)


def test_dashboard_chat_reply_strips_provider_sentinel_tokens(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "好的，继续。<|im_end|>\ufffd"}}]}

    class _FakeRequests:
        class RequestException(Exception):
            pass

        @staticmethod
        def post(*args, **kwargs):
            captured.update(kwargs)
            return _FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", _FakeRequests)
    monkeypatch.setattr(
        dashboard,
        "load_agent_config",
        lambda *args, **kwargs: type(
            "Config",
            (),
            {
                "model_provider": "openai_compatible",
                "model_base_url": "http://127.0.0.1:1234/v1",
                "model_request_timeout": 30.0,
                "model_api_key": "",
                "run_root": Path("runs"),
            },
        )(),
    )
    monkeypatch.setattr(DashboardApp, "_resolve_chat_model", lambda self, **kwargs: "test-model")

    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)
    payload = app.chat_reply(
        messages=[
            {"role": "user", "content": "第一问"},
            {"role": "assistant", "content": "上一轮回答里混入了 <|im_end|>\ufffd"},
            {"role": "user", "content": "继续"},
        ],
        config_overrides={},
        session_meta={"locale": "zh-CN"},
    )

    assert payload["assistant_message"] == "好的，继续。"
    assert captured["json"]["messages"][0]["role"] == "system"
    assert captured["json"]["messages"][1:] == [
        {"role": "user", "content": "第一问"},
        {"role": "assistant", "content": "上一轮回答里混入了"},
        {"role": "user", "content": "继续"},
    ]


def test_dashboard_chat_reply_uses_vision_compatibility_mode_for_lmstudio(monkeypatch):
    captured: dict[str, object] = {}
    prompt_calls: list[dict[str, object]] = []

    class _FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "你好，我可以帮你。"}}]}

    class _FakeRequests:
        class RequestException(Exception):
            pass

        @staticmethod
        def post(*args, **kwargs):
            captured.update(kwargs)
            return _FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", _FakeRequests)
    monkeypatch.setattr(
        dashboard,
        "load_agent_config",
        lambda *args, **kwargs: type(
            "Config",
            (),
            {
                "model_provider": "lmstudio_local",
                "model_base_url": "http://127.0.0.1:1234/v1",
                "model_request_timeout": 30.0,
                "model_api_key": "",
                "run_root": Path("runs"),
            },
        )(),
    )
    monkeypatch.setattr(
        DashboardApp,
        "_resolve_chat_model_selection",
        lambda self, **kwargs: ("qwen/qwen3-vl-30b", True),
    )
    monkeypatch.setattr(
        dashboard,
        "build_chat_system_prompt",
        lambda **kwargs: prompt_calls.append(kwargs) or "compat-system",
    )

    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)
    payload = app.chat_reply(
        messages=[
            {"role": "user", "content": "第一轮问题"},
            {"role": "assistant", "content": "第一轮回答"},
            {"role": "user", "content": "第二轮追问"},
        ],
        config_overrides={},
        session_meta={"locale": "zh-CN"},
    )

    assert payload["assistant_message"] == "你好，我可以帮你。"
    assert captured["json"]["model"] == "qwen/qwen3-vl-30b"
    assert "max_tokens" not in captured["json"]
    assert captured["json"]["messages"] == [
        {"role": "system", "content": "compat-system"},
        {"role": "assistant", "content": "第一轮回答"},
        {"role": "user", "content": "第二轮追问"},
    ]
    assert prompt_calls == [
        {
            "help_markdown": "",
            "locale": "zh-CN",
            "provider_name": "lmstudio_local",
            "model_name": "qwen/qwen3-vl-30b",
            "compatibility_mode": True,
            "math_mode": False,
        }
    ]


def test_dashboard_chat_route_returns_bad_request_for_provider_error(monkeypatch):
    def _raise_error(self, **kwargs):
        raise dashboard.ProviderToolError("Provider unavailable.")

    monkeypatch.setattr(DashboardApp, "chat_reply", _raise_error)

    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)
    app.auth_session_snapshot = lambda: {"authenticated": True, "profile": {"email": "user@example.com"}}
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/chat",
            data=json.dumps({"messages": [{"role": "user", "content": "hello"}]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(request)

        assert exc_info.value.code == 400
        payload = json.loads(exc_info.value.read().decode("utf-8"))
        assert payload["error"] == "Provider unavailable."
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_chat_route_surfaces_provider_http_400_details(monkeypatch):
    class _FakeResponse:
        status_code = 400
        text = '{"error":{"message":"prompt too long for template"}}'

        def json(self):
            return {"error": {"message": "prompt too long for template"}}

    class _FakeRequests:
        class RequestException(Exception):
            pass

        @staticmethod
        def post(*args, **kwargs):
            return _FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", _FakeRequests)
    monkeypatch.setattr(
        dashboard,
        "load_agent_config",
        lambda *args, **kwargs: type(
            "Config",
            (),
            {
                "model_provider": "openai_compatible",
                "model_base_url": "http://127.0.0.1:1234/v1",
                "model_request_timeout": 30.0,
                "model_api_key": "",
                "run_root": Path("runs"),
            },
        )(),
    )
    monkeypatch.setattr(DashboardApp, "_resolve_chat_model", lambda self, **kwargs: "test-model")

    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)
    app.auth_session_snapshot = lambda: {"authenticated": True, "profile": {"email": "user@example.com"}}
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/chat",
            data=json.dumps({"messages": [{"role": "user", "content": "hello"}]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(request)

        assert exc_info.value.code == 400
        payload = json.loads(exc_info.value.read().decode("utf-8"))
        assert "HTTP 400" in payload["error"]
        assert "prompt too long for template" in payload["error"]
        assert "Could not reach the chat model" not in payload["error"]
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_chat_stream_route_returns_sse_events(monkeypatch):
    def _stream_reply(self, **kwargs):
        yield "start", {"session_meta": {"locale": "en-US"}}
        yield "delta", {"content_delta": "Hello "}
        yield "delta", {"content_delta": "world"}
        yield "done", {
            "assistant_message": "Hello world",
            "agent_handoff": {"suggested_task": "visit openai.com", "reason": "Browser action required."},
            "session_meta": {"locale": "en-US"},
        }

    monkeypatch.setattr(DashboardApp, "chat_reply_stream", _stream_reply)

    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)
    app.auth_session_snapshot = lambda: {"authenticated": True, "profile": {"email": "user@example.com"}}
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/chat/stream",
            data=json.dumps({"messages": [{"role": "user", "content": "hello"}]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            payload = response.read().decode("utf-8")
            assert response.status == 200
            assert "text/event-stream" in response.headers.get("Content-Type", "")
            assert "event: start" in payload
            assert '"content_delta": "Hello "' in payload
            assert '"assistant_message": "Hello world"' in payload
            assert '"suggested_task": "visit openai.com"' in payload
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_chat_stream_route_surfaces_provider_http_400_details(monkeypatch):
    class _FakeResponse:
        status_code = 400
        headers = {"Content-Type": "application/json"}
        text = '{"error":{"message":"prompt too long for template"}}'
        closed = False

        def json(self):
            return {"error": {"message": "prompt too long for template"}}

        def close(self):
            self.closed = True

    class _FakeRequests:
        class RequestException(Exception):
            pass

        @staticmethod
        def post(*args, **kwargs):
            return fake_response

    fake_response = _FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", _FakeRequests)
    monkeypatch.setattr(
        dashboard,
        "load_agent_config",
        lambda *args, **kwargs: type(
            "Config",
            (),
            {
                "model_provider": "openai_compatible",
                "model_base_url": "http://127.0.0.1:1234/v1",
                "model_request_timeout": 30.0,
                "model_api_key": "",
                "run_root": Path("runs"),
            },
        )(),
    )
    monkeypatch.setattr(DashboardApp, "_resolve_chat_model", lambda self, **kwargs: "test-model")

    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)
    app.auth_session_snapshot = lambda: {"authenticated": True, "profile": {"email": "user@example.com"}}
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/chat/stream",
            data=json.dumps({"messages": [{"role": "user", "content": "hello"}]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            payload = response.read().decode("utf-8")
            assert response.status == 200
            assert "event: error" in payload
            assert "HTTP 400" in payload
            assert "prompt too long for template" in payload
        assert fake_response.closed is True
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_chat_stream_route_can_return_error_event(monkeypatch):
    def _stream_reply(self, **kwargs):
        yield "start", {"session_meta": None}
        yield "error", {"error": "Provider unavailable."}

    monkeypatch.setattr(DashboardApp, "chat_reply_stream", _stream_reply)

    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)
    app.auth_session_snapshot = lambda: {"authenticated": True, "profile": {"email": "user@example.com"}}
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/chat/stream",
            data=json.dumps({"messages": [{"role": "user", "content": "hello"}]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            payload = response.read().decode("utf-8")
            assert response.status == 200
            assert "event: error" in payload
            assert '"error": "Provider unavailable."' in payload
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_chat_reply_stream_decodes_utf8_sse_bytes(monkeypatch):
    class _FakeResponse:
        def __init__(self) -> None:
            self.headers = {"Content-Type": "text/event-stream"}
            self.closed = False

        def raise_for_status(self) -> None:
            return

        def iter_lines(self, decode_unicode: bool = False):
            assert decode_unicode is False
            payload = {
                "choices": [
                    {
                        "delta": {
                            "content": "你好",
                        }
                    }
                ]
            }
            yield f"data: {json.dumps(payload, ensure_ascii=False)}".encode("utf-8")
            yield b"data: [DONE]"

        def close(self) -> None:
            self.closed = True

    class _FakeRequests:
        class RequestException(Exception):
            pass

        @staticmethod
        def post(*args, **kwargs):
            return fake_response

    fake_response = _FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", _FakeRequests)
    monkeypatch.setattr(
        dashboard,
        "load_agent_config",
        lambda *args, **kwargs: type(
            "Config",
            (),
                {
                    "model_provider": "openai_compatible",
                    "model_base_url": "http://127.0.0.1:1234/v1",
                    "model_request_timeout": 30.0,
                    "model_api_key": "",
                    "run_root": Path("runs"),
                },
            )(),
    )
    monkeypatch.setattr(DashboardApp, "_resolve_chat_model", lambda self, **kwargs: "test-model")
    monkeypatch.setattr(dashboard, "load_help_markdown", lambda path: "docs")
    monkeypatch.setattr(dashboard, "resolve_help_path", lambda locale: Path("unused.md"))
    monkeypatch.setattr(dashboard, "build_chat_system_prompt", lambda **kwargs: "system")
    monkeypatch.setattr(
        dashboard,
        "build_agent_handoff",
        lambda message, locale="zh-CN": {"suggested_task": message, "reason": locale},
    )

    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)

    events = list(
        app.chat_reply_stream(
            messages=[{"role": "user", "content": "你好"}],
            config_overrides={},
            session_meta={"locale": "zh-CN"},
        )
    )

    assert events[0] == ("start", {"session_meta": {"locale": "zh-CN"}})
    assert ("delta", {"content_delta": "你好"}) in events
    assert events[-1] == (
        "done",
        {
            "assistant_message": "你好",
            "agent_handoff": {"suggested_task": "你好", "reason": "zh-CN"},
            "session_meta": {"locale": "zh-CN"},
        },
    )
    assert fake_response.closed is True


def _legacy_test_dashboard_chat_reply_stream_falls_back_to_non_stream_for_lmstudio(monkeypatch):
    monkeypatch.setattr(
        dashboard,
        "load_agent_config",
        lambda *args, **kwargs: type(
            "Config",
            (),
            {
                "model_provider": "lmstudio_local",
                "run_root": Path("runs"),
            },
        )(),
    )
    monkeypatch.setattr(
        DashboardApp,
        "chat_reply",
        lambda self, **kwargs: {
            "assistant_message": "你好，桌面助手已准备好。",
            "agent_handoff": {"suggested_task": "你好", "reason": "zh-CN"},
            "session_meta": {"locale": "zh-CN"},
        },
    )

    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)
    events = list(
        app.chat_reply_stream(
            messages=[{"role": "user", "content": "你好"}],
            config_overrides={},
            session_meta={"locale": "zh-CN"},
        )
    )

    assert events == [
        ("start", {"session_meta": {"locale": "zh-CN"}}),
        ("delta", {"content_delta": "你好，桌面助手已准备好。"}),
        (
            "done",
            {
                "assistant_message": "你好，桌面助手已准备好。",
                "agent_handoff": {"suggested_task": "你好", "reason": "zh-CN"},
                "session_meta": {"locale": "zh-CN"},
            },
        ),
    ]


def test_dashboard_serves_help_route():
    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(f"{base_url}/api/help?locale=zh-CN") as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert payload["title"] == "帮助中心"
            assert payload["locale"] == "zh-CN"
            assert payload["audience"] == "user"
            assert "第一次使用" in payload["markdown"]
            assert "本地优先" in payload["markdown"]

        with urllib.request.urlopen(f"{base_url}/api/help?locale=en-US") as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert payload["title"] == "Help Center"
            assert payload["locale"] == "en-US"
            assert payload["audience"] == "user"
            assert "First run" in payload["markdown"]
            assert "Advanced Docs" in payload["markdown"]

        with urllib.request.urlopen(f"{base_url}/api/help?locale=en-US&audience=developer") as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert payload["title"] == "Advanced Docs"
            assert payload["locale"] == "en-US"
            assert payload["audience"] == "developer"
            assert "Developer Guide" in payload["markdown"]
            assert '"Send to Agent"' in payload["markdown"]
    finally:
        server.shutdown()
        server.server_close()
