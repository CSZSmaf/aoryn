from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

from desktop_agent.runtime_paths import default_run_root


@dataclass(slots=True)
class AgentConfig:
    planner_mode: str = "auto"
    dry_run: bool = True
    max_steps: int = 12
    pause_after_action: float = 0.4
    max_text_length: int = 200
    max_browser_target_length: int = 512
    max_wait_seconds: float = 10.0
    max_scroll_amount: int = 1200
    primary_model_profile: str = "openai_api:best_available"
    fallback_model_profile: str = "lmstudio_local:auto"
    model_provider: str = "lmstudio_local"
    model_base_url: str = "http://127.0.0.1:1234/v1"
    model_name: str = "auto"
    model_api_key: str | None = None
    model_request_timeout: float = 90.0
    model_auto_discover: bool = True
    model_structured_output: str = "auto"
    default_surface_policy: str = "current_user_desktop"
    managed_browser_enabled: bool = True
    external_browser_attach_enabled: bool = True
    safe_mode_enabled: bool = False
    user_input_preemption_policy: str = "pause_and_resume"
    browser_runtime_transport: str = "local_http"
    browser_profile_strategy: str = "separate_managed_profile"
    managed_browser_host: str = "127.0.0.1"
    managed_browser_port: int = 38991
    browser_control_mode: str = "hybrid"
    browser_dom_backend: str = "playwright"
    browser_dom_timeout: float = 8.0
    browser_headless: bool = False
    browser_channel: str | None = "msedge"
    browser_executable_path: str | None = None
    screenshot_format: str = "png"
    window_display_mode: str = "workarea_maximized"
    desktop_autonomy_mode: str = "conservative"
    window_conflict_policy: str = "minimize_first"
    window_match_timeout: float = 2.5
    screen_target_policy: str = "foreground_window_monitor"
    approval_policy: str = "tiered"
    max_subgoal_retries: int = 2
    enabled_capabilities: list[str] = field(
        default_factory=lambda: [
            "browser_dom",
            "windows_uia",
            "desktop_gui",
            "filesystem",
            "clipboard",
            "office_com",
            "guarded_shell_recipe",
        ]
    )
    driver_preferences: list[str] = field(default_factory=list)
    shell_recipe_policy: str = "approval_required"
    shell_recipe_registry: dict[str, list[str]] = field(
        default_factory=lambda: {
            "python_env_bootstrap": ["python", "-m", "venv", ".venv"],
            "pip_install": ["python", "-m", "pip", "install"],
        }
    )
    display_override_enabled: bool = False
    display_override_monitor_device_name: str | None = None
    display_override_dpi_scale: float | None = None
    display_override_work_area_left: int | None = None
    display_override_work_area_top: int | None = None
    display_override_work_area_width: int | None = None
    display_override_work_area_height: int | None = None
    generic_app_launch_enabled: bool = True
    replan_on_recoverable_error: bool = True
    recoverable_error_retry_limit: int = 2
    run_root: Path = field(default_factory=default_run_root)
    browser_search_url: str = "https://www.google.com/search?q={query}"
    app_launch_map: dict[str, str] = field(
        default_factory=lambda: {
            "notepad": "notepad.exe",
            "calculator": "calc.exe",
            "explorer": "explorer.exe",
            "browser": "msedge.exe",
        }
    )
    allowed_apps: list[str] = field(
        default_factory=lambda: ["notepad", "calculator", "explorer", "browser"]
    )
    blocked_app_launch_terms: list[str] = field(
        default_factory=lambda: [
            "cmd",
            "powershell",
            "terminal",
            "wt",
            "pwsh",
            "bash",
            "python",
            "node",
            "wscript",
            "cscript",
            "regedit",
            "registry",
            "diskpart",
            "disk management",
            "compmgmt",
            "mmc",
        ]
    )
    allowed_hotkeys: list[list[str]] = field(
        default_factory=lambda: [
            ["win", "r"],
            ["ctrl", "l"],
            ["ctrl", "t"],
            ["ctrl", "a"],
            ["ctrl", "c"],
            ["ctrl", "v"],
            ["alt", "tab"],
        ]
    )
    allowed_browser_schemes: list[str] = field(default_factory=lambda: ["http", "https"])

    @classmethod
    def from_yaml(cls, path: str | Path | None) -> "AgentConfig":
        if path is None:
            return cls()
        import yaml

        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentConfig":
        payload = dict(data)
        if "run_root" in payload and payload["run_root"]:
            payload["run_root"] = Path(payload["run_root"])
        return cls(**payload)

    def hotkey_set(self) -> set[tuple[str, ...]]:
        return {tuple(key.lower() for key in combo) for combo in self.allowed_hotkeys}

    def build_browser_search_url(self, query: str) -> str:
        return self.browser_search_url.format(query=quote_plus(query.strip()))

    def normalize_browser_url(self, target: str) -> str:
        cleaned = target.strip()
        parsed = urlparse(cleaned)
        if parsed.scheme:
            return cleaned
        return f"https://{cleaned}"
