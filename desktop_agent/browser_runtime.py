from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from desktop_agent.config import AgentConfig
from desktop_agent.runtime_paths import local_data_root
from desktop_agent.version import APP_BROWSER_NAME, browser_executable_name, browser_install_dir_name


class BrowserRuntimeError(RuntimeError):
    """Raised when the managed browser runtime cannot satisfy a request."""


@dataclass(slots=True)
class BrowserObservation:
    runtime: str = "aoryn_browser"
    status: str = "unknown"
    url: str | None = None
    title: str | None = None
    text: str | None = None
    active_tab_id: str | None = None
    current_internal_page: str | None = None
    auth_pause_reason: str | None = None
    tab_count: int = 0
    downloads: list[dict[str, Any]] = field(default_factory=list)
    bookmarks: list[dict[str, Any]] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    tabs: list[dict[str, Any]] = field(default_factory=list)
    annotations: list[dict[str, Any]] = field(default_factory=list)
    permissions: list[dict[str, Any]] = field(default_factory=list)
    permission_requests: list[dict[str, Any]] = field(default_factory=list)
    handoffs: list[dict[str, Any]] = field(default_factory=list)
    managed_by: str = "aoryn_browser"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BrowserObservation":
        return cls(
            runtime=str(payload.get("runtime", "aoryn_browser")).strip() or "aoryn_browser",
            status=str(payload.get("status", "unknown")).strip() or "unknown",
            url=_optional_str(payload.get("url")),
            title=_optional_str(payload.get("title")),
            text=_optional_str(payload.get("text")),
            active_tab_id=_optional_str(payload.get("active_tab_id")),
            current_internal_page=_optional_str(payload.get("current_internal_page")),
            auth_pause_reason=_optional_str(payload.get("auth_pause_reason")),
            tab_count=max(0, int(payload.get("tab_count", 0) or 0)),
            downloads=[dict(item) for item in payload.get("downloads", []) or [] if isinstance(item, dict)],
            bookmarks=[dict(item) for item in payload.get("bookmarks", []) or [] if isinstance(item, dict)],
            history=[dict(item) for item in payload.get("history", []) or [] if isinstance(item, dict)],
            tabs=[dict(item) for item in payload.get("tabs", []) or [] if isinstance(item, dict)],
            annotations=[dict(item) for item in payload.get("annotations", []) or [] if isinstance(item, dict)],
            permissions=[dict(item) for item in payload.get("permissions", []) or [] if isinstance(item, dict)],
            permission_requests=[dict(item) for item in payload.get("permission_requests", []) or [] if isinstance(item, dict)],
            handoffs=[dict(item) for item in payload.get("handoffs", []) or [] if isinstance(item, dict)],
            managed_by=str(payload.get("managed_by", "aoryn_browser")).strip() or "aoryn_browser",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime": self.runtime,
            "status": self.status,
            "url": self.url,
            "title": self.title,
            "text": self.text,
            "active_tab_id": self.active_tab_id,
            "current_internal_page": self.current_internal_page,
            "auth_pause_reason": self.auth_pause_reason,
            "tab_count": self.tab_count,
            "downloads": list(self.downloads),
            "bookmarks": list(self.bookmarks),
            "history": list(self.history),
            "tabs": list(self.tabs),
            "annotations": list(self.annotations),
            "permissions": list(self.permissions),
            "permission_requests": list(self.permission_requests),
            "handoffs": list(self.handoffs),
            "managed_by": self.managed_by,
        }


@dataclass(slots=True)
class BrowserAction:
    action: str
    selector: str | None = None
    value: str | None = None
    url: str | None = None
    tab_id: str | None = None
    path: str | None = None
    files: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "selector": self.selector,
            "value": self.value,
            "url": self.url,
            "tab_id": self.tab_id,
            "path": self.path,
            "files": list(self.files or []),
        }


class BrowserRuntimeBridge:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.base_url = self._resolve_base_url()
        self._process: subprocess.Popen | None = None

    def status(self) -> BrowserObservation | None:
        payload = self._request_json("GET", "/status", ensure_running=False)
        if not isinstance(payload, dict):
            return None
        return BrowserObservation.from_dict(payload)

    def open_window(self, url: str | None = None) -> dict[str, Any]:
        return self._request_json("POST", "/open_window", payload={"url": url} if url else {})

    def open_tab(self, url: str | None = None) -> dict[str, Any]:
        return self._request_json("POST", "/open_tab", payload={"url": url} if url else {})

    def open_internal_page(self, page: str) -> dict[str, Any]:
        return self._request_json("POST", "/open_internal_page", payload={"page": page})

    def switch_tab(self, tab_id: str) -> dict[str, Any]:
        return self._request_json("POST", "/switch_tab", payload={"tab_id": tab_id})

    def close_tab(self, tab_id: str | None = None) -> dict[str, Any]:
        return self._request_json("POST", "/close_tab", payload={"tab_id": tab_id})

    def navigate(self, url: str, *, tab_id: str | None = None) -> dict[str, Any]:
        return self._request_json("POST", "/navigate", payload={"url": url, "tab_id": tab_id})

    def query_dom(self, *, selector: str | None = None, include_text: bool = True) -> dict[str, Any]:
        payload = {"selector": selector, "include_text": include_text}
        return self._request_json("POST", "/query_dom", payload=payload)

    def query_accessibility(self) -> dict[str, Any]:
        return self._request_json("POST", "/query_accessibility", payload={})

    def annotate_page(
        self,
        *,
        selector: str | None = None,
        label: str | None = None,
        tab_id: str | None = None,
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/annotate_page",
            payload={"selector": selector, "label": label, "tab_id": tab_id},
        )

    def list_tabs(self) -> dict[str, Any]:
        return self._request_json("POST", "/list_tabs", payload={})

    def list_annotations(self, *, tab_id: str | None = None) -> dict[str, Any]:
        return self._request_json("POST", "/list_annotations", payload={"tab_id": tab_id})

    def clear_annotations(self, *, tab_id: str | None = None, annotation_id: str | None = None) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/clear_annotations",
            payload={"tab_id": tab_id, "annotation_id": annotation_id},
        )

    def perform_action(self, action: BrowserAction | dict[str, Any]) -> dict[str, Any]:
        payload = action.to_dict() if isinstance(action, BrowserAction) else dict(action)
        return self._request_json("POST", "/perform_action", payload=payload)

    def wait_for_state(
        self,
        *,
        selector: str | None = None,
        text: str | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/wait_for_state",
            payload={
                "selector": selector,
                "text": text,
                "timeout_seconds": timeout_seconds or self.config.browser_dom_timeout,
            },
        )

    def collect_downloads(self, *, state: str | None = None) -> dict[str, Any]:
        return self._request_json("POST", "/collect_downloads", payload={"state": state})

    def wait_for_download(self, *, state: str = "completed", timeout_seconds: float = 12.0) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/wait_for_download",
            payload={"state": state, "timeout_seconds": timeout_seconds},
        )

    def list_permissions(self) -> dict[str, Any]:
        return self._request_json("POST", "/list_permissions", payload={})

    def list_permission_requests(self) -> dict[str, Any]:
        return self._request_json("POST", "/list_permission_requests", payload={})

    def decide_permission(
        self,
        *,
        origin: str | None = None,
        feature: str | None = None,
        decision: str,
        request_id: str | None = None,
        remember: bool = True,
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/decide_permission",
            payload={
                "origin": origin,
                "feature": feature,
                "decision": decision,
                "request_id": request_id,
                "remember": remember,
            },
        )

    def bookmark_page(self) -> dict[str, Any]:
        return self._request_json("POST", "/bookmark_page", payload={})

    def pause_for_auth(self, *, reason: str | None = None) -> dict[str, Any]:
        return self._request_json("POST", "/pause_for_auth", payload={"reason": reason})

    def resume_after_auth(self) -> dict[str, Any]:
        return self._request_json("POST", "/resume_after_auth", payload={})

    def snapshot(self) -> dict[str, Any] | None:
        payload = self._request_json("GET", "/snapshot", ensure_running=False)
        if not isinstance(payload, dict):
            return None
        return payload

    def session_state(self) -> dict[str, Any]:
        return self._request_json("POST", "/get_session_state", payload={})

    def ensure_running(self) -> None:
        if self.status() is not None:
            return
        self._launch_process()
        deadline = time.time() + 12.0
        while time.time() < deadline:
            if self.status() is not None:
                return
            time.sleep(0.15)
        raise BrowserRuntimeError("Aoryn Browser did not become ready in time.")

    def _launch_process(self) -> None:
        command = self._resolve_launch_command()
        kwargs = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._process = subprocess.Popen(command, **kwargs)

    def _resolve_launch_command(self) -> list[str]:
        if getattr(sys, "frozen", False):
            exe_path = _resolve_installed_browser_executable()
            if exe_path is None:
                raise BrowserRuntimeError(
                    "Managed browser executable was not found. Install Aoryn Browser or place AorynBrowser.exe next to Aoryn.exe."
                )
            command = [str(exe_path)]
        else:
            browser_entry = Path(__file__).resolve().parents[1] / "run_browser.py"
            command = [sys.executable, str(browser_entry)]

        command.extend(
            [
                "--port",
                str(int(self.config.managed_browser_port)),
                "--profile-root",
                str(self._profile_root()),
            ]
        )
        return command

    def _profile_root(self) -> Path:
        strategy = str(getattr(self.config, "browser_profile_strategy", "separate_managed_profile")).strip().lower()
        base = local_data_root() if getattr(sys, "frozen", False) else Path(".tmp") / "browser-runtime"
        if strategy == "separate_managed_profile":
            return base / "browser-profile"
        return base / "browser-profile"

    def _resolve_base_url(self) -> str:
        if str(getattr(self.config, "browser_runtime_transport", "")).strip().lower() not in {"local_http", "local_ipc"}:
            raise BrowserRuntimeError("Only local_http/local_ipc browser runtime transport is currently supported.")
        host = str(getattr(self.config, "managed_browser_host", "127.0.0.1")).strip() or "127.0.0.1"
        port = int(getattr(self.config, "managed_browser_port", 38991) or 38991)
        return f"http://{host}:{port}"

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        ensure_running: bool = True,
    ) -> dict[str, Any] | None:
        if ensure_running:
            self.ensure_running()
        requests = _import_requests()
        url = self.base_url.rstrip("/") + path
        try:
            response = requests.request(
                method.upper(),
                url,
                json=payload,
                timeout=max(2.0, float(self.config.browser_dom_timeout or 0.0) + 2.0),
            )
        except requests.RequestException:
            if ensure_running:
                raise BrowserRuntimeError(f"Managed browser request failed: {method.upper()} {path}")
            return None
        if response.status_code >= 400:
            raise BrowserRuntimeError(
                f"Managed browser request failed with HTTP {response.status_code}: {response.text.strip() or '<empty>'}"
            )
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise BrowserRuntimeError(f"Managed browser returned invalid JSON for {path}.") from exc


def browser_runtime_status(config: AgentConfig) -> dict[str, Any]:
    bridge = BrowserRuntimeBridge(config)
    observation = bridge.status()
    if observation is None:
        return {"available": False, "detail": "Aoryn Browser is not running.", "base_url": bridge.base_url}
    return {
        "available": True,
        "detail": observation.status,
        "base_url": bridge.base_url,
        "observation": observation.to_dict(),
    }


def _import_requests():
    try:
        import requests  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
        raise BrowserRuntimeError("The requests package is required for the browser runtime bridge.") from exc
    return requests


def _resolve_installed_browser_executable() -> Path | None:
    adjacent = Path(sys.executable).resolve().with_name(browser_executable_name())
    if adjacent.exists():
        return adjacent

    for candidate in _installed_browser_candidates():
        if candidate.exists():
            return candidate
    return None


def _installed_browser_candidates() -> list[Path]:
    candidates: list[Path] = []

    registry_dir = _browser_registry_install_dir()
    if registry_dir is not None:
        candidates.append(registry_dir / browser_executable_name())

    local_appdata = Path(
        os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
    )
    candidates.append(local_appdata / "Programs" / browser_install_dir_name() / browser_executable_name())
    candidates.append(local_appdata / "Programs" / APP_BROWSER_NAME / browser_executable_name())
    return candidates


def _browser_registry_install_dir() -> Path | None:
    if not sys.platform.startswith("win"):
        return None

    try:
        import winreg
    except ImportError:
        return None

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Aoryn\BrowserInstaller") as key:
            install_dir, _ = winreg.QueryValueEx(key, "InstallDir")
    except OSError:
        return None

    normalized = str(install_dir or "").strip()
    if not normalized:
        return None
    return Path(normalized)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
