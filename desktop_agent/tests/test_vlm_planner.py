import base64

import pytest

from desktop_agent.config import AgentConfig
from desktop_agent.planner import (
    AutoPlanner,
    OpenAIComputerUsePlanner,
    VLMPlanner,
    PlannerError,
    _build_environment_context,
    _build_task_decomposition,
    _build_vlm_payload,
    _build_response_format,
    _import_requests,
    _needs_model_discovery,
    _normalize_api_base_url,
    _redact_sensitive_text,
    _normalize_structured_output_mode,
    _pick_model_name,
    _task_graph_model_timeout,
    build_planner,
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


def test_vlm_planner_caches_auto_discovered_model_name():
    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"id": "qwen2.5-vl-7b-instruct"}]}

    class _Requests:
        class RequestException(Exception):
            pass

        def __init__(self):
            self.calls = 0

        def get(self, *args, **kwargs):
            self.calls += 1
            return _Response()

    requests = _Requests()
    planner = VLMPlanner(AgentConfig(model_name="auto", model_auto_discover=True))
    api_base = _normalize_api_base_url("http://127.0.0.1:1234")

    assert planner._resolve_model_name(requests, api_base) == "qwen2.5-vl-7b-instruct"
    assert planner._resolve_model_name(requests, api_base) == "qwen2.5-vl-7b-instruct"
    assert requests.calls == 1


def test_vlm_planner_parses_string_boolean_auto_discover_flag():
    class _Requests:
        class RequestException(Exception):
            pass

        def get(self, *args, **kwargs):
            raise AssertionError("explicit model with auto_discover=false should not fetch /models")

    planner = VLMPlanner(AgentConfig(model_name="qwen/qwen3-vl", model_auto_discover="false"))
    api_base = _normalize_api_base_url("http://127.0.0.1:1234")

    assert planner._resolve_model_name(_Requests(), api_base) == "qwen/qwen3-vl"


def test_task_graph_timeout_honors_configurable_budget():
    config = AgentConfig(model_request_timeout=90, task_graph_request_timeout=12)
    # The budget is used as-is when it fits within the overall request timeout,
    # replacing the previous hard-coded 3s cap that starved complex planning.
    assert _task_graph_model_timeout(config) == 12.0


def test_task_graph_timeout_capped_by_request_timeout():
    config = AgentConfig(model_request_timeout=5, task_graph_request_timeout=30)
    assert _task_graph_model_timeout(config) == 5.0


def test_import_requests_returns_pooled_session_proxy():
    pooled = _import_requests()
    # Reused across calls so connections stay keep-alive instead of reopening.
    assert _import_requests() is pooled
    assert callable(pooled.get) and callable(pooled.post)
    # Falls through to the underlying module for everything else.
    assert pooled.RequestException is not None


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


def test_computer_use_planner_posts_responses_api_and_maps_click(monkeypatch, tmp_path):
    screenshot_path = tmp_path / "screen.png"
    screenshot_path.write_bytes(
        base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+kv4QAAAAASUVORK5CYII=")
    )

    calls: list[dict] = []

    class _Response:
        status_code = 200
        text = ""

        def json(self):
            return {
                "id": "resp-test",
                "output": [
                    {
                        "type": "reasoning",
                        "summary": [{"type": "summary_text", "text": "Click the visible Continue button."}],
                    },
                    {
                        "type": "computer_call",
                        "call_id": "call-test",
                        "actions": [{"type": "click", "x": 156, "y": 50, "button": "left"}],
                        "pending_safety_checks": [],
                    },
                ],
            }

    class _Requests:
        class RequestException(Exception):
            pass

        def get(self, *args, **kwargs):
            raise AssertionError("computer_use planner must not discover a local /models catalog")

        def post(self, url, **kwargs):
            calls.append({"url": url, **kwargs})
            return _Response()

    monkeypatch.setattr("desktop_agent.planner._import_requests", lambda: _Requests())

    planner = OpenAIComputerUsePlanner(
        AgentConfig(
            planner_mode="computer_use",
            model_provider="openai_api",
            model_base_url="https://api.openai.com/v1",
            model_name="gpt-5.5",
            model_auto_discover=False,
        )
    )
    result = planner.plan("click continue", screenshot_path=screenshot_path, history=["opened the app"])

    assert calls[0]["url"] == "https://api.openai.com/v1/responses"
    payload = calls[0]["json"]
    assert payload["model"] == "gpt-5.5"
    assert payload["tools"][0]["type"] == "computer"
    assert payload["input"][0]["content"][1]["type"] == "input_image"
    assert payload["input"][0]["content"][1]["detail"] == "original"
    assert result.actions[0].type == "click"
    assert result.actions[0].x == 156
    assert result.actions[0].y == 50

    planner.plan("click continue", screenshot_path=screenshot_path, history=["clicked once"])
    followup_payload = calls[1]["json"]
    assert followup_payload["previous_response_id"] == "resp-test"
    assert followup_payload["input"][0]["type"] == "computer_call_output"
    assert followup_payload["input"][0]["call_id"] == "call-test"
    assert followup_payload["input"][0]["output"]["type"] == "computer_screenshot"
    assert followup_payload["input"][0]["output"]["detail"] == "original"


def test_computer_use_planner_defaults_to_openai_api_not_local_model(monkeypatch, tmp_path):
    screenshot_path = tmp_path / "screen.png"
    screenshot_path.write_bytes(
        base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+kv4QAAAAASUVORK5CYII=")
    )
    calls: list[str] = []

    class _Response:
        status_code = 200
        text = ""

        def json(self):
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": "Done."}]}]}

    class _Requests:
        class RequestException(Exception):
            pass

        def post(self, url, **kwargs):
            calls.append(url)
            return _Response()

    monkeypatch.setattr("desktop_agent.planner._import_requests", lambda: _Requests())

    OpenAIComputerUsePlanner(AgentConfig(planner_mode="computer_use")).plan(
        "inspect the screen",
        screenshot_path=screenshot_path,
        history=[],
    )

    assert calls == ["https://api.openai.com/v1/responses"]


def test_computer_use_planner_honors_explicit_non_local_base_url(monkeypatch, tmp_path):
    screenshot_path = tmp_path / "screen.png"
    screenshot_path.write_bytes(
        base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+kv4QAAAAASUVORK5CYII=")
    )
    calls: list[str] = []

    class _Response:
        status_code = 200
        text = ""

        def json(self):
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": "Done."}]}]}

    class _Requests:
        class RequestException(Exception):
            pass

        def post(self, url, **kwargs):
            calls.append(url)
            return _Response()

    monkeypatch.setattr("desktop_agent.planner._import_requests", lambda: _Requests())

    OpenAIComputerUsePlanner(
        AgentConfig(planner_mode="computer_use", model_base_url="https://api.gptsapi.net/v1")
    ).plan(
        "inspect the screen",
        screenshot_path=screenshot_path,
        history=[],
    )

    assert calls == ["https://api.gptsapi.net/v1/responses"]


def test_computer_use_planner_keeps_preview_tool_when_explicitly_configured(monkeypatch, tmp_path):
    screenshot_path = tmp_path / "screen.png"
    screenshot_path.write_bytes(
        base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+kv4QAAAAASUVORK5CYII=")
    )
    calls: list[dict] = []

    class _Response:
        status_code = 200
        text = ""

        def json(self):
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": "Done."}]}]}

    class _Requests:
        class RequestException(Exception):
            pass

        def post(self, url, **kwargs):
            calls.append({"url": url, **kwargs})
            return _Response()

    monkeypatch.setattr("desktop_agent.planner._import_requests", lambda: _Requests())

    OpenAIComputerUsePlanner(
        AgentConfig(
            planner_mode="computer_use",
            model_provider="openai_api",
            model_base_url="https://api.openai.com/v1",
            model_name="computer-use-preview",
            model_auto_discover=False,
        )
    ).plan("inspect the screen", screenshot_path=screenshot_path, history=[])

    payload = calls[0]["json"]
    assert payload["model"] == "computer-use-preview"
    assert payload["tools"][0]["type"] == "computer_use_preview"
    assert payload["tools"][0]["display_width"] > 0


def test_computer_use_planner_uses_openai_api_key_env_fallback(monkeypatch, tmp_path):
    screenshot_path = tmp_path / "screen.png"
    screenshot_path.write_bytes(
        base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+kv4QAAAAASUVORK5CYII=")
    )
    calls: list[dict] = []

    class _Response:
        status_code = 200
        text = ""

        def json(self):
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": "Done."}]}]}

    class _Requests:
        class RequestException(Exception):
            pass

        def post(self, url, **kwargs):
            calls.append({"url": url, **kwargs})
            return _Response()

    monkeypatch.setenv("OPENAI_API_KEY", "env-secret")
    monkeypatch.setattr("desktop_agent.planner._import_requests", lambda: _Requests())

    OpenAIComputerUsePlanner(AgentConfig(planner_mode="computer_use", model_api_key="")).plan(
        "inspect the screen",
        screenshot_path=screenshot_path,
        history=[],
    )

    assert calls[0]["headers"]["Authorization"] == "Bearer env-secret"


def test_computer_use_planner_falls_back_to_chat_completions_for_compatible_provider(monkeypatch, tmp_path):
    screenshot_path = tmp_path / "screen.png"
    screenshot_path.write_bytes(
        base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+kv4QAAAAASUVORK5CYII=")
    )
    calls: list[dict] = []

    class _Response:
        def __init__(self, status_code, payload, text=""):
            self.status_code = status_code
            self._payload = payload
            self.text = text

        def json(self):
            return self._payload

    class _Requests:
        class RequestException(Exception):
            pass

        def post(self, url, **kwargs):
            calls.append({"url": url, **kwargs})
            if url.endswith("/responses"):
                return _Response(
                    401,
                    {},
                    '{"error":{"code":"invalid_api_key","message":"Responses endpoint rejected this key"}}',
                )
            return _Response(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    '{"done": false, "status_summary": "Click Continue.", '
                                    '"reasoning": "The Continue button is visible.", '
                                    '"actions": [{"type": "click", "x": 160, "y": 48}]}'
                                )
                            }
                        }
                    ]
                },
            )

    monkeypatch.setattr("desktop_agent.planner._import_requests", lambda: _Requests())

    result = OpenAIComputerUsePlanner(
        AgentConfig(
            planner_mode="computer_use",
            model_provider="openai_api",
            model_base_url="https://api.gptsapi.net/v1",
            model_name="gpt-5.5",
            model_auto_discover=False,
        )
    ).plan("click continue", screenshot_path=screenshot_path, history=["opened the app"])

    assert calls[0]["url"] == "https://api.gptsapi.net/v1/responses"
    assert calls[1]["url"] == "https://api.gptsapi.net/v1/chat/completions"
    assert calls[1]["json"]["messages"][1]["content"][1]["type"] == "image_url"
    assert calls[1]["json"]["response_format"] == {"type": "json_object"}
    assert result.actions[0].type == "click"
    assert result.actions[0].x == 160
    assert result.actions[0].y == 48


def test_computer_use_planner_falls_back_when_responses_returns_non_json(monkeypatch, tmp_path):
    screenshot_path = tmp_path / "screen.png"
    screenshot_path.write_bytes(
        base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+kv4QAAAAASUVORK5CYII=")
    )
    calls: list[str] = []

    class _Response:
        def __init__(self, status_code, payload=None, text=""):
            self.status_code = status_code
            self._payload = payload
            self.text = text

        def json(self):
            if self._payload is None:
                raise ValueError("not json")
            return self._payload

    class _Requests:
        class RequestException(Exception):
            pass

        def post(self, url, **kwargs):
            calls.append(url)
            if url.endswith("/responses"):
                return _Response(200, None, "<html>responses proxy unavailable</html>")
            return _Response(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    '{"done": false, "status_summary": "Wait for the screen.", '
                                    '"actions": [{"type": "wait", "seconds": 0.5}]}'
                                )
                            }
                        }
                    ]
                },
            )

    monkeypatch.setattr("desktop_agent.planner._import_requests", lambda: _Requests())

    result = OpenAIComputerUsePlanner(
        AgentConfig(
            planner_mode="computer_use",
            model_provider="openai_api",
            model_base_url="https://api.gptsapi.net/v1",
            model_name="gpt-5.5",
            model_auto_discover=False,
        )
    ).plan("wait briefly", screenshot_path=screenshot_path, history=[])

    assert calls == ["https://api.gptsapi.net/v1/responses", "https://api.gptsapi.net/v1/chat/completions"]
    assert result.actions[0].type == "wait"
    assert result.actions[0].seconds == 0.5


def test_computer_use_chat_fallback_retries_without_response_format(monkeypatch, tmp_path):
    screenshot_path = tmp_path / "screen.png"
    screenshot_path.write_bytes(
        base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+kv4QAAAAASUVORK5CYII=")
    )
    calls: list[dict] = []

    class _Response:
        def __init__(self, status_code, payload, text=""):
            self.status_code = status_code
            self._payload = payload
            self.text = text

        def json(self):
            return self._payload

    class _Requests:
        class RequestException(Exception):
            pass

        def post(self, url, **kwargs):
            calls.append({"url": url, **kwargs})
            if url.endswith("/responses"):
                return _Response(404, {}, '{"error":{"message":"responses not found"}}')
            if "response_format" in kwargs["json"]:
                return _Response(400, {}, '{"error":{"message":"response_format is unsupported"}}')
            return _Response(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    "```json\n"
                                    '{"done": false, "summary": "Press Enter.", '
                                    '"actions": [{"type": "press", "key": "enter"}]}'
                                    "\n```"
                                )
                            }
                        }
                    ]
                },
            )

    monkeypatch.setattr("desktop_agent.planner._import_requests", lambda: _Requests())

    result = OpenAIComputerUsePlanner(
        AgentConfig(
            planner_mode="computer_use",
            model_provider="openai_api",
            model_base_url="https://api.gptsapi.net/v1",
            model_name="gpt-5.5",
            model_auto_discover=False,
        )
    ).plan("confirm", screenshot_path=screenshot_path, history=[])

    assert len(calls) == 3
    assert "response_format" in calls[1]["json"]
    assert "response_format" not in calls[2]["json"]
    assert result.actions[0].type == "press"
    assert result.actions[0].key == "enter"


def test_computer_use_planner_wraps_request_errors(monkeypatch, tmp_path):
    screenshot_path = tmp_path / "screen.png"
    screenshot_path.write_bytes(
        base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+kv4QAAAAASUVORK5CYII=")
    )

    class _Requests:
        class RequestException(Exception):
            pass

        def post(self, url, **kwargs):
            raise self.RequestException("timed out")

    monkeypatch.setattr("desktop_agent.planner._import_requests", lambda: _Requests())

    with pytest.raises(PlannerError, match="Could not reach the OpenAI computer use API"):
        OpenAIComputerUsePlanner(
            AgentConfig(planner_mode="computer_use", model_base_url="https://api.gptsapi.net", model_api_key="secret")
        ).plan(
            "inspect the screen",
            screenshot_path=screenshot_path,
            history=[],
        )


def test_redact_sensitive_text_masks_api_keys():
    assert _redact_sensitive_text("Incorrect key sk-abc123456789XYZ") == "Incorrect key sk-<redacted>"
    assert _redact_sensitive_text("Incorrect key sk-abcd********wxyz") == "Incorrect key sk-<redacted>"


def test_build_planner_supports_computer_use_mode():
    planner = build_planner(AgentConfig(planner_mode="computer_use"))

    assert isinstance(planner, OpenAIComputerUsePlanner)


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
    assert "2. open notepad and type hello world" in lowered
    assert "3. open notepad and press enter" in lowered
