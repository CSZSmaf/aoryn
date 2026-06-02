import json
import re
import shutil
import sys
import threading
import time
import types
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

import desktop_agent.dashboard as dashboard
import pytest
from desktop_agent.dashboard import DashboardApp, DashboardJob, TaskQueue, _clean_config_overrides
from desktop_agent.controller import AgentRunResult, load_agent_config
from desktop_agent.provider_tools import ProviderModelEntry, ProviderSnapshot
from desktop_agent.version import APP_ASSET_VERSION, APP_VERSION


def test_clean_config_overrides_accepts_model_browser_and_display_fields():
    raw = {
        "model_provider": "openai_compatible",
        "model_base_url": "https://api.example.com/v1",
        "model_name": "gpt-test",
        "model_api_key": "  secret \n",
        "model_request_timeout": "120",
        "task_graph_request_timeout": "18",
        "model_auto_discover": False,
        "model_structured_output": "json_object",
        "desktop_autonomy_mode": "autonomous",
        "complex_task_planning": "model",
        "plan_review_policy": "always",
        "max_task_subgoals": "14",
        "max_subgoal_retries": "3",
        "orchestrator_mode": "unified",
        "stage_review_policy": "always",
        "task_workspace_enabled": "true",
        "max_replans_per_run": "4",
        "max_failures_per_subgoal": "5",
        "replan_on_recoverable_error": "false",
        "recoverable_error_retry_limit": "6",
        "plugin_modules": "plugins.excel; plugins.vscode",
        "plugin_fail_fast": "true",
        "browser_control_mode": "dom",
        "browser_dom_backend": "playwright",
        "browser_dom_timeout": "12.5",
        "max_steps": "9",
        "max_run_seconds": "3600",
        "pause_after_action": "0.35",
        "cursor_motion_enabled": "false",
        "cursor_motion_duration": "1.8",
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
        "model_request_timeout": 120.0,
        "task_graph_request_timeout": 18.0,
        "model_auto_discover": False,
        "model_structured_output": "json_object",
        "desktop_autonomy_mode": "autonomous",
        "complex_task_planning": "model",
        "plan_review_policy": "always",
        "max_task_subgoals": 14,
        "max_subgoal_retries": 3,
        "orchestrator_mode": "unified",
        "stage_review_policy": "always",
        "task_workspace_enabled": True,
        "max_replans_per_run": 4,
        "max_failures_per_subgoal": 5,
        "replan_on_recoverable_error": False,
        "recoverable_error_retry_limit": 6,
        "plugin_modules": ["plugins.excel", "plugins.vscode"],
        "plugin_fail_fast": True,
        "browser_control_mode": "dom",
        "browser_dom_backend": "playwright",
        "browser_dom_timeout": 12.5,
        "max_steps": 9,
        "max_run_seconds": 3600.0,
        "pause_after_action": 0.35,
        "cursor_motion_enabled": False,
        "cursor_motion_duration": 1.8,
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
                    "model_request_timeout: 120",
                    "task_graph_request_timeout: 18",
                    "max_task_subgoals: 14",
                    "max_replans_per_run: 4",
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
        assert meta["defaults"]["model_request_timeout"] == 120.0
        assert meta["defaults"]["task_graph_request_timeout"] == 18.0
        assert meta["defaults"]["max_task_subgoals"] == 14
        assert meta["defaults"]["max_replans_per_run"] == 4
        assert meta["defaults"]["browser_control_mode"] == "hybrid"
        assert meta["defaults"]["cursor_motion_enabled"] is False
        assert meta["defaults"]["cursor_motion_duration"] == 0.12
        assert meta["defaults"]["pause_after_action"] == 0.12
        assert meta["defaults"]["browser_dom_timeout"] == 8.0
        assert meta["dom_status"]["detail"] == "Playwright missing"
        assert any(item["value"] == "openai_api" for item in meta["model_providers"])
        assert any(item["value"] == "openai_compatible" for item in meta["model_providers"])
        assert meta["autonomy_mode_presets"]["conservative"]["plan_review_policy"] == "low_risk_auto"
        assert meta["autonomy_mode_presets"]["review_first"]["approval_policy"] == "strict"
        assert meta["autonomy_mode_presets"]["autonomous"]["approval_policy"] == "autonomous"
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
        shutil.rmtree(temp_root, ignore_errors=True)


def test_dashboard_overview_does_not_block_on_managed_browser_status(monkeypatch):
    calls: list[str] = []

    def slow_browser_status(_config):
        calls.append(threading.current_thread().name)
        time.sleep(0.2)
        return {"available": False, "detail": "slow", "base_url": "http://127.0.0.1:38991"}

    monkeypatch.setattr(dashboard, "browser_runtime_status", slow_browser_status)

    temp_root = Path("test_artifacts") / f"dashboard_fast_overview_{uuid4().hex}"
    temp_root.mkdir(parents=True, exist_ok=True)
    try:
        config_path = temp_root / "config.yaml"
        run_root = temp_root / "runs"
        run_root.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            f"model_provider: lmstudio_local\nrun_root: {json.dumps(run_root.as_posix())}\n",
            encoding="utf-8",
        )
        app = DashboardApp(host="127.0.0.1", port=8765, config_path=config_path)

        started = time.perf_counter()
        payload = app.overview()
        elapsed = time.perf_counter() - started

        assert elapsed < 0.15
        assert payload["meta"]["managed_browser_status"]["available"] is False
        assert payload["meta"]["managed_browser_status"]["detail"] == "Aoryn Browser is not running."
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_dashboard_overview_returns_runs_on_first_load():
    temp_root = Path("test_artifacts") / f"dashboard_runs_cache_{uuid4().hex}"
    run_root = temp_root / "runs"
    run_dir = run_root / "20260409_000001_cached"
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        config_path = temp_root / "config.yaml"
        config_path.write_text(
            f"model_provider: lmstudio_local\nrun_root: {json.dumps(run_root.as_posix())}\n",
            encoding="utf-8",
        )
        (run_dir / "summary.json").write_text(
            json.dumps(
                {
                    "task": "cached overview",
                    "completed": True,
                    "steps": 1,
                    "started_at": 100.0,
                    "finished_at": 101.0,
                }
            ),
            encoding="utf-8",
        )
        app = DashboardApp(host="127.0.0.1", port=8765, config_path=config_path)

        first_payload = app.overview()
        assert first_payload["runs"][0]["id"] == "20260409_000001_cached"

        refreshed = app.overview()["runs"]
        assert refreshed[0]["id"] == "20260409_000001_cached"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_dashboard_overview_refreshes_runs_when_terminal_job_run_is_missing_from_cache():
    temp_root = Path("test_artifacts") / f"dashboard_terminal_job_refresh_{uuid4().hex}"
    run_root = temp_root / "runs"
    cached_run_dir = run_root / "20260409_000001_cached"
    finished_run_dir = run_root / "20260409_000002_finished"
    cached_run_dir.mkdir(parents=True, exist_ok=True)
    try:
        config_path = temp_root / "config.yaml"
        config_path.write_text(
            f"model_provider: lmstudio_local\nrun_root: {json.dumps(run_root.as_posix())}\n",
            encoding="utf-8",
        )
        (cached_run_dir / "summary.json").write_text(
            json.dumps(
                {
                    "task": "cached overview",
                    "completed": True,
                    "steps": 1,
                    "started_at": 100.0,
                    "finished_at": 101.0,
                }
            ),
            encoding="utf-8",
        )
        app = DashboardApp(host="127.0.0.1", port=8765, config_path=config_path)

        first_payload = app.overview()
        assert [item["id"] for item in first_payload["runs"]] == ["20260409_000001_cached"]

        finished_run_dir.mkdir(parents=True, exist_ok=True)
        (finished_run_dir / "summary.json").write_text(
            json.dumps(
                {
                    "task": "finished from active job",
                    "completed": True,
                    "steps": 2,
                    "started_at": 200.0,
                    "finished_at": 201.0,
                }
            ),
            encoding="utf-8",
        )
        job = DashboardJob(
            job_id="job-terminal-refresh",
            task="finished from active job",
            planner_mode="auto",
            dry_run=False,
            max_steps=6,
            pause_after_action=0.1,
            status="completed",
            result={
                "run_id": "20260409_000002_finished",
                "completed": True,
                "steps": 2,
                "finished_at": 201.0,
            },
        )
        app.queue.jobs[job.job_id] = job

        refreshed_payload = app.overview()

        assert refreshed_payload["jobs"][0]["result"]["run_id"] == "20260409_000002_finished"
        assert refreshed_payload["runs"][0]["id"] == "20260409_000002_finished"
        assert {item["id"] for item in refreshed_payload["runs"]} == {
            "20260409_000001_cached",
            "20260409_000002_finished",
        }
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_dashboard_overview_refreshes_runs_when_active_job_run_is_missing_from_cache():
    temp_root = Path("test_artifacts") / f"dashboard_active_job_refresh_{uuid4().hex}"
    run_root = temp_root / "runs"
    cached_run_dir = run_root / "20260409_000001_cached"
    active_run_dir = run_root / "20260409_000002_approval"
    cached_run_dir.mkdir(parents=True, exist_ok=True)
    try:
        config_path = temp_root / "config.yaml"
        config_path.write_text(
            f"model_provider: lmstudio_local\nrun_root: {json.dumps(run_root.as_posix())}\n",
            encoding="utf-8",
        )
        (cached_run_dir / "summary.json").write_text(
            json.dumps(
                {
                    "task": "cached overview",
                    "completed": True,
                    "steps": 1,
                    "started_at": 100.0,
                    "finished_at": 101.0,
                }
            ),
            encoding="utf-8",
        )
        app = DashboardApp(host="127.0.0.1", port=8765, config_path=config_path)

        first_payload = app.overview()
        assert [item["id"] for item in first_payload["runs"]] == ["20260409_000001_cached"]

        active_run_dir.mkdir(parents=True, exist_ok=True)
        (active_run_dir / "summary.json").write_text(
            json.dumps(
                {
                    "task": "approval from active job",
                    "completed": False,
                    "steps": 1,
                    "started_at": 200.0,
                }
            ),
            encoding="utf-8",
        )
        job = DashboardJob(
            job_id="job-active-refresh",
            task="approval from active job",
            planner_mode="auto",
            dry_run=False,
            max_steps=6,
            pause_after_action=0.1,
            status="approval",
            result={
                "run_id": "20260409_000002_approval",
                "pending_decision": {
                    "decision_type": "plan_review",
                    "summary": "Review the active plan.",
                },
            },
        )
        app.queue.jobs[job.job_id] = job
        app.queue.active_job_id = job.job_id

        refreshed_payload = app.overview()

        assert refreshed_payload["active_job"]["result"]["run_id"] == "20260409_000002_approval"
        assert refreshed_payload["runs"][0]["id"] == "20260409_000002_approval"
        assert {item["id"] for item in refreshed_payload["runs"]} == {
            "20260409_000001_cached",
            "20260409_000002_approval",
        }
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_dashboard_clear_history_removes_runs_and_finished_jobs():
    temp_root = Path("test_artifacts") / f"dashboard_clear_history_{uuid4().hex}"
    run_root = temp_root / "runs"
    run_dir = run_root / "20260409_000001_clear"
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        config_path = temp_root / "config.yaml"
        config_path.write_text(
            f"model_provider: lmstudio_local\nrun_root: {json.dumps(run_root.as_posix())}\n",
            encoding="utf-8",
        )
        (run_dir / "summary.json").write_text(
            json.dumps({"task": "clear history", "completed": True, "steps": 1, "started_at": 100.0}),
            encoding="utf-8",
        )
        app = DashboardApp(host="127.0.0.1", port=8765, config_path=config_path)
        finished_job = DashboardJob(
            job_id="job-finished",
            task="finished task",
            planner_mode="auto",
            dry_run=False,
            max_steps=1,
            pause_after_action=None,
            status="completed",
        )
        app.queue.jobs[finished_job.job_id] = finished_job

        payload = app.clear_history()

        assert payload["ok"] is True
        assert payload["runs_cleared"] == 1
        assert payload["jobs_cleared"] == 1
        assert not run_dir.exists()
        assert app.queue.list_jobs() == []
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_dashboard_clear_history_rejects_when_task_is_active():
    app = DashboardApp(host="127.0.0.1", port=8765, config_path=None)
    running_job = DashboardJob(
        job_id="job-running",
        task="running task",
        planner_mode="auto",
        dry_run=False,
        max_steps=1,
        pause_after_action=None,
        status="running",
    )
    app.queue.jobs[running_job.job_id] = running_job
    app.queue.active_job_id = running_job.job_id

    with pytest.raises(RuntimeError, match="Another task is running"):
        app.clear_history()


def test_dashboard_history_clear_endpoint_returns_counts():
    temp_root = Path("test_artifacts") / f"dashboard_clear_history_api_{uuid4().hex}"
    run_root = temp_root / "runs"
    run_dir = run_root / "20260409_000001_clear_api"
    run_dir.mkdir(parents=True, exist_ok=True)
    config_path = temp_root / "config.yaml"
    config_path.write_text(
        f"model_provider: lmstudio_local\nrun_root: {json.dumps(run_root.as_posix())}\n",
        encoding="utf-8",
    )
    (run_dir / "summary.json").write_text(
        json.dumps({"task": "clear via api", "completed": True, "steps": 1, "started_at": 100.0}),
        encoding="utf-8",
    )
    app = DashboardApp(host="127.0.0.1", port=0, config_path=config_path)
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/history/clear",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 202
            assert payload["ok"] is True
            assert payload["runs_cleared"] == 1
            assert payload["jobs_cleared"] == 0
    finally:
        server.shutdown()
        server.server_close()
        shutil.rmtree(temp_root, ignore_errors=True)


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


def test_load_agent_config_normalizes_run_root_from_config_overrides(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("dry_run: true\n", encoding="utf-8")
    run_root = tmp_path / "runtime-runs"

    config = load_agent_config(config_path, config_overrides={"run_root": str(run_root)})

    assert isinstance(config.run_root, Path)
    assert config.run_root == run_root


def test_load_agent_config_run_budget_arguments_override_config_overrides():
    temp_root = Path("test_artifacts") / f"dashboard_run_budget_{uuid4().hex}"
    temp_root.mkdir(parents=True, exist_ok=True)
    try:
        config_path = temp_root / "config.yaml"
        config_path.write_text("max_steps: 2\npause_after_action: 0.2\nmax_run_seconds: 10\n", encoding="utf-8")

        config = load_agent_config(
            config_path,
            max_steps=9,
            pause_after_action=0.05,
            config_overrides={
                "max_steps": 4,
                "pause_after_action": 0.6,
                "max_run_seconds": 20,
            },
        )

        assert config.max_steps == 9
        assert config.pause_after_action == 0.05
        assert config.max_run_seconds == 20
    finally:
        if config_path.exists():
            config_path.unlink()
        temp_root.rmdir()


def test_load_agent_config_clamps_cursor_motion_duration():
    temp_root = Path("test_artifacts") / f"dashboard_cursor_motion_{uuid4().hex}"
    temp_root.mkdir(parents=True, exist_ok=True)
    try:
        config_path = temp_root / "config.yaml"
        config_path.write_text("cursor_motion_duration: 2.4\n", encoding="utf-8")

        config = load_agent_config(
            config_path,
            config_overrides={
                "cursor_motion_enabled": False,
                "cursor_motion_duration": 0.02,
            },
        )

        assert config.cursor_motion_enabled is False
        assert config.cursor_motion_duration == 0.05
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


def test_dashboard_provider_load_model_route_parses_string_unload_flag(monkeypatch):
    captured: list[dict[str, object]] = []
    monkeypatch.setattr(
        DashboardApp,
        "provider_load_model",
        lambda self, **kwargs: captured.append(kwargs) or {"ok": True, "model_id": kwargs["model_id"]},
    )

    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/provider/load-model",
            data=json.dumps(
                {
                    "model_id": "qwen/qwen3-14b",
                    "unload_first": "false",
                    "config_overrides": {"browser_headless": "false"},
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert payload["model_id"] == "qwen/qwen3-14b"
    finally:
        server.shutdown()
        server.server_close()

    assert captured
    assert captured[0]["model_id"] == "qwen/qwen3-14b"
    assert captured[0]["unload_first"] is False
    assert captured[0]["config_overrides"]["browser_headless"] is False


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


def test_dashboard_job_serializes_terminal_state_without_stale_pending_decision():
    job = DashboardJob(
        job_id="job-failed-stale-review",
        task="fail after plan review",
        planner_mode="auto",
        dry_run=False,
        max_steps=6,
        pause_after_action=0.4,
        status="failed",
        error="planner stopped",
        requires_human=False,
        result={
            "error": "planner stopped",
            "requires_human": "false",
            "pending_decision": {"decision_type": "plan_review"},
            "execution_state": {
                "pending_decision": {"decision_type": "plan_review"},
                "plan_review_status": "pending",
            },
            "state": {
                "pending_decision": {"decision_type": "plan_review"},
                "plan_review_status": "pending",
            },
        },
    )

    payload = job.to_dict()

    assert payload["status"] == "failed"
    assert payload["requires_human"] is False
    assert payload["result"].get("pending_decision") is None
    assert payload["result"]["execution_state"].get("pending_decision") is None
    assert payload["result"]["state"].get("pending_decision") is None


def test_task_queue_cancel_active_marks_job_stopping():
    queue = TaskQueue(config_path=None)
    job = DashboardJob(
        job_id="job123",
        task="open calculator",
        planner_mode="auto",
        dry_run=False,
        max_steps=6,
        pause_after_action=0.4,
        status="approval",
        result={
            "pending_decision": {"decision_type": "plan_review"},
            "execution_state": {
                "pending_decision": {"decision_type": "plan_review"},
                "plan_health": {
                    "autonomy": {
                        "status": "review_required",
                        "can_continue": False,
                        "requires_review": True,
                    }
                },
            },
        },
    )
    queue.jobs[job.job_id] = job
    queue.cancel_events[job.job_id] = threading.Event()
    queue.decision_events[job.job_id] = threading.Event()
    queue.pending_decisions[job.job_id] = {"decision_type": "plan_review"}
    queue.active_job_id = job.job_id

    payload = queue.cancel_active()

    assert payload["status"] == "stopping"
    assert payload["cancel_requested"] is True
    assert queue.cancel_events[job.job_id].is_set() is True
    assert queue.decision_events[job.job_id].is_set() is True
    assert queue.pending_decisions.get(job.job_id) is None
    assert payload["result"].get("pending_decision") is None
    assert payload["result"]["execution_state"].get("pending_decision") is None
    assert payload["result"]["execution_state"]["plan_health"]["autonomy"]["status"] == "waiting_user"
    assert payload["result"]["execution_state"]["plan_health"]["autonomy"]["requires_review"] is False


def test_clear_pending_decision_updates_top_level_review_status():
    result = {
        "pending_decision": {"decision_type": "stage_review", "summary": "Review the replanned stage."},
        "stage_review_status": "pending",
        "execution_state": {
            "orchestration_phase": "stage_review",
            "stage_review_status": "pending",
            "pending_decision": {"decision_type": "stage_review"},
            "app_context": {"stage_review_status": "pending"},
            "plan_health": {
                "autonomy": {
                    "status": "review_required",
                    "can_continue": False,
                    "requires_review": True,
                    "next_action": "approve_stage",
                }
            },
        },
    }

    cleaned = dashboard._clear_pending_decision_from_result(result, decision="approved")

    state_payload = cleaned["execution_state"]
    assert cleaned.get("pending_decision") is None
    assert cleaned["stage_review_status"] == "approved"
    assert state_payload.get("pending_decision") is None
    assert state_payload["orchestration_phase"] == "stage_ready"
    assert state_payload["stage_review_status"] == "approved"
    assert state_payload["app_context"]["stage_review_status"] == "approved"
    assert state_payload["plan_health"]["autonomy"]["status"] == "ready"
    assert state_payload["plan_health"]["autonomy"]["next_action"] == "execute"

    summary_state = dashboard._clear_pending_decision_from_result(
        {
            "state": {
                "orchestration_phase": "stage_review",
                "stage_review_status": "pending",
                "pending_decision": {"decision_type": "stage_review"},
                "app_context": {"stage_review_status": "pending"},
                "plan_health": {
                    "autonomy": {
                        "status": "review_required",
                        "can_continue": False,
                        "requires_review": True,
                    }
                },
            },
        },
        decision="approve",
    )

    assert summary_state["stage_review_status"] == "approved"
    assert summary_state["state"].get("pending_decision") is None
    assert summary_state["state"]["orchestration_phase"] == "stage_ready"
    assert summary_state["state"]["stage_review_status"] == "approved"
    assert summary_state["state"]["app_context"]["stage_review_status"] == "approved"
    assert summary_state["state"]["plan_health"]["autonomy"]["status"] == "ready"

    without_context = dashboard._clear_pending_decision_from_result(
        {
            "pending_decision": {"decision_type": "stage_review"},
            "stage_review_status": "pending",
            "execution_state": {
                "orchestration_phase": "stage_review",
                "stage_review_status": "pending",
                "pending_decision": {"decision_type": "stage_review"},
            },
        },
        decision="reject",
    )

    assert without_context["stage_review_status"] == "rejected"
    assert without_context["execution_state"]["stage_review_status"] == "rejected"

    plan_review = dashboard._clear_pending_decision_from_result(
        {
            "pending_decision": {"decision_type": "plan_review"},
            "plan_review_status": "pending",
            "execution_state": {
                "orchestration_phase": "plan_review",
                "plan_review_status": "pending",
                "pending_decision": {"decision_type": "plan_review"},
            },
        },
        decision="cancelled",
    )

    assert plan_review["plan_review_status"] == "cancelled"
    assert plan_review["execution_state"]["plan_review_status"] == "cancelled"

    empty_shell = dashboard._clear_pending_decision_from_result(
        {
            "pending_decision": {},
            "stage_review_status": "pending",
            "execution_state": {
                "orchestration_phase": "stage_review",
                "stage_review_status": "pending",
                "pending_decision": {"decision_type": "stage_review"},
                "app_context": {"stage_review_status": "pending"},
            },
            "state": {"pending_decision": {}},
        },
        decision="approved",
    )

    assert empty_shell.get("pending_decision") is None
    assert empty_shell["stage_review_status"] == "approved"
    assert empty_shell["execution_state"]["stage_review_status"] == "approved"
    assert empty_shell["execution_state"]["app_context"]["stage_review_status"] == "approved"


def test_task_queue_progress_preserves_plan_health_for_frontend():
    queue = TaskQueue(config_path=None)
    job = DashboardJob(
        job_id="job-plan-health",
        task="recover and continue",
        planner_mode="auto",
        dry_run=False,
        max_steps=6,
        pause_after_action=0.1,
        status="running",
    )
    queue.jobs[job.job_id] = job
    queue.active_job_id = job.job_id

    queue._update_job_progress(
        job.job_id,
        {
            "run_id": "run-plan-health",
            "latest_summary": "Review the generated plan.",
            "execution_state": {
                "orchestration_phase": "plan_review",
                "pending_decision": {
                    "decision_type": "plan_review",
                    "summary": "Review the task plan.",
                },
                "plan_health": {
                    "counts": {"total": 2, "completed": 0, "blocked": 1, "ready": 1},
                    "next_subgoal_id": "subgoal_02",
                },
            },
        },
    )

    assert job.status == "approval"
    assert queue.pending_decisions[job.job_id]["decision_type"] == "plan_review"
    assert job.result["execution_state"]["plan_health"]["next_subgoal_id"] == "subgoal_02"
    assert job.result["execution_state"]["plan_health"]["counts"]["ready"] == 1


def test_task_queue_progress_ignores_empty_display_state_shells_over_full_state():
    queue = TaskQueue(config_path=None)
    job = DashboardJob(
        job_id="job-empty-display-shells",
        task="preserve full state through empty display shells",
        planner_mode="auto",
        dry_run=False,
        max_steps=6,
        pause_after_action=0.1,
        status="running",
    )
    queue.jobs[job.job_id] = job
    queue.active_job_id = job.job_id

    queue._update_job_progress(
        job.job_id,
        {
            "run_id": "run-empty-display-shells",
            "latest_summary": "Review the generated plan.",
            "execution_state": {
                "orchestration_phase": "plan_review",
                "pending_decision": {
                    "decision_type": "plan_review",
                    "summary": "Review the generated plan.",
                },
                "plan_health": {
                    "counts": {"total": 2, "completed": 0, "ready": 1},
                    "next_subgoal_id": "subgoal_01",
                },
                "workspace_summary": {
                    "facts": [{"key": "route", "value": "Generated plan is ready."}],
                },
            },
            "state": {
                "current_goal": "Review summarized plan",
                "pending_decision": {},
                "plan_health": {"counts": {}, "autonomy": {}, "items": []},
                "workspace_summary": {"facts": [], "sources": [], "evidence": [], "notes": []},
            },
        },
    )

    assert job.status == "approval"
    assert queue.pending_decisions[job.job_id]["summary"] == "Review the generated plan."
    assert job.result["pending_decision"]["summary"] == "Review the generated plan."
    assert job.result["state"]["current_goal"] == "Review summarized plan"
    assert job.result["state"]["pending_decision"]["summary"] == "Review the generated plan."
    assert job.result["state"]["plan_health"]["next_subgoal_id"] == "subgoal_01"
    assert job.result["state"]["workspace_summary"]["facts"][0]["value"] == "Generated plan is ready."


def test_task_queue_progress_mirrors_state_summary_over_stale_top_level_fields():
    queue = TaskQueue(config_path=None)
    job = DashboardJob(
        job_id="job-state-summary-progress",
        task="continue with state-only progress",
        planner_mode="auto",
        dry_run=False,
        max_steps=6,
        pause_after_action=0.1,
        status="running",
        result={
            "run_id": "run-state-summary-progress",
            "current_goal": "Review the stale goal",
            "plan_review_status": "pending",
            "chosen_capability": "browser_dom",
            "verification_status": "failed",
            "pending_decision": {"decision_type": "plan_review"},
            "step_proposal": {"intent": "review stale goal", "capability": "browser_dom"},
            "verification": {"status": "failed", "message": "Old verification."},
            "state": {
                "current_goal": "Review the stale goal",
                "plan_review_status": "pending",
                "pending_decision": {"decision_type": "plan_review"},
            },
        },
    )
    queue.jobs[job.job_id] = job
    queue.active_job_id = job.job_id

    queue._update_job_progress(
        job.job_id,
        {
            "run_id": "run-state-summary-progress",
            "latest_summary": "Continuing with verified progress.",
            "state": {
                "orchestration_phase": "stage_ready",
                "current_goal": "Verify updated goal",
                "plan_review_status": "approved",
                "chosen_capability": "shell",
                "verification_status": "success",
                "pending_decision": None,
                "last_step": {"intent": "verify updated goal", "capability": "shell"},
                "last_verification": {"status": "success", "message": "Updated goal verified."},
            },
        },
    )

    assert job.status == "running"
    assert queue.pending_decisions.get(job.job_id) is None
    assert job.result.get("pending_decision") is None
    assert job.result["state"].get("pending_decision") is None
    assert job.result["current_goal"] == "Verify updated goal"
    assert job.result["plan_review_status"] == "approved"
    assert job.result["chosen_capability"] == "shell"
    assert job.result["verification_status"] == "success"
    assert job.result["step_proposal"]["intent"] == "verify updated goal"
    assert job.result["verification"]["status"] == "success"


def test_task_queue_progress_handles_top_level_pending_decision_and_clears_it():
    queue = TaskQueue(config_path=None)
    job = DashboardJob(
        job_id="job-top-level-approval",
        task="review top-level approval payload",
        planner_mode="auto",
        dry_run=False,
        max_steps=6,
        pause_after_action=0.1,
        status="running",
    )
    queue.jobs[job.job_id] = job
    queue.active_job_id = job.job_id

    queue._update_job_progress(
        job.job_id,
        {
            "run_id": "run-top-level-approval",
            "latest_summary": "Review the generated plan.",
            "pending_decision": {
                "decision_type": "plan_review",
                "summary": "Review the task plan.",
            },
            "execution_state": {
                "orchestration_phase": "plan_review",
                "plan_health": {
                    "autonomy": {"status": "review_required", "can_continue": False},
                },
            },
        },
    )

    assert job.status == "approval"
    assert queue.pending_decisions[job.job_id]["decision_type"] == "plan_review"
    assert job.result["pending_decision"]["summary"] == "Review the task plan."

    queue._update_job_progress(
        job.job_id,
        {
            "run_id": "run-top-level-approval",
            "latest_summary": "Continuing after review.",
            "execution_state": {
                "orchestration_phase": "stage_ready",
                "plan_health": {
                    "autonomy": {"status": "ready", "can_continue": True},
                },
            },
        },
    )

    assert job.status == "running"
    assert queue.pending_decisions.get(job.job_id) is None
    assert job.result.get("pending_decision") is None
    assert job.result["execution_state"].get("pending_decision") is None
    assert job.result["execution_state"]["plan_health"]["autonomy"]["status"] == "ready"


def test_task_queue_await_job_decision_accepts_nested_state_pending_decision():
    queue = TaskQueue(config_path=None)
    job = DashboardJob(
        job_id="job-nested-state-approval",
        task="review nested approval payload",
        planner_mode="auto",
        dry_run=False,
        max_steps=6,
        pause_after_action=0.1,
        status="running",
    )
    queue.jobs[job.job_id] = job
    queue.active_job_id = job.job_id
    queue.decision_events[job.job_id] = threading.Event()
    responses: list[dict[str, object]] = []
    waiter = threading.Thread(
        target=lambda: responses.append(
            queue._await_job_decision(
                job.job_id,
                {
                    "pending_decision": {},
                    "state": {
                        "orchestration_phase": "plan_review",
                        "pending_decision": {
                            "decision_type": "plan_review",
                            "summary": "Review the nested task plan.",
                        },
                        "app_context": {"plan_review_status": "pending"},
                    },
                    "step_proposal": {"capability": "browser_dom"},
                },
            )
        ),
        daemon=True,
    )
    waiter.start()

    deadline = time.time() + 3
    while job.status != "approval" and time.time() < deadline:
        time.sleep(0.01)

    assert job.status == "approval"
    assert queue.pending_decisions[job.job_id]["decision_type"] == "plan_review"
    assert job.result["pending_decision"]["summary"] == "Review the nested task plan."
    assert job.result["execution_state"]["pending_decision"]["summary"] == "Review the nested task plan."

    queue.decide(job.job_id, decision="approved", note="Looks good.")
    waiter.join(timeout=3)

    assert responses == [{"decision": "approve", "note": "Looks good."}]
    assert queue.pending_decisions.get(job.job_id) is None
    assert job.status == "running"
    assert job.result.get("pending_decision") is None
    assert job.result["execution_state"].get("pending_decision") is None
    assert job.result["execution_state"]["plan_review_status"] == "approved"


def test_task_queue_await_job_decision_rejects_empty_pending_payload():
    queue = TaskQueue(config_path=None)
    job = DashboardJob(
        job_id="job-empty-approval",
        task="reject empty approval payload",
        planner_mode="auto",
        dry_run=False,
        max_steps=6,
        pause_after_action=0.1,
        status="running",
    )
    queue.jobs[job.job_id] = job
    queue.active_job_id = job.job_id
    queue.decision_events[job.job_id] = threading.Event()

    with pytest.raises(RuntimeError, match="pending decision"):
        queue._await_job_decision(
            job.job_id,
            {
                "pending_decision": {},
                "state": {
                    "orchestration_phase": "plan_review",
                    "pending_decision": {},
                },
            },
        )

    assert job.status == "running"
    assert queue.pending_decisions.get(job.job_id) is None
    assert job.result is None


def test_task_queue_buffered_unknown_decision_rejects_pending_review():
    queue = TaskQueue(config_path=None)
    job = DashboardJob(
        job_id="job-unknown-buffered-decision",
        task="review unknown buffered decision",
        planner_mode="auto",
        dry_run=False,
        max_steps=6,
        pause_after_action=0.1,
        status="approval",
        result={
            "pending_decision": {
                "decision_type": "plan_review",
                "summary": "Review the buffered task plan.",
            },
            "execution_state": {
                "orchestration_phase": "plan_review",
                "plan_review_status": "pending",
                "pending_decision": {
                    "decision_type": "plan_review",
                    "summary": "Review the buffered task plan.",
                },
                "app_context": {"plan_review_status": "pending"},
            },
        },
    )
    queue.jobs[job.job_id] = job
    queue.pending_decisions[job.job_id] = {"decision_type": "plan_review"}

    response = queue._apply_decision_response_locked(job.job_id, {"decision": "later", "note": "unknown"})

    assert response == {"decision": "reject", "note": "unknown"}
    assert queue.pending_decisions.get(job.job_id) is None
    assert job.status == "running"
    assert job.result.get("pending_decision") is None
    assert job.result["plan_review_status"] == "rejected"
    assert job.result["execution_state"].get("pending_decision") is None
    assert job.result["execution_state"]["plan_review_status"] == "rejected"
    assert job.result["execution_state"]["app_context"]["plan_review_status"] == "rejected"


def test_task_queue_submit_seeds_preview_plan_state_before_first_progress(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "complex_task_planning: heuristic",
                "plan_review_policy: always",
                "run_root: runs",
            ]
        ),
        encoding="utf-8",
    )
    app = DashboardApp(host="127.0.0.1", port=0, config_path=config_path)
    preview = app.preview_task(task="open calculator", config_overrides={})
    queue = TaskQueue(config_path=config_path)
    run_started = threading.Event()
    release_run = threading.Event()
    run_dir = tmp_path / "run-preview"
    run_dir.mkdir()

    def _run_task(*args, **kwargs):
        run_started.set()
        release_run.wait(timeout=3)
        return AgentRunResult(
            task="open calculator",
            completed=False,
            steps=0,
            run_dir=run_dir,
            started_at=10.0,
            finished_at=11.0,
            error="stopped after seed assertion",
        )

    monkeypatch.setattr(dashboard, "run_task", _run_task)

    job = queue.submit(
        task="open calculator",
        planner_mode=None,
        dry_run=False,
        max_steps=None,
        pause_after_action=None,
        initial_task_graph=preview["task_graph"],
    )

    try:
        assert job.status == "approval"
        assert queue.active_job()["status"] == "approval"
        assert queue.pending_decisions[job.job_id]["decision_type"] == "plan_review"
        assert job.result["pending_decision"]["decision_type"] == "plan_review"
        assert job.result["execution_state"]["pending_decision"]["decision_type"] == "plan_review"
        assert job.result["execution_state"]["plan_health"]["autonomy"]["status"] == "review_required"
        assert job.result["execution_state"]["plan_health"]["autonomy"]["next_action"] == "approve_plan"
        assert queue.active_job()["result"]["execution_state"]["plan_health"]["autonomy"]["can_continue"] is False
        assert run_started.wait(timeout=3)
        assert queue.active_job()["status"] == "approval"
    finally:
        release_run.set()
        deadline = time.time() + 3
        while queue.active_job_id is not None and time.time() < deadline:
            time.sleep(0.01)


def test_task_queue_submit_buffers_seeded_preview_plan_decision_before_runner_callback(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "complex_task_planning: heuristic",
                "plan_review_policy: always",
                "run_root: runs",
            ]
        ),
        encoding="utf-8",
    )
    app = DashboardApp(host="127.0.0.1", port=0, config_path=config_path)
    preview = app.preview_task(task="open calculator", config_overrides={})
    queue = TaskQueue(config_path=config_path)
    run_started = threading.Event()
    release_review_wait = threading.Event()
    responses: list[dict[str, object]] = []
    pending_decision_holder = {}
    run_dir = tmp_path / "run-preview-approved"
    run_dir.mkdir()

    def _run_task(*args, **kwargs):
        run_started.set()
        release_review_wait.wait(timeout=3)
        pending_decision = dict(pending_decision_holder["value"])
        responses.append(
            kwargs["decision_callback"](
                {
                    "execution_state": {
                        "orchestration_phase": "plan_review",
                        "pending_decision": pending_decision,
                        "plan_review_status": "pending",
                        "app_context": {"plan_review_status": "pending"},
                        "plan_health": {
                            "autonomy": {
                                "status": "review_required",
                                "can_continue": False,
                                "requires_review": True,
                                "next_action": "approve_plan",
                                "blockers": ["Plan review is required before execution."],
                            }
                        },
                    },
                }
            )
        )
        return AgentRunResult(
            task="open calculator",
            completed=True,
            steps=1,
            run_dir=run_dir,
            started_at=10.0,
            finished_at=11.0,
            execution_state={
                "orchestration_phase": "complete",
                "plan_review_status": "approved",
                "app_context": {"plan_review_status": "approved"},
            },
        )

    monkeypatch.setattr(dashboard, "run_task", _run_task)

    job = queue.submit(
        task="open calculator",
        planner_mode=None,
        dry_run=False,
        max_steps=None,
        pause_after_action=None,
        initial_task_graph=preview["task_graph"],
    )

    try:
        pending_decision_holder["value"] = dict(job.result["pending_decision"])
        assert job.status == "approval"
        assert queue.active_job()["status"] == "approval"
        assert queue.pending_decisions[job.job_id]["decision_type"] == "plan_review"
        assert job.result["execution_state"]["plan_health"]["autonomy"]["can_continue"] is False
        assert run_started.wait(timeout=3)

        decided = queue.decide(job.job_id, decision="approve", note="Preview approved.")
        assert decided["status"] == "running"
        assert decided["result"].get("pending_decision") is None
        assert decided["result"]["execution_state"].get("pending_decision") is None
        release_review_wait.set()

        deadline = time.time() + 3
        while queue.active_job_id is not None and time.time() < deadline:
            time.sleep(0.01)

        assert responses == [{"decision": "approve", "note": "Preview approved."}]
        assert queue.jobs[job.job_id].status == "completed"
        assert queue.jobs[job.job_id].result.get("pending_decision") is None
        assert queue.jobs[job.job_id].result["execution_state"].get("pending_decision") is None
        assert queue.jobs[job.job_id].result["execution_state"]["plan_review_status"] == "approved"
    finally:
        release_review_wait.set()
        deadline = time.time() + 3
        while queue.active_job_id is not None and time.time() < deadline:
            active = queue.jobs.get(job.job_id)
            if active is not None and active.status == "approval":
                try:
                    queue.decide(job.job_id, decision="approve", note="cleanup")
                except RuntimeError:
                    pass
            time.sleep(0.01)


def test_resume_job_initial_result_prefers_display_state_summary():
    result = dashboard._build_resume_job_result(
        run_id="run-human",
        details={
            "task": "continue interrupted task",
            "steps": 2,
            "interruption_reason": "Waiting for manual verification.",
            "timeline": [
                {
                    "screenshot": "step_02.png",
                    "plan": {"status_summary": "Paused for manual verification."},
                }
            ],
            "state": {
                "current_goal": "Resume after verification",
                "plan_health": {
                    "counts": {"total": 2, "completed": 1, "ready": 1},
                    "autonomy": {"status": "waiting_user", "can_continue": False},
                },
            },
            "execution_state": {
                "task_graph": {"subgoals": [{"id": "full-state-only"}]},
            },
        },
    )

    assert result["run_id"] == "run-human"
    assert result["latest_screenshot"] == "step_02.png"
    assert result["latest_summary"] == "Paused for manual verification."
    assert result["execution_state"]["current_goal"] == "Resume after verification"
    assert result["execution_state"]["plan_health"]["autonomy"]["status"] == "ready"
    assert result["execution_state"]["plan_health"]["autonomy"]["can_continue"] is True
    assert result["execution_state"]["app_context"]["manual_resume_status"] == "resumed"
    assert result["execution_state"]["task_graph"]["subgoals"][0]["id"] == "full-state-only"


def test_resume_job_initial_result_preserves_clarification_wait():
    result = dashboard._build_resume_job_result(
        run_id="run-clarify",
        details={
            "task": "ask which folder to use",
            "steps": 1,
            "interruption_kind": "requires_clarification",
            "interruption_reason": "Choose the destination folder.",
            "timeline": [],
            "state": {
                "current_goal": "Ask the user for the folder",
                "orchestration_phase": "awaiting_user",
                "app_context": {
                    "human_handoff_kind": "requires_clarification",
                    "human_handoff_reason": "Choose the destination folder.",
                },
                "last_verification": {
                    "success": False,
                    "status": "failed",
                    "failure_kind": "requires_clarification",
                    "message": "Choose the destination folder.",
                },
                "plan_health": {
                    "counts": {"total": 1, "completed": 0, "ready": 1},
                    "autonomy": {
                        "status": "waiting_user",
                        "can_continue": False,
                        "requires_user": True,
                        "next_action": "resume_after_user",
                    },
                },
            },
            "execution_state": {
                "task_graph": {
                    "subgoals": [
                        {"id": "subgoal_01", "title": "Ask the user for the folder", "goal_type": "clarify"}
                    ]
                },
            },
        },
    )

    assert result["execution_state"]["orchestration_phase"] == "awaiting_user"
    assert result["execution_state"]["plan_health"]["autonomy"]["status"] == "waiting_user"
    assert result["execution_state"]["app_context"]["human_handoff_kind"] == "requires_clarification"


def test_resume_job_initial_result_uses_verification_message_for_manual_resume_reason():
    result = dashboard._build_resume_job_result(
        run_id="run-auth-message",
        details={
            "task": "resume after auth prompt",
            "steps": 1,
            "requires_human": True,
            "timeline": [],
            "state": {
                "orchestration_phase": "awaiting_user",
                "last_verification": {
                    "success": False,
                    "status": "failed",
                    "failure_kind": "requires_auth",
                    "message": "Complete the sign-in challenge.",
                },
                "plan_health": {
                    "counts": {"total": 1, "completed": 0, "ready": 1},
                    "autonomy": {
                        "status": "waiting_user",
                        "can_continue": False,
                        "requires_user": True,
                    },
                },
            },
            "execution_state": {
                "task_graph": {
                    "task": "resume after auth prompt",
                    "subgoals": [{"id": "subgoal_01", "title": "Continue after auth"}],
                },
            },
        },
    )

    assert result["execution_state"]["orchestration_phase"] == "stage_ready"
    assert result["execution_state"]["app_context"]["manual_resume_status"] == "resumed"
    assert result["execution_state"]["app_context"]["manual_resume_reason"] == "Complete the sign-in challenge."
    assert result["execution_state"]["last_verification"] is None
    assert result["execution_state"]["plan_health"]["autonomy"]["can_continue"] is True


def test_resume_job_initial_result_ignores_empty_pending_shell_for_manual_resume():
    result = dashboard._build_resume_job_result(
        run_id="run-empty-pending-shell",
        details={
            "task": "resume after empty pending shell",
            "steps": 1,
            "requires_human": True,
            "timeline": [],
            "state": {
                "orchestration_phase": "awaiting_user",
                "pending_decision": {},
                "app_context": {
                    "human_handoff_reason": "Complete the local confirmation.",
                    "standard_recovery_kind": "requires_user",
                },
                "plan_health": {
                    "counts": {"total": 1, "completed": 0, "ready": 1},
                    "autonomy": {
                        "status": "waiting_user",
                        "can_continue": False,
                        "requires_user": True,
                    },
                },
            },
            "execution_state": {
                "task_graph": {
                    "task": "resume after empty pending shell",
                    "subgoals": [{"id": "subgoal_01", "title": "Continue after confirmation"}],
                },
            },
        },
    )

    execution_state = result["execution_state"]
    assert execution_state["orchestration_phase"] == "stage_ready"
    assert execution_state["pending_decision"] is None
    assert execution_state["app_context"]["manual_resume_status"] == "resumed"
    assert execution_state["app_context"]["manual_resume_reason"] == "Complete the local confirmation."
    assert "standard_recovery_kind" not in execution_state["app_context"]
    assert execution_state["plan_health"]["autonomy"]["status"] == "ready"
    assert execution_state["plan_health"]["autonomy"]["can_continue"] is True


def test_resume_job_initial_result_preserves_pending_review_decision():
    result = dashboard._build_resume_job_result(
        run_id="run-review",
        details={
            "task": "review generated task plan",
            "steps": 1,
            "requires_human": True,
            "resume_mode": "manual",
            "timeline": [],
            "state": {
                "current_goal": "Review generated task plan",
                "orchestration_phase": "plan_review",
                "plan_review_status": "pending",
                "pending_decision": {
                    "decision_type": "plan_review",
                    "summary": "Review the generated task plan.",
                    "reason": "The plan touches an external account.",
                    "risk_level": "high",
                },
                "app_context": {
                    "plan_review_status": "pending",
                    "human_handoff_reason": "Review the generated task plan.",
                    "standard_recovery_kind": "requires_user",
                },
                "plan_health": {
                    "counts": {"total": 1, "completed": 0, "ready": 1},
                    "autonomy": {
                        "status": "review_required",
                        "can_continue": False,
                        "requires_review": True,
                        "next_action": "approve_plan",
                    },
                },
            },
            "execution_state": {
                "task_graph": {
                    "task": "review generated task plan",
                    "subgoals": [{"id": "subgoal_01", "title": "Review generated task plan"}],
                }
            },
        },
    )

    assert result["execution_state"]["orchestration_phase"] == "plan_review"
    assert result["execution_state"]["plan_review_status"] == "pending"
    assert result["execution_state"]["pending_decision"]["decision_type"] == "plan_review"
    assert result["execution_state"]["plan_health"]["autonomy"]["status"] == "review_required"
    assert "human_handoff_reason" not in result["execution_state"]["app_context"]
    assert "standard_recovery_kind" not in result["execution_state"]["app_context"]
    assert "manual_resume_status" not in result["execution_state"]["app_context"]


def test_resume_job_initial_result_marks_saved_step_approval_as_resumed():
    result = dashboard._build_resume_job_result(
        run_id="run-step-approval",
        details={
            "task": "continue the guarded action",
            "steps": 2,
            "timeline": [],
            "state": {
                "current_goal": "Click guarded confirm",
                "orchestration_phase": "awaiting_approval",
                "plan_health": {
                    "counts": {"total": 1, "completed": 0, "ready": 1},
                    "autonomy": {
                        "status": "review_required",
                        "can_continue": False,
                        "requires_review": True,
                        "requires_user": False,
                        "next_action": "approve_step",
                    },
                },
            },
            "execution_state": {
                "task_graph": {
                    "task": "continue the guarded action",
                    "subgoals": [{"id": "subgoal_01", "title": "Click guarded confirm"}],
                }
            },
        },
    )

    execution_state = result["execution_state"]

    assert execution_state["orchestration_phase"] == "stage_ready"
    assert execution_state["pending_decision"] is None
    assert execution_state["app_context"]["manual_resume_status"] == "resumed"
    assert execution_state["plan_health"]["autonomy"]["status"] == "ready"
    assert execution_state["plan_health"]["autonomy"]["can_continue"] is True
    assert execution_state["plan_health"]["autonomy"]["requires_review"] is False


def test_resume_job_initial_result_can_seed_plan_only_details():
    result = dashboard._build_resume_job_result(
        run_id="run-plan-only",
        details={
            "task": "continue a saved plan",
            "steps": 1,
            "timeline": [],
            "plan": {
                "task": "continue a saved plan",
                "subgoals": [
                    {"id": "subgoal_01", "title": "Recover the saved plan", "status": "pending"},
                ],
                "dependencies": {"subgoal_01": []},
            },
        },
    )

    assert result["run_id"] == "run-plan-only"
    assert result["latest_summary"] == "continue a saved plan"
    assert result["execution_state"]["task_graph"]["subgoals"][0]["title"] == "Recover the saved plan"


def test_details_can_resume_honors_backend_resume_flags():
    assert dashboard._details_can_resume({"completed": False, "can_resume": True}) is True
    assert dashboard._details_can_resume({"completed": "false", "can_resume": "true"}) is True
    assert dashboard._details_can_resume({"completed": "true", "can_resume": "true"}) is False
    assert dashboard._details_can_resume({"completed": False, "resume_mode": "manual"}) is True
    assert (
        dashboard._details_can_resume(
            {
                "completed": False,
                "cancelled": True,
                "execution_state": {"task_graph": {"subgoals": [{"id": "subgoal_01"}]}},
            }
        )
        is True
    )
    assert (
        dashboard._details_can_resume(
            {
                "completed": False,
                "can_resume": False,
                "requires_human": True,
                "execution_state": {"task_graph": {"subgoals": [{"id": "subgoal_01"}]}},
            }
        )
        is False
    )
    assert (
        dashboard._details_can_resume(
            {
                "completed": "false",
                "can_resume": "false",
                "requires_human": "true",
                "execution_state": {"task_graph": {"subgoals": [{"id": "subgoal_01"}]}},
            }
        )
        is False
    )
    assert (
        dashboard._details_can_resume(
            {
                "completed": "false",
                "requires_human": "false",
                "plan": {"subgoals": [{"id": "subgoal_01"}]},
            }
        )
        is True
    )


def test_task_queue_resume_accepts_legacy_interruption_marker(monkeypatch, tmp_path):
    run_root = tmp_path / "runs"
    run_dir = run_root / "legacy-human-run"
    run_dir.mkdir(parents=True)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(f'run_root: "{run_root.as_posix()}"\n', encoding="utf-8")
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "task": "finish the legacy login flow",
                "completed": False,
                "steps": 2,
                "requires_human": False,
                "interruption_kind": "login",
                "interruption_reason": "A login prompt needs user input.",
            }
        ),
        encoding="utf-8",
    )
    queue = TaskQueue(config_path=config_path)
    run_started = threading.Event()

    def _resume_task(*args, **kwargs):
        run_started.set()
        return AgentRunResult(
            task="finish the legacy login flow",
            completed=False,
            steps=2,
            run_dir=run_dir,
            started_at=10.0,
            finished_at=11.0,
            error="stopped after resume assertion",
        )

    monkeypatch.setattr(dashboard, "resume_task", _resume_task)

    job = queue.resume(run_id="legacy-human-run")

    assert job.resume_run_id == "legacy-human-run"
    assert run_started.wait(timeout=3)
    deadline = time.time() + 3
    while queue.active_job_id is not None and time.time() < deadline:
        time.sleep(0.01)
    assert queue.jobs[job.job_id].status == "failed"


def test_task_queue_resume_accepts_execution_state_handoff_context(monkeypatch, tmp_path):
    run_root = tmp_path / "runs"
    run_dir = run_root / "state-handoff-run"
    run_dir.mkdir(parents=True)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(f'run_root: "{run_root.as_posix()}"\n', encoding="utf-8")
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "task": "finish the state login flow",
                "completed": False,
                "steps": 2,
                "requires_human": False,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "execution_state.json").write_text(
        json.dumps(
            {
                "orchestration_phase": "awaiting_user",
                "app_context": {
                    "human_handoff_kind": "login",
                    "human_handoff_reason": "A login prompt needs user input.",
                    "standard_recovery_kind": "requires_user",
                },
            }
        ),
        encoding="utf-8",
    )
    queue = TaskQueue(config_path=config_path)
    run_started = threading.Event()

    def _resume_task(*args, **kwargs):
        run_started.set()
        return AgentRunResult(
            task="finish the state login flow",
            completed=False,
            steps=2,
            run_dir=run_dir,
            started_at=10.0,
            finished_at=11.0,
            error="stopped after resume assertion",
        )

    monkeypatch.setattr(dashboard, "resume_task", _resume_task)

    job = queue.resume(run_id="state-handoff-run")

    assert job.resume_run_id == "state-handoff-run"
    assert run_started.wait(timeout=3)
    deadline = time.time() + 3
    while queue.active_job_id is not None and time.time() < deadline:
        time.sleep(0.01)
    assert queue.jobs[job.job_id].status == "failed"


def test_task_queue_resume_accepts_failed_run_with_saved_execution_state(monkeypatch, tmp_path):
    run_root = tmp_path / "runs"
    run_dir = run_root / "failed-graph-run"
    run_dir.mkdir(parents=True)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(f'run_root: "{run_root.as_posix()}"\n', encoding="utf-8")
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "task": "recover the blocked checkout",
                "completed": False,
                "steps": 4,
                "requires_human": False,
                "error": "Subgoal became stuck after repeated failed attempts.",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "execution_state.json").write_text(
        json.dumps(
            {
                "task": "recover the blocked checkout",
                "run_id": "failed-graph-run",
                "task_graph": {
                    "task": "recover the blocked checkout",
                    "subgoals": [
                        {
                            "id": "subgoal_01",
                            "title": "Recover blocked checkout",
                            "status": "blocked",
                            "attempts": 3,
                            "max_attempts": 3,
                        },
                        {"id": "subgoal_02", "title": "Finish checkout", "status": "pending"},
                    ],
                    "dependencies": {"subgoal_01": [], "subgoal_02": []},
                },
                "failure_budget": {"subgoal_01": 0, "subgoal_02": 2},
                "app_context": {"pending_repair": {"subgoal_id": "subgoal_02", "failure_kind": "blocked_by_ui"}},
            }
        ),
        encoding="utf-8",
    )
    queue = TaskQueue(config_path=config_path)
    run_started = threading.Event()
    captured_kwargs: dict[str, object] = {}

    def _resume_task(*args, **kwargs):
        captured_kwargs.update(kwargs)
        run_started.set()
        return AgentRunResult(
            task="recover the blocked checkout",
            completed=False,
            steps=4,
            run_dir=run_dir,
            started_at=10.0,
            finished_at=11.0,
            error="stopped after failed-state resume assertion",
        )

    monkeypatch.setattr(dashboard, "resume_task", _resume_task)

    job = queue.resume(
        run_id="failed-graph-run",
        max_steps=7,
        pause_after_action=0.25,
        config_overrides={"max_run_seconds": 30},
    )

    assert job.resume_run_id == "failed-graph-run"
    assert job.max_steps == 7
    assert job.pause_after_action == 0.25
    assert job.max_run_seconds == 30
    assert job.to_dict()["max_run_seconds"] == 30
    assert job.result["execution_state"]["task_graph"]["subgoals"][0]["id"] == "subgoal_01"
    assert run_started.wait(timeout=3)
    assert captured_kwargs["max_steps"] == 7
    assert captured_kwargs["pause_after_action"] == 0.25
    assert captured_kwargs["config_overrides"] == {"max_run_seconds": 30}
    deadline = time.time() + 3
    while queue.active_job_id is not None and time.time() < deadline:
        time.sleep(0.01)
    assert queue.jobs[job.job_id].status == "failed"


def test_task_queue_resume_buffers_seeded_pending_review_decision(monkeypatch, tmp_path):
    run_root = tmp_path / "runs"
    run_dir = run_root / "pending-review-run"
    run_dir.mkdir(parents=True)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(f'run_root: "{run_root.as_posix()}"\n', encoding="utf-8")
    pending_decision = {
        "decision_type": "plan_review",
        "summary": "Review the saved plan before continuing.",
    }
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "task": "continue a saved review",
                "completed": False,
                "steps": 2,
                "requires_human": "true",
                "resume_mode": "manual",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "execution_state.json").write_text(
        json.dumps(
            {
                "task": "continue a saved review",
                "run_id": "pending-review-run",
                "orchestration_phase": "plan_review",
                "pending_decision": pending_decision,
                "plan_review_status": "pending",
                "app_context": {
                    "plan_review_status": "pending",
                    "human_handoff_kind": "requires_user",
                    "standard_recovery_kind": "requires_user",
                },
                "plan_health": {
                    "autonomy": {
                        "status": "review_required",
                        "can_continue": False,
                        "requires_review": True,
                    }
                },
                "task_graph": {
                    "task": "continue a saved review",
                    "subgoals": [{"id": "subgoal_01", "title": "Review saved plan", "status": "pending"}],
                    "dependencies": {"subgoal_01": []},
                },
            }
        ),
        encoding="utf-8",
    )
    queue = TaskQueue(config_path=config_path)
    run_started = threading.Event()
    release_review_wait = threading.Event()
    responses: list[dict[str, object]] = []

    def _resume_task(*args, **kwargs):
        run_started.set()
        release_review_wait.wait(timeout=3)
        response = kwargs["decision_callback"](
            {
                "execution_state": {
                    "orchestration_phase": "plan_review",
                    "pending_decision": pending_decision,
                    "plan_review_status": "pending",
                    "app_context": {"plan_review_status": "pending"},
                },
            }
        )
        responses.append(response)
        return AgentRunResult(
            task="continue a saved review",
            completed=True,
            steps=3,
            run_dir=run_dir,
            started_at=10.0,
            finished_at=12.0,
            execution_budget={
                "max_steps": 8,
                "max_run_seconds": 180,
                "pause_after_action": 0.2,
                "desktop_autonomy_mode": "autonomous",
                "approval_policy": "autonomous",
                "recoverable_error_retry_limit": 4,
            },
            execution_environment={
                "browser_control_mode": "hybrid",
                "browser_dom_backend": "playwright",
                "browser_headless": False,
                "shell_recipe_policy": "approval_required",
            },
            execution_state={
                "orchestration_phase": "complete",
                "plan_review_status": "approved",
                "app_context": {"plan_review_status": "approved"},
            },
        )

    monkeypatch.setattr(dashboard, "resume_task", _resume_task)

    job = queue.resume(run_id="pending-review-run")

    try:
        assert job.status == "approval"
        assert queue.active_job()["status"] == "approval"
        assert queue.pending_decisions[job.job_id] == pending_decision
        assert job.result["pending_decision"] == pending_decision
        assert job.result["execution_state"]["pending_decision"] == pending_decision
        assert "manual_resume_status" not in job.result["execution_state"]["app_context"]
        assert run_started.wait(timeout=3)

        decided = queue.decide(job.job_id, decision="approve", note="Looks good.")
        assert decided["status"] == "running"
        assert decided["result"].get("pending_decision") is None
        release_review_wait.set()

        deadline = time.time() + 3
        while queue.active_job_id is not None and time.time() < deadline:
            time.sleep(0.01)

        assert responses == [{"decision": "approve", "note": "Looks good."}]
        assert queue.jobs[job.job_id].status == "completed"
        assert queue.jobs[job.job_id].result["execution_budget"]["desktop_autonomy_mode"] == "autonomous"
        assert queue.jobs[job.job_id].result["execution_budget"]["max_run_seconds"] == 180
        assert queue.jobs[job.job_id].result["execution_environment"]["browser_control_mode"] == "hybrid"
        assert queue.jobs[job.job_id].result["execution_environment"]["shell_recipe_policy"] == "approval_required"
        assert queue.jobs[job.job_id].result["execution_state"]["plan_review_status"] == "approved"
    finally:
        release_review_wait.set()
        deadline = time.time() + 3
        while queue.active_job_id is not None and time.time() < deadline:
            active = queue.jobs.get(job.job_id)
            if active is not None and active.status == "approval":
                try:
                    queue.decide(job.job_id, decision="approve", note="cleanup")
                except RuntimeError:
                    pass
            time.sleep(0.01)


def test_task_queue_submit_records_effective_runtime_budget(monkeypatch, tmp_path):
    run_root = tmp_path / "runs"
    run_dir = run_root / "budget-run"
    run_dir.mkdir(parents=True)
    config_path = tmp_path / "config.yaml"
    config_path.write_text("{}", encoding="utf-8")
    queue = TaskQueue(config_path=config_path)
    captured_kwargs: dict[str, object] = {}
    run_started = threading.Event()

    def _run_task(*args, **kwargs):
        captured_kwargs.update(kwargs)
        run_started.set()
        return AgentRunResult(
            task="open calculator",
            completed=True,
            steps=1,
            run_dir=run_dir,
            started_at=10.0,
            finished_at=11.0,
        )

    monkeypatch.setattr(dashboard, "run_task", _run_task)

    job = queue.submit(
        task="open calculator",
        planner_mode=None,
        dry_run=False,
        max_steps=None,
        pause_after_action=None,
        config_overrides={"max_steps": 5, "pause_after_action": 0.3, "max_run_seconds": 180},
    )

    assert job.max_steps == 5
    assert job.pause_after_action == 0.3
    assert job.max_run_seconds == 180
    assert job.to_dict()["max_run_seconds"] == 180
    assert run_started.wait(timeout=3)
    assert captured_kwargs["max_steps"] == 5
    assert captured_kwargs["pause_after_action"] == 0.3
    assert captured_kwargs["config_overrides"] == {"max_steps": 5, "pause_after_action": 0.3, "max_run_seconds": 180}


def test_task_queue_resume_rejects_failed_run_without_saved_state(tmp_path):
    run_root = tmp_path / "runs"
    run_dir = run_root / "failed-no-state-run"
    run_dir.mkdir(parents=True)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(f'run_root: "{run_root.as_posix()}"\n', encoding="utf-8")
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "task": "failed without a saved plan",
                "completed": False,
                "steps": 1,
                "requires_human": False,
                "error": "A generic failure happened before planning.",
            }
        ),
        encoding="utf-8",
    )
    queue = TaskQueue(config_path=config_path)

    with pytest.raises(RuntimeError, match="no saved execution state"):
        queue.resume(run_id="failed-no-state-run")


def test_task_queue_final_result_preserves_latest_progress_and_execution_state(monkeypatch, tmp_path):
    queue = TaskQueue(config_path=None)
    job = DashboardJob(
        job_id="job-final-state",
        task="finish a planned task",
        planner_mode="auto",
        dry_run=False,
        max_steps=6,
        pause_after_action=0.1,
        status="running",
        started_at=10.0,
        result={
            "run_id": "run-final-state",
            "latest_summary": "Executing the last planned step.",
            "latest_screenshot": "step_01.png",
        },
    )
    queue.jobs[job.job_id] = job
    queue.cancel_events[job.job_id] = threading.Event()
    queue.decision_events[job.job_id] = threading.Event()
    queue.active_job_id = job.job_id
    run_dir = tmp_path / "run-final-state"
    run_dir.mkdir()

    def _run_task(*args, **kwargs):
        return AgentRunResult(
            task="finish a planned task",
            completed=True,
            steps=2,
            run_dir=run_dir,
            started_at=10.0,
            finished_at=20.0,
            execution_state={
                "orchestration_phase": "complete",
                "plan_health": {
                    "counts": {"total": 2, "completed": 2, "ready": 0},
                    "next_subgoal_id": None,
                },
            },
        )

    monkeypatch.setattr(dashboard, "run_task", _run_task)

    queue._run_job(job.job_id)

    assert job.status == "completed"
    assert job.result["latest_summary"] == "Executing the last planned step."
    assert job.result["latest_screenshot"] == "step_01.png"
    assert job.result["execution_state"]["orchestration_phase"] == "complete"
    assert job.result["execution_state"]["plan_health"]["counts"]["completed"] == 2
    assert queue.active_job_id is None


def test_task_queue_final_result_replaces_stale_live_planning_state(monkeypatch, tmp_path):
    queue = TaskQueue(config_path=None)
    job = DashboardJob(
        job_id="job-final-clears-stale-state",
        task="finish after review",
        planner_mode="auto",
        dry_run=False,
        max_steps=6,
        pause_after_action=0.1,
        status="approval",
        started_at=10.0,
        result={
            "run_id": "run-final-clears-stale-state",
            "latest_summary": "Waiting for plan review.",
            "pending_decision": {"decision_type": "plan_review", "summary": "Review stale plan."},
            "plan_review_status": "pending",
            "current_goal": "Review stale plan",
            "step_proposal": {"intent": "review stale plan", "capability": "browser_dom"},
            "verification": {"status": "failed", "message": "Old verification."},
            "state": {
                "orchestration_phase": "plan_review",
                "pending_decision": {"decision_type": "plan_review"},
                "plan_review_status": "pending",
                "last_step": {"intent": "review stale plan", "capability": "browser_dom"},
            },
            "execution_state": {
                "orchestration_phase": "plan_review",
                "pending_decision": {"decision_type": "plan_review"},
                "plan_review_status": "pending",
                "last_step": {"intent": "review stale plan", "capability": "browser_dom"},
            },
        },
    )
    queue.jobs[job.job_id] = job
    queue.cancel_events[job.job_id] = threading.Event()
    queue.decision_events[job.job_id] = threading.Event()
    queue.pending_decisions[job.job_id] = {"decision_type": "plan_review"}
    queue.active_job_id = job.job_id
    run_dir = tmp_path / "run-final-clears-stale-state"
    run_dir.mkdir()

    def _run_task(*args, **kwargs):
        return AgentRunResult(
            task="finish after review",
            completed=True,
            steps=3,
            run_dir=run_dir,
            started_at=10.0,
            finished_at=22.0,
            execution_state={
                "orchestration_phase": "complete",
                "current_goal": "Verify final result",
                "plan_review_status": "approved",
                "chosen_capability": "shell",
                "verification_status": "success",
                "plan_health": {
                    "counts": {"total": 2, "completed": 2, "ready": 0},
                    "autonomy": {
                        "status": "complete",
                        "can_continue": False,
                        "requires_review": False,
                    },
                },
                "last_step": {"intent": "verify final result", "capability": "shell"},
                "last_verification": {"status": "success", "message": "Final result verified."},
                "app_context": {"plan_review_status": "approved"},
            },
        )

    monkeypatch.setattr(dashboard, "run_task", _run_task)

    queue._run_job(job.job_id)

    assert job.status == "completed"
    assert job.result["latest_summary"] == "Waiting for plan review."
    assert job.result.get("pending_decision") is None
    assert job.result["execution_state"].get("pending_decision") is None
    assert job.result["state"].get("pending_decision") is None
    assert job.result["plan_review_status"] == "approved"
    assert job.result["current_goal"] == "Verify final result"
    assert job.result["step_proposal"]["intent"] == "verify final result"
    assert job.result["verification"]["status"] == "success"
    assert queue.pending_decisions.get(job.job_id) is None
    assert queue.active_job_id is None


def test_task_queue_failed_runner_clears_stale_pending_review_state(monkeypatch):
    queue = TaskQueue(config_path=None)
    job = DashboardJob(
        job_id="job-failed-clears-review",
        task="fail after review progress",
        planner_mode="auto",
        dry_run=False,
        max_steps=6,
        pause_after_action=0.1,
        status="running",
    )
    queue.jobs[job.job_id] = job
    queue.cancel_events[job.job_id] = threading.Event()
    queue.decision_events[job.job_id] = threading.Event()
    queue.active_job_id = job.job_id

    def _run_task(*args, **kwargs):
        kwargs["progress_callback"](
            {
                "run_id": "run-failed-clears-review",
                "latest_summary": "Waiting for plan review.",
                "pending_decision": {"decision_type": "plan_review", "summary": "Review generated plan."},
                "execution_state": {
                    "orchestration_phase": "plan_review",
                    "pending_decision": {"decision_type": "plan_review"},
                    "plan_review_status": "pending",
                    "app_context": {"plan_review_status": "pending"},
                    "plan_health": {
                        "autonomy": {
                            "status": "review_required",
                            "can_continue": False,
                            "requires_review": True,
                            "blockers": [],
                        },
                    },
                },
            }
        )
        raise RuntimeError("planner crashed after review progress")

    monkeypatch.setattr(dashboard, "run_task", _run_task)

    queue._run_job(job.job_id)

    assert job.status == "failed"
    assert job.error == "planner crashed after review progress"
    assert job.requires_human is False
    assert job.result["latest_summary"] == "Waiting for plan review."
    assert job.result["error"] == "planner crashed after review progress"
    assert job.result.get("pending_decision") is None
    assert job.result["execution_state"].get("pending_decision") is None
    assert job.result["execution_state"]["orchestration_phase"] == "blocked"
    assert job.result["execution_state"]["plan_review_status"] == "failed"
    assert job.result["execution_state"]["app_context"]["plan_review_status"] == "failed"
    autonomy = job.result["execution_state"]["plan_health"]["autonomy"]
    assert autonomy["status"] == "blocked"
    assert autonomy["requires_review"] is False
    assert autonomy["next_action"] == "inspect_failure"
    assert "planner crashed after review progress" in autonomy["blockers"]
    assert queue.pending_decisions.get(job.job_id) is None
    assert queue.active_job_id is None


def test_task_queue_failed_result_clears_stale_pending_review_state(monkeypatch, tmp_path):
    queue = TaskQueue(config_path=None)
    job = DashboardJob(
        job_id="job-failed-result-clears-review",
        task="fail after stale review state",
        planner_mode="auto",
        dry_run=False,
        max_steps=6,
        pause_after_action=0.1,
        status="approval",
        result={
            "pending_decision": {"decision_type": "plan_review", "summary": "Review stale plan."},
            "execution_state": {
                "pending_decision": {"decision_type": "plan_review"},
                "plan_review_status": "pending",
            },
        },
    )
    queue.jobs[job.job_id] = job
    queue.cancel_events[job.job_id] = threading.Event()
    queue.decision_events[job.job_id] = threading.Event()
    queue.pending_decisions[job.job_id] = {"decision_type": "plan_review"}
    queue.active_job_id = job.job_id
    run_dir = tmp_path / "run-failed-result-clears-review"
    run_dir.mkdir()

    def _run_task(*args, **kwargs):
        return AgentRunResult(
            task="fail after stale review state",
            completed=False,
            steps=2,
            run_dir=run_dir,
            started_at=10.0,
            finished_at=12.0,
            error="planner returned failure",
            requires_human=False,
            execution_state={
                "orchestration_phase": "failed",
                "pending_decision": {"decision_type": "plan_review"},
                "plan_review_status": "pending",
            },
        )

    monkeypatch.setattr(dashboard, "run_task", _run_task)

    queue._run_job(job.job_id)

    assert job.status == "failed"
    assert job.requires_human is False
    assert job.result["error"] == "planner returned failure"
    assert job.result.get("pending_decision") is None
    assert job.result["execution_state"].get("pending_decision") is None
    assert (job.result.get("state") or {}).get("pending_decision") is None
    assert queue.pending_decisions.get(job.job_id) is None
    assert queue.active_job_id is None


def test_dashboard_job_decision_route_releases_approval_wait():
    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)
    job = DashboardJob(
        job_id="job-approval-route",
        task="review generated plan",
        planner_mode="auto",
        dry_run=False,
        max_steps=3,
        pause_after_action=0.1,
        status="approval",
        result={
            "pending_decision": {"decision_type": "plan_review"},
            "execution_state": {
                "orchestration_phase": "plan_review",
                "pending_decision": {"decision_type": "plan_review"},
                "app_context": {"plan_review_status": "pending"},
                "plan_health": {
                    "autonomy": {
                        "status": "review_required",
                        "can_continue": False,
                        "requires_review": True,
                        "next_action": "approve_plan",
                        "blockers": ["The generated plan is waiting for review before execution starts."],
                    }
                },
            },
        },
    )
    app.queue.jobs[job.job_id] = job
    app.queue.active_job_id = job.job_id
    app.queue.decision_events[job.job_id] = threading.Event()
    app.queue.pending_decisions[job.job_id] = {
        "decision_type": "plan_review",
        "summary": "Review the task plan.",
    }
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/jobs/{job.job_id}/decision",
            data=json.dumps({"decision": "approve", "note": "Looks good."}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 202

        assert payload["id"] == job.job_id
        assert payload["status"] == "running"
        assert payload["result"].get("pending_decision") is None
        assert payload["result"]["execution_state"].get("pending_decision") is None
        assert payload["result"]["execution_state"]["orchestration_phase"] == "stage_ready"
        assert payload["result"]["execution_state"]["app_context"]["plan_review_status"] == "approved"
        assert payload["result"]["execution_state"]["plan_health"]["autonomy"]["status"] == "ready"
        assert payload["result"]["execution_state"]["plan_health"]["autonomy"]["can_continue"] is True
        assert payload["result"]["execution_state"]["plan_health"]["autonomy"]["requires_review"] is False
        assert app.queue.pending_decisions.get(job.job_id) is None
        assert app.queue.decision_responses[job.job_id] == {"decision": "approve", "note": "Looks good."}
        assert app.queue.decision_events[job.job_id].is_set() is True
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_previews_task_plan_without_queueing(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "complex_task_planning: heuristic",
                "max_task_subgoals: 4",
                "max_steps: 6",
                "max_run_seconds: 120",
                "pause_after_action: 0.25",
                "run_root: runs",
            ]
        ),
        encoding="utf-8",
    )
    app = DashboardApp(host="127.0.0.1", port=0, config_path=config_path)

    payload = app.preview_task(
        task="open calculator then wait 1 seconds",
        config_overrides={"max_task_subgoals": "3"},
    )

    assert payload["task"] == "open calculator then wait 1 seconds"
    assert payload["task_graph"]["task"] == payload["task"]
    assert len(payload["task_graph"]["subgoals"]) >= 1
    assert payload["plan_health"]["counts"]["total"] == len(payload["task_graph"]["subgoals"])
    assert payload["execution_budget"] == {
        "task_graph_request_timeout": 30.0,
        "max_steps": 6,
        "max_run_seconds": 120.0,
        "pause_after_action": 0.25,
        "desktop_autonomy_mode": "conservative",
        "approval_policy": "tiered",
        "complex_task_planning": "heuristic",
        "plan_review_policy": "low_risk_auto",
        "max_task_subgoals": 3,
        "max_subgoal_retries": 2,
        "stage_review_policy": "risk_change",
        "max_replans_per_run": 3,
        "max_failures_per_subgoal": 3,
        "replan_on_recoverable_error": True,
        "recoverable_error_retry_limit": 2,
    }
    assert payload["execution_environment"] == {
        "browser_control_mode": "hybrid",
        "browser_dom_backend": "playwright",
        "browser_dom_timeout": 4.0,
        "browser_headless": False,
        "browser_channel": "msedge",
        "browser_executable_path": None,
        "cursor_motion_enabled": False,
        "cursor_motion_duration": 0.12,
        "display_override_enabled": False,
        "display_override_monitor_device_name": None,
        "display_override_dpi_scale": None,
        "display_override_work_area_left": None,
        "display_override_work_area_top": None,
        "display_override_work_area_width": None,
        "display_override_work_area_height": None,
        "generic_app_launch_enabled": True,
        "shell_recipe_policy": "approval_required",
    }
    assert payload["plan_health"]["next_subgoal_id"]
    if payload["requires_review"]:
        assert payload["plan_health"]["autonomy"]["status"] == "review_required"
        assert payload["plan_health"]["autonomy"]["can_continue"] is False
    else:
        assert payload["plan_health"]["autonomy"]["status"] == "ready"
        assert payload["plan_health"]["autonomy"]["can_continue"] is True
    assert payload["risk_level"] in {"low", "medium", "high", "critical"}
    assert isinstance(payload["task_graph_signature"], str)
    assert len(payload["task_graph_signature"]) == 64
    assert app.queue.list_jobs(limit=5) == []


def test_dashboard_preview_task_route_returns_plan_health(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "complex_task_planning: heuristic",
                "max_task_subgoals: 4",
                "run_root: runs",
            ]
        ),
        encoding="utf-8",
    )
    app = DashboardApp(host="127.0.0.1", port=0, config_path=config_path)
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/tasks/preview",
            data=json.dumps(
                {
                    "task": "visit example.com and summarize the page",
                    "config_overrides": {"max_task_subgoals": "2", "max_steps": "9", "max_run_seconds": "240", "pause_after_action": "0.35"},
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 200

        assert payload["task"] == "visit example.com and summarize the page"
        assert len(payload["task_graph"]["subgoals"]) <= 2
        assert isinstance(payload["task_graph_signature"], str)
        assert payload["plan_health"]["counts"]["total"] == len(payload["task_graph"]["subgoals"])
        assert payload["summary"]["plan_health"]["next_subgoal_id"] == payload["plan_health"]["next_subgoal_id"]
        assert payload["summary"]["plan_health"]["autonomy"] == payload["plan_health"]["autonomy"]
        assert payload["can_start"] is True
        assert payload["start_blocker"] is None
        assert payload["execution_budget"]["max_steps"] == 9
        assert payload["execution_budget"]["max_run_seconds"] == 240.0
        assert payload["execution_budget"]["pause_after_action"] == 0.35
        assert payload["execution_budget"]["complex_task_planning"] == "heuristic"
        assert payload["execution_budget"]["max_task_subgoals"] == 2
        assert payload["execution_budget"]["max_replans_per_run"] == 3
        assert payload["execution_budget"]["replan_on_recoverable_error"] is True
        assert payload["execution_environment"]["browser_control_mode"] == "hybrid"
        assert payload["execution_environment"]["browser_dom_backend"] == "playwright"
        assert payload["execution_environment"]["browser_dom_timeout"] == 4.0
        assert payload["execution_environment"]["cursor_motion_enabled"] is False
        assert payload["execution_environment"]["display_override_enabled"] is False
        assert app.queue.list_jobs(limit=5) == []
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_preview_task_reports_clarification_autonomy(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "complex_task_planning: heuristic",
                "run_root: runs",
            ]
        ),
        encoding="utf-8",
    )
    app = DashboardApp(host="127.0.0.1", port=0, config_path=config_path)

    payload = app.preview_task(task="do it", config_overrides={})

    autonomy = payload["plan_health"]["autonomy"]
    assert payload["requires_review"] is False
    assert payload["can_start"] is False
    assert payload["start_blocker"] == "Wait for the user to clarify the intended goal before automation continues."
    assert payload["task_graph"]["subgoals"][0]["goal_type"] == "clarify"
    assert autonomy["status"] == "needs_clarification"
    assert autonomy["next_action"] == "ask_user"
    assert autonomy["can_continue"] is False
    assert autonomy["requires_user"] is True
    assert autonomy["blockers"] == ["Wait for the user to clarify the intended goal before automation continues."]


def test_dashboard_task_route_rejects_clarification_preview_graph(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "complex_task_planning: heuristic",
                "run_root: runs",
            ]
        ),
        encoding="utf-8",
    )
    app = DashboardApp(host="127.0.0.1", port=0, config_path=config_path)
    preview = app.preview_task(task="do it", config_overrides={})
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/tasks",
            data=json.dumps(
                {
                    "task": "do it",
                    "task_graph": preview["task_graph"],
                    "task_graph_signature": preview["task_graph_signature"],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(request)
        assert exc_info.value.code == 400
        payload = json.loads(exc_info.value.read().decode("utf-8"))
        assert "clarify" in payload["error"]
        assert app.queue.list_jobs(limit=5) == []
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_preview_plan_review_matches_execution_policy(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "complex_task_planning: heuristic",
                "plan_review_policy: always",
                "run_root: runs",
            ]
        ),
        encoding="utf-8",
    )
    app = DashboardApp(host="127.0.0.1", port=0, config_path=config_path)

    payload = app.preview_task(task="open calculator", config_overrides={})

    assert payload["requires_review"] is True
    assert payload["can_start"] is True
    assert payload["start_blocker"] is None
    assert payload["plan_health"]["autonomy"]["status"] == "review_required"
    assert payload["plan_health"]["autonomy"]["next_action"] == "approve_plan"
    assert payload["plan_health"]["autonomy"]["can_continue"] is False


def test_dashboard_task_route_accepts_matching_preview_task_graph(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "complex_task_planning: heuristic",
                "max_task_subgoals: 4",
                "run_root: runs",
            ]
        ),
        encoding="utf-8",
    )
    app = DashboardApp(host="127.0.0.1", port=0, config_path=config_path)
    captured: dict[str, object] = {}
    task_graph = app.preview_task(
        task="open calculator then wait 1 seconds",
        config_overrides={},
    )

    def _submit(**kwargs):
        captured.update(kwargs)
        return DashboardJob(
            job_id="job-preview",
            task=kwargs["task"],
            planner_mode=kwargs.get("planner_mode") or "auto",
            dry_run=bool(kwargs.get("dry_run")),
            max_steps=kwargs.get("max_steps"),
            pause_after_action=kwargs.get("pause_after_action"),
            config_overrides=dict(kwargs.get("config_overrides") or {}),
            initial_task_graph=kwargs.get("initial_task_graph"),
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
                    "task": "open calculator then wait 1 seconds",
                    "task_graph": task_graph["task_graph"],
                    "task_graph_signature": task_graph["task_graph_signature"],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 202

        assert payload["id"] == "job-preview"
        assert captured["initial_task_graph"]["task"] == "open calculator then wait 1 seconds"
        assert captured["initial_task_graph"]["subgoals"]
        assert all(item["status"] == "pending" for item in captured["initial_task_graph"]["subgoals"])
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_task_route_accepts_reviewed_preview_as_plan_approval(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "complex_task_planning: heuristic",
                "plan_review_policy: always",
                "max_task_subgoals: 4",
                "run_root: runs",
            ]
        ),
        encoding="utf-8",
    )
    app = DashboardApp(host="127.0.0.1", port=0, config_path=config_path)
    captured: dict[str, object] = {}
    preview = app.preview_task(
        task="open calculator then wait 1 seconds",
        config_overrides={},
    )

    def _submit(**kwargs):
        captured.update(kwargs)
        return DashboardJob(
            job_id="job-reviewed-preview",
            task=kwargs["task"],
            planner_mode=kwargs.get("planner_mode") or "auto",
            dry_run=bool(kwargs.get("dry_run")),
            max_steps=kwargs.get("max_steps"),
            pause_after_action=kwargs.get("pause_after_action"),
            config_overrides=dict(kwargs.get("config_overrides") or {}),
            initial_task_graph=kwargs.get("initial_task_graph"),
            initial_plan_review_status=kwargs.get("initial_plan_review_status"),
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
                    "task": "open calculator then wait 1 seconds",
                    "task_graph": preview["task_graph"],
                    "task_graph_signature": preview["task_graph_signature"],
                    "task_graph_review_status": "approved",
                    "task_graph_review_signature": preview["task_graph_signature"],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 202

        assert payload["id"] == "job-reviewed-preview"
        assert payload["initial_plan_review_status"] == "approved"
        assert captured["initial_plan_review_status"] == "approved"
        assert captured["initial_task_graph"]["task"] == "open calculator then wait 1 seconds"
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_task_route_rejects_review_status_when_preview_does_not_require_review(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "complex_task_planning: heuristic",
                "plan_review_policy: never",
                "max_task_subgoals: 4",
                "run_root: runs",
            ]
        ),
        encoding="utf-8",
    )
    app = DashboardApp(host="127.0.0.1", port=0, config_path=config_path)
    preview = app.preview_task(
        task="open calculator then wait 1 seconds",
        config_overrides={},
    )
    assert preview["requires_review"] is False
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/tasks",
            data=json.dumps(
                {
                    "task": "open calculator then wait 1 seconds",
                    "task_graph": preview["task_graph"],
                    "task_graph_signature": preview["task_graph_signature"],
                    "task_graph_review_status": "approved",
                    "task_graph_review_signature": preview["task_graph_signature"],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(request)
        assert exc_info.value.code == 400
        payload = json.loads(exc_info.value.read().decode("utf-8"))
        assert "review policy" in payload["error"]
        assert app.queue.list_jobs(limit=5) == []
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_task_route_accepts_preview_graph_with_matching_run_limit(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "complex_task_planning: heuristic",
                "max_task_subgoals: 4",
                "run_root: runs",
            ]
        ),
        encoding="utf-8",
    )
    app = DashboardApp(host="127.0.0.1", port=0, config_path=config_path)
    captured: dict[str, object] = {}
    task_graph = app.preview_task(
        task="open calculator then wait 1 seconds",
        config_overrides={"max_run_seconds": "42"},
    )

    def _submit(**kwargs):
        captured.update(kwargs)
        return DashboardJob(
            job_id="job-preview-run-limit",
            task=kwargs["task"],
            planner_mode=kwargs.get("planner_mode") or "auto",
            dry_run=bool(kwargs.get("dry_run")),
            max_steps=kwargs.get("max_steps"),
            pause_after_action=kwargs.get("pause_after_action"),
            config_overrides=dict(kwargs.get("config_overrides") or {}),
            initial_task_graph=kwargs.get("initial_task_graph"),
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
                    "task": "open calculator then wait 1 seconds",
                    "task_graph": task_graph["task_graph"],
                    "task_graph_signature": task_graph["task_graph_signature"],
                    "config_overrides": {"max_run_seconds": "42"},
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 202

        assert payload["id"] == "job-preview-run-limit"
        assert captured["config_overrides"]["max_run_seconds"] == 42.0
        assert captured["initial_task_graph"]["task"] == "open calculator then wait 1 seconds"
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_task_route_rejects_stale_preview_task_graph_signature(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("complex_task_planning: heuristic\nmax_task_subgoals: 4\n", encoding="utf-8")
    app = DashboardApp(host="127.0.0.1", port=0, config_path=config_path)
    preview = app.preview_task(
        task="open calculator then wait 1 seconds",
        config_overrides={"plan_review_policy": "never"},
    )
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/tasks",
            data=json.dumps(
                {
                    "task": "open calculator then wait 1 seconds",
                    "task_graph": preview["task_graph"],
                    "task_graph_signature": preview["task_graph_signature"],
                    "config_overrides": {"plan_review_policy": "always"},
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(request)
        assert exc_info.value.code == 400
        payload = json.loads(exc_info.value.read().decode("utf-8"))
        assert "signature" in payload["error"]
        assert app.queue.list_jobs(limit=5) == []
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_task_route_rejects_stale_preview_review_signature(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("complex_task_planning: heuristic\nmax_task_subgoals: 4\n", encoding="utf-8")
    app = DashboardApp(host="127.0.0.1", port=0, config_path=config_path)
    preview = app.preview_task(task="open calculator then wait 1 seconds", config_overrides={})
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/tasks",
            data=json.dumps(
                {
                    "task": "open calculator then wait 1 seconds",
                    "task_graph": preview["task_graph"],
                    "task_graph_signature": preview["task_graph_signature"],
                    "task_graph_review_status": "approved",
                    "task_graph_review_signature": "stale-review-signature",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(request)
        assert exc_info.value.code == 400
        payload = json.loads(exc_info.value.read().decode("utf-8"))
        assert "review signature" in payload["error"]
        assert app.queue.list_jobs(limit=5) == []
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_task_route_rejects_preview_signature_after_config_file_change(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "complex_task_planning: heuristic\nmax_task_subgoals: 4\nplan_review_policy: never\n",
        encoding="utf-8",
    )
    app = DashboardApp(host="127.0.0.1", port=0, config_path=config_path)
    preview = app.preview_task(task="open calculator then wait 1 seconds", config_overrides={})
    config_path.write_text(
        "complex_task_planning: heuristic\nmax_task_subgoals: 4\nplan_review_policy: always\n",
        encoding="utf-8",
    )
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/tasks",
            data=json.dumps(
                {
                    "task": "open calculator then wait 1 seconds",
                    "task_graph": preview["task_graph"],
                    "task_graph_signature": preview["task_graph_signature"],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(request)
        assert exc_info.value.code == 400
        payload = json.loads(exc_info.value.read().decode("utf-8"))
        assert "signature" in payload["error"]
        assert app.queue.list_jobs(limit=5) == []
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_task_route_rejects_preview_signature_after_runtime_budget_file_change(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "complex_task_planning: heuristic",
                "max_task_subgoals: 4",
                "max_steps: 6",
                "max_run_seconds: 120",
                "pause_after_action: 0.25",
                "plan_review_policy: never",
            ]
        ),
        encoding="utf-8",
    )
    app = DashboardApp(host="127.0.0.1", port=0, config_path=config_path)
    preview = app.preview_task(task="open calculator then wait 1 seconds", config_overrides={})
    config_path.write_text(
        "\n".join(
            [
                "complex_task_planning: heuristic",
                "max_task_subgoals: 4",
                "max_steps: 6",
                "max_run_seconds: 240",
                "pause_after_action: 0.25",
                "plan_review_policy: never",
            ]
        ),
        encoding="utf-8",
    )
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/tasks",
            data=json.dumps(
                {
                    "task": "open calculator then wait 1 seconds",
                    "task_graph": preview["task_graph"],
                    "task_graph_signature": preview["task_graph_signature"],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(request)
        assert exc_info.value.code == 400
        payload = json.loads(exc_info.value.read().decode("utf-8"))
        assert "signature" in payload["error"]
        assert app.queue.list_jobs(limit=5) == []
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_task_route_rejects_preview_signature_after_execution_environment_file_change(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "complex_task_planning: heuristic",
                "max_task_subgoals: 4",
                "plan_review_policy: never",
                "browser_control_mode: hybrid",
                "browser_dom_backend: playwright",
                "browser_dom_timeout: 4",
                "browser_headless: false",
                "browser_channel: msedge",
                "cursor_motion_enabled: false",
                "cursor_motion_duration: 0.12",
                "display_override_enabled: false",
                "generic_app_launch_enabled: true",
            ]
        ),
        encoding="utf-8",
    )
    app = DashboardApp(host="127.0.0.1", port=0, config_path=config_path)
    preview = app.preview_task(task="open calculator then wait 1 seconds", config_overrides={})
    config_path.write_text(
        "\n".join(
            [
                "complex_task_planning: heuristic",
                "max_task_subgoals: 4",
                "plan_review_policy: never",
                "browser_control_mode: hybrid",
                "browser_dom_backend: playwright",
                "browser_dom_timeout: 12",
                "browser_headless: true",
                "browser_channel: chrome",
                "cursor_motion_enabled: true",
                "cursor_motion_duration: 0.35",
                "display_override_enabled: true",
                "display_override_monitor_device_name: DISPLAY2",
                "display_override_dpi_scale: 1.5",
                "display_override_work_area_left: 2000",
                "display_override_work_area_top: 20",
                "display_override_work_area_width: 1600",
                "display_override_work_area_height: 900",
                "generic_app_launch_enabled: false",
            ]
        ),
        encoding="utf-8",
    )
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/tasks",
            data=json.dumps(
                {
                    "task": "open calculator then wait 1 seconds",
                    "task_graph": preview["task_graph"],
                    "task_graph_signature": preview["task_graph_signature"],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(request)
        assert exc_info.value.code == 400
        payload = json.loads(exc_info.value.read().decode("utf-8"))
        assert "signature" in payload["error"]
        assert app.queue.list_jobs(limit=5) == []
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_task_route_rejects_preview_task_graph_without_signature(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("complex_task_planning: heuristic\nmax_task_subgoals: 4\n", encoding="utf-8")
    app = DashboardApp(host="127.0.0.1", port=0, config_path=config_path)
    preview = app.preview_task(task="open calculator then wait 1 seconds", config_overrides={})
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/tasks",
            data=json.dumps(
                {
                    "task": "open calculator then wait 1 seconds",
                    "task_graph": preview["task_graph"],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(request)
        assert exc_info.value.code == 400
        payload = json.loads(exc_info.value.read().decode("utf-8"))
        assert "signature" in payload["error"]
        assert app.queue.list_jobs(limit=5) == []
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_task_route_rejects_mismatched_preview_task_graph(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("complex_task_planning: heuristic\nmax_task_subgoals: 4\n", encoding="utf-8")
    app = DashboardApp(host="127.0.0.1", port=0, config_path=config_path)
    task_graph = app.preview_task(task="open calculator", config_overrides={})["task_graph"]
    server = app.create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/tasks",
            data=json.dumps({"task": "open notepad", "task_graph": task_graph}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(request)
        assert exc_info.value.code == 400
        payload = json.loads(exc_info.value.read().decode("utf-8"))
        assert "does not match" in payload["error"]
        assert app.queue.list_jobs(limit=5) == []
    finally:
        server.shutdown()
        server.server_close()


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
    assert 'id="cursorMotionEnabled"' in index_html
    assert 'id="cursorMotionDuration"' in index_html
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
    hydrate_section = app_js[app_js.find("function hydrateDefaults()") : app_js.find("function ensureSelectedRun")]
    overview_signature_section = app_js[
        app_js.find("function summarizeOverviewJob") : app_js.find("function summarizeOverviewRun")
    ]
    assert 'loadAuthSession({ silent: true })' not in dom_ready_section
    assert "renderAuthGate();" not in render_section
    assert "scheduleRuntimePreferencesSync();" not in hydrate_section
    assert 'updated_at: job.status === "running" ? null' in overview_signature_section
    assert "summarizeOverviewAction" in overview_signature_section


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
                    "task_graph_request_timeout": "18",
                    "max_steps": "9",
                    "max_run_seconds": "240",
                    "pause_after_action": "0.35",
                    "desktop_autonomy_mode": "autonomous",
                    "max_task_subgoals": "14",
                    "max_replans_per_run": "4",
                    "approval_policy": "autonomous",
                    "replan_on_recoverable_error": False,
                    "recoverable_error_retry_limit": "6",
                    "cursor_motion_enabled": False,
                    "cursor_motion_duration": 0.35,
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
                "task_graph_request_timeout": 18.0,
                "max_steps": 9,
                "max_run_seconds": 240.0,
                "pause_after_action": 0.35,
                "desktop_autonomy_mode": "autonomous",
                "max_task_subgoals": 14,
                "max_replans_per_run": 4,
                "approval_policy": "autonomous",
                "replan_on_recoverable_error": False,
                "recoverable_error_retry_limit": 6,
                "cursor_motion_enabled": False,
                "cursor_motion_duration": 0.35,
                "browser_headless": True,
            }
            assert snapshot["ui_preferences"]["onboarding_completed"] is True

        with urllib.request.urlopen(f"{base_url}/api/runtime-preferences") as response:
            persisted = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert persisted["config_overrides"]["model_provider"] == "openai_compatible"
            assert persisted["config_overrides"]["model_api_key"] == "secret"
            assert persisted["config_overrides"]["task_graph_request_timeout"] == 18.0
            assert persisted["config_overrides"]["max_steps"] == 9
            assert persisted["config_overrides"]["max_run_seconds"] == 240.0
            assert persisted["config_overrides"]["pause_after_action"] == 0.35
            assert persisted["config_overrides"]["desktop_autonomy_mode"] == "autonomous"
            assert persisted["config_overrides"]["max_task_subgoals"] == 14
            assert persisted["config_overrides"]["max_replans_per_run"] == 4
            assert persisted["config_overrides"]["approval_policy"] == "autonomous"
            assert persisted["config_overrides"]["replan_on_recoverable_error"] is False
            assert persisted["config_overrides"]["recoverable_error_retry_limit"] == 6
            assert persisted["config_overrides"]["cursor_motion_enabled"] is False
            assert persisted["config_overrides"]["cursor_motion_duration"] == 0.35
            assert persisted["ui_preferences"]["onboarding_completed"] is True
            assert isinstance(persisted["updated_at"], float)
    finally:
        server.shutdown()
        server.server_close()
        shutil.rmtree(temp_root, ignore_errors=True)


def test_dashboard_ui_preferences_parse_string_booleans():
    assert dashboard._clean_ui_preferences({"onboarding_completed": "false"})["onboarding_completed"] is False
    assert dashboard._clean_ui_preferences({"onboarding_completed": "true"})["onboarding_completed"] is True
    assert (
        dashboard._clean_ui_preferences(
            {"onboarding_completed": "false"},
            existing={"onboarding_completed": True},
        )["onboarding_completed"]
        is False
    )
    assert (
        dashboard._clean_ui_preferences(
            {"onboarding_completed": "not-a-bool"},
            existing={"onboarding_completed": True},
        )["onboarding_completed"]
        is True
    )


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
            "max_steps": 5,
            "max_run_seconds": 180,
            "pause_after_action": 0.3,
            "desktop_autonomy_mode": "review_first",
            "approval_policy": "strict",
            "replan_on_recoverable_error": False,
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
                    "max_steps": "8",
                    "pause_after_action": "0.2",
                    "config_overrides": {
                        "model_base_url": " https://override.example.com/v1 ",
                        "desktop_autonomy_mode": "autonomous",
                        "approval_policy": "autonomous",
                        "recoverable_error_retry_limit": "4",
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

        assert captured["max_steps"] == 8
        assert captured["pause_after_action"] == 0.2
        assert captured["config_overrides"] == {
            "model_provider": "openai_compatible",
            "model_base_url": "https://override.example.com/v1",
            "model_api_key": "runtime-secret",
            "max_steps": 5,
            "max_run_seconds": 180.0,
            "pause_after_action": 0.3,
            "desktop_autonomy_mode": "autonomous",
            "approval_policy": "autonomous",
            "replan_on_recoverable_error": False,
            "recoverable_error_retry_limit": 4,
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
            max_steps=kwargs.get("max_steps"),
            pause_after_action=kwargs.get("pause_after_action"),
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
                    "max_steps": "8",
                    "pause_after_action": "0.2",
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
        assert captured["max_steps"] == 8
        assert captured["pause_after_action"] == 0.2
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
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
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


def test_dashboard_environment_check_computer_use_uses_openai_env_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-secret")
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
                "planner_mode": "computer_use",
                "model_provider": "lmstudio_local",
                "model_base_url": "http://127.0.0.1:1234/v1",
                "model_name": "gpt-5.5",
                "model_api_key": "",
                "model_auto_discover": False,
                "model_request_timeout": 15.0,
                "browser_dom_backend": "playwright",
                "browser_channel": "chrome",
                "browser_executable_path": "",
                "run_root": Path("runs"),
                "plugin_modules": [],
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
    calls: list[dict] = []

    def fake_environment_snapshot(*, provider, base_url, api_key, timeout):
        calls.append({"provider": provider, "base_url": base_url, "api_key": api_key, "timeout": timeout})
        return ProviderSnapshot(
            ok=True,
            provider=provider,
            api_base=base_url,
            root_base=base_url.removesuffix("/v1"),
            catalog_models=[ProviderModelEntry(model_id="gpt-5.5", label="gpt-5.5")],
            loaded_models=[],
        )

    app._environment_provider_snapshot = fake_environment_snapshot

    payload = app.environment_check()

    assert calls == [
        {
            "provider": "openai_api",
            "base_url": "https://api.openai.com/v1",
            "api_key": "env-secret",
            "timeout": 15.0,
        }
    ]
    computer_use_item = next(item for item in payload["items"] if item["id"] == "computer_use_api")
    assert computer_use_item["status"] == "Ready"
    assert "local model discovery is skipped" in computer_use_item["detail"]


def test_dashboard_environment_check_reports_loaded_plugins(monkeypatch):
    module = types.ModuleType("aoryn_dashboard_test_plugin")

    class _DashboardPluginDriver:
        name = "dashboard_test_driver"

        def matches(self, world_model):
            return False

    class _DashboardPluginCapability:
        name = "dashboard_test_capability"

    def register_plugin(context):
        context.register_driver(_DashboardPluginDriver())
        context.register_capability(_DashboardPluginCapability())

    module.register_plugin = register_plugin
    monkeypatch.setitem(sys.modules, module.__name__, module)
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
                "planner_mode": "auto",
                "model_provider": "",
                "model_base_url": "",
                "model_name": "auto",
                "model_api_key": "",
                "model_auto_discover": True,
                "model_request_timeout": 15.0,
                "browser_dom_backend": "playwright",
                "browser_channel": "chrome",
                "browser_executable_path": "",
                "run_root": Path("runs"),
                "plugin_modules": [module.__name__],
                "plugin_fail_fast": False,
                "enabled_capabilities": [],
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

    payload = DashboardApp(host="127.0.0.1", port=0, config_path=None).environment_check()

    plugin_item = next(item for item in payload["items"] if item["id"] == "software_plugins")
    assert plugin_item["status"] == "Ready"
    assert "1 capability adapter" in plugin_item["detail"]
    assert "1 app driver" in plugin_item["detail"]


def test_dashboard_environment_check_uses_background_provider_cache(monkeypatch):
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
                "model_provider": "lmstudio_local",
                "model_base_url": "http://127.0.0.1:1234/v1",
                "model_name": "auto",
                "model_api_key": "",
                "model_auto_discover": True,
                "model_request_timeout": 90.0,
                "browser_dom_backend": "playwright",
                "browser_channel": "msedge",
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
                    {"status": "auto", "warnings": [], "editable": True},
                )(),
            },
        )(),
    )
    provider_checked = threading.Event()
    calls: list[float] = []

    def fake_fetch_provider_snapshot(*, provider, base_url, api_key, timeout):
        calls.append(timeout)
        provider_checked.set()
        return ProviderSnapshot(
            ok=False,
            provider=provider,
            api_base=base_url,
            root_base=base_url.removesuffix("/v1"),
            loaded_models=[],
            catalog_models=[],
            error="LM Studio offline",
        )

    monkeypatch.setattr(dashboard, "fetch_provider_snapshot", fake_fetch_provider_snapshot)
    app = DashboardApp(host="127.0.0.1", port=0, config_path=None)

    first_payload = app.environment_check()
    first_connection = next(item for item in first_payload["items"] if item["id"] == "provider_connection")

    assert first_connection["status"] == "Needs setup"
    assert "background" in first_connection["detail"]
    assert provider_checked.wait(1.0)

    second_connection = first_connection
    for _ in range(20):
        second_payload = app.environment_check()
        second_connection = next(item for item in second_payload["items"] if item["id"] == "provider_connection")
        if second_connection["detail"] == "LM Studio offline":
            break
        time.sleep(0.01)

    assert second_connection["status"] == "Connection failed"
    assert second_connection["detail"] == "LM Studio offline"
    assert len(calls) == 1
    assert calls[0] == pytest.approx(0.9)
    app.environment_check()
    assert len(calls) == 1


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
