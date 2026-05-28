from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_dev_start():
    module_path = Path("scripts") / "dev_start.py"
    spec = importlib.util.spec_from_file_location("dev_start_under_test", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_dev_start_default_plan_includes_source_agent_and_browser(tmp_path):
    dev_start = _load_dev_start()

    plan = dev_start.build_launch_plan(dev_start.parse_args([]), project_root=tmp_path)

    assert Path(plan.dashboard_command[1]).name == "run_agent.py"
    assert Path(plan.browser_command[1]).name == "run_browser.py"
    assert plan.dashboard_command[2:5] == ["ui", "--host", "127.0.0.1"]
    assert plan.dashboard_url == "http://127.0.0.1:8766"
    assert "--profile-root" in plan.browser_command
    assert str(tmp_path / ".tmp" / "source-test" / "browser-profile") in plan.browser_command
    assert "--config" in plan.dashboard_command
    assert "--config-path" in plan.browser_command
    assert plan.config_path == tmp_path / ".tmp" / "source-test" / "config.yaml"
    assert "managed_browser_port: 38992" in plan.config_path.read_text(encoding="utf-8")


def test_dev_start_web_mode_uses_dashboard_only_flags(tmp_path):
    dev_start = _load_dev_start()

    args = dev_start.parse_args(["--ui", "web", "--no-browser-tab", "--port", "9000"])
    plan = dev_start.build_launch_plan(args, project_root=tmp_path)

    assert "--browser" in plan.dashboard_command
    assert "--no-browser" in plan.dashboard_command
    assert plan.dashboard_url == "http://127.0.0.1:9000"


def test_dev_start_no_managed_browser_skips_browser_command(tmp_path):
    dev_start = _load_dev_start()

    args = dev_start.parse_args(["--no-managed-browser"])
    plan = dev_start.build_launch_plan(args, project_root=tmp_path)

    assert plan.browser_command is None


def test_dev_start_print_commands_does_not_create_process(monkeypatch, tmp_path, capsys):
    dev_start = _load_dev_start()

    def fail_start(*args, **kwargs):
        raise AssertionError("print-commands must not start subprocesses")

    def fail_probe(*args, **kwargs):
        raise AssertionError("print-commands must not require live port probes")

    monkeypatch.setattr(dev_start, "_start_process", fail_start)
    monkeypatch.setattr(dev_start, "_probe_dashboard_port", fail_probe)

    assert dev_start.run(["--print-commands"], project_root=tmp_path) == 0

    output = capsys.readouterr().out
    assert "run_agent.py" in output
    assert "run_browser.py" in output


def test_dev_start_reuses_existing_aoryn_dashboard(monkeypatch, tmp_path, capsys):
    dev_start = _load_dev_start()

    monkeypatch.setattr(dev_start, "_probe_dashboard_port", lambda host, port: dev_start.PortProbe("aoryn"))
    monkeypatch.setattr(
        dev_start,
        "_start_process",
        lambda *args, **kwargs: pytest.fail("existing dashboard should be reused without starting subprocesses"),
    )

    assert dev_start.run([], project_root=tmp_path) == 0

    assert "Reusing existing Aoryn dashboard" in capsys.readouterr().out


def test_dev_start_dashboard_port_conflict_fails_before_launch(monkeypatch, tmp_path, capsys):
    dev_start = _load_dev_start()

    monkeypatch.setattr(
        dev_start,
        "_probe_dashboard_port",
        lambda host, port: dev_start.PortProbe("occupied", "not aoryn"),
    )
    monkeypatch.setattr(
        dev_start,
        "_start_process",
        lambda *args, **kwargs: pytest.fail("port conflict should stop before subprocess launch"),
    )

    assert dev_start.run([], project_root=tmp_path) == 2

    assert "Dashboard port 8766 is already in use" in capsys.readouterr().err


def test_dev_start_generated_config_preserves_user_config_and_overrides_dev_ports(tmp_path):
    dev_start = _load_dev_start()
    user_config = tmp_path / "config.yaml"
    user_config.write_text(
        "model_provider: openai_compatible\nmanaged_browser_port: 38991\n",
        encoding="utf-8",
    )

    args = dev_start.parse_args(["--managed-browser-port", "39010"])
    plan = dev_start.build_launch_plan(args, project_root=tmp_path)

    generated = plan.config_path.read_text(encoding="utf-8")
    assert "model_provider: openai_compatible" in generated
    assert "managed_browser_port: 39010" in generated


def test_dev_start_packaged_dashboard_on_port_is_not_reused(monkeypatch):
    dev_start = _load_dev_start()

    monkeypatch.setattr(dev_start, "_tcp_port_open", lambda host, port: True)
    monkeypatch.setattr(
        dev_start,
        "_read_json",
        lambda url, timeout=0.45: {"title": "Aoryn", "runtime_mode": "packaged"} if url.endswith("/api/meta") else {},
    )

    probe = dev_start._probe_dashboard_port("127.0.0.1", 8765)

    assert probe.is_occupied
    assert "packaged" in probe.detail
