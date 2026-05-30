import pytest

from desktop_agent.planner import PlannerError, RulePlanner, TaskIntent


def test_task_intent_from_dict_parses_string_boolean_requires_clarification():
    intent = TaskIntent.from_dict(
        {
            "task_type": "browser",
            "primary_goal": "open the dashboard",
            "requires_clarification": "false",
        }
    )
    clarification_intent = TaskIntent.from_dict(
        {
            "task_type": "browser",
            "primary_goal": "choose a destination",
            "requires_clarification": "true",
        }
    )

    assert intent.requires_clarification is False
    assert clarification_intent.requires_clarification is True


def test_open_notepad_and_type():
    planner = RulePlanner()

    result = planner.plan("open notepad and type hello world", screenshot_path=None, history=[])

    assert result.done is True
    assert result.actions[0].type == "open_app_if_needed"
    assert result.actions[0].app == "notepad"
    assert result.actions[-1].type == "type"
    assert result.actions[-1].text == "hello world"


def test_open_notepad_without_typing():
    planner = RulePlanner()

    result = planner.plan("open notepad", screenshot_path=None, history=[])

    assert result.done is True
    assert [action.type for action in result.actions] == ["open_app_if_needed", "wait"]
    assert result.actions[0].app == "notepad"


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


def test_standalone_calculator_expression_opens_calculator():
    planner = RulePlanner()

    result = planner.plan("calculate 12/4", screenshot_path=None, history=[])

    assert result.done is True
    assert [action.type for action in result.actions] == ["open_app_if_needed", "wait", "type", "press"]
    assert result.actions[0].app == "calculator"
    assert result.actions[2].text == "12/4"


def test_open_url_with_open_verb_uses_browser_action():
    planner = RulePlanner()

    result = planner.plan("open https://example.com", screenshot_path=None, history=[])

    assert result.done is True
    assert [action.type for action in result.actions] == ["browser_open"]
    assert result.actions[0].text == "https://example.com"


def test_browser_follow_up_click_uses_dom_action():
    planner = RulePlanner()

    result = planner.plan("click More information", screenshot_path=None, history=[])

    assert result.done is True
    assert [action.type for action in result.actions] == ["browser_dom_click"]
    assert result.actions[0].text == "More information"


def test_save_as_uses_standard_save_shortcut():
    planner = RulePlanner()

    result = planner.plan("save as notes.txt", screenshot_path=None, history=[])

    assert result.done is True
    assert [action.type for action in result.actions] == ["hotkey", "wait", "type", "press"]
    assert result.actions[0].keys == ["ctrl", "s"]
    assert result.actions[2].text == "notes.txt"


def test_generic_app_and_hotkey_uses_hotkey_action():
    planner = RulePlanner()

    result = planner.plan("open paint and press ctrl+s", screenshot_path=None, history=[])

    assert result.done is True
    assert [action.type for action in result.actions] == ["open_app_if_needed", "wait", "hotkey"]
    assert result.actions[0].app == "paint"
    assert result.actions[2].keys == ["ctrl", "s"]


def test_close_calculator_uses_close_window():
    planner = RulePlanner()

    result = planner.plan("关闭计算器", screenshot_path=None, history=[])

    assert result.done is True
    assert [action.type for action in result.actions] == ["close_window"]
    assert result.actions[0].title == "计算器"


def test_wait_task_accepts_short_zh_form():
    planner = RulePlanner()

    result = planner.plan("等5秒", screenshot_path=None, history=[])

    assert result.done is True
    assert [action.type for action in result.actions] == ["wait"]
    assert result.actions[0].seconds == 5.0


def test_open_browser_uses_local_app_action():
    planner = RulePlanner()

    result = planner.plan("打开浏览器", screenshot_path=None, history=[])

    assert result.done is True
    assert [action.type for action in result.actions[:2]] == ["open_app_if_needed", "wait"]
    assert result.actions[0].app == "browser"


def test_open_generic_local_app_uses_open_app_action():
    planner = RulePlanner()

    result = planner.plan("打开微信", screenshot_path=None, history=[])

    assert result.done is True
    assert [action.type for action in result.actions[:2]] == ["open_app_if_needed", "wait"]
    assert result.actions[0].app == "微信"


def test_generic_open_does_not_swallow_follow_up_sequence():
    planner = RulePlanner()

    with pytest.raises(PlannerError):
        planner.plan("open notepad then wait 1 seconds then close notepad", screenshot_path=None, history=[])


def test_open_generic_app_and_type_text():
    planner = RulePlanner()

    result = planner.plan("打开微信并输入你好", screenshot_path=None, history=[])

    assert result.done is True
    assert [action.type for action in result.actions] == ["open_app_if_needed", "wait", "type"]
    assert result.actions[0].app == "微信"
    assert result.actions[2].text == "你好"


def test_open_generic_app_and_click_named_control():
    planner = RulePlanner()

    result = planner.plan("open slack and click New message", screenshot_path=None, history=[])

    assert result.done is True
    assert [action.type for action in result.actions] == ["open_app_if_needed", "wait", "uia_invoke"]
    assert result.actions[0].app == "slack"
    assert result.actions[2].text == "New message"


def test_open_generic_app_and_fill_named_field():
    planner = RulePlanner()

    result = planner.plan("open appcenter and fill Username with alice", screenshot_path=None, history=[])

    assert result.done is True
    assert [action.type for action in result.actions] == ["open_app_if_needed", "wait", "uia_set_value"]
    assert result.actions[0].app == "appcenter"
    assert result.actions[2].selector == "name=Username"
    assert result.actions[2].text == "alice"


def test_open_generic_app_and_search_uses_find_shortcut():
    planner = RulePlanner()

    result = planner.plan("open wechat and search for Alice", screenshot_path=None, history=[])

    assert result.done is True
    assert [action.type for action in result.actions] == ["open_app_if_needed", "wait", "hotkey", "type", "press"]
    assert result.actions[0].app == "wechat"
    assert result.actions[2].keys == ["ctrl", "f"]
    assert result.actions[3].text == "Alice"
    assert result.actions[4].key == "enter"


def test_open_generic_app_and_search_zh_uses_find_shortcut():
    planner = RulePlanner()

    result = planner.plan("打开微信并搜索张三", screenshot_path=None, history=[])

    assert result.done is True
    assert [action.type for action in result.actions] == ["open_app_if_needed", "wait", "hotkey", "type", "press"]
    assert result.actions[0].app == "微信"
    assert result.actions[3].text == "张三"


def test_close_generic_app_uses_close_window():
    planner = RulePlanner()

    result = planner.plan("关闭微信", screenshot_path=None, history=[])

    assert result.done is True
    assert [action.type for action in result.actions] == ["close_window"]
    assert result.actions[0].title == "微信"


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
