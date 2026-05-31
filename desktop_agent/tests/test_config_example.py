from pathlib import Path

from desktop_agent.config import AgentConfig


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_config_example_loads_and_matches_complex_task_defaults():
    config = AgentConfig.from_yaml(PROJECT_ROOT / "config.example.yaml")
    defaults = AgentConfig()

    assert config.max_steps == defaults.max_steps == 20
    assert config.desktop_autonomy_mode == defaults.desktop_autonomy_mode == "conservative"
    assert config.max_task_subgoals == defaults.max_task_subgoals == 12
    assert config.max_replans_per_run == defaults.max_replans_per_run == 3
    assert config.approval_policy == defaults.approval_policy == "tiered"
    assert config.task_graph_request_timeout == defaults.task_graph_request_timeout == 30.0
    assert config.replan_on_recoverable_error is defaults.replan_on_recoverable_error is True
    assert config.recoverable_error_retry_limit == defaults.recoverable_error_retry_limit == 2
    assert config.app_launch_map["settings"] == "ms-settings:"


def test_agent_config_normalizes_approval_policy_aliases():
    assert AgentConfig(approval_policy="high_autonomy").approval_policy == "high autonomy"
    assert AgentConfig(approval_policy="autonomous").approval_policy == "autonomous"
    assert AgentConfig(approval_policy="unknown").approval_policy == "tiered"


def test_agent_config_normalizes_recoverable_retry_controls():
    assert AgentConfig(replan_on_recoverable_error=0).replan_on_recoverable_error is False
    assert AgentConfig(recoverable_error_retry_limit="-1").recoverable_error_retry_limit == 0
    assert AgentConfig(recoverable_error_retry_limit="99").recoverable_error_retry_limit == 10
    assert AgentConfig(recoverable_error_retry_limit="bad").recoverable_error_retry_limit == 2


def test_agent_config_normalizes_string_boolean_controls():
    config = AgentConfig.from_dict(
        {
            "dry_run": "false",
            "cursor_motion_enabled": "true",
            "model_auto_discover": "false",
            "managed_browser_enabled": "false",
            "external_browser_attach_enabled": "false",
            "safe_mode_enabled": "true",
            "browser_headless": "true",
            "task_workspace_enabled": "false",
            "display_override_enabled": "true",
            "generic_app_launch_enabled": "false",
            "replan_on_recoverable_error": "false",
        }
    )

    assert config.dry_run is False
    assert config.cursor_motion_enabled is True
    assert config.model_auto_discover is False
    assert config.managed_browser_enabled is False
    assert config.external_browser_attach_enabled is False
    assert config.safe_mode_enabled is True
    assert config.browser_headless is True
    assert config.task_workspace_enabled is False
    assert config.display_override_enabled is True
    assert config.generic_app_launch_enabled is False
    assert config.replan_on_recoverable_error is False

    invalid = AgentConfig.from_dict(
        {
            "dry_run": "maybe",
            "cursor_motion_enabled": "maybe",
            "browser_headless": "maybe",
            "task_workspace_enabled": "maybe",
            "replan_on_recoverable_error": "maybe",
        }
    )

    assert invalid.dry_run is True
    assert invalid.cursor_motion_enabled is False
    assert invalid.browser_headless is False
    assert invalid.task_workspace_enabled is True
    assert invalid.replan_on_recoverable_error is True


def test_agent_config_applies_explicit_autonomy_mode_presets():
    autonomous = AgentConfig.from_dict({"desktop_autonomy_mode": "autonomous"})
    assert autonomous.desktop_autonomy_mode == "autonomous"
    assert autonomous.plan_review_policy == "never"
    assert autonomous.approval_policy == "autonomous"
    assert autonomous.stage_review_policy == "never"
    assert autonomous.recoverable_error_retry_limit == 4
    assert autonomous.max_replans_per_run == 5
    assert autonomous.max_failures_per_subgoal == 5
    assert AgentConfig.from_dict({"desktop_autonomy_mode": "aggressive"}).desktop_autonomy_mode == "autonomous"

    review_first = AgentConfig.from_dict({"desktop_autonomy_mode": "review-first"})
    assert review_first.desktop_autonomy_mode == "review_first"
    assert review_first.plan_review_policy == "always"
    assert review_first.approval_policy == "strict"
    assert review_first.stage_review_policy == "always"
    assert review_first.recoverable_error_retry_limit == 1

    custom = AgentConfig.from_dict(
        {
            "desktop_autonomy_mode": "autonomous",
            "plan_review_policy": "always",
            "recoverable_error_retry_limit": 1,
        }
    )
    assert custom.plan_review_policy == "always"
    assert custom.approval_policy == "autonomous"
    assert custom.recoverable_error_retry_limit == 1
