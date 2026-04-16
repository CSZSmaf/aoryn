from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from pathlib import Path

from desktop_agent.version import APP_NAME


def is_frozen_runtime() -> bool:
    return bool(getattr(sys, "frozen", False))


def _roaming_base() -> Path:
    return Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))


def _local_base() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))


def appdata_config_root() -> Path:
    return _roaming_base() / APP_NAME


def local_data_root() -> Path:
    return _local_base() / APP_NAME


def _is_writable_directory(path: Path) -> bool:
    probe_name = f".runtime-path-write-test-{os.getpid()}"
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe_path = path / probe_name
        probe_path.write_text("ok", encoding="utf-8")
        probe_path.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _fallback_runtime_root(kind: str) -> Path:
    return Path(tempfile.gettempdir()) / "desktop-agent-workspace" / APP_NAME / kind


def _writable_packaged_root(preferred: Path, *, kind: str) -> Path:
    fallback = _fallback_runtime_root(kind)
    for candidate in (preferred, fallback):
        if _is_writable_directory(candidate):
            return candidate
    return fallback


def writable_appdata_config_root() -> Path:
    return _writable_packaged_root(appdata_config_root(), kind="roaming")


def writable_local_data_root() -> Path:
    return _writable_packaged_root(local_data_root(), kind="local")


def default_packaged_config_path() -> Path:
    return writable_appdata_config_root() / "config.yaml"


def default_packaged_runtime_preferences_path() -> Path:
    return writable_appdata_config_root() / "runtime-preferences.json"


def default_packaged_auth_session_path() -> Path:
    return writable_appdata_config_root() / "auth-session.json"


def default_packaged_run_root() -> Path:
    return writable_local_data_root() / "runs"


def default_packaged_cache_root() -> Path:
    return writable_local_data_root() / "cache"


def default_run_root() -> Path:
    if is_frozen_runtime():
        return default_packaged_run_root()
    return Path("runs")


def default_cache_root() -> Path:
    if is_frozen_runtime():
        return default_packaged_cache_root()
    return Path(tempfile.gettempdir()) / "desktop-agent-workspace" / "cache"


def discover_default_config_path() -> Path | None:
    if is_frozen_runtime():
        preferred_path = appdata_config_root() / "config.yaml"
        if preferred_path.exists():
            return preferred_path
        packaged_path = default_packaged_config_path()
        return packaged_path if packaged_path.exists() else None
    default_path = Path("config.yaml")
    return default_path if default_path.exists() else None


def runtime_preferences_path_for(config_path: Path | None) -> Path:
    if is_frozen_runtime():
        return default_packaged_runtime_preferences_path()

    key_source = str(config_path.resolve()) if isinstance(config_path, Path) else "default"
    digest = hashlib.sha1(key_source.encode("utf-8")).hexdigest()[:10]
    root = Path(tempfile.gettempdir()) / "desktop-agent-workspace"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"runtime-preferences-{digest}.json"


def auth_session_path_for(config_path: Path | None) -> Path:
    if is_frozen_runtime():
        return default_packaged_auth_session_path()

    key_source = str(config_path.resolve()) if isinstance(config_path, Path) else "default"
    digest = hashlib.sha1(key_source.encode("utf-8")).hexdigest()[:10]
    root = Path(tempfile.gettempdir()) / "desktop-agent-workspace"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"auth-session-{digest}.json"
