import pytest

from desktop_agent.config import AgentConfig
from desktop_agent.planner import (
    AutoPlanner,
    VLMPlanner,
    PlannerError,
    _build_environment_context,
    _build_task_decomposition,
    _build_vlm_payload,
    _build_response_format,
    _needs_model_discovery,
    _normalize_api_base_url,
    _normalize_structured_output_mode,
    _pick_model_name,
)
from desktop_agent.windows_env import DesktopEnvironment, MonitorSnapshot, Rect, TaskbarState, WindowSnapshot


def test_normalize_api_base_url_adds_v1():
    assert _normalize_api_base_url("http://127.0.0.1:1234") == "http://127.0.0.1:1234/v1"


def test_normalize_api_base_url_keeps_v1():
    assert _normalize_api_base_url("http://127.0.0.1:1234/v1") == "http://127.0.0.1:1234/v1"


def test_normalize_structured_output_mode_auto_prefers_json_schema():
    assert _normalize_structured_output_mode("auto") == "json_schema"


def test_build_response_format_uses_json_schema_for_lmstudio_auto():
    response_format = _build_response_format("json_schema")
    assert response_format is not None
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "desktop_agent_plan"


def test_needs_model_discovery_for_auto():
    assert _needs_model_discovery("auto") is True
    assert _needs_model_discovery("") is True
    assert _needs_model_discovery("qwen2.5-vl") is False


def test_pick_model_name_uses_first_available_when_auto():
    models = [{"id": "qwen2.5-vl-7b-instruct"}, {"id": "llava"}]
    assert _pick_model_name("auto", models) == "qwen2.5-vl-7b-instruct"


def test_pick_model_name_rejects_missing_explicit_model():
    with pytest.raises(PlannerError):
        _pick_model_name("missing-model", [{"id": "qwen2.5-vl-7b-instruct"}])


def test_vlm_planner_short_circuits_explicit_browser_tasks():
    planner = VLMPlanner(AgentConfig())
    planner.web_agent.inspect_target = lambda target: None  # type: ignore[method-assign]

    result = planner.plan("visit openai.com", screenshot_path=None, history=[])

    assert result.done is True
    assert result.actions[0].type == "browser_open"
    assert result.actions[0].text == "https://openai.com"


def test_vlm_planner_short_circuits_shopping_tasks():
    planner = VLMPlanner(AgentConfig())

    result = planner.plan("shop for high-value men's pants on amazon", screenshot_path=None, history=[])

    assert result.done is True
    assert result.actions[0].type == "browser_open"
    assert result.actions[0].text.startswith("https://www.amazon.com/s?k=")


def test_auto_planner_prefers_vlm_for_complex_cross_app_task():
    planner = AutoPlanner(AgentConfig())
    calls: list[str] = []

    planner.vlm.plan = lambda *args, **kwargs: calls.append("vlm") or VLMPlanner(AgentConfig()).web_agent.try_plan("visit openai.com")  # type: ignore[method-assign]
    planner.rule.plan = lambda *args, **kwargs: calls.append("rule") or (_ for _ in ()).throw(PlannerError("rule should not run"))  # type: ignore[method-assign]

    result = planner.plan(
        "open browser search for OpenAI desktop agent and write notes in notepad",
        screenshot_path=None,
        history=[],
    )

    assert result is not None
    assert calls == ["vlm"]


def test_auto_planner_keeps_rule_shortcuts_for_simple_tasks():
    planner = AutoPlanner(AgentConfig())
    calls: list[str] = []

    planner.rule.plan = lambda *args, **kwargs: calls.append("rule") or planner.rule.web_agent.try_plan("visit openai.com")  # type: ignore[method-assign]
    planner.vlm.plan = lambda *args, **kwargs: calls.append("vlm") or (_ for _ in ()).throw(PlannerError("vlm should not run"))  # type: ignore[method-assign]

    result = planner.plan("visit openai.com", screenshot_path=None, history=[])

    assert result is not None
    assert calls == ["rule"]


def test_build_vlm_payload_includes_browser_context():
    payload = _build_vlm_payload(
        model_name="demo-model",
        task="visit openai.com and click login",
        history_text="Round 1:\n  opened browser",
        decomposition_text="Overall goal: visit openai.com and click login",
        image_b64="ZmFrZQ==",
        browser_context="Browser popup policy: dismiss translate popup first.",
        environment_context=None,
        response_format_mode="off",
    )

    content = payload["messages"][1]["content"][0]["text"]

    assert "Browser context:" in content
    assert "dismiss translate popup first" in content
    assert "Task decomposition hints:" in content
    assert "choose the next unmet sub-goal" in content


def test_build_vlm_payload_includes_environment_context():
    payload = _build_vlm_payload(
        model_name="demo-model",
        task="open notepad",
        history_text="Round 1:\n  no history",
        decomposition_text="Overall goal: open notepad",
        image_b64="ZmFrZQ==",
        browser_context=None,
        environment_context="Current monitor: DISPLAY1 work area 0,0 1920x1040",
        response_format_mode="off",
    )

    content = payload["messages"][1]["content"][0]["text"]

    assert "Desktop environment:" in content
    assert "Current monitor: DISPLAY1 work area 0,0 1920x1040" in content


def test_build_environment_context_describes_foreground_and_taskbar():
    environment = DesktopEnvironment(
        platform="windows",
        virtual_bounds=Rect(0, 0, 1920, 1080),
        monitors=[
            MonitorSnapshot(
                device_name="DISPLAY1",
                is_primary=True,
                bounds=Rect(0, 0, 1920, 1080),
                work_area=Rect(0, 0, 1920, 1040),
            )
        ],
        current_monitor=MonitorSnapshot(
            device_name="DISPLAY1",
            is_primary=True,
            bounds=Rect(0, 0, 1920, 1080),
            work_area=Rect(0, 0, 1920, 1040),
        ),
        dpi_scale=1.25,
        taskbar=TaskbarState(position="bottom", auto_hide=False, occupies_work_area=True, rect=Rect(0, 1040, 1920, 1080)),
        foreground_window=WindowSnapshot(
            handle=100,
            title="Notepad",
            rect=Rect(20, 20, 1200, 900),
            is_visible=True,
            is_minimized=False,
            is_maximized=False,
        ),
        visible_windows=[WindowSnapshot(handle=100, title="Notepad")],
    )

    context = _build_environment_context(environment)

    assert context is not None
    assert "Taskbar: position=bottom" in context
    assert "Foreground window: Notepad" in context
    assert "DPI scale: 1.25" in context


def test_build_task_decomposition_splits_multi_step_task():
    decomposition = _build_task_decomposition(
        "open notepad and type hello world and press enter",
        history=[],
        browser_command=None,
    )

    lowered = decomposition.lower()
    assert "candidate sub-goals" in lowered
    assert "1. open notepad" in lowered
    assert "2. type hello world" in lowered
    assert "3. press enter" in lowered
