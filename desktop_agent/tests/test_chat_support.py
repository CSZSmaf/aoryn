from desktop_agent.chat_support import (
    build_chat_system_prompt,
    extract_assistant_message,
    looks_like_math_request,
    sanitize_chat_messages,
)


def test_build_chat_system_prompt_uses_compact_summary_instead_of_full_markdown():
    help_markdown = "# Aoryn\n\n" + ("very long docs " * 1200)

    prompt = build_chat_system_prompt(
        help_markdown=help_markdown,
        locale="en-US",
        provider_name="openai_api",
        model_name="gpt-4o-mini",
    )

    assert "general chat assistant inside Aoryn" in prompt
    assert "Provider: OpenAI API" in prompt
    assert "Model: gpt-4o-mini" in prompt
    assert "built-in product assistant" not in prompt
    assert "very long docs very long docs very long docs" not in prompt
    assert len(prompt) < 1500


def test_build_chat_system_prompt_uses_shorter_vision_compatibility_prompt():
    prompt = build_chat_system_prompt(
        help_markdown="unused",
        locale="en-US",
        provider_name="lmstudio_local",
        model_name="qwen/qwen3-vl-30b",
        compatibility_mode=True,
    )

    assert "vision-model compatibility chat mode" in prompt
    assert "Provider: LM Studio local server" in prompt
    assert "Do not output placeholder text" in prompt
    assert "If the user asks which model or provider is being used" in prompt
    assert len(prompt) < 1200


def test_build_chat_system_prompt_uses_math_safe_prompt_in_compatibility_mode():
    prompt = build_chat_system_prompt(
        help_markdown="unused",
        locale="en-US",
        provider_name="lmstudio_local",
        model_name="qwen/qwen3-vl-30b",
        compatibility_mode=True,
        math_mode=True,
    )

    assert "asking for math or formulas" in prompt
    assert "Model: qwen/qwen3-vl-30b" in prompt
    assert "standalone $...$ or $$...$$" in prompt
    assert "Do not use \\begin \\end align cases left right" in prompt


def test_build_chat_system_prompt_uses_runtime_context_in_chinese_mode():
    prompt = build_chat_system_prompt(
        help_markdown="unused",
        locale="zh-CN",
        provider_name="openai_compatible",
        model_name="qwen-max",
    )

    assert "通用聊天助手" in prompt
    assert "Provider: OpenAI 兼容接口" in prompt
    assert "Model: qwen-max" in prompt
    assert "不要把自己说成 LM Studio" in prompt


def test_looks_like_math_request_detects_formula_heavy_messages():
    assert looks_like_math_request(r"Explain Maxwell equations with \nabla \cdot E = \frac{\rho}{\epsilon_0}.")
    assert looks_like_math_request("Give me a calculus formula for an integral.")
    assert not looks_like_math_request("hello there")


def test_sanitize_chat_messages_strips_assistant_sentinel_tokens():
    cleaned = sanitize_chat_messages(
        [
            {"role": "user", "content": "What is <|im_end|>?"},
            {"role": "assistant", "content": "Sure, continue.<|im_end|>\ufffd"},
        ]
    )

    assert cleaned == [
        {"role": "user", "content": "What is <|im_end|>?"},
        {"role": "assistant", "content": "Sure, continue."},
    ]


def test_extract_assistant_message_strips_sentinel_tokens_and_invalid_chars():
    payload = {
        "choices": [
            {
                "message": {
                    "content": "Here is the formula.<|im_end|>\ufffd",
                }
            }
        ]
    }

    assert extract_assistant_message(payload) == "Here is the formula."
