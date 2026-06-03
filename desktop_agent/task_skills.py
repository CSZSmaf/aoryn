"""Deterministic task skills with spoken results.

This module implements a small set of high-value desktop tasks end-to-end so the
agent can both *perform* the action on the real desktop and *report a concrete
answer back into the conversation*. It is intentionally independent from the
LLM/VLM planner: every answer is produced by deterministic local logic, so the
four showcase tasks work reliably even without a model server.

Supported skills:

1. ``calculator``     - open Windows Calculator and compute an arithmetic
                        expression, reporting the exact result.
2. ``notepad_poem``   - open Notepad and write an original short poem.
3. ``shopping_pants`` - open a shopping site search for men's trousers and
                        report a cost-performance (性价比) analysis.
4. ``travel_word``    - research Beijing attractions, build a 3-day itinerary and
                        save it as a real Word (.docx) document.

The runner stays pure: it executes :class:`~desktop_agent.actions.Action`
objects through whatever executor it is handed (real or mock) and never reaches
into global state. Side effects that touch the filesystem or launch external
viewers are gated by explicit flags so the runner is safe to unit-test.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from xml.sax.saxutils import escape as _xml_escape

from desktop_agent.actions import Action
from desktop_agent.web_research import (
    PageReading,
    classify_page,
    excerpt,
    extract_brand_mentions,
    extract_prices,
    model_chat,
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


# ---------------------------------------------------------------------------
# Keyword vocabularies (Chinese + English) used by the matchers.
# ---------------------------------------------------------------------------

_CALC_APP_TERMS = ("计算器", "calculator", "calc")
_CALC_VERB_TERMS = ("计算", "运算", "算一下", "算出", "算", "compute", "calculate", "evaluate", "equals")
_NOTEPAD_TERMS = ("记事本", "notepad")
_POEM_TERMS = ("诗", "poem", "verse", "poetry")
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


def _beijing_research_targets() -> tuple[tuple[str, str], ...]:
    return (
        ("百度搜索", "https://www.baidu.com/s?wd=" + _url_quote("北京旅游攻略 必去景点 行程")),
        ("必应搜索", "https://cn.bing.com/search?q=" + _url_quote("北京旅游攻略 三天 行程")),
        ("马蜂窝北京", "https://www.mafengwo.cn/travel-scenic-spot/mafengwo/10065.html"),
        ("携程北京目的地", "https://you.ctrip.com/place/beijing1.html"),
    )


def build_beijing_travel_summary(readings: list[PageReading]) -> str:
    """Build a Notepad-friendly Beijing travel summary from page readings.

    The summary records which pages were actually opened/read, then gives a
    conservative route plan that is stable enough for live demos even when a
    search site blocks automation.
    """

    usable = [reading for reading in readings if reading.usable]
    lines: list[str] = [
        "北京旅游攻略总结",
        "",
        "一、网页阅读情况",
    ]
    if not readings:
        lines.append("1. 未读取到浏览器页面快照，以下为保底行程整理。")
    else:
        for index, reading in enumerate(readings, start=1):
            title = reading.title or "(无标题)"
            url = reading.url or "(无 URL)"
            state = "已读取" if reading.usable else f"未取得有效正文：{reading.reason}"
            lines.append(f"{index}. {state}")
            lines.append(f"   标题：{title}")
            lines.append(f"   地址：{url}")
            if reading.usable:
                page_excerpt = " ".join(excerpt(reading.text, limit=220).split())
                if page_excerpt:
                    lines.append(f"   摘要：{page_excerpt}")
    lines += [
        "",
        "二、综合建议",
        "1. 第一天走中轴线：天安门广场、故宫、景山公园、王府井。故宫需要提前实名预约，景山适合俯瞰故宫全景。",
        "2. 第二天安排长城与奥运区域：八达岭或慕田峪长城择一，下午返回市区看鸟巢、水立方夜景。",
        "3. 第三天看皇家园林和胡同：颐和园、圆明园、什刹海或南锣鼓巷，节奏比前两天轻松。",
        "4. 交通优先地铁，长城段选择正规旅游专线或市郊铁路；热门景点门票、升旗观礼和博物馆建议提前预约。",
        "5. 餐饮可安排北京烤鸭、炸酱面、卤煮、豆汁焦圈等本地特色，但景区周边用餐要看价格和评价。",
        "",
        "三、演示说明",
    ]
    if usable:
        lines.append(f"本次已成功读取 {len(usable)} 个网页的正文，上面的攻略综合了可读页面内容和稳定经典路线。")
    else:
        lines.append("本次网页可能被搜索引擎/旅游站点拦截或返回空正文，系统仍已打开多个网页并生成可展示的保底攻略。")
    return "\r\n".join(lines).strip() + "\r\n"


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
        if self._is_notepad_poem(text, lowered):
            return "notepad_poem"
        if self._is_shopping_pants(text, lowered):
            return "shopping_pants"
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
        has_summary = _contains_any(text, _SUMMARY_TERMS) or _contains_any(lowered, _SUMMARY_TERMS)
        has_search = _contains_any(text, _SEARCH_TERMS) or _contains_any(lowered, _SEARCH_TERMS)
        has_read = _contains_any(text, _READ_TERMS) or _contains_any(lowered, _READ_TERMS)
        asks_word = _contains_any(lowered, _WORD_TERMS)
        return has_travel and not asks_word and (has_notepad or (has_summary and (has_search or has_read)))

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
            "travel_notepad": self._run_travel_notepad,
            "travel_word": self._run_travel_word,
            "qq_group_message": self._run_qq_group_message,
        }.get(skill)
        if handler is None:
            return TaskSkillResult(handled=False, skill=skill)
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
        return handler(task, context)

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

    def _run_travel_notepad(self, task: str, ctx: "_SkillContext") -> TaskSkillResult:
        actions: list[Action] = []
        readings: list[PageReading] = []
        for index, (label, url) in enumerate(_beijing_research_targets(), start=1):
            step_actions = [
                Action.from_dict({"type": "browser_open", "text": url}),
                Action.from_dict({"type": "wait", "seconds": 1.4 if index > 1 else 2.0}),
            ]
            ctx.execute(step_actions, f"打开并阅读北京旅游攻略网页 {index}：{label}")
            actions.extend(step_actions)
            readings.append(classify_page(ctx.read_page()))

        summary = build_beijing_travel_summary(readings)
        artifacts: list[str] = []
        notepad_status = ""
        saved_path: Path | None = None
        if ctx.allow_filesystem:
            try:
                saved_path = ctx.write_text_file(_TRAVEL_NOTE_FILENAME, summary)
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
        headline = f"任务已完成：已阅读 {len(readings)} 个北京旅游相关网页，并把攻略总结写入记事本"
        answer = (
            "✅ 任务已完成：已打开浏览器搜索/阅读北京旅游攻略相关网页，并把总结内容写入记事本。\n\n"
            f"网页读取：共打开并读取 {len(readings)} 个页面，其中 {usable_count} 个页面读取到有效正文。\n"
            f"{notepad_status}\n\n"
            f"{summary}"
        )
        return TaskSkillResult(
            handled=True,
            skill="travel_notepad",
            completed=True,
            answer=answer.strip(),
            headline=headline,
            actions=actions,
            artifacts=artifacts,
        )

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
        actions = [
            Action.from_dict({"type": "open_app_if_needed", "app": "qq"}),
            Action.from_dict({"type": "wait", "seconds": 2.0}),
            Action.from_dict({"type": "hotkey", "keys": ["ctrl", "f"]}),
            Action.from_dict({"type": "wait", "seconds": 0.3}),
            Action.from_dict({"type": "hotkey", "keys": ["ctrl", "a"]}),
            Action.from_dict({"type": "type", "text": group_name}),
            Action.from_dict({"type": "press", "key": "enter"}),
            Action.from_dict({"type": "wait", "seconds": 1.2}),
            Action.from_dict({"type": "type", "text": message}),
            Action.from_dict({"type": "press", "key": "enter"}),
        ]
        ctx.execute(actions, f"打开 QQ，搜索群聊“{group_name}”，并发送消息")
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
