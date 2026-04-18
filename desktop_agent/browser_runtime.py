from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from desktop_agent.config import AgentConfig
from desktop_agent.runtime_paths import local_data_root


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
    tab_count: int = 0
    downloads: list[dict[str, Any]] = field(default_factory=list)
    bookmarks: list[dict[str, Any]] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
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
            tab_count=max(0, int(payload.get("tab_count", 0) or 0)),
            downloads=[dict(item) for item in payload.get("downloads", []) or [] if isinstance(item, dict)],
            bookmarks=[dict(item) for item in payload.get("bookmarks", []) or [] if isinstance(item, dict)],
            history=[dict(item) for item in payload.get("history", []) or [] if isinstance(item, dict)],
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
            "tab_count": self.tab_count,
            "downloads": list(self.downloads),
            "bookmarks": list(self.bookmarks),
            "history": list(self.history),
            "managed_by": self.managed_by,
        }


@dataclass(slots=True)
class BrowserAction:
    action: str
    selector: str | None = None
    value: str | None = None
    url: str | None = None
    tab_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "selector": self.selector,
            "value": self.value,
            "url": self.url,
            "tab_id": self.tab_id,
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

    def navigate(self, url: str, *, tab_id: str | None = None) -> dict[str, Any]:
        return self._request_json("POST", "/navigate", payload={"url": url, "tab_id": tab_id})

    def query_dom(self, *, selector: str | None = None, include_text: bool = True) -> dict[str, Any]:
        payload = {"selector": selector, "include_text": include_text}
        return self._request_json("POST", "/query_dom", payload=payload)

    def query_accessibility(self) -> dict[str, Any]:
        return self._request_json("POST", "/query_accessibility", payload={})

    def annotate_page(self, *, selector: str | None = None, label: str | None = None) -> dict[str, Any]:
        return self._request_json("POST", "/annotate_page", payload={"selector": selector, "label": label})

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

    def collect_downloads(self) -> dict[str, Any]:
        return self._request_json("POST", "/collect_downloads", payload={})

    def bookmark_page(self) -> dict[str, Any]:
        return self._request_json("POST", "/bookmark_page", payload={})

    def pause_for_auth(self, *, reason: str | None = None) -> dict[str, Any]:
        return self._request_json("POST", "/pause_for_auth", payload={"reason": reason})

    def snapshot(self) -> dict[str, Any] | None:
        payload = self._request_json("GET", "/snapshot", ensure_running=False)
        if not isinstance(payload, dict):
            return None
        return payload

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
            exe_path = Path(sys.executable).resolve().with_name("AorynBrowser.exe")
            if not exe_path.exists():
                raise BrowserRuntimeError(f"Managed browser executable was not found: {exe_path}")
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


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
