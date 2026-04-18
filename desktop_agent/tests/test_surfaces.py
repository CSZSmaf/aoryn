import time

from desktop_agent.config import AgentConfig
from desktop_agent.surfaces import (
    choose_surface_kind,
    detect_user_input_preemption,
)


def test_choose_surface_kind_prefers_managed_browser_for_browser_context():
    config = AgentConfig()

    surface = choose_surface_kind(
        config=config,
        active_app="browser",
        browser_snapshot={"url": "https://openai.com"},
        goal_type="navigate",
    )

    assert surface == "managed_aoryn_browser"


def test_detect_user_input_preemption_uses_recent_external_input():
    config = AgentConfig(user_input_preemption_policy="pause_and_resume")
    context = {"last_agent_action_at": time.time() - 2.0}
    session = type("Session", (), {"last_input_age_seconds": 0.5})()

    assert detect_user_input_preemption(config=config, execution_context=context, session=session) is True


def test_detect_user_input_preemption_ignores_recent_agent_actions():
    config = AgentConfig(user_input_preemption_policy="pause_and_resume")
    context = {"last_agent_action_at": time.time() - 0.2}
    session = type("Session", (), {"last_input_age_seconds": 0.1})()

    assert detect_user_input_preemption(config=config, execution_context=context, session=session) is False
