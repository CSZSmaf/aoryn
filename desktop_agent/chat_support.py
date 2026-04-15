from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any


def _runtime_project_root() -> Path:
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        if (bundle_root / "README.md").exists():
            return bundle_root
        if (bundle_root.parent / "README.md").exists():
            return bundle_root.parent
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _runtime_project_root()
README_ZH_PATH = PROJECT_ROOT / "README.md"
README_EN_PATH = PROJECT_ROOT / "README.en.md"
_CHAT_SENTINEL_TOKENS = (
    "<|im_start|>",
    "<|im_end|>",
    "<|end|>",
    "<|endoftext|>",
    "<|assistant|>",
    "<|user|>",
    "<|system|>",
    "<|tool|>",
    "<|eot_id|>",
    "<|start_header_id|>",
    "<|end_header_id|>",
)
_CHAT_SENTINEL_PATTERN = re.compile("|".join(re.escape(token) for token in _CHAT_SENTINEL_TOKENS))
_CHAT_CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def normalize_help_locale(value: Any) -> str:
    locale = str(value or "").strip().lower()
    if locale.startswith("en"):
        return "en-US"
    return "zh-CN"


def resolve_help_path(locale: str) -> Path:
    return README_EN_PATH if normalize_help_locale(locale) == "en-US" else README_ZH_PATH


def load_help_markdown(path: Path | None = None) -> str:
    source = path or README_ZH_PATH
    try:
        content = source.read_text(encoding="utf-8").strip()
    except OSError:
        content = ""
    if content:
        return content
    if source == README_EN_PATH:
        return (
            "# Aoryn Developer Guide\n\n"
            "Aoryn includes chat mode, Agent mode, and a developer console."
        )
    return (
        "# Aoryn 开发者文档\n\n"
        "Aoryn 提供普通对话、Agent 模式和开发者控制台。"
    )


def normalize_text(value: Any) -> str:
    return str(value or "").replace("\r\n", "\n").strip()


def sanitize_assistant_chat_text(value: Any) -> str:
    cleaned = normalize_text(value)
    if not cleaned:
        return ""
    cleaned = cleaned.replace("\ufffd", "")
    cleaned = _CHAT_SENTINEL_PATTERN.sub("", cleaned)
    cleaned = _CHAT_CONTROL_CHAR_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def sanitize_chat_messages(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    cleaned: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip().lower()
        if role not in {"user", "assistant"}:
            continue
        content = (
            sanitize_assistant_chat_text(item.get("content"))
            if role == "assistant"
            else normalize_text(item.get("content"))
        )
        if not content:
            continue
        cleaned.append({"role": role, "content": content})
    return cleaned


def looks_like_math_request(text: Any) -> bool:
    source = normalize_text(text)
    if not source:
        return False
    lowered = source.lower()
    if any(
        token in lowered
        for token in (
            "latex",
            "equation",
            "equations",
            "formula",
            "formulas",
            "integral",
            "derivative",
            "matrix",
            "maxwell",
            "\\frac",
            "\\sqrt",
            "\\sum",
            "\\int",
            "\\nabla",
            "\\partial",
        )
    ):
        return True
    if any(
        token in source
        for token in (
            "公式",
            "方程",
            "积分",
            "导数",
            "矩阵",
            "麦克斯韦",
            "数学",
            "LaTeX",
            "∫",
            "Σ",
            "∑",
            "≈",
            "≠",
            "≤",
        )
    ):
        return True
    return bool(re.search(r"[$^_=]|\\[A-Za-z]+", source))


def _provider_display_name(provider_name: Any, locale: str) -> str:
    provider_key = str(provider_name or "").strip()
    normalized_locale = normalize_help_locale(locale)
    if normalized_locale == "zh-CN":
        mapping = {
            "lmstudio_local": "LM Studio 本地服务",
            "openai_api": "OpenAI API",
            "openai_compatible": "OpenAI 兼容接口",
            "custom": "自定义 Provider",
        }
        return mapping.get(provider_key, provider_key or "未指定")

    mapping = {
        "lmstudio_local": "LM Studio local server",
        "openai_api": "OpenAI API",
        "openai_compatible": "OpenAI-compatible API",
        "custom": "custom provider",
    }
    return mapping.get(provider_key, provider_key or "unspecified")


def _chat_runtime_context(*, locale: str, provider_name: Any, model_name: Any) -> str:
    normalized_locale = normalize_help_locale(locale)
    provider_label = _provider_display_name(provider_name, locale)
    model_label = str(model_name or "").strip() or ("未指定" if normalized_locale == "zh-CN" else "unspecified")
    if normalized_locale == "zh-CN":
        return (
            "当前运行环境：\n"
            f"- Provider: {provider_label}\n"
            f"- Model: {model_label}\n"
        )
    return (
        "Current runtime:\n"
        f"- Provider: {provider_label}\n"
        f"- Model: {model_label}\n"
    )


def build_chat_system_prompt(
    *,
    help_markdown: str,
    locale: str,
    provider_name: Any | None = None,
    model_name: Any | None = None,
    compatibility_mode: bool = False,
    math_mode: bool = False,
) -> str:
    _ = help_markdown
    normalized_locale = normalize_help_locale(locale)
    runtime_context = _chat_runtime_context(
        locale=normalized_locale,
        provider_name=provider_name,
        model_name=model_name,
    )
    if normalized_locale == "zh-CN":
        if compatibility_mode and math_mode:
            return (
                "你是 Aoryn 中的通用聊天助手。\n"
                "当前处于视觉模型兼容聊天模式，用户正在询问数学或公式内容。\n"
                f"{runtime_context}"
                "回答规则：\n"
                "- 你不是底层模型本身，不要把自己说成固定厂商、LM Studio 产品助手或某个具体模型，除非上面的运行时信息明确如此。\n"
                "- 如果用户问你正在使用什么模型或 provider，优先根据上面的运行时信息回答；如果信息不足，就明确说明你不知道。\n"
                "- 说明文字用简洁中文，公式只放在独立的 $...$ 或 $$...$$ 中。\n"
                "- 只使用稳定的 LaTeX 子集，例如 \\frac \\sqrt \\sum \\int \\partial \\nabla \\mathbf 以及上下标。\n"
                "- 不要使用 \\begin \\end align cases left right 等高风险写法，不要把长段说明和公式混在同一行。\n"
                "- 不要输出模板残片、乱码、损坏的转义序列、占位符或无意义字符。"
            )
        if compatibility_mode:
            return (
                "你是 Aoryn 中的通用聊天助手。\n"
                "当前处于视觉模型兼容聊天模式，请优先根据当前可见对话直接回答。\n"
                f"{runtime_context}"
                "回答规则：\n"
                "- 你不是底层模型本身，不要把自己说成固定厂商、LM Studio 产品助手或某个具体模型，除非上面的运行时信息明确如此。\n"
                "- 如果用户问你正在使用什么模型或 provider，优先根据上面的运行时信息回答；如果信息不足，就明确说明你不知道。\n"
                "- 普通问题按正常聊天回答，不要强行转成产品介绍。\n"
                "- 如果用户问的是 Aoryn、LM Studio、浏览器配置或 Agent 模式，再提供产品和排障帮助。\n"
                "- 对问候或简单问题，用 1 到 2 句自然回答。\n"
                "- 不要输出模板残片、重复符号、分隔线、占位符或乱码。"
            )
        if math_mode:
            return (
                "你是 Aoryn 中的通用聊天助手。\n"
                "用户正在询问数学或公式内容。\n"
                f"{runtime_context}"
                "回答规则：\n"
                "- 你不是底层模型本身，不要把自己说成固定厂商、LM Studio 产品助手或某个具体模型，除非上面的运行时信息明确如此。\n"
                "- 如果用户问你正在使用什么模型或 provider，优先根据上面的运行时信息回答；如果信息不足，就明确说明你不知道。\n"
                "- 先用简洁中文解释，再把公式放在独立的 $...$ 或 $$...$$ 中。\n"
                "- 优先使用稳定的 LaTeX 子集，例如 \\frac \\sqrt \\sum \\int \\partial \\nabla \\mathbf 以及上下标。\n"
                "- 不要输出损坏的转义序列、乱码或模板残片。"
            )
        return (
            "你是 Aoryn 中的通用聊天助手。\n"
            f"{runtime_context}"
            "回答规则：\n"
            "- 你服务于当前用户，不是底层模型本身。\n"
            "- 不要把自己说成 LM Studio、本地产品助手或某个固定厂商，除非上面的运行时信息明确如此。\n"
            "- 如果用户问你正在使用什么模型或 provider，优先根据上面的运行时信息回答；如果信息不足，就明确说明你不知道。\n"
            "- 普通问题按正常聊天回答，不要把每个问题都硬转成产品说明。\n"
            "- 如果用户问的是 Aoryn、LM Studio、浏览器配置、运行历史或 Agent 模式，再提供产品和排障帮助。\n"
            "- 不要声称你已经执行了桌面或浏览器操作。\n"
            "- 跟随用户语言，回答简洁自然；对问候或简单问题，用 1 到 3 句回答。\n"
            "- 不要输出模板残片、占位符、分隔线、重复符号或乱码。"
        )
    if compatibility_mode and math_mode:
        return (
            "You are the general chat assistant inside Aoryn.\n"
            "You are currently in vision-model compatibility chat mode, and the user is asking for math or formulas.\n"
            f"{runtime_context}"
            "Rules:\n"
            "- You are not the underlying model itself. Do not describe yourself as LM Studio, a built-in product assistant, or a fixed provider unless the runtime context above explicitly says so.\n"
            "- If the user asks which model or provider is being used, answer from the runtime context above. If it is unknown, say you do not know.\n"
            "- Keep explanations concise, and place formulas in standalone $...$ or $$...$$ blocks only.\n"
            "- Use a stable LaTeX subset such as \\frac \\sqrt \\sum \\int \\partial \\nabla \\mathbf and subscripts or superscripts.\n"
            "- Do not use \\begin \\end align cases left right or long mixed prose-plus-formula lines.\n"
            "- Do not output placeholder text, broken escape sequences, gibberish, or template fragments."
        )
    if compatibility_mode:
        return (
            "You are the general chat assistant inside Aoryn.\n"
            "You are currently in vision-model compatibility chat mode, so prefer short, direct replies from the visible turn.\n"
            f"{runtime_context}"
            "Rules:\n"
            "- You are not the underlying model itself. Do not describe yourself as LM Studio, a built-in product assistant, or a fixed provider unless the runtime context above explicitly says so.\n"
            "- If the user asks which model or provider is being used, answer from the runtime context above. If it is unknown, say you do not know.\n"
            "- Treat ordinary questions as ordinary chat questions instead of forcing product support framing.\n"
            "- If the user asks about Aoryn, LM Studio, browser settings, or Agent mode, provide product guidance.\n"
            "- Keep greetings and simple questions to 1 to 2 sentences.\n"
            "- Do not output placeholder text, repeated symbols, separators, template notes, or gibberish."
        )
    if math_mode:
        return (
            "You are the general chat assistant inside Aoryn.\n"
            "The user is asking for math or formulas.\n"
            f"{runtime_context}"
            "Rules:\n"
            "- You are not the underlying model itself. Do not describe yourself as LM Studio, a built-in product assistant, or a fixed provider unless the runtime context above explicitly says so.\n"
            "- If the user asks which model or provider is being used, answer from the runtime context above. If it is unknown, say you do not know.\n"
            "- Explain briefly in plain language, then put formulas in standalone $...$ or $$...$$ blocks.\n"
            "- Prefer a stable LaTeX subset such as \\frac \\sqrt \\sum \\int \\partial \\nabla \\mathbf and subscripts or superscripts.\n"
            "- Do not output broken escape sequences, gibberish, or template fragments."
        )
    return (
        "You are the general chat assistant inside Aoryn.\n"
        f"{runtime_context}"
        "Rules:\n"
        "- You serve the current user and are not the underlying model itself.\n"
        "- Do not describe yourself as LM Studio, a local product assistant, or a fixed provider unless the runtime context above explicitly says so.\n"
        "- If the user asks which model or provider is being used, answer from the runtime context above. If it is unknown, say you do not know.\n"
        "- Treat ordinary questions as ordinary chat questions; do not force every reply into product support.\n"
        "- If the user asks about Aoryn, LM Studio, browser settings, run history, or Agent mode, provide product guidance.\n"
        "- Do not claim that you executed desktop or browser actions.\n"
        "- Reply in the user's language. Keep greetings and simple questions short.\n"
        "- Do not output placeholder text, template fragments, repeated symbols, or gibberish."
    )


def looks_like_agent_task(text: str) -> bool:
    source = normalize_text(text).lower()
    if not source:
        return False

    action_patterns = (
        r"\b(open|launch|visit|go to|browse|search|click|type|press|scroll|download|upload|shop|buy|login|log in|sign in|fill|submit|run|execute)\b",
        r"(打开|启动|访问|浏览|搜索|点击|输入|按下|滚动|下载|上传|购物|购买|登录|登陆|填写|提交|运行|执行)",
    )
    if not any(re.search(pattern, source, re.I) for pattern in action_patterns):
        return False

    question_only_patterns = (
        r"^(how|what|why|explain|tell me|help me understand)\b",
        r"^(如何|怎么|为什么|介绍|说明|解释|告诉我|帮我理解)",
    )
    if any(re.search(pattern, source, re.I) for pattern in question_only_patterns):
        return False

    return True


def build_agent_handoff(text: str, *, locale: str) -> dict[str, str] | None:
    task = normalize_text(text)
    if not looks_like_agent_task(task):
        return None
    return {
        "suggested_task": task[:280],
        "reason": (
            "这个请求包含更适合交给 Agent 执行的桌面或浏览器动作。"
            if normalize_help_locale(locale) == "zh-CN"
            else "This request includes desktop or browser actions that Agent mode can execute."
        ),
    }


def extract_assistant_message(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""

    message = choices[0].get("message", {})
    content = message.get("content")
    if isinstance(content, str):
        return sanitize_assistant_chat_text(content)
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return sanitize_assistant_chat_text(
            "\n".join(part.strip() for part in parts if part.strip())
        )
    return ""
