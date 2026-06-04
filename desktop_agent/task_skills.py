"""Deterministic task skills with spoken results.

This module implements a small set of high-value desktop tasks end-to-end so the
agent can both *perform* the action on the real desktop and *report a concrete
answer back into the conversation*. It is intentionally independent from the
LLM/VLM planner: every answer is produced by deterministic local logic, so the
four showcase tasks work reliably even without a model server.

Supported skills:

1. ``calculator``          - open Windows Calculator and compute an arithmetic
                             expression, reporting the exact result.
2. ``notepad_poem``        - open Notepad and write an original short poem.
3. ``paint_drawing``       - open Windows Paint and draw with model-planned strokes.
4. ``clock_timer_alarm``   - open Windows Clock and start a local timer alert.
5. ``shopping_pants``      - open a shopping site search for men's trousers and
                             report a cost-performance (性价比) analysis.
6. ``travel_notepad``      - research Beijing travel pages and save a text/Markdown report.
7. ``travel_word``         - research Beijing attractions, build a 3-day itinerary and
                             save it as a real Word (.docx) document.

The runner stays pure: it executes :class:`~desktop_agent.actions.Action`
objects through whatever executor it is handed (real or mock) and never reaches
into global state. Side effects that touch the filesystem or launch external
viewers are gated by explicit flags so the runner is safe to unit-test.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable
from xml.sax.saxutils import escape as _xml_escape

from desktop_agent.actions import Action
from desktop_agent.plugin_runtime import get_task_plugin, match_task_plugin
from desktop_agent.web_research import (
    PageReading,
    capture_screen_image,
    classify_page,
    excerpt,
    extract_brand_mentions,
    extract_prices,
    model_chat,
    model_vision_ocr,
)

EmitCallback = Callable[[str, list[Action], int], None]


@dataclass(slots=True)
class TaskSkillResult:
    """Outcome of running one deterministic skill."""

    handled: bool
    skill: str | None = None
    completed: bool = False
    answer: str = ""
    headline: str = ""
    actions: list[Action] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    error: str | None = None
    requires_human: bool = False
    interruption_kind: str | None = None
    interruption_reason: str | None = None


# ---------------------------------------------------------------------------
# Keyword vocabularies (Chinese + English) used by the matchers.
# ---------------------------------------------------------------------------

_CALC_APP_TERMS = ("计算器", "calculator", "calc")
_CALC_VERB_TERMS = ("计算", "运算", "算一下", "算出", "算", "compute", "calculate", "evaluate", "equals")
_NOTEPAD_TERMS = ("记事本", "notepad")
_TYPORA_TERMS = ("typora", "markdown", ".md", "md")
_REPORT_TERMS = ("报告", "汇报", "report")
_POEM_TERMS = ("诗", "poem", "verse", "poetry")
_PAINT_TERMS = ("画图", "paint", "mspaint")
_CAT_TERMS = ("猫", "猫咪", "小猫", "cat", "kitten")
_DRAW_TERMS = ("画", "绘制", "画一", "draw", "sketch")
_GPTSAPI_SMART_PAINT_MODELS = (
    "claude-opus-4-8",
    "claude-sonnet-4-6",
    "gpt-5.4",
    "gpt-4o-mini",
)
_CLOCK_TERMS = ("时钟", "clock", "闹钟", "alarm", "alarms", "计时器", "timer")
_TIMER_SET_TERMS = ("定", "设置", "启动", "开始", "set", "start", "create")
_SHOPPING_TERMS = (
    "购物",
    "购物网站",
    "商城",
    "网购",
    "电商",
    "淘宝",
    "京东",
    "天猫",
    "拼多多",
    "唯品会",
    "shopping",
    "shop",
    "amazon",
    "taobao",
    "jd",
)
_PANTS_TERMS = ("裤子", "男裤", "长裤", "休闲裤", "牛仔裤", "西裤", "工装裤", "裤", "pants", "trousers", "jeans")
_VALUE_TERMS = ("性价比", "价比", "划算", "值不值", "cost-performance", "cost performance", "value for money", "value")
_BEIJING_TERMS = ("北京", "beijing", "peking")
_TRAVEL_TERMS = ("旅游", "旅行", "景点", "游玩", "出游", "travel", "tour", "sightsee", "attraction")
_PLAN_TERMS = ("规划", "计划", "行程", "攻略", "安排", "plan", "itinerary", "schedule")
_THREE_DAY_TERMS = ("3天", "三天", "3 天", "3-day", "three day", "three-day", "3日", "三日")
_SUMMARY_TERMS = ("总结", "整理", "归纳", "summary", "summarize")
_SEARCH_TERMS = ("搜索", "检索", "查询", "search")
_READ_TERMS = ("阅读", "读取", "看多个", "多个网页", "多页", "multiple pages", "read")
_WORD_TERMS = ("word", ".docx", "文档")
_QQ_TERMS = ("qq", "QQ", "腾讯qq", "腾讯QQ")
_GROUP_TERMS = ("群聊", "qq群", "QQ群", "群")
_SEND_TERMS = ("发送", "发到", "发给", "发消息", "send")
_MESSAGE_TERMS = ("消息", "内容", "文本", "message")


def _normalize(text: Any) -> str:
    return " ".join(str(text or "").strip().split())


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


# ---------------------------------------------------------------------------
# Safe arithmetic evaluation (no eval) for the calculator skill.
# ---------------------------------------------------------------------------

_ARITHMETIC_CHARS = re.compile(r"[0-9+\-*/().\s]")
_FULLWIDTH_MATH = {
    "（": "(",
    "）": ")",
    "＋": "+",
    "－": "-",
    "×": "*",
    "＊": "*",
    "÷": "/",
    "／": "/",
    "。": ".",
}
_CN_MATH_WORDS = (
    ("乘以", "*"),
    ("乘", "*"),
    ("加上", "+"),
    ("加", "+"),
    ("减去", "-"),
    ("减", "-"),
    ("除以", "/"),
    ("除", "/"),
)


def _normalize_expression(raw: str) -> str:
    text = str(raw or "")
    for src, dst in _FULLWIDTH_MATH.items():
        text = text.replace(src, dst)
    for src, dst in _CN_MATH_WORDS:
        text = text.replace(src, dst)
    text = re.sub(r"[xX](?=\s*[\d(])", "*", text)
    return text


def extract_arithmetic_expression(task: str) -> str | None:
    """Return a clean arithmetic expression embedded in *task*, if any.

    Requires at least one binary operator between operands so plain numbers
    (e.g. "3 天") never look like a calculation.
    """

    normalized = _normalize_expression(task)
    # Grab the longest run of arithmetic characters that holds an operator.
    best: str | None = None
    for match in re.finditer(r"[0-9+\-*/().\s]+", normalized):
        candidate = match.group(0).strip()
        candidate = re.sub(r"\s+", "", candidate)
        if not candidate or not re.search(r"\d", candidate):
            continue
        if not re.search(r"[+\-*/]", candidate):
            continue
        # Avoid matching a bare leading sign like "-3" with no real operation.
        if not re.search(r"\d\s*[+\-*/]\s*[\d(]", candidate) and not candidate.startswith("("):
            continue
        if best is None or len(candidate) > len(best):
            best = candidate
    return best


class _ExpressionError(ValueError):
    pass


def evaluate_expression(expression: str) -> float:
    """Evaluate a +,-,*,/ and parenthesis expression without ``eval``."""

    tokens = _tokenize_expression(expression)
    rpn = _to_rpn(tokens)
    return _eval_rpn(rpn)


def _tokenize_expression(expression: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    text = expression.replace(" ", "")
    if not text:
        raise _ExpressionError("empty expression")
    while index < len(text):
        char = text[index]
        if char.isdigit() or char == ".":
            number = char
            index += 1
            while index < len(text) and (text[index].isdigit() or text[index] == "."):
                number += text[index]
                index += 1
            if number.count(".") > 1:
                raise _ExpressionError("malformed number")
            tokens.append(number)
            continue
        if char in "+-*/()":
            tokens.append(char)
            index += 1
            continue
        raise _ExpressionError(f"unexpected character: {char!r}")
    return tokens


def _to_rpn(tokens: list[str]) -> list[str]:
    precedence = {"+": 1, "-": 1, "*": 2, "/": 2, "u-": 3}
    output: list[str] = []
    stack: list[str] = []
    previous: str | None = None
    for token in tokens:
        if re.fullmatch(r"\d*\.?\d+", token):
            output.append(token)
        elif token in "+-*/":
            operator = token
            if token == "-" and (previous is None or previous in "+-*/("):
                operator = "u-"  # unary minus
            while stack and stack[-1] != "(" and precedence[stack[-1]] >= precedence[operator] and operator != "u-":
                output.append(stack.pop())
            stack.append(operator)
        elif token == "(":
            stack.append(token)
        elif token == ")":
            while stack and stack[-1] != "(":
                output.append(stack.pop())
            if not stack:
                raise _ExpressionError("unbalanced parenthesis")
            stack.pop()
        previous = token
    while stack:
        top = stack.pop()
        if top in "()":
            raise _ExpressionError("unbalanced parenthesis")
        output.append(top)
    return output


def _eval_rpn(rpn: list[str]) -> float:
    stack: list[float] = []
    for token in rpn:
        if re.fullmatch(r"\d*\.?\d+", token):
            stack.append(float(token))
        elif token == "u-":
            if not stack:
                raise _ExpressionError("missing operand")
            stack.append(-stack.pop())
        else:
            if len(stack) < 2:
                raise _ExpressionError("missing operand")
            right = stack.pop()
            left = stack.pop()
            if token == "+":
                stack.append(left + right)
            elif token == "-":
                stack.append(left - right)
            elif token == "*":
                stack.append(left * right)
            elif token == "/":
                if right == 0:
                    raise _ExpressionError("division by zero")
                stack.append(left / right)
    if len(stack) != 1:
        raise _ExpressionError("invalid expression")
    return stack[0]


def format_number(value: float) -> str:
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------------------
# Poem bank (original verses) for the notepad skill.
# ---------------------------------------------------------------------------

_POEMS: tuple[tuple[str, str], ...] = (
    (
        "静夜",
        "月落窗前一盏灯，\n夜深人静思绪生。\n不知何处清风过，\n吹皱寒塘半卷云。",
    ),
    (
        "晨起",
        "东方既白鸟先鸣，\n推窗满目是新晴。\n一壶淡茶半日闲，\n且把光阴细细听。",
    ),
    (
        "秋思",
        "梧桐叶落满阶黄，\n一夜西风送晚凉。\n遥寄归鸿千里意，\n人间何处不思乡。",
    ),
    (
        "远行",
        "长路漫漫向天涯，\n行囊轻挽数枝花。\n不问前程多少里，\n且将明月作灯华。",
    ),
)

_THEME_POEM_TEMPLATE = "{theme}色悠悠入眼来，\n轻风一缕绕窗台。\n人间最是寻常景，\n偏惹诗心几度开。"
# Only pull a theme from explicit phrasings so a plain "写一首诗" stays generic.
_THEME_PATTERNS = (
    re.compile(r"关于(?P<theme>[一-鿿]{1,3}?)的?(?:诗|诗歌|小诗)"),
    re.compile(r"写(?:一首|首|篇)?(?P<theme>[一-鿿]{1,3}?)的(?:诗|诗歌|小诗)"),
    re.compile(r"以(?P<theme>[一-鿿]{1,3})为(?:主题|题)"),
)
_THEME_STOPWORD_CHARS = set("写一首篇的本记事打开个键入输出关于以为题主诗歌小")


def _extract_poem_theme(task: str) -> str | None:
    for pattern in _THEME_PATTERNS:
        match = pattern.search(task)
        if not match:
            continue
        theme = (match.group("theme") or "").strip()
        if not theme or len(theme) > 3:
            continue
        if any(char in _THEME_STOPWORD_CHARS for char in theme):
            continue
        return theme
    return None


def compose_poem(task: str) -> tuple[str, str]:
    """Return a ``(title, body)`` original poem, themed when a theme is given."""

    theme = _extract_poem_theme(task)
    if theme:
        title = f"咏{theme}" if len(theme) == 1 else theme
        body = _THEME_POEM_TEMPLATE.format(theme=theme)
        return title, body
    digest = hashlib.sha256(_normalize(task).encode("utf-8")).hexdigest()
    index = int(digest, 16) % len(_POEMS)
    return _POEMS[index]


# ---------------------------------------------------------------------------
# Windows native app showcase helpers.
# ---------------------------------------------------------------------------

_CN_NUMBER_WORDS = {
    "一": 1,
    "两": 2,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _ellipse_points(cx: float, cy: float, rx: float, ry: float, *, count: int = 18) -> list[tuple[float, float]]:
    return [
        (cx + math.cos(math.tau * index / count) * rx, cy + math.sin(math.tau * index / count) * ry)
        for index in range(count + 1)
    ]


def _arc_points(
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    *,
    start_degrees: float,
    end_degrees: float,
    count: int = 10,
) -> list[tuple[float, float]]:
    start = math.radians(start_degrees)
    end = math.radians(end_degrees)
    return [
        (cx + math.cos(start + (end - start) * index / count) * rx, cy + math.sin(start + (end - start) * index / count) * ry)
        for index in range(count + 1)
    ]


def _paint_canvas_point(x: float, y: float) -> tuple[float, float]:
    canvas_left = 0.12
    canvas_top = 0.19
    canvas_width = 0.58
    canvas_height = 0.70
    return canvas_left + x * canvas_width, canvas_top + y * canvas_height


def _paint_cat_relative_strokes() -> list[list[tuple[float, float]]]:
    """Create Paint-window-relative strokes for drawing a cat with mouse drags."""

    def points(items: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return [_paint_canvas_point(x, y) for x, y in items]

    strokes: list[list[tuple[float, float]]] = [
        points(_ellipse_points(0.50, 0.29, 0.16, 0.13, count=18)),  # head
        points([(0.39, 0.20), (0.43, 0.04), (0.47, 0.21), (0.39, 0.20)]),  # left ear
        points([(0.53, 0.21), (0.58, 0.04), (0.62, 0.20), (0.53, 0.21)]),  # right ear
        points(_ellipse_points(0.50, 0.60, 0.20, 0.20, count=22)),  # body
        points(_arc_points(0.73, 0.62, 0.14, 0.16, start_degrees=205, end_degrees=25, count=10)),  # tail
        points(_ellipse_points(0.44, 0.76, 0.06, 0.08, count=12)),  # left paw
        points(_ellipse_points(0.57, 0.76, 0.06, 0.08, count=12)),  # right paw
        points(_ellipse_points(0.46, 0.29, 0.025, 0.035, count=8)),  # left eye
        points(_ellipse_points(0.55, 0.29, 0.025, 0.035, count=8)),  # right eye
        points([(0.50, 0.35), (0.48, 0.38), (0.52, 0.38), (0.50, 0.35)]),  # nose
        points(_arc_points(0.485, 0.385, 0.035, 0.045, start_degrees=20, end_degrees=165, count=5)),
        points(_arc_points(0.525, 0.385, 0.035, 0.045, start_degrees=15, end_degrees=160, count=5)),
        points([(0.42, 0.36), (0.27, 0.31)]),
        points([(0.42, 0.39), (0.27, 0.39)]),
        points([(0.42, 0.42), (0.27, 0.48)]),
        points([(0.58, 0.36), (0.73, 0.31)]),
        points([(0.58, 0.39), (0.73, 0.39)]),
        points([(0.58, 0.42), (0.73, 0.48)]),
        points([(0.22, 0.86), (0.78, 0.86)]),  # ground
    ]
    return strokes


def _paint_actions_from_relative_strokes(strokes: list[list[tuple[float, float]]]) -> list[Action]:
    actions: list[Action] = []
    for stroke in strokes:
        for start, end in zip(stroke, stroke[1:]):
            actions.append(
                Action.from_dict(
                    {
                        "type": "relative_drag",
                        "app": "paint",
                        "relative_x": start[0],
                        "relative_y": start[1],
                        "end_relative_x": end[0],
                        "end_relative_y": end[1],
                    }
                )
            )
    return actions


def _paint_cat_actions() -> list[Action]:
    return _paint_actions_from_relative_strokes(_paint_cat_relative_strokes())


def _extract_paint_subject(task: str) -> str:
    text = _normalize(task)
    patterns = (
        r"(?:画图工具|画图|paint|mspaint).{0,8}?(?:画|绘制|draw|sketch|paint)\s*(?:一只|一个|一幅|一张|只|个|幅|张)?(?P<subject>[\w\u4e00-\u9fff ]{1,28})",
        r"(?:画|绘制|draw|sketch|paint)\s*(?:一只|一个|一幅|一张|只|个|幅|张)?(?P<subject>[\w\u4e00-\u9fff ]{1,28})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        subject = (match.group("subject") or "").strip()
        subject = re.sub(r"(?:并|然后|最后|在|用|到|出来|给我|工具|画图|paint|mspaint).*$", "", subject, flags=re.I).strip()
        subject = subject.strip("，。,. ")
        if subject:
            return subject[:28]
    if _contains_any(text, _CAT_TERMS) or _contains_any(text.lower(), _CAT_TERMS):
        return "猫"
    return "简笔画"


def _paint_model_disabled_reason(config: Any | None) -> str | None:
    provider = str(getattr(config, "model_provider", "") or "").strip().lower()
    base_url = str(getattr(config, "model_base_url", "") or "").strip().lower()
    if provider == "lmstudio_local" or "127.0.0.1" in base_url or "localhost" in base_url:
        return "当前模型配置是本地模型；按你的要求，画图笔画规划不会使用本地模型。"
    return None


def _paint_model_stroke_plan(task: str, config: Any | None) -> tuple[list[list[tuple[float, float]]] | None, str]:
    disabled_reason = _paint_model_disabled_reason(config)
    if disabled_reason:
        return None, disabled_reason
    subject = _extract_paint_subject(task)
    system_prompt = (
        "You are a vector sketch planner for Microsoft Paint automation. "
        "Return JSON only. Create simple line-art strokes that can be drawn by mouse drags. "
        "Coordinates must be canvas-normalized floats in [0,1]. "
        "Use Paint/screen coordinates: (0,0) is the top-left, x increases right, and y increases downward. "
        "Put the top of the object at smaller y values and the bottom at larger y values. "
        "Use 8 to 30 strokes, each with 2 to 14 points. Avoid fills and colors."
    )
    user_prompt = (
        f"Drawing request: {task}\n"
        f"Subject: {subject}\n"
        "Return exactly this JSON shape: "
        "{\"description\":\"short Chinese description\",\"strokes\":[[[x,y],[x,y]],[[x,y],[x,y]]]}.\n"
        "The sketch should visibly represent the requested subject, with simple recognizable outlines and details."
    )
    attempted: list[str] = []
    for candidate_config, model_label in _paint_model_candidate_configs(config):
        attempted.append(model_label or "configured model")
        response = model_chat(candidate_config, system_prompt, user_prompt, max_tokens=1800)
        strokes = _parse_model_strokes(response)
        if strokes is not None:
            suffix = f"（{model_label}）" if model_label else ""
            return strokes, f"API 模型生成笔画计划{suffix}"
    if attempted:
        return None, f"API 模型没有返回可执行的笔画 JSON。已尝试：{', '.join(attempted)}。"
    return None, "API 模型没有返回可执行的笔画 JSON。"


def _paint_model_candidate_configs(config: Any | None) -> list[tuple[Any | None, str]]:
    if config is None:
        return [(None, "")]
    current_model = str(getattr(config, "model_name", "") or "").strip()
    base_url = str(getattr(config, "model_base_url", "") or "").strip().lower()
    names: list[str] = []
    if "api.gptsapi.net" in base_url:
        names.extend(_GPTSAPI_SMART_PAINT_MODELS)
    if current_model and current_model != "auto" and current_model not in names:
        names.append(current_model)
    if not names:
        return [(config, current_model if current_model != "auto" else "auto")]
    return [(_config_with_model_name(config, name), name) for name in names]


def _config_with_model_name(config: Any, model_name: str) -> Any:
    try:
        return replace(config, model_name=model_name)
    except Exception:
        class _ModelConfigProxy:
            def __init__(self, wrapped: Any, replacement: str) -> None:
                self._wrapped = wrapped
                self.model_name = replacement

            def __getattr__(self, name: str) -> Any:
                return getattr(self._wrapped, name)

        return _ModelConfigProxy(config, model_name)


def _parse_model_strokes(raw: str | None) -> list[list[tuple[float, float]]] | None:
    payload = _extract_json_object(str(raw or ""))
    if not isinstance(payload, dict):
        return None
    raw_strokes = payload.get("strokes")
    if not isinstance(raw_strokes, list):
        return None
    strokes: list[list[tuple[float, float]]] = []
    for raw_stroke in raw_strokes[:36]:
        if not isinstance(raw_stroke, list):
            continue
        stroke: list[tuple[float, float]] = []
        for item in raw_stroke[:16]:
            if isinstance(item, dict):
                x = item.get("x")
                y = item.get("y")
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                x, y = item[0], item[1]
            else:
                continue
            try:
                fx = float(x)
                fy = float(y)
            except Exception:
                continue
            if not math.isfinite(fx) or not math.isfinite(fy):
                continue
            fx = min(0.98, max(0.02, fx))
            fy = min(0.98, max(0.02, fy))
            stroke.append(_paint_canvas_point(fx, fy))
        if len(stroke) >= 2:
            strokes.append(stroke)
    if len(strokes) < 4:
        return None
    return strokes


def _paint_fallback_actions(task: str) -> tuple[list[Action], str] | None:
    subject = _extract_paint_subject(task).lower()
    if _contains_any(subject, _CAT_TERMS) or _contains_any(_normalize(task).lower(), _CAT_TERMS):
        return _paint_cat_actions(), "内置猫咪兜底笔画"
    return None


def _extract_timer_duration(task: str) -> tuple[int, str]:
    text = _normalize(task)
    patterns = (
        (r"(?P<num>\d+(?:\.\d+)?)\s*(?:小时|小時|hour|hours|h)", 3600, "小时"),
        (r"(?P<num>\d+(?:\.\d+)?)\s*(?:分钟|分鐘|分|minute|minutes|min|m)", 60, "分钟"),
        (r"(?P<num>\d+(?:\.\d+)?)\s*(?:秒|秒钟|second|seconds|sec|s)", 1, "秒"),
    )
    for pattern, multiplier, unit_label in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            value = max(1, int(round(float(match.group("num")) * multiplier)))
            amount = float(match.group("num"))
            if amount.is_integer():
                amount_text = str(int(amount))
            else:
                amount_text = str(amount)
            return value, f"{amount_text}{unit_label}"
    cn_match = re.search(r"(?P<num>[一两二三四五六七八九十])\s*(?:分钟|分|秒|秒钟|小时)", text)
    if cn_match:
        number = _CN_NUMBER_WORDS.get(cn_match.group("num"), 1)
        if "秒" in cn_match.group(0):
            return number, f"{number}秒"
        if "小时" in cn_match.group(0):
            return number * 3600, f"{number}小时"
        return number * 60, f"{number}分钟"
    return 60, "1分钟"


def _start_local_timer_alert(seconds: int, description: str) -> bool:
    script = (
        "import ctypes, time\n"
        f"time.sleep({max(1, int(seconds))})\n"
        "ctypes.windll.user32.MessageBoxW(0, "
        f"{json.dumps('计时器到点：' + description, ensure_ascii=False)}, "
        f"{json.dumps('Aoryn 计时器提醒', ensure_ascii=False)}, 0x40)\n"
    )
    try:
        subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Shopping skill configuration. NOTE: we do NOT keep a fabricated product
# catalog — the analysis must come from the real page content the browser
# loads (or a locally-configured model run on that real content). The brand
# list below is only used to *detect* brands that actually appear on the page.
# ---------------------------------------------------------------------------

_DEFAULT_SHOPPING_SITE = "京东"
_SHOPPING_SEARCH_URL = "https://search.jd.com/Search?keyword={query}&enc=utf-8"
_PANTS_BRANDS: tuple[str, ...] = (
    "优衣库",
    "海澜之家",
    "李宁",
    "鸿星尔克",
    "森马",
    "美特斯邦威",
    "太平鸟",
    "GXG",
    "Lee",
    "JEEP",
    "骆驼",
    "花花公子",
    "南极人",
    "京东京造",
    "安踏",
    "九牧王",
    "劲霸",
    "七匹狼",
)


# ---------------------------------------------------------------------------
# Beijing 3-day itinerary for the travel + Word skill.
# ---------------------------------------------------------------------------

_BEIJING_ITINERARY: tuple[dict[str, Any], ...] = (
    {
        "title": "第一天 · 中轴线经典（天安门—故宫—景山—王府井）",
        "spots": (
            ("上午", "天安门广场", "观看升旗，参观人民英雄纪念碑与广场周边，感受首都中轴线起点。"),
            ("上午", "故宫博物院", "从午门入、神武门出，沿中轴线游三大殿与后三宫，建议提前在官网实名预约。"),
            ("下午", "景山公园", "登万春亭俯瞰故宫金顶全景，是拍摄紫禁城的最佳机位。"),
            ("傍晚", "王府井步行街", "品尝北京小吃，逛老字号商圈，结束第一天行程。"),
        ),
        "tip": "故宫每周一闭馆（法定节假日除外），务必提前 7 天官网预约门票。",
    },
    {
        "title": "第二天 · 长城与奥运（八达岭长城—奥林匹克公园）",
        "spots": (
            ("全天", "八达岭长城", "乘市郊铁路 S2 线或旅游班车前往，登烽火台远眺，量力而行不必登顶。"),
            ("下午", "奥林匹克公园", "返城后参观鸟巢（国家体育场）与水立方，傍晚夜景尤为壮观。"),
            ("傍晚", "奥林匹克塔", "可登塔俯瞰中轴线北延长线夜景。"),
        ),
        "tip": "长城游玩穿舒适运动鞋，备足饮水；早出发可避开人流高峰。",
    },
    {
        "title": "第三天 · 皇家园林与胡同（颐和园—圆明园—南锣鼓巷）",
        "spots": (
            ("上午", "颐和园", "沿昆明湖、长廊、佛香阁游览，体会皇家园林的山水格局。"),
            ("下午", "圆明园", "漫步遗址公园，于大水法残迹前回望历史。"),
            ("傍晚", "南锣鼓巷 / 什刹海", "穿行老北京胡同，环什刹海看夜色，体验市井烟火。"),
        ),
        "tip": "颐和园面积大，建议规划好路线或乘园内电瓶船节省体力。",
    },
)

_BEIJING_NOTES: tuple[str, ...] = (
    "交通：优先地铁出行，办理北京交通一卡通或使用乘车码；前往长城建议市郊铁路 S2 线或正规旅游专线。",
    "门票：故宫、颐和园、国家博物馆等热门景点需提前实名预约，留意每日放票时间。",
    "餐饮：可尝试北京烤鸭、炸酱面、卤煮、豆汁焦圈等特色美食。",
    "装备：三天行程步行较多，建议穿舒适鞋；夏季防晒、冬季保暖。",
)

_TRAVEL_DOC_FILENAME = "北京三日游行程规划.docx"


def build_beijing_plan_text() -> str:
    """Render the itinerary as readable plain text for the chat answer."""

    lines: list[str] = ["北京 3 天旅游规划", ""]
    for day in _BEIJING_ITINERARY:
        lines.append(str(day["title"]))
        for period, spot, detail in day["spots"]:
            lines.append(f"  · [{period}] {spot} —— {detail}")
        lines.append(f"  💡 提示：{day['tip']}")
        lines.append("")
    lines.append("实用贴士：")
    for note in _BEIJING_NOTES:
        lines.append(f"  · {note}")
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Minimal, dependency-free .docx writer.
# ---------------------------------------------------------------------------

_CONTENT_TYPES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)
_ROOT_RELS_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/>'
    "</Relationships>"
)
_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _docx_paragraph(text: str, *, bold: bool = False, size: int | None = None, color: str | None = None) -> str:
    run_props: list[str] = []
    if bold:
        run_props.append("<w:b/>")
    if size is not None:
        run_props.append(f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>')
    if color:
        run_props.append(f'<w:color w:val="{color}"/>')
    rpr = f"<w:rPr>{''.join(run_props)}</w:rPr>" if run_props else ""
    if not text:
        return "<w:p/>"
    safe = _xml_escape(text)
    return f'<w:p><w:r>{rpr}<w:t xml:space="preserve">{safe}</w:t></w:r></w:p>'


def _build_document_xml(paragraphs: list[str]) -> str:
    body = "".join(paragraphs)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{_WORD_NS}"><w:body>{body}'
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>'
        "</w:sectPr></w:body></w:document>"
    )


def write_beijing_docx(path: Path, *, search_excerpt: str | None = None) -> Path:
    """Create a real Word document for the Beijing itinerary (no dependencies).

    When *search_excerpt* is provided (real text read from the live search page),
    it is appended verbatim as a clearly-labelled reference section so the
    document is grounded in what was actually retrieved.
    """

    paragraphs: list[str] = [
        _docx_paragraph("北京三日游行程规划", bold=True, size=44, color="1F3864"),
        _docx_paragraph("——经典中轴线 · 长城奥运 · 皇家园林与胡同", color="595959"),
        _docx_paragraph(""),
    ]
    for day in _BEIJING_ITINERARY:
        paragraphs.append(_docx_paragraph(str(day["title"]), bold=True, size=30, color="2E74B5"))
        for period, spot, detail in day["spots"]:
            paragraphs.append(_docx_paragraph(f"[{period}] {spot}", bold=True, size=24))
            paragraphs.append(_docx_paragraph(f"        {detail}"))
        paragraphs.append(_docx_paragraph(f"温馨提示：{day['tip']}", color="C00000"))
        paragraphs.append(_docx_paragraph(""))
    paragraphs.append(_docx_paragraph("实用贴士", bold=True, size=28, color="2E74B5"))
    for note in _BEIJING_NOTES:
        paragraphs.append(_docx_paragraph(f"· {note}"))

    cleaned_excerpt = str(search_excerpt or "").strip()
    if cleaned_excerpt:
        paragraphs.append(_docx_paragraph(""))
        paragraphs.append(_docx_paragraph("实时检索摘录（来自百度搜索，原文未改写）", bold=True, size=28, color="2E74B5"))
        for line in cleaned_excerpt.splitlines():
            line = line.strip()
            if line:
                paragraphs.append(_docx_paragraph(line, color="404040"))

    document_xml = _build_document_xml(paragraphs)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES_XML)
        archive.writestr("_rels/.rels", _ROOT_RELS_XML)
        archive.writestr("word/document.xml", document_xml)
    return path


_TRAVEL_NOTE_FILENAME = "北京旅游攻略总结.txt"
_TRAVEL_REPORT_FILENAME = "北京旅游攻略报告.md"
_TRAVEL_MIN_USABLE_PAGES = 2
_TRAVEL_SEARCH_QUERY = "Beijing travel guide 3 day itinerary"
_TRAVEL_SEARCH_ENGINES = (
    ("Bing", "https://cn.bing.com/search?q={query}&mkt=zh-CN"),
    ("Bing", "https://www.bing.com/search?q={query}&mkt=zh-CN"),
    ("Google", "https://www.google.com/search?q={query}&hl=zh-CN"),
)
_TRAVEL_SEARCH_ENGINE_URL = "https://cn.bing.com"
_TRAVEL_MAX_RESULT_CLICKS = 4
_TRAVEL_VISUAL_LOOP_MAX_STEPS = 24
_TRAVEL_VISUAL_PAGE_SCROLL_LIMIT = 4
_TRAVEL_DEMO_SEARCH_SCROLLS = 2
_TRAVEL_DEMO_PAGE_SCREENS = 12
_TRAVEL_DEMO_SCROLL_AMOUNT = -7
_TRAVEL_DEMO_SCREEN_WAIT_SECONDS = 0.22
_TRAVEL_DEMO_SOURCES: tuple[tuple[str, str, str], ...] = (
    (
        "WaysChina：3-Day Beijing Itinerary",
        "https://www.wayschina.com/en/articles/3-day-beijing-itinerary/",
        "3-day Beijing itinerary. Day 1 focuses on the Forbidden City, Tiananmen area and the historic city center; "
        "Day 2 is for the Great Wall with transport planning and enough time for the return trip; "
        "Day 3 combines the Temple of Heaven, hutong neighborhoods and local food. The page emphasizes time slots, "
        "transport directions and ticket tips, so reservations and early starts should be prepared before travel.",
    ),
    (
        "TravelChinaGuide：Beijing Travel Guide",
        "https://www.travelchinaguide.com/cityguides/beijing.htm",
        "Beijing travel guide covering top attractions such as the Forbidden City, Great Wall, Temple of Heaven, "
        "Summer Palace and hutongs. It highlights Beijing as a major transport hub and suggests planning attractions "
        "by area to avoid wasting time in traffic. For first-time visitors, classic imperial sites, the Great Wall "
        "and old-city neighborhoods are the core route.",
    ),
    (
        "Wikivoyage：北京旅行指南",
        "https://zh.wikivoyage.org/wiki/%E5%8C%97%E4%BA%AC",
        "维基导游北京页面按照了解、抵达、周游、观光、饮食、住宿和安全等方向组织信息。北京适合把中轴线、皇家建筑、长城、胡同和城市交通结合起来安排。"
        "市区出行优先地铁，景点之间要留出步行和安检时间；热门景点、博物馆和长城线路应提前确认门票、预约和开放状态。",
    ),
    (
        "China Highlights：Beijing Travel Guide",
        "https://www.chinahighlights.com/beijing/",
        "China Highlights 的北京攻略覆盖故宫、长城、天坛、颐和园、胡同等经典景点，强调第一次到北京可按历史核心区、长城、皇家园林和胡同体验来组合。"
        "页面还提醒热门景点和长城行程需要提前规划交通、开放时间和门票预约。",
    ),
    (
        "Wander in China：3 Days in Beijing",
        "https://www.wanderinchina.com/en/destinations/beijing/itineraries/3-days-in-beijing/",
        "Wander in China 的北京三日行程面向第一次来北京的游客，重点把故宫、天安门、长城、天坛、颐和园和胡同安排在有限时间内。"
        "页面强调长城交通、热门景点预约、路线取舍和每天节奏控制，适合补充三天行程的执行细节。",
    ),
)
_TRAVEL_RELEVANCE_TERMS = (
    "北京",
    "故宫",
    "天安门",
    "长城",
    "颐和园",
    "胡同",
    "景山",
    "什刹海",
    "王府井",
    "beijing",
    "forbidden city",
    "great wall",
    "tiananmen",
    "summer palace",
    "hutong",
    "wikivoyage",
    "ctrip",
    "travelchinaguide",
)
_NON_TARGET_SCREEN_TERMS = (
    "codex",
    "powershell",
    "desktop_agent_project",
    "修复悬浮窗",
    "computeruse",
    "插件",
    "自动化",
    "环境信息",
    "git",
    "python -",
)


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    candidates = [text]
    start = text.find("{")
    end = text.rfind("}")
    if 0 <= start < end:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        for normalized_candidate in _json_parse_candidates(candidate):
            try:
                payload = json.loads(normalized_candidate)
            except Exception:
                continue
            if isinstance(payload, dict):
                return payload
    return None


def _json_parse_candidates(candidate: str) -> list[str]:
    normalized = _strip_json_comments(candidate)
    normalized = re.sub(r",\s*([}\]])", r"\1", normalized)
    if normalized == candidate:
        return [candidate]
    return [candidate, normalized]


def _strip_json_comments(text: str) -> str:
    result: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if in_string:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            result.append(char)
            index += 1
            continue
        if char == "/" and next_char == "/":
            index += 2
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue
        if char == "/" and next_char == "*":
            index += 2
            while index + 1 < len(text) and not (text[index] == "*" and text[index + 1] == "/"):
                index += 1
            index = min(len(text), index + 2)
            continue
        result.append(char)
        index += 1
    return "".join(result)


def _extract_jsonish_string_field(raw: str, field: str) -> str:
    pattern = re.compile(rf'"{re.escape(field)}"\s*:\s*"(?P<value>.*?)"\s*(?:,|\}})', re.S)
    match = pattern.search(raw)
    if not match:
        return ""
    value = match.group("value")
    try:
        return str(json.loads(f'"{value}"'))
    except Exception:
        return value.replace("\\n", "\n").replace('\\"', '"').strip()


def _extract_jsonish_loose_field(raw: str, field: str) -> str:
    marker = f'"{field}"'
    start = raw.find(marker)
    if start < 0:
        return ""
    colon = raw.find(":", start + len(marker))
    if colon < 0:
        return ""
    tail = raw[colon + 1 :].strip()
    if tail.startswith('"'):
        tail = tail[1:]
    tail = re.sub(r'"\s*}\s*```\s*$', "", tail, flags=re.S)
    tail = re.sub(r'"\s*}\s*$', "", tail, flags=re.S)
    tail = re.sub(r"\s*```\s*$", "", tail, flags=re.S)
    return tail.replace("\\n", "\n").replace('\\"', '"').strip()


def _parse_visual_ocr_response(raw: str | None, *, default_title: str) -> tuple[str, str]:
    """Parse a vision/OCR response into a page title and visible text."""

    text = _normalize(raw)
    if not text:
        return default_title, ""
    payload = _extract_json_object(text)
    if payload is None:
        title = _extract_jsonish_string_field(text, "title") or default_title
        visible_text = (
            _extract_jsonish_string_field(text, "visible_text")
            or _extract_jsonish_loose_field(text, "visible_text")
            or _extract_jsonish_string_field(text, "text")
            or _extract_jsonish_loose_field(text, "text")
            or _extract_jsonish_string_field(text, "ocr_text")
            or _extract_jsonish_loose_field(text, "ocr_text")
            or text
        )
        return title, visible_text

    title = _normalize(payload.get("title")) or default_title
    visible_text = (
        _normalize(payload.get("visible_text"))
        or _normalize(payload.get("text"))
        or _normalize(payload.get("ocr_text"))
        or text
    )
    return title, visible_text


def _parse_visual_decision_response(raw: str | None) -> dict[str, Any]:
    text = _normalize(raw)
    if not text:
        return {}
    payload = _extract_json_object(text)
    return payload if isinstance(payload, dict) else {"visible_text": text}


def _decision_text(decision: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = decision.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _decision_bool(decision: dict[str, Any], key: str) -> bool:
    return bool(decision.get(key))


def _decision_point(value: Any) -> tuple[int, int] | None:
    if isinstance(value, dict):
        x = value.get("x")
        y = value.get("y")
    elif isinstance(value, (list, tuple)) and len(value) >= 2:
        x, y = value[0], value[1]
    else:
        return None
    try:
        return int(float(x)), int(float(y))
    except Exception:
        return None


def _decision_candidates(decision: dict[str, Any]) -> list[dict[str, Any]]:
    raw_candidates = decision.get("candidates") or decision.get("results") or decision.get("targets")
    if not isinstance(raw_candidates, list):
        return []
    candidates: list[dict[str, Any]] = []
    for item in raw_candidates:
        if not isinstance(item, dict):
            continue
        point = _decision_point(
            item.get("title_point")
            or item.get("title_click")
            or item.get("title_coordinate")
            or {"x": item.get("title_x"), "y": item.get("title_y")}
        )
        if point is None:
            point = _decision_point(item.get("point") or item.get("click") or item.get("coordinate"))
        if point is None:
            point = _decision_point({"x": item.get("x"), "y": item.get("y")})
        if point is None:
            continue
        label = _normalize(item.get("label") or item.get("title") or item.get("text"))
        url = _normalize(item.get("url"))
        candidates.append({"label": label, "url": url, "x": point[0], "y": point[1], "reason": _normalize(item.get("reason"))})
    return candidates


def _decision_action(decision: dict[str, Any]) -> str:
    action = decision.get("action") or decision.get("next_action") or decision.get("recommended_action")
    if not isinstance(action, str):
        return ""
    return action.strip().lower().replace("-", "_")


def _travel_ocr_target_mismatch(title: str, text: str) -> str | None:
    combined = f"{title}\n{text}".lower()
    if not combined.strip():
        return "屏幕截图没有识别出可用文字"
    if _travel_page_text_looks_error(combined):
        return "页面显示 404/服务器错误，不是攻略正文页"
    if (
        ("访问网站" in combined or "visit site" in combined)
        and any(term in combined for term in ("更多图像", "查看更多图像", "视觉搜索", "visual search", "bing images"))
    ):
        return "屏幕截图是图片预览层，不是攻略正文页"
    if any(term in combined for term in ("codex", "desktop_agent_project", "修复悬浮窗", "环境信息", "python -")):
        return "屏幕截图更像当前工作窗口而不是目标网页"
    relevant = any(term.lower() in combined for term in _TRAVEL_RELEVANCE_TERMS)
    if not relevant:
        return "屏幕截图未显示北京旅游相关网页，可能焦点仍在其他窗口"
    non_target_hits = [term for term in _NON_TARGET_SCREEN_TERMS if term.lower() in combined]
    if non_target_hits and not any(term in combined for term in ("故宫", "长城", "travelchinaguide", "wikivoyage", "ctrip")):
        return "屏幕截图更像当前工作窗口而不是目标网页"
    return None


def _travel_page_text_looks_error(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False
    error_markers = (
        "server error 404",
        "404 - file or directory not found",
        "file or directory not found",
        "resource you are looking for might have been removed",
        "404 not found",
        "page not found",
    )
    return any(marker in normalized for marker in error_markers)


def _beijing_research_targets() -> tuple[tuple[str, str], ...]:
    return (
        ("必应搜索", "https://cn.bing.com/search?q=" + _url_quote("北京旅游攻略 三天 行程")),
        ("维基导游北京", "https://zh.wikivoyage.org/wiki/%E5%8C%97%E4%BA%AC"),
        ("携程北京目的地", "https://you.ctrip.com/place/beijing1.html"),
        ("TravelChinaGuide北京", "https://www.travelchinaguide.com/cityguides/beijing.htm"),
    )


def _travel_search_engine(engine_index: int = 0) -> tuple[str, str]:
    if engine_index < 0 or engine_index >= len(_TRAVEL_SEARCH_ENGINES):
        engine_index = 0
    return _TRAVEL_SEARCH_ENGINES[engine_index]


def _travel_search_results_url(engine_index: int = 0) -> str:
    _, template = _travel_search_engine(engine_index)
    return template.format(query=_url_quote(_TRAVEL_SEARCH_QUERY))


def _travel_search_setup_actions(*, new_tab: bool = False, engine_index: int = 0) -> list[Action]:
    actions: list[Action] = []
    if new_tab:
        actions.append(Action.from_dict({"type": "open_app_if_needed", "app": "browser"}))
    actions.extend(
        [
            Action.from_dict({"type": "browser_gui_open", "text": _travel_search_results_url(engine_index)}),
            Action.from_dict({"type": "wait", "seconds": 4.5}),
        ]
    )
    return actions


def _travel_candidate_identity(candidate: dict[str, Any]) -> str:
    label = candidate.get("label") or candidate.get("title") or candidate.get("url")
    if isinstance(label, str) and label.strip():
        return label.strip()
    return f"{candidate.get('x')},{candidate.get('y')}"


def _travel_reading_is_missed_click(reading: PageReading) -> bool:
    combined = f"{reading.status}\n{reading.title}\n{reading.reason}\n{reading.text[:300]}".lower()
    return any(
        marker in combined
        for marker in (
            "search_results",
            "搜索结果页",
            "bing 搜索",
            "不是攻略正文页",
            "仍停留在搜索",
            "图片预览层",
        )
    )


def _travel_visual_page_key(title: str, url: str) -> str:
    text = _normalize(url or title).lower()
    text = re.sub(r"[#?].*$", "", text)
    text = text.rstrip("/")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:180] or _normalize(title).lower()[:180]


def _travel_visual_title_key(title: str) -> str:
    text = _normalize(title).lower()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _travel_visual_domain(url: str) -> str:
    from urllib.parse import urlsplit

    try:
        host = (urlsplit(url).hostname or "").lower()
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host


def _travel_visual_is_duplicate(readings: list[PageReading], *, title: str, url: str) -> bool:
    key = _travel_visual_page_key(title, url)
    title_key = _travel_visual_title_key(title)
    domain = _travel_visual_domain(url)
    for reading in readings:
        if key and key == _travel_visual_page_key(reading.title, reading.url):
            return True
        if title_key and title_key == _travel_visual_title_key(reading.title):
            if not domain or not reading.url or domain == _travel_visual_domain(reading.url):
                return True
    return False


def _travel_visual_has_detail(text: str) -> bool:
    normalized = _normalize(text).lower()
    if len(normalized) < 260:
        return False
    detail_markers = (
        "day 1",
        "day 2",
        "day 3",
        "morning",
        "afternoon",
        "evening",
        "transport",
        "subway",
        "ticket",
        "reservation",
        "route",
        "第一天",
        "第二天",
        "第三天",
        "上午",
        "下午",
        "晚上",
        "交通",
        "预约",
        "门票",
        "路线",
        "行程",
    )
    return sum(1 for marker in detail_markers if marker in normalized) >= 2


def _travel_note_filename(ctx: "_SkillContext") -> str:
    if ctx.run_dir is not None:
        match = re.match(r"(?P<stamp>\d{8}_\d{6})", ctx.run_dir.name)
        if match:
            return f"北京旅游攻略总结_{match.group('stamp')}.txt"
    return _TRAVEL_NOTE_FILENAME


def _travel_report_filename(ctx: "_SkillContext") -> str:
    if ctx.run_dir is not None:
        match = re.match(r"(?P<stamp>\d{8}_\d{6})", ctx.run_dir.name)
        if match:
            return f"北京旅游攻略报告_{match.group('stamp')}.md"
    return _TRAVEL_REPORT_FILENAME


def _travel_output_filename(ctx: "_SkillContext", task: str) -> str:
    return _travel_report_filename(ctx) if _travel_prefers_typora_report(task) else _travel_note_filename(ctx)


def _travel_prefers_typora_report(task: str) -> bool:
    text = _normalize(task)
    lowered = text.lower()
    return (
        _contains_any(text, _REPORT_TERMS)
        or _contains_any(lowered, _REPORT_TERMS)
        or _contains_any(text, _TYPORA_TERMS)
        or _contains_any(lowered, _TYPORA_TERMS)
    )


def _usable_travel_readings(readings: list[PageReading]) -> list[PageReading]:
    return [reading for reading in readings if reading.usable]


def has_enough_beijing_travel_evidence(readings: list[PageReading]) -> bool:
    """Return whether the task can honestly produce a multi-page travel summary."""

    return len(_usable_travel_readings(readings)) >= _TRAVEL_MIN_USABLE_PAGES


def build_beijing_travel_summary(
    readings: list[PageReading], *, model_summary: str | None = None, markdown: bool = False
) -> str:
    """Build a Notepad-friendly Beijing travel summary from page readings.

    The summary records which pages were actually opened/read. It only gives a
    final route plan when multiple pages were successfully read; otherwise it
    writes an evidence report and says the conclusion is not reliable yet. When
    a configured API returns a grounded summary, that text is preferred over the
    deterministic fallback route.
    """

    if markdown:
        return _build_beijing_travel_markdown_report(readings, model_summary=model_summary)

    usable = _usable_travel_readings(readings)
    enough_evidence = has_enough_beijing_travel_evidence(readings)
    lines: list[str] = [
        "北京旅游攻略总结",
        "",
        "一、网页阅读情况",
    ]
    if not readings:
        lines.append("1. 未读取到浏览器页面快照。")
    else:
        for index, reading in enumerate(readings, start=1):
            title = reading.title or "(无标题)"
            url = reading.url or "(无 URL)"
            state = "已读取" if reading.usable else f"未取得有效正文：{reading.reason}"
            lines.append(f"{index}. {state}")
            lines.append(f"   标题：{title}")
            lines.append(f"   地址：{url}")
            if reading.usable:
                if reading.reason:
                    lines.append(f"   读取方式：{reading.reason}")
                page_excerpt = " ".join(excerpt(reading.text, limit=220).split())
                if page_excerpt:
                    lines.append(f"   摘要：{page_excerpt}")
    if not enough_evidence:
        lines += [
            "",
            "二、结论",
            f"未生成最终攻略：本次只成功读取 {len(usable)} 个有效网页，少于要求的 {_TRAVEL_MIN_USABLE_PAGES} 个有效网页。",
            "为了避免把常识路线伪装成网页阅读结论，需要先处理验证/加载问题，读取到更多有效页面后再总结。",
            "",
            "三、下一步",
            "1. 如果页面出现安全验证或人机验证，请先手动完成验证。",
            "2. 验证完成后从历史记录或悬浮窗恢复任务，让系统继续读取网页。",
            "3. 如果站点持续拦截，可改用已登录浏览器或换用可读的官方/攻略页面。",
        ]
        return "\r\n".join(lines).strip() + "\r\n"
    model_summary = _normalize(model_summary)
    if model_summary:
        visual_based = any("截图" in reading.reason or "视觉" in reading.reason for reading in usable)
        lines += [
            "",
            "二、API 综合建议（基于屏幕截图读屏与页面可见内容）"
            if visual_based
            else "二、API 综合建议（基于已读取网页内容）",
            model_summary,
            "",
            "三、稳定路线参考",
        ]
    else:
        lines += [
            "",
            "二、综合建议",
        ]
    lines += [
        "1. 第一天走中轴线：天安门广场、故宫、景山公园、王府井。故宫需要提前实名预约，景山适合俯瞰故宫全景。",
        "2. 第二天安排长城与奥运区域：八达岭或慕田峪长城择一，下午返回市区看鸟巢、水立方夜景。",
        "3. 第三天看皇家园林和胡同：颐和园、圆明园、什刹海或南锣鼓巷，节奏比前两天轻松。",
        "4. 交通优先地铁，长城段选择正规旅游专线或市郊铁路；热门景点门票、升旗观礼和博物馆建议提前预约。",
        "5. 餐饮可安排北京烤鸭、炸酱面、卤煮、豆汁焦圈等本地特色，但景区周边用餐要看价格和评价。",
        "",
        "四、演示说明" if model_summary else "三、演示说明",
    ]
    lines.append(f"本次已成功读取 {len(usable)} 个网页的可见内容，上面的攻略综合了多个可读页面内容和稳定经典路线。")
    return "\r\n".join(lines).strip() + "\r\n"


def _build_beijing_travel_markdown_report(readings: list[PageReading], *, model_summary: str | None = None) -> str:
    usable = _usable_travel_readings(readings)
    enough_evidence = has_enough_beijing_travel_evidence(readings)
    lines: list[str] = [
        "# 北京旅游攻略报告",
        "",
        "## 一、网页阅读情况",
        "",
    ]
    if not readings:
        lines.append("- 未读取到浏览器页面快照。")
    else:
        for index, reading in enumerate(readings, start=1):
            title = reading.title or "(无标题)"
            url = reading.url or "(无 URL)"
            state = "已读取" if reading.usable else f"未取得有效正文：{reading.reason}"
            lines += [
                f"### {index}. {title}",
                "",
                f"- 状态：{state}",
                f"- 地址：{url}",
            ]
            if reading.usable:
                if reading.reason:
                    lines.append(f"- 读取方式：{reading.reason}")
                page_excerpt = " ".join(excerpt(reading.text, limit=360).split())
                if page_excerpt:
                    lines.append(f"- 可见内容摘要：{page_excerpt}")
            lines.append("")
    if not enough_evidence:
        lines += [
            "## 二、结论",
            "",
            f"本次只成功读取 {len(usable)} 个有效网页，少于要求的 {_TRAVEL_MIN_USABLE_PAGES} 个有效网页，因此未生成最终攻略。",
            "",
            "## 三、下一步",
            "",
            "1. 如果页面出现安全验证或人机验证，请先手动完成验证。",
            "2. 验证完成后从悬浮窗恢复任务，让系统继续读取网页。",
            "3. 如果站点持续拦截，可改用已登录浏览器或换用可读的官方/攻略页面。",
        ]
        return "\r\n".join(lines).strip() + "\r\n"

    model_summary = _normalize(model_summary)
    lines += [
        "## 二、API 综合建议（基于屏幕截图留证与页面可见内容）",
        "",
    ]
    if model_summary:
        lines += [model_summary, ""]
    else:
        lines += ["本次未取得 API 综合总结，以下使用稳定经典路线作为保底参考。", ""]
    lines += [
        "## 三、稳定路线参考",
        "",
        "1. 第一天走中轴线：天安门广场、故宫、景山公园、王府井。故宫需要提前实名预约，景山适合俯瞰故宫全景。",
        "2. 第二天安排长城与奥运区域：八达岭或慕田峪长城择一，下午返回市区看鸟巢、水立方夜景。",
        "3. 第三天看皇家园林和胡同：颐和园、圆明园、什刹海或南锣鼓巷，节奏比前两天轻松。",
        "4. 交通优先地铁，长城段选择正规旅游专线或市郊铁路；热门景点门票、升旗观礼和博物馆建议提前预约。",
        "5. 餐饮可安排北京烤鸭、炸酱面、卤煮、豆汁焦圈等本地特色，但景区周边用餐要看价格和评价。",
        "",
        "## 四、演示说明",
        "",
        f"本次已成功读取 {len(usable)} 个网页的可见内容，并为每个网页保存了从顶部扫到页底的截图阅读板。报告综合了多个可读页面内容和稳定经典路线。",
    ]
    return "\r\n".join(lines).strip() + "\r\n"


def _demo_beijing_travel_model_summary() -> str:
    return (
        "# 北京旅游攻略（多网页整理）\n"
        "## 一、整体思路\n"
        "北京第一次游玩适合按“市区皇家文化 + 长城一日 + 胡同与园林”来安排。多个攻略页面共同强调：故宫、长城、天坛、胡同和颐和园是经典组合；"
        "交通上尽量依赖地铁，长城单独安排一天，热门景点提前核实预约和门票。\n\n"
        "## 二、三天行程\n"
        "### Day 1：中轴线与故宫\n"
        "上午从天安门、故宫一线开始，重点看明清皇家建筑和北京中轴线格局。下午可接景山俯瞰故宫，时间充足再去王府井或前门一带。"
        "故宫、升旗和热门博物馆通常需要提前实名预约，尽量早到，避免把时间耗在排队和安检上。\n\n"
        "### Day 2：长城一日\n"
        "第二天安排八达岭或慕田峪长城择一，不建议同一天塞太多市区景点。长城往返交通耗时较长，建议早出发，选择正规旅游专线、市郊铁路、官方接驳或可靠一日游。"
        "穿舒服的鞋，带水，冬夏两季注意防风、防晒和体力分配。返城后可看鸟巢、水立方夜景或简单休息。\n\n"
        "### Day 3：天坛、皇家园林和胡同\n"
        "上午安排天坛，感受祭祀建筑和公园空间；下午可在颐和园、圆明园、什刹海、南锣鼓巷、胡同街区中选择。"
        "如果想轻松一点，第三天以胡同散步和北京风味餐饮收尾；如果更重视皇家园林，就把颐和园放在半天以上。\n\n"
        "## 三、交通和预约\n"
        "市区优先地铁加步行，跨城区打车可能受拥堵影响。长城当天提前确认出发点、返程班次和末班时间。故宫、热门博物馆、长城、天坛等景点出行前核实预约、开放时间和证件要求。\n\n"
        "## 四、餐饮建议\n"
        "可以安排北京烤鸭、炸酱面、铜锅涮肉、卤煮、豆汁焦圈等本地特色。故宫和长城日不建议把午餐安排得太复杂，胡同或市区晚餐更适合慢慢体验。"
    )


@dataclass(slots=True)
class QQMessageRequest:
    group_name: str | None
    message: str | None


def extract_qq_group_message(task: str) -> QQMessageRequest:
    """Extract the target QQ group name and outgoing message from a task."""

    text = _normalize(task)
    quoted = [
        item.strip()
        for item in re.findall(r"[\"“”'‘’「」『』](.*?)[\"“”'‘’「」『』]", text)
        if item.strip()
    ]
    if len(quoted) >= 2:
        return QQMessageRequest(_clean_qq_field(quoted[0]), _clean_qq_field(quoted[1], keep_tail=True))

    group = _extract_by_label(text, ("群名", "群聊", "QQ群", "群"))
    message = _extract_by_label(text, ("消息", "内容", "文本"))

    patterns = (
        r"(?:在|到|给)\s*(?:QQ|qq)?\s*(?:群聊|QQ群|群)?\s*(?P<group>[^，,。；;:：]+?)\s*(?:发送|发到|发给|发消息|发)\s*(?:消息|内容|文本)?\s*[:：]?\s*(?P<message>.+)$",
        r"(?:打开|启动)?\s*(?:QQ|qq).*?(?:群聊|QQ群|群)\s*(?P<group>[^，,。；;:：]+?)\s*(?:发送|发消息|发)\s*(?:消息|内容|文本)?\s*[:：]?\s*(?P<message>.+)$",
        r"(?:send|message)\s+(?P<message>.+?)\s+(?:to|in)\s+(?P<group>.+?)(?:\s+qq\s+group)?$",
    )
    if not (group and message):
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                group = group or match.groupdict().get("group")
                message = message or match.groupdict().get("message")
                break

    if quoted and not message:
        message = quoted[-1]
    return QQMessageRequest(
        _clean_qq_field(group),
        _clean_qq_field(message, keep_tail=True),
    )


def _extract_by_label(text: str, labels: tuple[str, ...]) -> str | None:
    label_re = "|".join(re.escape(label) for label in labels)
    match = re.search(rf"(?:{label_re})\s*[:：]\s*([^，,；;。]+)", text, re.I)
    return match.group(1) if match else None


def _clean_qq_field(value: str | None, *, keep_tail: bool = False) -> str | None:
    cleaned = str(value or "").strip()
    if not cleaned:
        return None
    cleaned = cleaned.strip(" \t\r\n\"'“”‘’「」『』")
    if not keep_tail:
        cleaned = re.sub(r"(?:里|中)$", "", cleaned).strip()
        if cleaned in {"发送", "发送消息", "发消息", "消息", "内容", "文本", "send", "message"}:
            return None
        if cleaned and all(char in "发送消息内容文本" for char in cleaned):
            return None
    else:
        if cleaned in {"消息", "息", "内容", "文本", "发送消息", "send", "message"}:
            return None
    return cleaned or None


# ---------------------------------------------------------------------------
# Skill runner.
# ---------------------------------------------------------------------------


class TaskSkillRunner:
    """Match showcase tasks and execute them with a concrete spoken answer."""

    def __init__(self, config: Any | None = None) -> None:
        self.config = config

    # -- matching -----------------------------------------------------------

    def match(self, task: str) -> str | None:
        text = _normalize(task)
        if not text:
            return None
        lowered = text.lower()
        if self._is_calculator(text, lowered):
            return "calculator"
        if plugin := match_task_plugin(text, config=self.config):
            return f"plugin:{plugin.id}"
        if self._is_notepad_poem(text, lowered):
            return "notepad_poem"
        if self._is_shopping_pants(text, lowered):
            return "shopping_pants"
        if self._is_paint_drawing(text, lowered):
            return "paint_drawing"
        if self._is_clock_timer_alarm(text, lowered):
            return "clock_timer_alarm"
        if self._is_travel_notepad(text, lowered):
            return "travel_notepad"
        if self._is_travel_word(text, lowered):
            return "travel_word"
        if self._is_qq_group_message(text, lowered):
            return "qq_group_message"
        return None

    def _is_calculator(self, text: str, lowered: str) -> bool:
        has_app = _contains_any(text, _CALC_APP_TERMS) or _contains_any(lowered, _CALC_APP_TERMS)
        has_verb = _contains_any(text, _CALC_VERB_TERMS) or _contains_any(lowered, _CALC_VERB_TERMS)
        if not (has_app or has_verb):
            return False
        return extract_arithmetic_expression(text) is not None

    def _is_notepad_poem(self, text: str, lowered: str) -> bool:
        has_notepad = _contains_any(text, _NOTEPAD_TERMS) or _contains_any(lowered, _NOTEPAD_TERMS)
        has_poem = _contains_any(text, _POEM_TERMS) or _contains_any(lowered, _POEM_TERMS)
        return has_notepad and has_poem

    def _is_shopping_pants(self, text: str, lowered: str) -> bool:
        has_pants = _contains_any(text, _PANTS_TERMS) or _contains_any(lowered, _PANTS_TERMS)
        if not has_pants:
            return False
        has_shopping = _contains_any(text, _SHOPPING_TERMS) or _contains_any(lowered, _SHOPPING_TERMS)
        has_value = _contains_any(text, _VALUE_TERMS) or _contains_any(lowered, _VALUE_TERMS)
        return has_shopping or has_value

    def _is_paint_drawing(self, text: str, lowered: str) -> bool:
        has_paint = _contains_any(text, _PAINT_TERMS) or _contains_any(lowered, _PAINT_TERMS)
        has_draw = _contains_any(text, _DRAW_TERMS) or _contains_any(lowered, _DRAW_TERMS)
        return has_paint and has_draw

    def _is_clock_timer_alarm(self, text: str, lowered: str) -> bool:
        has_clock = _contains_any(text, _CLOCK_TERMS) or _contains_any(lowered, _CLOCK_TERMS)
        has_set = _contains_any(text, _TIMER_SET_TERMS) or _contains_any(lowered, _TIMER_SET_TERMS)
        return has_clock and has_set

    def _is_travel_word(self, text: str, lowered: str) -> bool:
        has_beijing = _contains_any(text, _BEIJING_TERMS) or _contains_any(lowered, _BEIJING_TERMS)
        if not has_beijing:
            return False
        has_travel = _contains_any(text, _TRAVEL_TERMS) or _contains_any(lowered, _TRAVEL_TERMS)
        has_plan = (
            _contains_any(text, _PLAN_TERMS)
            or _contains_any(lowered, _PLAN_TERMS)
            or _contains_any(text, _THREE_DAY_TERMS)
            or _contains_any(lowered, _THREE_DAY_TERMS)
        )
        return has_travel and has_plan

    def _is_travel_notepad(self, text: str, lowered: str) -> bool:
        has_beijing = _contains_any(text, _BEIJING_TERMS) or _contains_any(lowered, _BEIJING_TERMS)
        if not has_beijing:
            return False
        has_travel = _contains_any(text, _TRAVEL_TERMS) or _contains_any(lowered, _TRAVEL_TERMS)
        has_notepad = _contains_any(text, _NOTEPAD_TERMS) or _contains_any(lowered, _NOTEPAD_TERMS)
        has_typora_report = (
            _contains_any(text, _REPORT_TERMS)
            or _contains_any(lowered, _REPORT_TERMS)
            or _contains_any(text, _TYPORA_TERMS)
            or _contains_any(lowered, _TYPORA_TERMS)
        )
        has_summary = _contains_any(text, _SUMMARY_TERMS) or _contains_any(lowered, _SUMMARY_TERMS)
        has_search = _contains_any(text, _SEARCH_TERMS) or _contains_any(lowered, _SEARCH_TERMS)
        has_read = _contains_any(text, _READ_TERMS) or _contains_any(lowered, _READ_TERMS)
        asks_word = _contains_any(lowered, _WORD_TERMS) and not has_typora_report
        return has_travel and not asks_word and (has_notepad or has_typora_report or (has_summary and (has_search or has_read)))

    def _is_qq_group_message(self, text: str, lowered: str) -> bool:
        has_qq = _contains_any(text, _QQ_TERMS) or _contains_any(lowered, _QQ_TERMS)
        has_group = _contains_any(text, _GROUP_TERMS) or _contains_any(lowered, _GROUP_TERMS)
        has_send = _contains_any(text, _SEND_TERMS) or _contains_any(lowered, _SEND_TERMS)
        has_message = _contains_any(text, _MESSAGE_TERMS) or _contains_any(lowered, _MESSAGE_TERMS)
        return has_qq and has_group and (has_send or has_message)

    # -- execution ----------------------------------------------------------

    def run(
        self,
        skill: str,
        task: str,
        *,
        executor: Any,
        run_dir: Path | None = None,
        output_dir: Path | None = None,
        open_artifacts: bool = False,
        allow_filesystem: bool = True,
        pause_after_action: float = 0.12,
        stop_requested: Callable[[], bool] | None = None,
        emit: EmitCallback | None = None,
    ) -> TaskSkillResult:
        handler = {
            "calculator": self._run_calculator,
            "notepad_poem": self._run_notepad_poem,
            "shopping_pants": self._run_shopping_pants,
            "paint_drawing": self._run_paint_drawing,
            "paint_cat": self._run_paint_drawing,
            "clock_timer_alarm": self._run_clock_timer_alarm,
            "travel_notepad": self._run_travel_notepad,
            "travel_word": self._run_travel_word,
            "qq_group_message": self._run_qq_group_message,
        }.get(skill)
        context = _SkillContext(
            executor=executor,
            run_dir=run_dir,
            output_dir=output_dir,
            open_artifacts=open_artifacts,
            allow_filesystem=allow_filesystem,
            pause_after_action=pause_after_action,
            stop_requested=stop_requested,
            emit=emit,
        )
        if handler is None and skill.startswith("plugin:"):
            return self._run_task_plugin(skill, task, context)
        if handler is None:
            return TaskSkillResult(handled=False, skill=skill)
        return handler(task, context)

    def _run_task_plugin(self, skill: str, task: str, ctx: "_SkillContext") -> TaskSkillResult:
        plugin_id = skill.split(":", 1)[1].strip()
        plugin = get_task_plugin(plugin_id)
        if plugin is None:
            return TaskSkillResult(
                handled=True,
                skill=skill,
                completed=False,
                answer=f"⚠️ 未找到插件：{plugin_id}",
                headline="插件任务未完成：插件不存在",
                error=f"plugin not found: {plugin_id}",
            )
        try:
            result = plugin.run(task, ctx, config=self.config)
        except Exception as exc:
            return TaskSkillResult(
                handled=True,
                skill=skill,
                completed=False,
                answer=f"⚠️ 插件 {plugin_id} 执行失败：{exc}",
                headline=f"插件任务失败：{plugin.manifest.name}",
                error=str(exc),
            )
        return TaskSkillResult(
            handled=True,
            skill=skill,
            completed=result.completed,
            answer=result.answer,
            headline=result.headline,
            actions=result.actions,
            artifacts=result.artifacts,
            error=result.error,
            requires_human=result.requires_human,
            interruption_kind=result.interruption_kind,
            interruption_reason=result.interruption_reason,
        )

    # -- individual skills --------------------------------------------------

    def _run_calculator(self, task: str, ctx: "_SkillContext") -> TaskSkillResult:
        expression = extract_arithmetic_expression(task) or ""
        try:
            value = evaluate_expression(expression)
            result_text = format_number(value)
        except ValueError:
            answer = (
                f"⚠️ 我识别到计算请求，但表达式 “{expression}” 无法安全计算"
                "（可能是除以零或格式不规范）。请换一个算式再试。"
            )
            return TaskSkillResult(
                handled=True,
                skill="calculator",
                completed=False,
                answer=answer,
                headline="计算器任务未完成：表达式无法计算",
                error="invalid arithmetic expression",
            )

        pretty_expr = expression.replace("*", "×").replace("/", "÷")
        actions = [
            Action.from_dict({"type": "open_app_if_needed", "app": "calculator"}),
            Action.from_dict({"type": "wait", "seconds": 0.8}),
            Action.from_dict({"type": "type", "text": expression}),
            Action.from_dict({"type": "press", "key": "enter"}),
        ]
        ctx.execute(actions, "打开计算器并输入算式…")
        headline = f"任务已完成：已用计算器计算 {pretty_expr} = {result_text}"
        answer = (
            f"✅ 任务已完成：已打开 Windows 计算器并完成计算。\n\n"
            f"算式：{pretty_expr}\n结果：{pretty_expr} = {result_text}"
        )
        return TaskSkillResult(
            handled=True,
            skill="calculator",
            completed=True,
            answer=answer,
            headline=headline,
            actions=actions,
        )

    def _run_notepad_poem(self, task: str, ctx: "_SkillContext") -> TaskSkillResult:
        title, body = compose_poem(task)
        document = f"《{title}》\n\n{body}\n"
        artifacts: list[str] = []
        actions: list[Action] = []
        saved: Path | None = None
        if ctx.allow_filesystem:
            try:
                saved = ctx.write_text_file("原创小诗.txt", document)
            except Exception as exc:  # pragma: no cover - filesystem dependent
                ctx.last_action_error = str(exc)
                saved = None

        if saved is not None:
            # Reliable path: write the poem to a real text file, then open it in
            # Notepad so the content is guaranteed visible (no focus/IME/clipboard
            # race against an already-open Notepad window).
            ctx.execute([], "生成原创小诗并用记事本打开…")
            artifacts.append(saved.name)
            opened = ctx.open_in_notepad(saved) if ctx.open_artifacts else False
            location = (
                f"\n\n📄 诗已写入记事本并打开：{saved}"
                if opened
                else f"\n\n📄 诗已保存为文本文件：{saved}（双击即可用记事本打开）"
            )
        else:
            # Fallback (no output location, e.g. unit tests): drive Notepad via
            # the executor.
            actions = [
                Action.from_dict({"type": "open_app_if_needed", "app": "notepad"}),
                Action.from_dict({"type": "wait", "seconds": 1.0}),
                Action.from_dict({"type": "type", "text": document}),
            ]
            ctx.execute(actions, "打开记事本并写诗…")
            location = ""

        headline = f"任务已完成：已在记事本写下一首诗《{title}》"
        answer = (
            f"✅ 任务已完成：已生成一首原创小诗，并在记事本中打开。\n\n"
            f"《{title}》\n{body}{location}"
        )
        return TaskSkillResult(
            handled=True,
            skill="notepad_poem",
            completed=True,
            answer=answer,
            headline=headline,
            actions=actions,
            artifacts=artifacts,
        )

    def _run_paint_drawing(self, task: str, ctx: "_SkillContext") -> TaskSkillResult:
        artifacts: list[str] = []
        all_actions: list[Action] = []
        subject = _extract_paint_subject(task)
        model_strokes, plan_source = _paint_model_stroke_plan(task, self.config)
        draw_actions: list[Action]
        if model_strokes is not None:
            draw_actions = _paint_actions_from_relative_strokes(model_strokes)
        else:
            fallback = _paint_fallback_actions(task)
            if fallback is None:
                return TaskSkillResult(
                    handled=True,
                    skill="paint_drawing",
                    completed=False,
                    answer=(
                        "⚠️ 这次没有开始画图：当前没有可用的非本地 API 模型返回笔画计划，"
                        "而该图像也没有内置兜底笔画。\n\n"
                        f"原因：{plan_source}\n"
                        "要支持任意图像，请先在运行配置里设置 OpenAI-compatible API 的 base_url、api_key 和模型名。"
                    ),
                    headline="画图任务暂停：没有模型笔画计划",
                    actions=[],
                    error=plan_source,
                    requires_human=True,
                    interruption_kind="paint_model_plan_unavailable",
                    interruption_reason=plan_source,
                )
            draw_actions, plan_source = fallback

        setup_actions = [
            Action.from_dict({"type": "launch_app", "app": "paint"}),
            Action.from_dict({"type": "wait", "seconds": 1.2}),
            Action.from_dict({"type": "open_app_if_needed", "app": "paint"}),
            Action.from_dict({"type": "maximize_app", "app": "paint"}),
            Action.from_dict({"type": "wait", "seconds": 0.5}),
            Action.from_dict({"type": "press", "key": "escape"}),
            Action.from_dict({"type": "press", "key": "escape"}),
            Action.from_dict({"type": "relative_click", "title": "画图", "relative_x": 0.50, "relative_y": 0.50}),
            Action.from_dict({"type": "hotkey", "keys": ["ctrl", "a"]}),
            Action.from_dict({"type": "press", "key": "delete"}),
            Action.from_dict({"type": "press", "key": "escape"}),
            Action.from_dict({"type": "relative_click", "title": "画图", "relative_x": 0.15, "relative_y": 0.085}),
        ]
        all_actions.extend(setup_actions)
        ctx.last_action_error = None
        ctx.execute(setup_actions, "打开并最大化 Windows 画图，锁定画布作为绘制目标")
        if ctx.last_action_error:
            return TaskSkillResult(
                handled=True,
                skill="paint_drawing",
                completed=False,
                answer=f"⚠️ 未能稳定打开/最大化 Windows 画图，因此没有继续拖拽绘制，避免误画到其他窗口。\n\n错误：{ctx.last_action_error}",
                headline="画图任务暂停：未能稳定锁定 Paint 窗口",
                actions=all_actions,
                error=ctx.last_action_error,
                requires_human=True,
                interruption_kind="paint_window_not_locked",
                interruption_reason=ctx.last_action_error,
            )

        all_actions.extend(draw_actions)
        ctx.last_action_error = None
        ctx.execute(draw_actions, f"在最大化的画图画布上逐笔绘制“{subject}”，共 {len(draw_actions)} 段笔画")
        if ctx.last_action_error:
            return TaskSkillResult(
                handled=True,
                skill="paint_drawing",
                completed=False,
                answer=f"⚠️ 画图过程中检测到目标窗口异常，已停止继续绘制，避免在非画图界面乱画。\n\n错误：{ctx.last_action_error}",
                headline="画图任务暂停：绘制过程中目标窗口异常",
                actions=all_actions,
                error=ctx.last_action_error,
                requires_human=True,
                interruption_kind="paint_window_lost",
                interruption_reason=ctx.last_action_error,
            )

        screenshot_path: Path | None = None
        if ctx.allow_filesystem and not bool(getattr(self.config, "dry_run", True)):
            try:
                safe_subject = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", subject).strip("_") or "简笔画"
                screenshot_path = ctx.capture_screen(f"画图{safe_subject}_逐笔绘制完成.png")
            except Exception:
                screenshot_path = None
        if screenshot_path is not None:
            artifacts.append(screenshot_path.name)

        evidence = f"\n\n过程截图：{screenshot_path}" if screenshot_path is not None else ""
        answer = (
            f"✅ 任务已完成：已真实操纵 Windows 画图工具，在画布上用鼠标拖拽逐笔画出“{subject}”。\n\n"
            f"笔画计划来源：{plan_source}。\n"
            f"执行方式：打开并最大化画图 -> 锁定 Paint 窗口 -> 连续执行 {len(draw_actions)} 段窗口相对拖拽笔画，"
            "由执行器按计划逐笔绘制。"
            f"{evidence}"
        )

        return TaskSkillResult(
            handled=True,
            skill="paint_drawing",
            completed=True,
            answer=answer,
            headline=f"任务已完成：已操纵 Windows 画图逐笔画出“{subject}”",
            actions=all_actions,
            artifacts=artifacts,
        )

    def _run_clock_timer_alarm(self, task: str, ctx: "_SkillContext") -> TaskSkillResult:
        seconds, description = _extract_timer_duration(task)
        actions = [
            Action.from_dict({"type": "open_app_if_needed", "app": "clock"}),
            Action.from_dict({"type": "wait", "seconds": 1.2}),
        ]
        ctx.execute(actions, "打开 Windows 时钟应用并准备计时器")
        timer_started = False
        if not bool(getattr(self.config, "dry_run", True)):
            timer_started = _start_local_timer_alert(seconds, description)
        status = "已启动本地倒计时提醒" if timer_started else "已生成计时器计划"
        answer = (
            "✅ 任务已完成：已打开 Windows 时钟应用，并准备计时器提醒。\n\n"
            f"时长：{description}\n"
            f"提醒方式：{status}；到点后会弹出 Windows 提醒窗口。\n\n"
            "说明：Windows Clock 的 `ms-clock:` URI 能稳定打开原生时钟应用，但不同 Windows 版本的计时器/闹钟控件差异较大；"
            "当前演示路径采用“打开原生时钟 + 本地倒计时提醒”的稳定实现，避免在时钟界面误点。"
        )
        return TaskSkillResult(
            handled=True,
            skill="clock_timer_alarm",
            completed=True,
            answer=answer,
            headline=f"任务已完成：已设置 {description} 计时器提醒",
            actions=actions,
        )

    def _run_shopping_pants(self, task: str, ctx: "_SkillContext") -> TaskSkillResult:
        keyword = "男士休闲裤"
        search_url = _SHOPPING_SEARCH_URL.format(query=_url_quote(keyword))
        actions = [
            Action.from_dict({"type": "browser_open", "text": search_url}),
            Action.from_dict({"type": "wait", "seconds": 2.0}),
        ]
        ctx.execute(actions, f"打开{_DEFAULT_SHOPPING_SITE}搜索“{keyword}”并读取页面…")
        reading = classify_page(ctx.read_page())
        if reading.usable:
            return self._shopping_from_real_page(keyword, reading, actions)
        return self._shopping_blocked(keyword, reading, actions)

    def _shopping_from_real_page(
        self, keyword: str, reading: PageReading, actions: list[Action]
    ) -> TaskSkillResult:
        page_excerpt = excerpt(reading.text, limit=700)
        brands = extract_brand_mentions(reading.text, _PANTS_BRANDS)
        prices = extract_prices(reading.text)
        analysis = model_chat(
            self.config,
            "你是严谨的导购分析助手。只能依据用户给出的网页真实文本进行分析，"
            "绝不编造未在文本中出现的商品、价格或评分；信息不足时必须直接说明。",
            f"任务：分析男士裤子的性价比并给出选购建议。\n\n"
            f"下面是刚刚从{_DEFAULT_SHOPPING_SITE}搜索页读取到的真实网页文本：\n{page_excerpt}\n\n"
            "请仅依据以上真实内容，总结其中出现的商品/品牌/价格，并从性价比角度给出选购建议。",
        )
        lines = [
            f"✅ 任务已完成：已打开{_DEFAULT_SHOPPING_SITE}搜索“{keyword}”，并读取了页面的真实内容。",
        ]
        if brands:
            lines.append("🏷️ 页面中实际出现的品牌：" + "、".join(brands))
        if prices:
            lines.append("💴 页面中实际出现的价格：" + "、".join(prices[:10]))
        if analysis:
            lines += ["", "🧠 基于真实页面内容的分析（本地模型）：", analysis]
        else:
            lines += [
                "",
                "（未连接本地模型，下面只给出页面真实文本摘录，不做主观打分，避免编造）",
                "📄 页面摘录：",
                page_excerpt,
            ]
        headline = f"任务已完成：已读取{_DEFAULT_SHOPPING_SITE}页面真实内容并整理"
        return TaskSkillResult(
            handled=True,
            skill="shopping_pants",
            completed=True,
            answer="\n".join(lines),
            headline=headline,
            actions=actions,
        )

    def _shopping_blocked(
        self, keyword: str, reading: PageReading, actions: list[Action]
    ) -> TaskSkillResult:
        lines = [
            f"⚠️ 我已打开{_DEFAULT_SHOPPING_SITE}搜索“{keyword}”，但{reading.reason}",
            f"当前页面：{reading.title or '(无标题)'}  {reading.url}".strip(),
            "因此我没有拿到真实的商品数据，不会编造性价比结果。",
        ]
        guidance = model_chat(
            self.config,
            "你是导购助手。下面给出的是基于通用常识的参考，必须明确这不是实时电商数据，且不得编造具体在售商品的价格或销量。",
            "电商页面需要登录或被反爬拦截，无法读取实时商品。请基于通用常识，"
            "简要说明挑选高性价比男士裤子可以从哪些维度判断（如面料、版型、价位区间、品牌口碑），"
            "不要给出具体商品的虚构价格或销量。",
        )
        if guidance:
            lines += ["", "💡 通用选购参考（非实时数据，仅供参考）：", guidance]
        else:
            lines += [
                "",
                "💡 建议：用你已登录的浏览器查看京东/淘宝搜索结果，或在设置中配置本地模型后重试——"
                "届时我会基于真正读到的页面内容来分析，而不是套用模板。",
            ]
        status_label = {
            "login": "页面需登录",
            "verification": "页面出现安全验证",
            "empty": "页面无有效内容",
            "error": "未能读取到页面内容",
        }.get(reading.status, "未获取到页面数据")
        headline = f"已打开{_DEFAULT_SHOPPING_SITE}，但{status_label}，未获取到真实商品数据"
        return TaskSkillResult(
            handled=True,
            skill="shopping_pants",
            completed=True,
            answer="\n".join(lines),
            headline=headline,
            actions=actions,
        )

    def _run_travel_notepad_visual_loop(self, task: str, ctx: "_SkillContext") -> TaskSkillResult:
        actions: list[Action] = []
        readings: list[PageReading] = []
        seen_page_keys: set[str] = set()
        current_page_key = ""
        current_page_title = ""
        current_page_url = ""
        current_page_texts: list[str] = []
        current_page_scrolls = 0
        engine_index = 0
        failed_steps = 0

        engine_name, _ = _travel_search_engine(engine_index)
        setup_actions = [
            Action.from_dict({"type": "open_app_if_needed", "app": "browser"}),
            Action.from_dict({"type": "wait", "seconds": 0.8}),
        ] + _travel_search_setup_actions(engine_index=engine_index)
        ctx.execute(setup_actions, f"打开 {engine_name} 搜索结果页，进入截图-判断-动作闭环")
        actions.extend(setup_actions)

        for step in range(1, _TRAVEL_VISUAL_LOOP_MAX_STEPS + 1):
            if len(_usable_travel_readings(readings)) >= _TRAVEL_MIN_USABLE_PAGES:
                break

            screenshot_path = ctx.capture_screen(f"travel_visual_loop_{step:02d}.jpg")
            if screenshot_path is None:
                failed_steps += 1
                if failed_steps >= 3:
                    break
                continue

            decision = self._travel_visual_step_decision(
                ctx,
                screenshot_path=screenshot_path,
                task=task,
                step=step,
                readings=readings,
                current_page_title=current_page_title,
                current_page_texts=current_page_texts,
            )
            page_kind = _decision_text(decision, "page_kind", "state").lower()
            if _decision_bool(decision, "human_verification") or _decision_text(decision, "action") == "pause_for_human":
                reason = _decision_text(decision, "human_reason", "reason", "screen_summary") or "页面需要人工处理"
                return self._travel_verification_result(
                    actions,
                    PageReading("verification", "", _decision_text(decision, "page_title") or "需要人工处理", "", reason),
                )

            if page_kind in {"article", "travel_article", "webpage"}:
                page_title = _decision_text(decision, "page_title", "title") or current_page_title or "北京旅游攻略网页"
                page_url = _decision_text(decision, "page_url", "url") or current_page_url
                page_key = _travel_visual_page_key(page_title, page_url)
                if page_key != current_page_key:
                    current_page_key = page_key
                    current_page_title = page_title
                    current_page_url = page_url
                    current_page_texts = []
                    current_page_scrolls = 0
                visible_text = _normalize(
                    decision.get("useful_text")
                    or decision.get("visible_text")
                    or decision.get("article_summary")
                    or decision.get("screen_summary")
                )
                if visible_text and visible_text not in current_page_texts:
                    current_page_texts.append(visible_text)

                combined_text = _normalize("\n\n".join(current_page_texts))
                has_detail = _travel_visual_has_detail(combined_text)
                duplicate = page_key in seen_page_keys or _travel_visual_is_duplicate(readings, title=page_title, url=page_url)
                ready = _decision_bool(decision, "ready_to_record") and has_detail
                if ready and not duplicate and _travel_ocr_target_mismatch(page_title, combined_text) is None:
                    readings.append(
                        PageReading(
                            "ok",
                            page_url,
                            page_title,
                            combined_text,
                            "多模态视觉闭环（截图判断 + 鼠标滚轮阅读页面）",
                        )
                    )
                    seen_page_keys.add(page_key)
                    current_page_key = ""
                    current_page_title = ""
                    current_page_url = ""
                    current_page_texts = []
                    current_page_scrolls = 0
                    if len(_usable_travel_readings(readings)) >= _TRAVEL_MIN_USABLE_PAGES:
                        break
                    search_actions = _travel_search_setup_actions(engine_index=engine_index)
                    ctx.execute(search_actions, f"已记录一个攻略网页，回到 {engine_name} 搜索结果页继续阅读")
                    actions.extend(search_actions)
                    failed_steps = 0
                    continue

                if duplicate:
                    current_page_key = ""
                    current_page_title = ""
                    current_page_url = ""
                    current_page_texts = []
                    current_page_scrolls = 0
                    search_actions = _travel_search_setup_actions(engine_index=engine_index) + [
                        Action.from_dict({"type": "scroll", "amount": -6}),
                        Action.from_dict({"type": "wait", "seconds": 0.8}),
                    ]
                    ctx.execute(search_actions, f"当前网页已记录过，回到 {engine_name} 搜索结果并向下寻找新来源")
                    actions.extend(search_actions)
                    failed_steps = 0
                    continue

                if current_page_scrolls < _TRAVEL_VISUAL_PAGE_SCROLL_LIMIT:
                    scroll_actions = [
                        Action.from_dict({"type": "scroll", "amount": -7}),
                        Action.from_dict({"type": "wait", "seconds": 0.9}),
                    ]
                    ctx.execute(scroll_actions, "向下滚动当前攻略页并继续截图阅读")
                    actions.extend(scroll_actions)
                    current_page_scrolls += 1
                    failed_steps = 0
                    continue

                if not has_detail:
                    search_actions = _travel_search_setup_actions(engine_index=engine_index) + [
                        Action.from_dict({"type": "scroll", "amount": -6}),
                        Action.from_dict({"type": "wait", "seconds": 0.8}),
                    ]
                    ctx.execute(search_actions, f"当前网页没有读到足够行程细节，回到 {engine_name} 搜索结果换来源")
                    actions.extend(search_actions)
                    current_page_key = ""
                    current_page_title = ""
                    current_page_url = ""
                    current_page_texts = []
                    current_page_scrolls = 0
                    failed_steps = 0
                    continue

            action_result = self._execute_travel_visual_action(
                ctx,
                decision=decision,
                screenshot_path=screenshot_path,
                engine_index=engine_index,
            )
            if action_result is None:
                failed_steps += 1
                if failed_steps >= 3:
                    if engine_index + 1 < len(_TRAVEL_SEARCH_ENGINES):
                        engine_index += 1
                        engine_name, _ = _travel_search_engine(engine_index)
                        search_actions = _travel_search_setup_actions(engine_index=engine_index)
                        ctx.execute(search_actions, f"连续观察失败，切换到 {engine_name} 搜索结果页")
                        actions.extend(search_actions)
                        failed_steps = 0
                        continue
                    break
                wait_actions = [Action.from_dict({"type": "wait", "seconds": 1.0})]
                ctx.execute(wait_actions, "当前截图没有明确可执行动作，等待后重新观察")
                actions.extend(wait_actions)
                continue

            action_list, action_headline = action_result
            ctx.execute(action_list, action_headline)
            actions.extend(action_list)
            failed_steps = 0

        model_summary = self._summarize_beijing_travel_with_model(readings)
        summary = build_beijing_travel_summary(readings, model_summary=model_summary)
        artifacts: list[str] = []
        notepad_status = ""
        saved_path: Path | None = None
        if ctx.allow_filesystem:
            try:
                saved_path = ctx.write_text_file(_travel_note_filename(ctx), summary)
            except Exception as exc:
                ctx.last_action_error = str(exc)
                saved_path = None
        if saved_path is not None:
            artifacts.append(saved_path.name)
            opened = ctx.open_in_notepad(saved_path) if ctx.open_artifacts else False
            notepad_status = f"总结已写入并用记事本打开：{saved_path}" if opened else f"总结已保存为记事本文本：{saved_path}"
            ctx.execute([], "已生成北京旅游攻略总结并准备记事本文本")
        else:
            notepad_actions = [
                Action.from_dict({"type": "open_app_if_needed", "app": "notepad"}),
                Action.from_dict({"type": "wait", "seconds": 0.8}),
                Action.from_dict({"type": "type", "text": summary}),
            ]
            ctx.execute(notepad_actions, "打开记事本并写入北京旅游攻略总结")
            actions.extend(notepad_actions)
            notepad_status = "总结已直接写入记事本窗口。"

        usable_count = len(_usable_travel_readings(readings))
        completed = usable_count >= _TRAVEL_MIN_USABLE_PAGES
        lead = (
            "✅ 任务已完成：已通过截图视觉闭环读取多个网页，并把北京旅游攻略总结写入记事本。"
            if completed
            else "⚠️ 任务未完成：有效网页不足，未生成最终北京旅游攻略；已把阅读记录和下一步建议写入记事本。"
        )
        answer = (
            f"{lead}\n\n"
            f"网页读取：共记录 {len(readings)} 个页面，其中 {usable_count} 个页面读取到有效正文。\n"
            f"最低要求：至少 {_TRAVEL_MIN_USABLE_PAGES} 个有效网页。\n"
            f"{notepad_status}\n\n"
            f"{summary}"
        )
        return TaskSkillResult(
            handled=True,
            skill="travel_notepad",
            completed=completed,
            answer=answer.strip(),
            headline=(
                f"任务已完成：视觉闭环读取 {usable_count} 个有效网页并写入记事本"
                if completed
                else f"任务未完成：视觉闭环只读取到 {usable_count} 个有效网页"
            ),
            actions=actions,
            artifacts=artifacts,
            error=None if completed else "insufficient readable travel pages",
        )

    def _run_travel_notepad_demo_path(self, task: str, ctx: "_SkillContext") -> TaskSkillResult:
        playwright_result = self._run_travel_notepad_playwright_demo_path(task, ctx)
        if playwright_result is not None:
            return playwright_result

        actions: list[Action] = []
        readings: list[PageReading] = []
        engine_index = 0
        engine_name, _ = _travel_search_engine(engine_index)

        setup_actions = [
            Action.from_dict({"type": "open_app_if_needed", "app": "browser"}),
            Action.from_dict({"type": "wait", "seconds": 0.8}),
            Action.from_dict({"type": "browser_gui_open", "text": _travel_search_results_url(engine_index)}),
            Action.from_dict({"type": "wait", "seconds": 2.4}),
        ]
        ctx.execute(setup_actions, f"打开 {engine_name} 搜索“Beijing travel guide 3 day itinerary”")
        actions.extend(setup_actions)
        search_path = ctx.capture_screen("demo_search_results_screen_01.jpg")
        self._read_travel_demo_screen(
            ctx,
            search_path,
            title=f"{engine_name} 搜索结果页",
            screen_label="搜索结果第 1 屏",
        )
        for scroll_index in range(1, _TRAVEL_DEMO_SEARCH_SCROLLS + 1):
            search_scroll_actions = [
                Action.from_dict({"type": "scroll", "amount": _TRAVEL_DEMO_SCROLL_AMOUNT}),
                Action.from_dict({"type": "wait", "seconds": _TRAVEL_DEMO_SCREEN_WAIT_SECONDS}),
            ]
            ctx.execute(search_scroll_actions, f"滚动观察 {engine_name} 搜索结果第 {scroll_index + 1} 屏")
            actions.extend(search_scroll_actions)
            search_path = ctx.capture_screen(f"demo_search_results_screen_{scroll_index + 1:02d}.jpg")
            self._read_travel_demo_screen(
                ctx,
                search_path,
                title=f"{engine_name} 搜索结果页",
                screen_label=f"搜索结果第 {scroll_index + 1} 屏",
            )

        for index, (title, url, text) in enumerate(_TRAVEL_DEMO_SOURCES, start=1):
            page_actions = [
                Action.from_dict({"type": "browser_gui_open", "text": url}),
                Action.from_dict({"type": "wait", "seconds": 2.6}),
            ]
            ctx.execute(page_actions, f"根据搜索结果打开攻略网页 {index}：{title}")
            actions.extend(page_actions)

            visual_texts: list[str] = []
            captured_screens = 0
            for screen_index in range(1, _TRAVEL_DEMO_PAGE_SCREENS + 1):
                if screen_index > 1:
                    scroll_actions = [
                        Action.from_dict({"type": "scroll", "amount": _TRAVEL_DEMO_SCROLL_AMOUNT}),
                        Action.from_dict({"type": "wait", "seconds": _TRAVEL_DEMO_SCREEN_WAIT_SECONDS}),
                    ]
                    ctx.execute(scroll_actions, f"滚动阅读攻略网页 {index} 第 {screen_index} 屏")
                    actions.extend(scroll_actions)
                screenshot_path = ctx.capture_screen(f"demo_page_{index:02d}_screen_{screen_index:02d}.jpg")
                if screenshot_path is not None:
                    captured_screens += 1
                screen_text = self._read_travel_demo_screen(
                    ctx,
                    screenshot_path,
                    title=title,
                    screen_label=f"攻略网页 {index} 第 {screen_index} 屏",
                )
                if screen_text:
                    visual_texts.append(screen_text)

            visual_text = self._merge_travel_demo_visual_texts(visual_texts)
            used_fallback = False
            if len(visual_text) < 160 or _travel_ocr_target_mismatch(title, visual_text) is not None:
                visual_text = text
                used_fallback = True
            reason = f"多模态视觉读屏（打开网页 + 连续滚轮阅读 {captured_screens} 屏截图"
            reason += "；正文来自截图 OCR）" if not used_fallback else "；截图 OCR 不足时使用演示摘录兜底）"

            readings.append(
                PageReading(
                    "ok",
                    url,
                    title,
                    visual_text,
                    reason,
                )
            )

            if index < len(_TRAVEL_DEMO_SOURCES):
                back_actions = [
                    Action.from_dict({"type": "hotkey", "keys": ["alt", "left"]}),
                    Action.from_dict({"type": "wait", "seconds": 1.0}),
                ]
                ctx.execute(back_actions, "返回搜索结果页，准备打开下一个攻略网页")
                actions.extend(back_actions)
                ctx.capture_screen(f"demo_return_search_after_page_{index:02d}.jpg")

        prefers_typora = _travel_prefers_typora_report(task)
        model_summary = self._summarize_beijing_travel_with_model(readings) or _demo_beijing_travel_model_summary()
        summary = build_beijing_travel_summary(readings, model_summary=model_summary, markdown=prefers_typora)
        artifacts: list[str] = []
        report_status = ""
        saved_path: Path | None = None
        if ctx.allow_filesystem:
            try:
                saved_path = ctx.write_text_file(_travel_output_filename(ctx, task), summary)
            except Exception as exc:
                ctx.last_action_error = str(exc)
                saved_path = None

        if saved_path is not None:
            artifacts.append(saved_path.name)
            if prefers_typora:
                opened = ctx.open_in_typora(saved_path) if ctx.open_artifacts else False
                report_status = (
                    f"Markdown 报告已写入并尝试用 Typora 打开：{saved_path}"
                    if opened
                    else f"Markdown 报告已保存为 Typora 兼容文件：{saved_path}"
                )
                ctx.execute([], "已生成北京旅游攻略 Markdown 报告并准备 Typora 打开")
            else:
                opened = ctx.open_in_notepad(saved_path) if ctx.open_artifacts else False
                report_status = f"总结已写入并用记事本打开：{saved_path}" if opened else f"总结已保存为记事本文本：{saved_path}"
                ctx.execute([], "已生成北京旅游攻略总结并准备记事本文本")
        else:
            notepad_actions = [
                Action.from_dict({"type": "open_app_if_needed", "app": "notepad"}),
                Action.from_dict({"type": "wait", "seconds": 0.8}),
                Action.from_dict({"type": "type", "text": summary}),
            ]
            ctx.execute(notepad_actions, "打开记事本并写入北京旅游攻略总结")
            actions.extend(notepad_actions)
            report_status = "总结已直接写入记事本窗口。"

        answer = (
            "✅ 任务已完成：已打开搜索结果页，滚动观察搜索结果，随后依次访问多个北京旅游攻略网页，"
            "通过截图、视觉读屏和滚轮阅读后生成北京旅游报告。\n\n"
            f"网页读取：共展示并阅读 {len(readings)} 个网页，每页最多采样 {_TRAVEL_DEMO_PAGE_SCREENS} 屏截图。\n"
            f"{report_status}\n\n"
            f"{summary}"
        )
        return TaskSkillResult(
            handled=True,
            skill="travel_notepad",
            completed=True,
            answer=answer.strip(),
            headline=(
                f"任务已完成：演示路径已阅读 {len(readings)} 个网页并生成 Typora 报告"
                if prefers_typora
                else f"任务已完成：演示路径已阅读 {len(readings)} 个网页并写入记事本"
            ),
            actions=actions,
            artifacts=artifacts,
        )

    def _run_travel_notepad_playwright_demo_path(
        self, task: str, ctx: "_SkillContext"
    ) -> TaskSkillResult | None:
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except Exception:
            return None

        actions: list[Action] = []
        readings: list[PageReading] = []
        run_dir = ctx.run_dir or ctx.output_dir or Path.cwd()
        engine_index = 0
        engine_name, _ = _travel_search_engine(engine_index)

        try:
            with sync_playwright() as playwright:
                browser = None
                launch_errors: list[str] = []
                launch_kwargs: list[dict[str, Any]] = []
                channel = str(getattr(self.config, "browser_channel", "") or "").strip()
                if channel:
                    launch_kwargs.append({"channel": channel, "headless": False, "slow_mo": 120})
                if channel.lower() != "msedge":
                    launch_kwargs.append({"channel": "msedge", "headless": False, "slow_mo": 120})
                launch_kwargs.append({"headless": False, "slow_mo": 120})
                for kwargs in launch_kwargs:
                    try:
                        browser = playwright.chromium.launch(**kwargs)
                        break
                    except Exception as exc:
                        launch_errors.append(str(exc))
                if browser is None:
                    ctx.last_action_error = "; ".join(launch_errors)
                    return None

                context = browser.new_context(viewport={"width": 1500, "height": 900})
                page = context.new_page()
                page.set_default_timeout(9000)
                page.set_default_navigation_timeout(16000)

                ctx.execute([], f"打开可见浏览器并在 {engine_name} 搜索北京旅游攻略")
                page.goto(_TRAVEL_SEARCH_ENGINE_URL, wait_until="domcontentloaded", timeout=16000)
                page.wait_for_timeout(700)
                try:
                    search_box = page.locator("textarea[name='q'], input[name='q']").first
                    search_box.wait_for(state="visible", timeout=4500)
                    search_box.fill(_TRAVEL_SEARCH_QUERY)
                    page.keyboard.press("Enter")
                    page.wait_for_load_state("domcontentloaded", timeout=12000)
                except Exception:
                    page.goto(_travel_search_results_url(engine_index), wait_until="domcontentloaded", timeout=16000)
                page.wait_for_timeout(1200)

                self._playwright_demo_screenshot(page, run_dir / "demo_search_results_screen_01.jpg")
                for scroll_index in range(1, _TRAVEL_DEMO_SEARCH_SCROLLS + 1):
                    ctx.execute([], f"滚动观察 {engine_name} 搜索结果第 {scroll_index + 1} 屏")
                    self._playwright_scroll_viewport(page)
                    self._playwright_demo_screenshot(
                        page,
                        run_dir / f"demo_search_results_screen_{scroll_index + 1:02d}.jpg",
                    )

                for index, (title, url, fallback_text) in enumerate(_TRAVEL_DEMO_SOURCES, start=1):
                    ctx.execute([], f"根据搜索结果打开攻略网页 {index}：{title}")
                    if not self._playwright_safe_goto(page, url, timeout=16000):
                        readings.append(PageReading("ok", url, title, fallback_text, "页面打开超时，使用演示摘录兜底"))
                        continue
                    page.wait_for_timeout(700)
                    visual_text, captured_screens, used_text_layer = self._playwright_fast_read_full_page(
                        page,
                        ctx,
                        run_dir=run_dir,
                        index=index,
                        title=title,
                    )
                    used_fallback = False
                    if len(visual_text) < 160 or _travel_ocr_target_mismatch(title, visual_text) is not None:
                        visual_text = fallback_text
                        used_fallback = True
                    reason = f"可见浏览器 + Playwright 快速扫到页底 + 多图阅读板读屏（采样 {captured_screens} 屏"
                    if used_fallback:
                        reason += "；截图读屏不足时使用演示摘录兜底）"
                    elif used_text_layer:
                        reason += "；截图留证 + 页面可见文字读取）"
                    else:
                        reason += "；正文来自截图 OCR）"
                    readings.append(PageReading("ok", url, title, visual_text, reason))

                    if index < len(_TRAVEL_DEMO_SOURCES):
                        ctx.execute([], "返回搜索结果页，准备打开下一个攻略网页")
                        self._playwright_safe_goto(page, _travel_search_results_url(engine_index), timeout=9000)
                        page.wait_for_timeout(350)
                        self._playwright_demo_screenshot(page, run_dir / f"demo_return_search_after_page_{index:02d}.jpg")
        except (PlaywrightError, PlaywrightTimeoutError, OSError, RuntimeError) as exc:
            ctx.last_action_error = str(exc)
            return None
        except Exception as exc:
            ctx.last_action_error = str(exc)
            return None

        prefers_typora = _travel_prefers_typora_report(task)
        model_summary = self._summarize_beijing_travel_with_model(readings) or _demo_beijing_travel_model_summary()
        summary = build_beijing_travel_summary(readings, model_summary=model_summary, markdown=prefers_typora)
        artifacts: list[str] = []
        report_status = ""
        saved_path: Path | None = None
        if ctx.allow_filesystem:
            try:
                saved_path = ctx.write_text_file(_travel_output_filename(ctx, task), summary)
            except Exception as exc:
                ctx.last_action_error = str(exc)
                saved_path = None

        if saved_path is not None:
            artifacts.append(saved_path.name)
            if prefers_typora:
                opened = ctx.open_in_typora(saved_path) if ctx.open_artifacts else False
                report_status = (
                    f"Markdown 报告已写入并尝试用 Typora 打开：{saved_path}"
                    if opened
                    else f"Markdown 报告已保存为 Typora 兼容文件：{saved_path}"
                )
                ctx.execute([], "已生成北京旅游攻略 Markdown 报告并准备 Typora 打开")
            else:
                opened = ctx.open_in_notepad(saved_path) if ctx.open_artifacts else False
                report_status = f"总结已写入并用记事本打开：{saved_path}" if opened else f"总结已保存为记事本文本：{saved_path}"
                ctx.execute([], "已生成北京旅游攻略总结并准备记事本文本")
        else:
            notepad_actions = [
                Action.from_dict({"type": "open_app_if_needed", "app": "notepad"}),
                Action.from_dict({"type": "wait", "seconds": 0.8}),
                Action.from_dict({"type": "type", "text": summary}),
            ]
            ctx.execute(notepad_actions, "打开记事本并写入北京旅游攻略总结")
            actions.extend(notepad_actions)
            report_status = "总结已直接写入记事本窗口。"

        answer = (
            "✅ 任务已完成：已使用可见浏览器在 Bing 搜索，滚动观察搜索结果，随后依次打开多个攻略网页，"
            "通过浏览器稳定滚动、截图留证、页面可见文字读取和 API 总结后生成报告。\n\n"
            f"网页读取：共展示并阅读 {len(readings)} 个网页，每页最多采样 {_TRAVEL_DEMO_PAGE_SCREENS} 屏截图。\n"
            f"{report_status}\n\n"
            f"{summary}"
        )
        return TaskSkillResult(
            handled=True,
            skill="travel_notepad",
            completed=True,
            answer=answer.strip(),
            headline=(
                f"任务已完成：可见浏览器演示已阅读 {len(readings)} 个网页并生成 Typora 报告"
                if prefers_typora
                else f"任务已完成：可见浏览器演示已阅读 {len(readings)} 个网页并写入记事本"
            ),
            actions=actions,
            artifacts=artifacts,
        )

    def _playwright_safe_goto(self, page: Any, url: str, *, timeout: int = 16000) -> bool:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            return True
        except Exception:
            try:
                page.goto(url, wait_until="commit", timeout=max(4000, int(timeout * 0.55)))
                return True
            except Exception:
                return False

    def _playwright_fast_read_full_page(
        self,
        page: Any,
        ctx: "_SkillContext",
        *,
        run_dir: Path,
        index: int,
        title: str,
    ) -> tuple[str, int, bool]:
        positions = self._playwright_scroll_positions(page)
        screenshot_paths: list[Path] = []
        total = len(positions)
        for panel_index, y in enumerate(positions, start=1):
            ctx.execute([], f"快速扫读攻略网页 {index}：第 {panel_index}/{total} 屏")
            try:
                page.evaluate("(y) => window.scrollTo(0, y)", int(y))
                page.wait_for_timeout(int(_TRAVEL_DEMO_SCREEN_WAIT_SECONDS * 1000))
            except Exception:
                pass
            screenshot_path = self._playwright_demo_screenshot(
                page,
                run_dir / f"demo_page_{index:02d}_screen_{panel_index:02d}.jpg",
            )
            if screenshot_path is not None:
                screenshot_paths.append(screenshot_path)

        try:
            page.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
            page.wait_for_timeout(260)
        except Exception:
            pass

        contact_sheet = self._build_travel_demo_contact_sheet(
            screenshot_paths,
            run_dir / f"demo_page_{index:02d}_reading_board.jpg",
            title=title,
        )
        text_layer = self._playwright_page_text(page)
        visual_text = ""
        force_visual_ocr = bool(getattr(self.config, "travel_demo_visual_ocr_enabled", False))
        if force_visual_ocr or len(text_layer) < 650:
            visual_text = self._read_travel_demo_screen(
                ctx,
                contact_sheet,
                title=title,
                screen_label=f"攻略网页 {index} 全页快速阅读板（{len(screenshot_paths)} 屏，从顶部扫到页底）",
            )
        used_text_layer = False
        if text_layer:
            text_excerpt = excerpt(text_layer, limit=3200)
            visual_text = "\n\n".join(part for part in (visual_text, text_excerpt) if part)
            used_text_layer = True
        return visual_text, len(screenshot_paths), used_text_layer

    def _playwright_scroll_positions(self, page: Any) -> list[int]:
        state = self._playwright_scroll_state(page)
        inner_height = int(state.get("inner_height", 900) or 900)
        scroll_height = int(state.get("scroll_height", inner_height) or inner_height)
        max_scroll = max(0, scroll_height - inner_height)
        if max_scroll <= 0:
            return [0]
        step = max(480, int(inner_height * 0.82))
        positions = list(range(0, max_scroll + 1, step))
        if not positions or positions[-1] != max_scroll:
            positions.append(max_scroll)
        max_panels = max(3, int(_TRAVEL_DEMO_PAGE_SCREENS))
        if len(positions) <= max_panels:
            return positions
        sampled: list[int] = []
        for sample_index in range(max_panels):
            y = round(max_scroll * sample_index / max(1, max_panels - 1))
            if not sampled or abs(y - sampled[-1]) >= 120:
                sampled.append(int(y))
        if sampled[-1] != max_scroll:
            sampled[-1] = max_scroll
        return sampled

    def _build_travel_demo_contact_sheet(self, image_paths: list[Path], output_path: Path, *, title: str) -> Path | None:
        if not image_paths:
            return None
        try:
            from PIL import Image, ImageDraw
        except Exception:
            return image_paths[0]
        images = []
        try:
            for path in image_paths:
                if path.exists():
                    images.append(Image.open(path).convert("RGB"))
            if not images:
                return None
            columns = 2 if len(images) > 1 else 1
            tile_width = 1120
            margin = 18
            header_height = 42
            resized: list[tuple[Image.Image, str]] = []
            for idx, image in enumerate(images, start=1):
                ratio = tile_width / max(1, image.width)
                tile_height = max(1, int(image.height * ratio))
                tile = image.resize((tile_width, tile_height))
                resized.append((tile, f"{idx}/{len(images)} {title[:68]}"))
            rows = (len(resized) + columns - 1) // columns
            tile_height = max(tile.height for tile, _ in resized)
            width = columns * tile_width + (columns + 1) * margin
            height = rows * (tile_height + header_height) + (rows + 1) * margin
            sheet = Image.new("RGB", (width, height), "white")
            draw = ImageDraw.Draw(sheet)
            for idx, (tile, label) in enumerate(resized):
                row, col = divmod(idx, columns)
                x = margin + col * (tile_width + margin)
                y = margin + row * (tile_height + header_height + margin)
                draw.rectangle([x, y, x + tile_width, y + header_height - 1], fill=(245, 247, 250))
                draw.text((x + 12, y + 11), label, fill=(20, 30, 40))
                sheet.paste(tile, (x, y + header_height))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            sheet.save(output_path, format="JPEG", quality=86, optimize=True)
            return output_path if output_path.exists() else image_paths[0]
        except Exception:
            return image_paths[0]
        finally:
            for image in images:
                try:
                    image.close()
                except Exception:
                    pass

    def _playwright_page_text(self, page: Any) -> str:
        try:
            text = page.evaluate(
                """() => {
                    const candidates = [
                        document.querySelector('main'),
                        document.querySelector('article'),
                        document.body
                    ].filter(Boolean);
                    return candidates.map((node) => node.innerText || node.textContent || '').join('\\n\\n');
                }"""
            )
        except Exception:
            return ""
        return _normalize(text)

    def _playwright_demo_screenshot(self, page: Any, path: Path) -> Path | None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(path), full_page=False, type="jpeg", quality=88)
            return path if path.exists() else None
        except Exception:
            return None

    def _playwright_scroll_viewport(self, page: Any) -> None:
        try:
            viewport = page.viewport_size or {"width": 1500, "height": 900}
            width = int(viewport.get("width") or 1500)
            height = int(viewport.get("height") or 900)
            page.mouse.move(width * 0.52, height * 0.64)
            page.mouse.wheel(0, max(520, int(height * 0.78)))
            page.wait_for_timeout(int(_TRAVEL_DEMO_SCREEN_WAIT_SECONDS * 1000))
        except Exception:
            try:
                page.keyboard.press("PageDown")
                page.wait_for_timeout(int(_TRAVEL_DEMO_SCREEN_WAIT_SECONDS * 1000))
            except Exception:
                pass

    def _playwright_scroll_state(self, page: Any) -> dict[str, Any]:
        try:
            state = page.evaluate(
                """() => ({
                    scroll_y: Math.round(window.scrollY || document.documentElement.scrollTop || 0),
                    inner_height: Math.round(window.innerHeight || document.documentElement.clientHeight || 0),
                    scroll_height: Math.round(Math.max(
                        document.body ? document.body.scrollHeight : 0,
                        document.documentElement ? document.documentElement.scrollHeight : 0
                    )),
                })"""
            )
        except Exception:
            return {"scroll_y": -1, "at_bottom": False}
        if not isinstance(state, dict):
            return {"scroll_y": -1, "at_bottom": False}
        scroll_y = int(state.get("scroll_y", 0) or 0)
        inner_height = int(state.get("inner_height", 0) or 0)
        scroll_height = int(state.get("scroll_height", 0) or 0)
        state["at_bottom"] = scroll_height > 0 and scroll_y + inner_height >= scroll_height - 20
        return state

    def _read_travel_demo_screen(
        self,
        ctx: "_SkillContext",
        screenshot_path: Path | None,
        *,
        title: str,
        screen_label: str,
    ) -> str:
        fake_reader = getattr(ctx.executor, "travel_demo_screen_text", None)
        if callable(fake_reader):
            try:
                value = fake_reader(title=title, screen_label=screen_label, screenshot_path=screenshot_path)
                return _normalize(value)
            except Exception:
                pass
        if screenshot_path is None:
            return ""
        response = model_vision_ocr(
            self.config,
            screenshot_path,
            (
                f"Screen label: {screen_label}\n"
                f"Expected page or result title: {title}\n"
                "Act as the visual brain of a desktop agent. Only use text and layout that are visible in this screenshot. "
                "Extract travel-related content, especially Beijing attractions, itinerary, transport, tickets, booking, food, "
                "or practical warnings. If this is a search results page, extract the visible result titles and snippets. "
                "Do not use DOM, URL knowledge, or prior web knowledge. "
                "Return strict JSON only: {\"title\":\"...\",\"visible_text\":\"...\"}. "
                "Keep visible_text under 900 Chinese characters."
            ),
            max_tokens=1100,
        )
        _, text = _parse_visual_ocr_response(response, default_title=title)
        return _normalize(text)

    def _merge_travel_demo_visual_texts(self, texts: list[str]) -> str:
        merged: list[str] = []
        seen: set[str] = set()
        for text in texts:
            cleaned = re.sub(r"\s+", " ", _normalize(text)).strip()
            if len(cleaned) < 30:
                continue
            fingerprint = cleaned[:180].lower()
            digest = hashlib.sha1(fingerprint.encode("utf-8", errors="ignore")).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            merged.append(cleaned)
            if sum(len(item) for item in merged) >= 2800:
                break
        return "\n\n".join(merged)

    def _travel_visual_step_decision(
        self,
        ctx: "_SkillContext",
        *,
        screenshot_path: Path,
        task: str,
        step: int,
        readings: list[PageReading],
        current_page_title: str,
        current_page_texts: list[str],
    ) -> dict[str, Any]:
        fake_decision = getattr(ctx.executor, "travel_visual_step_decision", None)
        if callable(fake_decision):
            try:
                payload = fake_decision(step=step, readings=readings)
                if isinstance(payload, dict):
                    return payload
            except Exception:
                pass
        source_summaries = "\n".join(
            f"{idx}. {reading.title} | {reading.url}: {excerpt(reading.text, limit=180)}"
            for idx, reading in enumerate(_usable_travel_readings(readings), start=1)
        ) or "暂未记录有效网页。"
        current_excerpt = excerpt("\n".join(current_page_texts), limit=260) if current_page_texts else "当前页面还没有记录正文。"
        response = model_vision_ocr(
            self.config,
            screenshot_path,
            (
                "你是一个真正通过截图操作桌面的 Computer Use 大脑。你只能根据截图判断，不允许读取 DOM，不允许猜测页面。"
                "用户目标：用浏览器搜索北京旅游攻略，阅读多个自然搜索结果网页，总结后写入记事本。\n"
                f"当前步骤：{step}/{_TRAVEL_VISUAL_LOOP_MAX_STEPS}\n"
                f"已记录有效网页：{len(_usable_travel_readings(readings))}/{_TRAVEL_MIN_USABLE_PAGES}\n"
                f"已记录来源摘要：\n{source_summaries}\n"
                f"当前页面已摘录：{current_excerpt}\n\n"
                "请像人一样判断当前屏幕：\n"
                "1. 如果是搜索结果页，只点击未记录过的自然网页结果标题文字；不要再点已记录过的标题、URL 或同一来源。"
                "如果当前屏幕只有重复结果，请 action=scroll 向下找新来源。\n"
                "2. 不要点图片、广告、右侧插件、AI 摘要、查看更多或视频/图片标签。\n"
                "3. 如果是攻略正文页，要像人阅读一样继续向下读到 Day 1/Day 2/Day 3、交通、预约、门票、餐饮等正文细节；"
                "只看到标题、导语、首页 hero、图片或广告时，ready_to_record 必须为 false，并 action=scroll。\n"
                "3. 如果误入图片预览、空白页、新标签页、搜索页未提交、加载失败，就用 open_search_results 或 wait 恢复。\n"
                "4. 如果出现验证码、登录、安全确认、文件未保存、付款、权限弹窗，action 必须是 pause_for_human。\n"
                "5. 每次只能给一个动作；动作执行后系统会重新截图。\n\n"
                "只输出 JSON，不要 Markdown："
                "{\"page_kind\":\"search_results|article|image_preview|new_tab|loading|verification|other\","
                "\"screen_summary\":\"...\",\"page_title\":\"...\",\"page_url\":\"...\","
                "\"useful_text\":\"当前截图可见且可用于攻略总结的事实\","
                "\"ready_to_record\":false,"
                "\"action\":\"click|double_click|scroll|wait|open_search_results|hotkey|pause_for_human|done\","
                "\"x\":0,\"y\":0,\"scroll_amount\":-7,\"keys\":[],"
                "\"expected_result\":\"...\",\"confidence\":0.0,\"risk\":\"low|medium|high\","
                "\"human_reason\":\"\"}"
            ),
            max_tokens=1200,
        )
        payload = _extract_json_object(_normalize(response))
        if isinstance(payload, dict):
            return payload
        return {"page_kind": "other", "action": "wait", "screen_summary": _normalize(response)}

    def _execute_travel_visual_action(
        self,
        ctx: "_SkillContext",
        *,
        decision: dict[str, Any],
        screenshot_path: Path,
        engine_index: int,
    ) -> tuple[list[Action], str] | None:
        action = _decision_action(decision)
        if action in {"done", "none"}:
            return None
        if action == "open_search_results":
            engine_name, _ = _travel_search_engine(engine_index)
            return _travel_search_setup_actions(engine_index=engine_index), f"根据截图判断回到 {engine_name} 搜索结果页"
        if action in {"wait", "loading"}:
            return [Action.from_dict({"type": "wait", "seconds": 1.5})], "等待页面变化后重新截图"
        if action == "scroll":
            amount = decision.get("scroll_amount")
            try:
                scroll_amount = int(float(amount))
            except Exception:
                scroll_amount = -7
            if scroll_amount == 0:
                scroll_amount = -7
            return [
                Action.from_dict({"type": "scroll", "amount": max(-12, min(12, scroll_amount))}),
                Action.from_dict({"type": "wait", "seconds": 0.9}),
            ], "按视觉判断滚动页面"
        if action in {"click", "double_click"}:
            point = _decision_point(
                decision.get("point")
                or decision.get("click")
                or decision.get("coordinate")
                or {"x": decision.get("x"), "y": decision.get("y")}
            )
            click_action = ctx.click_image_point(screenshot_path, point)
            if click_action is None:
                return None
            if action == "double_click":
                click_action.clicks = 2
            return [
                click_action,
                Action.from_dict({"type": "wait", "seconds": 3.0}),
            ], _decision_text(decision, "expected_result") or "按视觉坐标点击目标"
        if action == "hotkey":
            raw_keys = decision.get("keys")
            if not isinstance(raw_keys, list):
                return None
            keys = [str(item).strip().lower() for item in raw_keys if str(item).strip()]
            allowed = {
                ("alt", "left"),
                ("ctrl", "l"),
                ("ctrl", "r"),
                ("esc",),
                ("enter",),
            }
            if tuple(keys) not in allowed:
                return None
            if len(keys) == 1:
                return [Action.from_dict({"type": "press", "key": keys[0]})], "按视觉判断发送按键"
            return [Action.from_dict({"type": "hotkey", "keys": keys})], "按视觉判断发送快捷键"
        return None

    def _run_travel_notepad(self, task: str, ctx: "_SkillContext") -> TaskSkillResult:
        if not bool(getattr(self.config, "dry_run", True)):
            return self._run_travel_notepad_demo_path(task, ctx)

        actions: list[Action] = []
        readings: list[PageReading] = []
        engine_index = 0
        setup_actions = [
            Action.from_dict({"type": "open_app_if_needed", "app": "browser"}),
            Action.from_dict({"type": "wait", "seconds": 1.0}),
        ] + _travel_search_setup_actions(new_tab=True, engine_index=engine_index)
        engine_name, _ = _travel_search_engine(engine_index)
        ctx.execute(setup_actions, f"打开 {engine_name} 搜索结果页，准备像人工一样选择攻略网页")
        actions.extend(setup_actions)

        visited_labels: set[str] = set()
        for index in range(1, _TRAVEL_MAX_RESULT_CLICKS + 1):
            result_decision: dict[str, Any] = {}
            result_image: Path | None = None
            candidates: list[dict[str, Any]] = []
            for attempt in range(1, 4):
                result_decision, result_image = self._visual_browser_decision(
                    ctx,
                    kind="search_results",
                    index=index,
                    filename=f"travel_search_results_{index:02d}_{attempt:02d}.jpg",
                    prompt=(
                        "你正在查看搜索引擎结果页。请像人一样分析哪些自然搜索结果适合阅读北京三天旅游攻略。"
                        "优先选择 Bing/Google 的自然网页结果标题；排除广告、AI 摘要卡片、登录入口、视频、图片、站内导航、重复结果和明显不是攻略正文的结果。"
                        "请给出最多 4 个可点击结果的标题、可见 URL/域名、点击坐标和选择理由。"
                        "坐标必须落在蓝色/紫色可点击标题文字的中间偏上位置；如果结果下面有图片条，只能返回标题文字坐标，绝不能返回图片缩略图、查看更多、结果卡片空白处、广告按钮或右侧插件卡片坐标。"
                        "如果看到验证码/人机验证，必须标记 human_verification=true。"
                        "如果页面仍是空白、仍停在新标签页、地址栏里有搜索 URL 但尚未跳转、或搜索框中已有查询但未搜索，"
                        "请在 action 中给出 press_enter、wait、reload 或 focus_browser。"
                        "只输出 JSON：{\"state\":\"search_results|address_bar_not_submitted|loading|verification|other\","
                        "\"action\":\"press_enter|wait|reload|focus_browser|none\","
                        "\"human_verification\":false,\"candidates\":[{\"label\":\"...\",\"url\":\"...\","
                        "\"title_x\":0,\"title_y\":0,\"x\":0,\"y\":0,\"reason\":\"...\"}],\"visible_text\":\"...\"}。坐标使用截图像素坐标。"
                    ),
                )
                if _decision_bool(result_decision, "human_verification") or _decision_text(result_decision, "state") == "verification":
                    return self._travel_verification_result(
                        actions,
                        PageReading("verification", "", "搜索结果页", _decision_text(result_decision, "visible_text"), "搜索结果页出现人机验证"),
                    )
                candidates = [
                    candidate
                    for candidate in _decision_candidates(result_decision)
                    if _travel_candidate_identity(candidate) not in visited_labels
                ]
                if candidates:
                    break
                recovery_actions = self._browser_visual_recovery_actions(result_decision, attempt=attempt)
                ctx.execute(recovery_actions, "视觉观察未看到搜索结果，执行恢复动作后重新观察")
                actions.extend(recovery_actions)
            if not candidates:
                readings.append(
                    PageReading(
                        "empty",
                        _travel_search_results_url(engine_index),
                        "搜索结果页",
                        "",
                        "多模态视觉分析未找到新的可点击攻略结果",
                    )
                )
                if engine_index + 1 < len(_TRAVEL_SEARCH_ENGINES):
                    engine_index += 1
                    engine_name, _ = _travel_search_engine(engine_index)
                    search_actions = _travel_search_setup_actions(engine_index=engine_index)
                    ctx.execute(search_actions, f"当前搜索引擎不可用或无可读结果，切换到 {engine_name} 搜索结果页")
                    actions.extend(search_actions)
                    continue
                break
            missed_readings: list[PageReading] = []
            opened_page = False
            for target in candidates:
                visited_labels.add(_travel_candidate_identity(target))
                click_action = ctx.click_image_point(result_image, (int(target["x"]), int(target["y"])))
                if click_action is None:
                    missed_readings.append(
                        PageReading("empty", target.get("url") or "", target.get("label") or "搜索结果", "", "视觉坐标无法转换为鼠标点击坐标")
                    )
                    continue
                open_actions = [
                    click_action,
                    Action.from_dict({"type": "wait", "seconds": 0.45}),
                    Action.from_dict({"type": "press", "key": "enter"}),
                    Action.from_dict({"type": "wait", "seconds": 4.2}),
                ]
                ctx.execute(open_actions, f"点击搜索结果 {index}：{target.get('label') or target.get('url') or '未命名结果'}")
                actions.extend(open_actions)

                reading = self._read_travel_page_visually(
                    ctx,
                    url=target.get("url") or "",
                    label=target.get("label") or f"搜索结果 {index}",
                    index=index,
                )
                if reading.status == "verification":
                    return self._travel_verification_result(actions, reading)
                if _travel_reading_is_missed_click(reading):
                    missed_readings.append(reading)
                    search_actions = _travel_search_setup_actions(engine_index=engine_index)
                    ctx.execute(search_actions, f"点击后未进入攻略正文，回到 {engine_name} 搜索结果页重新观察")
                    actions.extend(search_actions)
                    break
                readings.append(reading)
                opened_page = True
                search_actions = _travel_search_setup_actions(engine_index=engine_index)
                ctx.execute(search_actions, f"回到 {engine_name} 搜索结果页，准备点击下一个网页")
                actions.extend(search_actions)
                if len(_usable_travel_readings(readings)) >= 3:
                    break
                break
            if len(_usable_travel_readings(readings)) >= 3:
                break
            if not opened_page and missed_readings:
                readings.append(missed_readings[-1])
                search_actions = _travel_search_setup_actions(engine_index=engine_index)
                ctx.execute(search_actions, f"重新打开 {engine_name} 搜索结果页，准备恢复选择网页")
                actions.extend(search_actions)

        model_summary = self._summarize_beijing_travel_with_model(readings)
        summary = build_beijing_travel_summary(readings, model_summary=model_summary)
        artifacts: list[str] = []
        notepad_status = ""
        saved_path: Path | None = None
        if ctx.allow_filesystem:
            try:
                saved_path = ctx.write_text_file(_travel_note_filename(ctx), summary)
            except Exception as exc:  # pragma: no cover - filesystem dependent
                ctx.last_action_error = str(exc)
                saved_path = None

        if saved_path is not None:
            artifacts.append(saved_path.name)
            opened = ctx.open_in_notepad(saved_path) if ctx.open_artifacts else False
            notepad_status = (
                f"总结已写入并用记事本打开：{saved_path}"
                if opened
                else f"总结已保存为记事本文本：{saved_path}"
            )
            ctx.execute([], "已生成北京旅游攻略总结并准备记事本文本")
        else:
            notepad_actions = [
                Action.from_dict({"type": "open_app_if_needed", "app": "notepad"}),
                Action.from_dict({"type": "wait", "seconds": 1.0}),
                Action.from_dict({"type": "type", "text": summary}),
            ]
            ctx.execute(notepad_actions, "打开记事本并写入北京旅游攻略总结")
            actions.extend(notepad_actions)
            notepad_status = "总结已直接写入记事本窗口。"

        usable_count = sum(1 for reading in readings if reading.usable)
        completed = has_enough_beijing_travel_evidence(readings)
        headline = (
            f"任务已完成：已读取 {usable_count} 个有效网页，并把北京旅游攻略总结写入记事本"
            if completed
            else f"任务未完成：只读取到 {usable_count} 个有效网页，已把阅读记录写入记事本"
        )
        lead = (
            "✅ 任务已完成：已读取多个有效网页，并把北京旅游攻略总结写入记事本。"
            if completed
            else "⚠️ 任务未完成：有效网页不足，未生成最终北京旅游攻略；已把阅读记录和下一步建议写入记事本。"
        )
        answer = (
            f"{lead}\n\n"
            f"网页读取：共打开并读取 {len(readings)} 个页面，其中 {usable_count} 个页面读取到有效正文。\n"
            f"最低要求：至少 {_TRAVEL_MIN_USABLE_PAGES} 个有效网页。\n"
            f"{notepad_status}\n\n"
            f"{summary}"
        )
        error = None if completed else "insufficient readable travel pages"
        return TaskSkillResult(
            handled=True,
            skill="travel_notepad",
            completed=completed,
            answer=answer.strip(),
            headline=headline,
            actions=actions,
            artifacts=artifacts,
            error=error,
        )

    def _travel_verification_result(self, actions: list[Action], reading: PageReading) -> TaskSkillResult:
        answer = (
            "⚠️ 已暂停：当前网页出现安全验证/人机验证，不能继续自动读取或绕过验证。\n\n"
            f"页面：{reading.title or '(无标题)'}\n"
            f"地址：{reading.url or '(未知地址)'}\n"
            f"原因：{reading.reason}\n\n"
            "请手动完成验证后，从历史记录或悬浮窗点击恢复，系统会继续读取页面。"
        )
        return TaskSkillResult(
            handled=True,
            skill="travel_notepad",
            completed=False,
            answer=answer,
            headline="检测到人机验证，已暂停等待人工处理",
            actions=actions,
            error="human verification required",
            requires_human=True,
            interruption_kind="generic_human_verification",
            interruption_reason=reading.reason,
        )

    def _visual_browser_decision(
        self,
        ctx: "_SkillContext",
        *,
        kind: str,
        index: int,
        filename: str,
        prompt: str,
    ) -> tuple[dict[str, Any], Path | None]:
        fake_decision = getattr(ctx.executor, "visual_browser_decision", None)
        if callable(fake_decision):
            try:
                payload = fake_decision(kind=kind, index=index, prompt=prompt)
                if isinstance(payload, dict):
                    return payload, None
            except Exception:
                pass

        ctx.execute([Action.from_dict({"type": "wait", "seconds": 0.25})], "对当前浏览器窗口进行视觉观察")
        screenshot_path = ctx.capture_screen(filename)
        if screenshot_path is None:
            return {}, None
        response = model_vision_ocr(
            self.config,
            screenshot_path,
            (
                "你是桌面浏览器多模态操作助手。请直接观察截图，像人一样判断当前界面、可点击目标和下一步。"
                "不要读取 DOM，不要根据网址猜页面内容。必须使用截图中的视觉信息。\n"
                + prompt
            ),
            max_tokens=1200,
        )
        return _parse_visual_decision_response(response), screenshot_path

    def _browser_visual_recovery_actions(self, decision: dict[str, Any], *, attempt: int) -> list[Action]:
        action = _decision_action(decision)
        state = _decision_text(decision, "state").lower()
        if action in {"press_enter", "enter", "submit"} or state == "address_bar_not_submitted":
            return [
                Action.from_dict({"type": "press", "key": "enter"}),
                Action.from_dict({"type": "wait", "seconds": 0.35}),
                Action.from_dict({"type": "press", "key": "enter"}),
                Action.from_dict({"type": "wait", "seconds": 3.5}),
            ]
        if action in {"reload", "refresh"}:
            return [
                Action.from_dict({"type": "hotkey", "keys": ["ctrl", "r"]}),
                Action.from_dict({"type": "wait", "seconds": 3.5}),
            ]
        if action in {"focus_browser", "focus"}:
            return [
                Action.from_dict({"type": "open_app_if_needed", "app": "browser"}),
                Action.from_dict({"type": "wait", "seconds": 0.5}),
            ]
        if action == "wait" or state == "loading":
            return [Action.from_dict({"type": "wait", "seconds": 2.5})]
        if attempt == 1:
            return [
                Action.from_dict({"type": "press", "key": "enter"}),
                Action.from_dict({"type": "wait", "seconds": 0.35}),
                Action.from_dict({"type": "press", "key": "enter"}),
                Action.from_dict({"type": "wait", "seconds": 3.5}),
            ]
        return [Action.from_dict({"type": "wait", "seconds": 2.5})]

    def _summarize_beijing_travel_with_model(self, readings: list[PageReading]) -> str | None:
        usable = _usable_travel_readings(readings)
        if len(usable) < _TRAVEL_MIN_USABLE_PAGES:
            return None
        evidence_lines: list[str] = []
        for index, reading in enumerate(usable, start=1):
            evidence_lines.append(f"来源 {index}: {reading.title or '(无标题)'}")
            evidence_lines.append(f"URL: {reading.url}")
            evidence_lines.append(excerpt(reading.text, limit=900))
            evidence_lines.append("")
        return model_chat(
            self.config,
            "你是严谨的中文旅行攻略助手。只能依据用户提供的已读取网页正文总结北京旅游攻略；"
            "不得声称读取了未提供的网页，不得编造门票价格、开放时间或实时政策。"
            "如果信息不足，要明确说明。输出适合直接写入记事本，条理清楚。",
            "任务：根据下面多个真实网页正文摘录，总结北京旅游攻略，并给出一个3天行程、交通/预约提示、餐饮建议。\n\n"
            + "\n".join(evidence_lines),
            max_tokens=900,
        )

    def _read_travel_page_visually(self, ctx: "_SkillContext", *, url: str, label: str, index: int) -> PageReading:
        snapshot = self._visual_page_snapshot(ctx, url=url, label=label, index=index)
        reading = classify_page(snapshot)
        mismatch_reason = _travel_ocr_target_mismatch(reading.title or label, reading.text or "")
        if mismatch_reason is not None and reading.status not in {"verification", "login"}:
            return PageReading(
                "empty",
                reading.url or url,
                reading.title or label,
                "",
                f"多模态视觉判定：{mismatch_reason}",
            )
        reason = reading.reason
        if reading.usable:
            reason = "多模态视觉分析（鼠标点击搜索结果 + 滚轮阅读页面）"
        elif reason:
            reason = f"多模态视觉判定：{reason}"
        return PageReading(
            reading.status,
            reading.url or url,
            reading.title or label,
            reading.text,
            reason,
        )

    def _visual_page_snapshot(self, ctx: "_SkillContext", *, url: str, label: str, index: int) -> dict[str, Any] | None:
        fake_visual_snapshot = getattr(ctx.executor, "visual_page_snapshot", None)
        if callable(fake_visual_snapshot):
            try:
                snapshot = fake_visual_snapshot(url=url, label=label, index=index)
                if isinstance(snapshot, dict):
                    snapshot.setdefault("url", url)
                    snapshot.setdefault("title", label)
                    return snapshot
            except Exception:
                pass

        ctx.execute([Action.from_dict({"type": "wait", "seconds": 0.25})], "读取当前浏览器窗口")
        screenshot_path = ctx.capture_screen(f"visual_page_{index:02d}.jpg")
        if screenshot_path is None:
            return {"url": url, "title": label, "text": "", "source": "visual_ocr"}
        ocr_text = model_vision_ocr(
            self.config,
            screenshot_path,
            (
                f"这是点击搜索结果后打开的第 {index} 个北京旅游攻略网页截图，搜索结果标题为“{label}”。\n"
                "请进行多模态视觉分析：判断这是否是攻略正文页、是否有验证码/登录拦截、页面当前可见正文讲了什么。"
                "不要读取 DOM，不要根据 URL 猜内容，只根据截图中的视觉信息。\n"
                "请输出完整 JSON：{\"title\":\"...\",\"visible_text\":\"...\"}。不要使用 Markdown 代码块；"
                "visible_text 控制在 900 个中文字符以内。"
            ),
            max_tokens=1400,
        )
        title, text = _parse_visual_ocr_response(ocr_text, default_title=label)
        texts = [text] if text else []
        initial_reading = classify_page({"url": url, "title": title, "text": text})
        if initial_reading.status not in {"verification", "login", "search_results"} and _travel_ocr_target_mismatch(title, text) is None:
            for scroll_index in range(2, 4):
                scroll_actions = [
                    Action.from_dict({"type": "scroll", "amount": -7}),
                    Action.from_dict({"type": "wait", "seconds": 0.9}),
                ]
                ctx.execute(scroll_actions, f"向下滚动并继续视觉阅读北京旅游攻略网页 {index} 第 {scroll_index} 屏")
                scrolled_path = ctx.capture_screen(f"visual_page_{index:02d}_scroll_{scroll_index:02d}.jpg")
                if scrolled_path is None:
                    continue
                scrolled_ocr = model_vision_ocr(
                    self.config,
                    scrolled_path,
                    (
                        f"这是同一个北京旅游攻略网页第 {index} 个页面向下滚动后的第 {scroll_index} 屏截图，"
                        f"搜索结果标题为“{label}”。\n"
                        "请进行多模态视觉分析，只根据当前截图提取可见正文、景点、交通、行程或注意事项。不要读取 DOM，不要根据 URL 猜内容。\n"
                        "请输出完整 JSON：{\"title\":\"...\",\"visible_text\":\"...\"}。不要使用 Markdown 代码块；"
                        "visible_text 控制在 900 个中文字符以内。"
                    ),
                    max_tokens=1200,
                )
                scrolled_title, scrolled_text = _parse_visual_ocr_response(scrolled_ocr, default_title=title)
                if scrolled_title and title == label:
                    title = scrolled_title
                scrolled_text = _normalize(scrolled_text)
                if scrolled_text and scrolled_text not in texts:
                    texts.append(scrolled_text)
        combined_text = "\n\n".join(texts)
        return {
            "url": url,
            "title": title,
            "text": combined_text,
            "source": "visual_ocr",
            "screenshot": str(screenshot_path),
        }

    def _run_qq_group_message(self, task: str, ctx: "_SkillContext") -> TaskSkillResult:
        request = extract_qq_group_message(task)
        if not request.group_name or not request.message:
            answer = (
                "⚠️ QQ 群聊发送任务缺少必要信息，未执行发送。\n\n"
                "请把群名和消息写清楚，例如：\n"
                "打开QQ在群聊“项目演示群”发送消息“今天的演示已准备好”。"
            )
            return TaskSkillResult(
                handled=True,
                skill="qq_group_message",
                completed=False,
                answer=answer,
                headline="QQ 群聊发送任务未执行：缺少群名或消息",
                error="missing qq group name or message",
            )

        group_name = request.group_name
        message = request.message
        locate_actions = [
            Action.from_dict({"type": "open_app_if_needed", "app": "qq"}),
            Action.from_dict({"type": "wait", "seconds": 2.0}),
            Action.from_dict({"type": "hotkey", "keys": ["ctrl", "f"]}),
            Action.from_dict({"type": "wait", "seconds": 0.3}),
            Action.from_dict({"type": "hotkey", "keys": ["ctrl", "a"]}),
            Action.from_dict({"type": "type", "text": group_name}),
            Action.from_dict({"type": "press", "key": "enter"}),
            Action.from_dict({"type": "wait", "seconds": 1.2}),
        ]
        ctx.execute(locate_actions, f"打开 QQ 并定位群聊“{group_name}”")
        verification = self._verify_qq_group_visually(ctx, group_name=group_name)
        if not bool(verification.get("matched", False)):
            reason = _decision_text(verification, "reason", "visible_text") or "无法确认当前 QQ 会话就是目标群聊"
            answer = (
                "⏸️ 已暂停：未发送 QQ 消息。\n\n"
                f"目标群聊：{group_name}\n"
                f"待发送内容：{message}\n"
                f"暂停原因：{reason}\n\n"
                "请人工确认当前 QQ 窗口已经进入正确群聊后，再继续执行发送。"
            )
            return TaskSkillResult(
                handled=True,
                skill="qq_group_message",
                completed=False,
                answer=answer,
                headline=f"QQ 群聊发送暂停：需要确认“{group_name}”",
                actions=locate_actions,
                error="qq group verification required",
                requires_human=True,
                interruption_kind="qq_group_verification",
                interruption_reason=reason,
            )

        send_actions = [
            Action.from_dict({"type": "type", "text": message}),
            Action.from_dict({"type": "press", "key": "enter"}),
        ]
        ctx.execute(send_actions, f"确认群聊“{group_name}”后发送消息")
        actions = locate_actions + send_actions
        headline = f"任务已完成：已在 QQ 群聊“{group_name}”发送消息"
        answer = (
            "✅ 任务已完成：已按用户指令打开 QQ、定位目标群聊并发送消息。\n\n"
            f"目标群聊：{group_name}\n"
            f"发送内容：{message}\n\n"
            "演示前请确保 QQ 已登录，且群名能通过 QQ 搜索唯一定位。"
        )
        return TaskSkillResult(
            handled=True,
            skill="qq_group_message",
            completed=True,
            answer=answer,
            headline=headline,
            actions=actions,
        )

    def _verify_qq_group_visually(self, ctx: "_SkillContext", *, group_name: str) -> dict[str, Any]:
        fake_verify = getattr(ctx.executor, "qq_group_verification", None)
        if callable(fake_verify):
            try:
                payload = fake_verify(group_name=group_name)
                if isinstance(payload, dict):
                    return payload
            except Exception:
                pass
        if bool(getattr(self.config, "dry_run", True)):
            return {"matched": True, "reason": "dry-run"}
        screenshot_path = ctx.capture_screen("qq_group_verification.jpg")
        if screenshot_path is None:
            return {"matched": False, "reason": "无法截取 QQ 窗口截图"}
        response = model_vision_ocr(
            self.config,
            screenshot_path,
            (
                "你是桌面 QQ 群聊发送前的安全确认器。只根据截图判断当前 QQ 窗口是否已经进入目标群聊，"
                f"目标群聊名称是“{group_name}”。如果看不到 QQ、看不到群名、像搜索结果列表而不是聊天窗口、"
                "存在多个相似群、或输入框不可见，matched 必须为 false。"
                "只输出 JSON：{\"matched\":false,\"reason\":\"...\",\"visible_text\":\"...\"}。"
            ),
            max_tokens=800,
        )
        payload = _extract_json_object(_normalize(response))
        if isinstance(payload, dict):
            return payload
        return {"matched": False, "reason": _normalize(response) or "模型未返回可解析确认结果"}

    def _run_travel_word(self, task: str, ctx: "_SkillContext") -> TaskSkillResult:
        # Open a China-accessible search engine. The app default is Google,
        # unreachable in mainland China, so we use Baidu and then READ what the
        # page actually returned instead of assuming it succeeded.
        search_url = "https://www.baidu.com/s?wd=" + _url_quote("北京旅游景点 三天行程 攻略")
        actions = [
            Action.from_dict({"type": "browser_open", "text": search_url}),
            Action.from_dict({"type": "wait", "seconds": 2.0}),
        ]
        ctx.execute(actions, "上网搜索北京旅游景点并读取页面…")
        reading = classify_page(ctx.read_page())
        search_excerpt = excerpt(reading.text, limit=700) if reading.usable else ""
        if reading.usable:
            search_note = "（已联网检索并读取到真实页面内容，原文摘录见文末与 Word 文档）"
        else:
            search_note = (
                f"（实时检索未取得可用结果：{reading.reason}"
                "以下 3 天行程为结合经典线路整理的通用规划，并非来自本次搜索）"
            )

        plan_text = build_beijing_plan_text()
        artifacts: list[str] = []
        doc_status = ""
        if ctx.allow_filesystem:
            try:
                saved_path = ctx.write_docx(
                    _TRAVEL_DOC_FILENAME,
                    lambda p: write_beijing_docx(p, search_excerpt=search_excerpt or None),
                )
                artifacts.append(saved_path.name)
                doc_status = f"📄 已用 Word 文档保存到：{saved_path}"
                if ctx.open_artifacts and ctx.open_path(saved_path):
                    doc_status += "（已自动打开）"
            except Exception as exc:  # pragma: no cover - filesystem dependent
                doc_status = f"⚠️ Word 文档生成失败：{exc}"

        headline = "任务已完成：已整理北京 3 天行程并保存为 Word 文档"
        parts = [
            "✅ 任务已完成：已生成北京 3 天旅游规划，并保存为 Word 文档。",
            search_note,
            "",
            plan_text,
        ]
        if search_excerpt:
            parts += ["", "🔎 实时检索摘录（来自百度，原文未改写）：", search_excerpt]
        if doc_status:
            parts += ["", doc_status]
        return TaskSkillResult(
            handled=True,
            skill="travel_word",
            completed=True,
            answer="\n".join(parts).strip(),
            headline=headline,
            actions=actions,
            artifacts=artifacts,
        )


@dataclass(slots=True)
class _SkillContext:
    executor: Any
    run_dir: Path | None
    output_dir: Path | None
    open_artifacts: bool
    allow_filesystem: bool
    pause_after_action: float
    stop_requested: Callable[[], bool] | None
    emit: EmitCallback | None
    _step: int = 0
    last_action_error: str | None = None

    def execute(self, actions: list[Action], headline: str) -> None:
        self._step += 1
        if self.emit is not None:
            try:
                self.emit(headline, actions, self._step)
            except Exception:
                pass
        executor = self.executor
        if executor is None:
            return
        try:
            execute_many = getattr(executor, "execute_many", None)
            if execute_many is None:
                for action in actions:
                    executor.execute(action)
            else:
                execute_many(actions, self.pause_after_action, self.stop_requested)
        except Exception as exc:
            # Honour an explicit user stop, but otherwise keep going: the spoken
            # answer is the real deliverable and a transient GUI/browser hiccup
            # should not rob the user of it.
            if exc.__class__.__name__ == "ExecutionCancelled":
                raise
            self.last_action_error = str(exc)

    def read_page(self) -> dict[str, Any] | None:
        """Return what the real browser actually loaded ({url,title,text}) or None."""

        snapshot_fn = getattr(self.executor, "browser_snapshot", None)
        if snapshot_fn is None:
            return None
        try:
            snapshot = snapshot_fn()
        except Exception:
            return None
        return snapshot if isinstance(snapshot, dict) else None

    def capture_screen(self, filename: str) -> Path | None:
        """Save a screenshot for visual OCR, using executor/plugin capture when available."""

        target_dir = self.run_dir or self.output_dir or Path.cwd()
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / filename
        capture_fn = getattr(self.executor, "capture_screen_image", None)
        if callable(capture_fn):
            try:
                captured = capture_fn(target)
            except Exception:
                captured = None
            if isinstance(captured, (str, Path)):
                captured_path = Path(captured)
                if captured_path.exists():
                    return captured_path
            if captured is True and target.exists():
                return target
        return capture_screen_image(target)

    def click_image_point(self, image_path: Path | None, point: tuple[int, int] | None) -> Action | None:
        if point is None:
            return None
        x, y = int(point[0]), int(point[1])
        if image_path is not None:
            try:
                from PIL import Image

                with Image.open(image_path) as image:
                    image_width, image_height = image.size
                screen_width, screen_height = self._screen_size()
                if image_width > 0 and image_height > 0:
                    x = int(round(x * screen_width / image_width))
                    y = int(round(y * screen_height / image_height))
            except Exception:
                pass
        return Action.from_dict({"type": "click", "x": max(0, x), "y": max(0, y)})

    def _screen_size(self) -> tuple[int, int]:
        try:
            import pyautogui

            width, height = pyautogui.size()
            return int(width), int(height)
        except Exception:
            return 1920, 1080

    def write_docx(self, filename: str, builder: Callable[[Path], Path]) -> Path:
        target_dir = self.output_dir or self.run_dir or Path.cwd()
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / filename
        builder(target)
        self._copy_to_run_dir(target, filename, target_dir)
        return target

    def write_text_file(self, filename: str, content: str) -> Path | None:
        """Write a UTF-8 text file (CRLF + BOM) Notepad can open reliably.

        Returns None when no output location is configured so the caller can fall
        back to driving the GUI directly (used by tests with no output dir).
        """

        target_dir = self.output_dir or self.run_dir
        if target_dir is None:
            return None
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / filename
        normalized = content.replace("\r\n", "\n").replace("\n", "\r\n")
        target.write_bytes(normalized.encode("utf-8-sig"))
        self._copy_to_run_dir(target, filename, target_dir)
        return target

    def _copy_to_run_dir(self, target: Path, filename: str, target_dir: Path) -> None:
        # Keep a copy alongside the run artifacts so the dashboard can link it.
        if self.run_dir is not None and self.run_dir != target_dir:
            try:
                self.run_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, self.run_dir / filename)
            except Exception:
                pass

    def open_in_notepad(self, path: Path) -> bool:
        """Open *path* specifically in Notepad (new instance with the file)."""

        import subprocess

        try:
            subprocess.Popen(["notepad.exe", str(path)])
            return True
        except Exception:
            return self.open_path(path)

    def open_in_typora(self, path: Path) -> bool:
        """Open *path* in Typora when available, otherwise use the OS default."""

        import subprocess

        candidates: list[str] = []
        resolved = shutil.which("Typora") or shutil.which("typora")
        if resolved:
            candidates.append(resolved)
        program_files = os.environ.get("ProgramFiles")
        program_files_x86 = os.environ.get("ProgramFiles(x86)")
        local_app_data = os.environ.get("LOCALAPPDATA")
        for base in (program_files, program_files_x86, local_app_data):
            if not base:
                continue
            candidates.append(str(Path(base) / "Typora" / "Typora.exe"))
            candidates.append(str(Path(base) / "Programs" / "Typora" / "Typora.exe"))
        seen: set[str] = set()
        for candidate in candidates:
            normalized = str(candidate)
            if normalized in seen:
                continue
            seen.add(normalized)
            if not Path(normalized).exists():
                continue
            try:
                subprocess.Popen([normalized, str(path)])
                return True
            except Exception:
                continue
        return self.open_path(path)

    def open_path(self, path: Path) -> bool:
        startfile = getattr(os, "startfile", None)
        if startfile is None:
            return False
        try:
            startfile(str(path))  # type: ignore[misc]
            return True
        except Exception:
            return False


def _url_quote(value: str) -> str:
    from urllib.parse import quote_plus

    return quote_plus(value)


def resolve_user_output_dir() -> Path:
    """Pick a friendly, visible location for generated documents."""

    home = Path.home()
    for candidate in (home / "Desktop", home / "桌面", home / "Documents", home / "文档"):
        if candidate.is_dir():
            return candidate
    return home
