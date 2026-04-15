from desktop_agent.planner import RulePlanner


def test_open_notepad_and_type():
    planner = RulePlanner()

    result = planner.plan("open notepad and type hello world", screenshot_path=None, history=[])

    assert result.done is True
    assert result.actions[0].type == "open_app_if_needed"
    assert result.actions[0].app == "notepad"
    assert result.actions[-1].type == "type"
    assert result.actions[-1].text == "hello world"


def test_open_calculator():
    planner = RulePlanner()

    result = planner.plan("open calculator", screenshot_path=None, history=[])

    assert result.done is True
    assert result.actions[0].app == "calculator"


def test_calculator_expression_uses_deterministic_actions():
    planner = RulePlanner()

    result = planner.plan("open calculator and calculate 1+1", screenshot_path=None, history=[])

    assert result.done is True
    assert [action.type for action in result.actions] == ["open_app_if_needed", "wait", "type", "press"]
    assert result.actions[0].app == "calculator"
    assert result.actions[2].text == "1+1"
    assert result.actions[3].key == "enter"


def test_browser_search_uses_web_action():
    planner = RulePlanner()

    result = planner.plan("search for OpenAI desktop agent", screenshot_path=None, history=[])

    assert result.done is True
    assert result.actions == [result.actions[0]]
    assert result.actions[0].type == "browser_search"
    assert result.actions[0].text == "OpenAI desktop agent"


def test_browser_open_url_uses_web_action_without_needing_network():
    planner = RulePlanner()
    planner.web_agent.inspect_target = lambda target: None  # type: ignore[method-assign]

    result = planner.plan("visit openai.com/docs", screenshot_path=None, history=[])

    assert result.done is True
    assert result.actions[0].type == "browser_open"
    assert result.actions[0].text == "https://openai.com/docs"
