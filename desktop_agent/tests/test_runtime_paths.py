import shutil
from pathlib import Path
from uuid import uuid4

import desktop_agent.runtime_paths as runtime_paths


def test_packaged_runtime_uses_appdata_roots(monkeypatch):
    scratch_root = Path("test_artifacts") / f"runtime_paths_packaged_{uuid4().hex}"
    roaming = scratch_root / "Roaming"
    local = scratch_root / "Local"
    try:
        monkeypatch.setenv("APPDATA", str(roaming))
        monkeypatch.setenv("LOCALAPPDATA", str(local))
        monkeypatch.setattr(runtime_paths.sys, "frozen", True, raising=False)

        assert runtime_paths.default_packaged_config_path() == roaming / "Aoryn" / "config.yaml"
        assert runtime_paths.default_run_root() == local / "Aoryn" / "runs"
        assert runtime_paths.runtime_preferences_path_for(None) == roaming / "Aoryn" / "runtime-preferences.json"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_discover_default_config_path_reads_packaged_config(monkeypatch):
    scratch_root = Path("test_artifacts") / f"runtime_paths_config_{uuid4().hex}"
    roaming = scratch_root / "Roaming"
    local = scratch_root / "Local"
    config_path = roaming / "Aoryn" / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("max_steps: 9\n", encoding="utf-8")
    try:
        monkeypatch.setenv("APPDATA", str(roaming))
        monkeypatch.setenv("LOCALAPPDATA", str(local))
        monkeypatch.setattr(runtime_paths.sys, "frozen", True, raising=False)

        assert runtime_paths.discover_default_config_path() == config_path
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_development_runtime_keeps_project_relative_defaults(monkeypatch):
    scratch_root = Path("test_artifacts") / f"runtime_paths_dev_{uuid4().hex}"
    scratch_root.mkdir(parents=True, exist_ok=True)
    try:
        monkeypatch.setattr(runtime_paths.sys, "frozen", False, raising=False)
        monkeypatch.chdir(scratch_root)
        Path("config.yaml").write_text("max_steps: 4\n", encoding="utf-8")

        assert runtime_paths.default_run_root() == Path("runs")
        assert runtime_paths.discover_default_config_path() == Path("config.yaml")
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_packaged_runtime_falls_back_when_appdata_roots_are_not_writable(monkeypatch):
    scratch_root = Path("test_artifacts") / f"runtime_paths_fallback_{uuid4().hex}"
    roaming = scratch_root / "Roaming"
    local = scratch_root / "Local"
    temp_root = scratch_root / "Temp"

    try:
        monkeypatch.setenv("APPDATA", str(roaming))
        monkeypatch.setenv("LOCALAPPDATA", str(local))
        monkeypatch.setattr(runtime_paths.sys, "frozen", True, raising=False)
        monkeypatch.setattr(
            runtime_paths,
            "_fallback_runtime_root",
            lambda kind: temp_root / kind,
        )
        monkeypatch.setattr(
            runtime_paths,
            "_is_writable_directory",
            lambda path: str(path).startswith(str(temp_root)),
        )

        assert runtime_paths.default_packaged_config_path() == temp_root / "roaming" / "config.yaml"
        assert runtime_paths.default_packaged_runtime_preferences_path() == (
            temp_root / "roaming" / "runtime-preferences.json"
        )
        assert runtime_paths.default_run_root() == temp_root / "local" / "runs"
        assert runtime_paths.default_cache_root() == temp_root / "local" / "cache"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)
