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
    max_steps: int = 20
    max_run_seconds: float | None = None
    pause_after_action: float = 0.12
    cursor_motion_enabled: bool = False
    cursor_motion_duration: float = 0.12
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
    task_graph_request_timeout: float = 12.0
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
    browser_dom_timeout: float = 4.0
    browser_headless: bool = False
    browser_channel: str | None = "msedge"
    browser_executable_path: str | None = None
    screenshot_format: str = "png"
    window_display_mode: str = "workarea_maximized"
    desktop_autonomy_mode: str = "conservative"
    window_conflict_policy: str = "minimize_first"
    window_match_timeout: float = 1.5
    screen_target_policy: str = "foreground_window_monitor"
    approval_policy: str = "tiered"
    complex_task_planning: str = "hybrid"
    plan_review_policy: str = "low_risk_auto"
    max_task_subgoals: int = 12
    max_subgoal_retries: int = 2
    orchestrator_mode: str = "unified"
    stage_review_policy: str = "risk_change"
    task_workspace_enabled: bool = True
    max_replans_per_run: int = 3
    max_failures_per_subgoal: int = 3
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
            "paint": "mspaint.exe",
            "settings": "ms-settings:",
            "word": "winword.exe",
            "excel": "excel.exe",
            "powerpoint": "powerpnt.exe",
            "vscode": "code.exe",
        }
    )
    allowed_apps: list[str] = field(
        default_factory=lambda: [
            "notepad",
            "calculator",
            "explorer",
            "browser",
            "paint",
            "settings",
            "word",
            "excel",
            "powerpoint",
            "vscode",
        ]
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
            "终端",
            "命令提示符",
            "命令行",
            "注册表",
            "磁盘管理",
        ]
    )
    allowed_hotkeys: list[list[str]] = field(
        default_factory=lambda: [
            ["win", "r"],
            ["ctrl", "l"],
            ["ctrl", "t"],
            ["ctrl", "f"],
            ["ctrl", "a"],
            ["ctrl", "c"],
            ["ctrl", "v"],
            ["ctrl", "s"],
            ["alt", "tab"],
            ["alt", "f4"],
        ]
    )
    allowed_browser_schemes: list[str] = field(default_factory=lambda: ["http", "https"])

    def __post_init__(self) -> None:
        self.normalize()

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

    def normalize(self) -> None:
        self.cursor_motion_enabled = bool(self.cursor_motion_enabled)
        try:
            duration = float(self.cursor_motion_duration)
        except (TypeError, ValueError):
            duration = 0.12
        self.cursor_motion_duration = max(0.05, min(1.0, duration))
        self.pause_after_action = _clamped_float(self.pause_after_action, default=0.12, minimum=0.0, maximum=2.0)
        self.browser_dom_timeout = _clamped_float(self.browser_dom_timeout, default=4.0, minimum=0.5, maximum=30.0)
        self.max_wait_seconds = _clamped_float(self.max_wait_seconds, default=10.0, minimum=0.2, maximum=60.0)
        self.window_match_timeout = _clamped_float(self.window_match_timeout, default=1.5, minimum=0.2, maximum=15.0)
        self.model_request_timeout = _clamped_float(
            self.model_request_timeout,
            default=90.0,
            minimum=5.0,
            maximum=300.0,
        )
        self.task_graph_request_timeout = _clamped_float(
            self.task_graph_request_timeout,
            default=12.0,
            minimum=0.5,
            maximum=60.0,
        )
        if self.max_run_seconds is not None:
            try:
                run_seconds = float(self.max_run_seconds)
            except (TypeError, ValueError):
                run_seconds = 0.0
            self.max_run_seconds = max(0.0, run_seconds) or None
        planning_mode = str(self.complex_task_planning or "hybrid").strip().lower()
        self.complex_task_planning = planning_mode if planning_mode in {"off", "heuristic", "hybrid", "model"} else "hybrid"
        review_policy = str(self.plan_review_policy or "low_risk_auto").strip().lower()
        self.plan_review_policy = review_policy if review_policy in {"never", "low_risk_auto", "always"} else "low_risk_auto"
        orchestrator_mode = str(self.orchestrator_mode or "unified").strip().lower()
        self.orchestrator_mode = orchestrator_mode if orchestrator_mode in {"off", "unified"} else "unified"
        stage_review_policy = str(self.stage_review_policy or "risk_change").strip().lower()
        self.stage_review_policy = (
            stage_review_policy
            if stage_review_policy in {"never", "risk_change", "always"}
            else "risk_change"
        )
        self.task_workspace_enabled = bool(self.task_workspace_enabled)
        try:
            max_subgoals = int(self.max_task_subgoals)
        except (TypeError, ValueError):
            max_subgoals = 8
        self.max_task_subgoals = max(1, min(20, max_subgoals))
        try:
            max_replans = int(self.max_replans_per_run)
        except (TypeError, ValueError):
            max_replans = 2
        self.max_replans_per_run = max(0, min(10, max_replans))
        try:
            max_failures = int(self.max_failures_per_subgoal)
        except (TypeError, ValueError):
            max_failures = 3
        self.max_failures_per_subgoal = max(1, min(12, max_failures))

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


def _clamped_float(value: Any, *, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))
