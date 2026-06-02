from __future__ import annotations

from dataclasses import dataclass, field, fields as dataclass_fields
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

from desktop_agent.runtime_paths import default_run_root


_AUTONOMY_MODE_ALIASES = {
    "conservative": "conservative",
    "safe": "conservative",
    "default": "conservative",
    "standard": "conservative",
    "balanced": "conservative",
    "review-first": "review_first",
    "review_first": "review_first",
    "supervised": "review_first",
    "strict": "review_first",
    "autonomous": "autonomous",
    "aggressive": "autonomous",
    "high-autonomy": "autonomous",
    "high_autonomy": "autonomous",
    "auto": "autonomous",
}

_AUTONOMY_MODE_PRESETS = {
    "conservative": {
        "plan_review_policy": "low_risk_auto",
        "approval_policy": "tiered",
        "stage_review_policy": "risk_change",
        "replan_on_recoverable_error": True,
        "recoverable_error_retry_limit": 2,
        "max_replans_per_run": 3,
        "max_failures_per_subgoal": 3,
    },
    "review_first": {
        "plan_review_policy": "always",
        "approval_policy": "strict",
        "stage_review_policy": "always",
        "replan_on_recoverable_error": True,
        "recoverable_error_retry_limit": 1,
        "max_replans_per_run": 2,
        "max_failures_per_subgoal": 2,
    },
    "autonomous": {
        "plan_review_policy": "never",
        "approval_policy": "autonomous",
        "stage_review_policy": "never",
        "replan_on_recoverable_error": True,
        "recoverable_error_retry_limit": 4,
        "max_replans_per_run": 5,
        "max_failures_per_subgoal": 5,
    },
}

def desktop_autonomy_mode_presets() -> dict[str, dict[str, Any]]:
    return {key: dict(value) for key, value in _AUTONOMY_MODE_PRESETS.items()}


_TRUE_STRING_VALUES = {"1", "true", "t", "yes", "y", "on"}
_FALSE_STRING_VALUES = {"0", "false", "f", "no", "n", "off"}


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
    max_document_length: int = 20000
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
    task_graph_request_timeout: float = 30.0
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
    shell_start_mode: str = "main"
    desktop_autonomy_mode: str = "conservative"
    window_conflict_policy: str = "minimize_first"
    window_match_timeout: float = 1.5
    screen_target_policy: str = "foreground_window_monitor"
    approval_policy: str = "tiered"
    complex_task_planning: str = "hybrid"
    composition_enabled: bool = True
    research_extract_enabled: bool = True
    document_default_app: str = "word"
    plan_reflection_enabled: bool = True
    max_plan_reflections: int = 2
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
            "document_authoring",
            "guarded_shell_recipe",
        ]
    )
    driver_preferences: list[str] = field(default_factory=list)
    plugin_modules: list[str] = field(default_factory=list)
    plugin_fail_fast: bool = False
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
    _provided_keys: set[str] = field(default_factory=set, repr=False, compare=False)

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
        allowed_fields = {item.name for item in dataclass_fields(cls)}
        payload["_provided_keys"] = {key for key in payload if key in allowed_fields and key != "_provided_keys"}
        return cls(**payload)

    def normalize(self) -> None:
        if not isinstance(self.run_root, Path):
            self.run_root = Path(self.run_root) if self.run_root else default_run_root()
        self.dry_run = _normalized_bool(self.dry_run, default=True)
        self.cursor_motion_enabled = _normalized_bool(self.cursor_motion_enabled, default=False)
        self.model_auto_discover = _normalized_bool(self.model_auto_discover, default=True)
        self.managed_browser_enabled = _normalized_bool(self.managed_browser_enabled, default=True)
        self.external_browser_attach_enabled = _normalized_bool(self.external_browser_attach_enabled, default=True)
        self.safe_mode_enabled = _normalized_bool(self.safe_mode_enabled, default=False)
        self.browser_headless = _normalized_bool(self.browser_headless, default=False)
        self.display_override_enabled = _normalized_bool(self.display_override_enabled, default=False)
        self.generic_app_launch_enabled = _normalized_bool(self.generic_app_launch_enabled, default=True)
        self.plugin_fail_fast = _normalized_bool(self.plugin_fail_fast, default=False)
        self.composition_enabled = _normalized_bool(self.composition_enabled, default=True)
        self.research_extract_enabled = _normalized_bool(self.research_extract_enabled, default=True)
        self.plan_reflection_enabled = _normalized_bool(self.plan_reflection_enabled, default=True)
        try:
            max_plan_reflections = int(self.max_plan_reflections)
        except (TypeError, ValueError):
            max_plan_reflections = 2
        self.max_plan_reflections = max(0, min(10, max_plan_reflections))
        try:
            max_document_length = int(self.max_document_length)
        except (TypeError, ValueError):
            max_document_length = 20000
        self.max_document_length = max(self.max_text_length, min(200000, max_document_length))
        self.document_default_app = str(self.document_default_app or "word").strip() or "word"
        self.enabled_capabilities = _normalized_string_list(self.enabled_capabilities)
        self.driver_preferences = _normalized_string_list(self.driver_preferences)
        self.plugin_modules = _normalized_string_list(self.plugin_modules)
        if self.enabled_capabilities and "document_authoring" not in {
            str(item).strip().lower() for item in self.enabled_capabilities
        }:
            # document_authoring is a core capability introduced after some configs
            # were written; ensure stale configs still wire it in.
            self.enabled_capabilities.append("document_authoring")
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
            default=30.0,
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
        shell_start_mode = str(self.shell_start_mode or "main").strip().lower().replace("-", "_")
        self.shell_start_mode = shell_start_mode if shell_start_mode in {"floating", "main"} else "main"
        review_policy = str(self.plan_review_policy or "low_risk_auto").strip().lower()
        self.plan_review_policy = review_policy if review_policy in {"never", "low_risk_auto", "always"} else "low_risk_auto"
        approval_policy = str(self.approval_policy or "tiered").strip().lower().replace("_", " ")
        self.approval_policy = (
            approval_policy
            if approval_policy in {"tiered", "strict", "always", "autonomous", "high autonomy"}
            else "tiered"
        )
        autonomy_mode = str(self.desktop_autonomy_mode or "conservative").strip().lower().replace(" ", "-")
        self.desktop_autonomy_mode = _AUTONOMY_MODE_ALIASES.get(autonomy_mode, "conservative")
        orchestrator_mode = str(self.orchestrator_mode or "unified").strip().lower()
        self.orchestrator_mode = orchestrator_mode if orchestrator_mode in {"off", "unified"} else "unified"
        stage_review_policy = str(self.stage_review_policy or "risk_change").strip().lower()
        self.stage_review_policy = (
            stage_review_policy
            if stage_review_policy in {"never", "risk_change", "always"}
            else "risk_change"
        )
        self._apply_desktop_autonomy_mode_preset()
        self.task_workspace_enabled = _normalized_bool(self.task_workspace_enabled, default=True)
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
        self.replan_on_recoverable_error = _normalized_bool(self.replan_on_recoverable_error, default=True)
        try:
            recoverable_retry_limit = int(self.recoverable_error_retry_limit)
        except (TypeError, ValueError):
            recoverable_retry_limit = 2
        self.recoverable_error_retry_limit = max(0, min(10, recoverable_retry_limit))

    def _apply_desktop_autonomy_mode_preset(self) -> None:
        provided_keys = set(self._provided_keys or set())
        mode_was_explicit = "desktop_autonomy_mode" in provided_keys
        if self.desktop_autonomy_mode == "conservative" and not mode_was_explicit:
            return
        preset = _AUTONOMY_MODE_PRESETS.get(self.desktop_autonomy_mode)
        if not preset:
            return
        for key, value in preset.items():
            if key not in provided_keys:
                setattr(self, key, value)

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


def _normalized_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _TRUE_STRING_VALUES:
            return True
        if normalized in _FALSE_STRING_VALUES:
            return False
    return default


def _normalized_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items = value.replace(";", ",").split(",")
    elif isinstance(value, (list, tuple, set)):
        raw_items = value
    else:
        raw_items = []
    items: list[str] = []
    for item in raw_items:
        text = str(item or "").strip()
        if text and text not in items:
            items.append(text)
    return items
