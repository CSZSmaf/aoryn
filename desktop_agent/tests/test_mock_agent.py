from desktop_agent.actions import Action, PlanResult
from desktop_agent.config import AgentConfig
from desktop_agent.controller import build_agent
from desktop_agent.executor import MockExecutor


def test_mock_agent_notepad_task():
    config = AgentConfig(dry_run=True, planner_mode="rule")
    agent = build_agent(config)

    result = agent.run("open notepad and type demo")

    assert result.completed is True
    assert result.error is None
    executor = agent.executor
    assert isinstance(executor, MockExecutor)
    assert executor.state.active_app == "notepad"
    assert executor.state.text_buffers["notepad"].endswith("demo")


def test_mock_agent_browser_search_task():
    config = AgentConfig(dry_run=True, planner_mode="rule")
    agent = build_agent(config)

    result = agent.run("search for OpenAI")

    assert result.completed is True
    executor = agent.executor
    assert isinstance(executor, MockExecutor)
    assert "browser" in executor.state.open_apps
    assert executor.state.browser_queries[-1] == "OpenAI"
    assert executor.state.current_url == config.build_browser_search_url("OpenAI")


def test_mock_agent_browser_open_url_task():
    config = AgentConfig(dry_run=True, planner_mode="rule")
    agent = build_agent(config)
    agent.planner.web_agent.inspect_target = lambda target: None  # type: ignore[method-assign]

    result = agent.run("visit openai.com")

    assert result.completed is True
    executor = agent.executor
    assert isinstance(executor, MockExecutor)
    assert executor.state.current_url == "https://openai.com"
    assert executor.state.browser_history[-1] == "https://openai.com"


def test_mock_agent_shopping_task_uses_browser_search_or_open():
    config = AgentConfig(dry_run=True, planner_mode="rule")
    agent = build_agent(config)

    result = agent.run("shop for high-value men's pants on amazon")

    assert result.completed is True
    executor = agent.executor
    assert isinstance(executor, MockExecutor)
    assert executor.state.current_url is not None
    assert "amazon.com" in executor.state.current_url


def test_mock_agent_records_dom_clicks_for_follow_up_browser_task():
    config = AgentConfig(dry_run=True, planner_mode="auto")
    agent = build_agent(config)
    agent.planner.vlm.web_agent.inspect_target = lambda target: None  # type: ignore[method-assign]

    def fake_vlm_plan(task, screenshot_path, history, environment=None):
        if not history:
            return PlanResult(
                status_summary="Open openai.com first.",
                done=False,
                current_focus="open https://openai.com",
                remaining_steps=["click login"],
                actions=[Action.from_dict({"type": "browser_open", "text": "https://openai.com"})],
            )
        return PlanResult(
            status_summary="Click login after the page loads.",
            done=True,
            current_focus="click login",
            actions=[Action.from_dict({"type": "browser_dom_click", "text": "login"})],
        )

    agent.planner.vlm.plan = fake_vlm_plan  # type: ignore[method-assign]

    result = agent.run("visit openai.com and click login")

    assert result.completed is True
    executor = agent.executor
    assert isinstance(executor, MockExecutor)
    assert executor.state.browser_history[0] == "https://openai.com"
    assert "login" in executor.state.browser_dom_clicks[-1].lower()


def test_mock_agent_calculator_expression_task():
    config = AgentConfig(dry_run=True, planner_mode="rule")
    agent = build_agent(config)

    result = agent.run("open calculator and calculate 1+1")

    assert result.completed is True
    executor = agent.executor
    assert isinstance(executor, MockExecutor)
    assert executor.state.active_app == "calculator"
    assert executor.state.text_buffers["calculator"] == "1+1"
