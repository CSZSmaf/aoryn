"""Honest web-research helpers for the task skills.

The two web tasks (shopping cost-performance, Beijing travel) must base their
answers on what was *actually* retrieved, never on fabricated data. In practice
mainland-China search engines and shopping sites aggressively block automation
(login walls, 安全验证 captchas), so retrieval frequently fails. These helpers
let a skill:

* read the page the real browser actually loaded,
* classify it (ok / search_results / login / verification / empty / error), and
* optionally run a genuine analysis with a locally-configured OpenAI-compatible
  model **on the real page content** — only when that endpoint is reachable.

Nothing here invents product prices, ratings, or search results.
"""

from __future__ import annotations

import json
import re
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit


@dataclass(slots=True)
class PageReading:
    status: str  # "ok" | "search_results" | "login" | "verification" | "empty" | "error"
    url: str
    title: str
    text: str
    reason: str

    @property
    def usable(self) -> bool:
        return self.status == "ok"


_LOGIN_MARKERS = ("passport.", "/login", "login.aspx", "signin", "sign-in", "/sign_in", "accounts.")
_LOGIN_TEXT_MARKERS = ("请登录", "登录后", "扫码登录", "账号登录", "sign in to", "log in to")
_VERIFY_MARKERS = ("安全验证", "人机验证", "滑动验证", "captcha", "verify you are human", "unusual traffic", "robot")
_SEARCH_ENGINE_HOSTS = (
    "bing.com",
    "cn.bing.com",
    "www.bing.com",
    "baidu.com",
    "www.baidu.com",
    "google.com",
    "www.google.com",
    "sogou.com",
    "www.sogou.com",
    "so.com",
    "www.so.com",
)
_SEARCH_ENGINE_PATHS = ("/search", "/s", "/web")
_SEARCH_RESULT_TEXT_MARKERS = ("网页", "图片", "视频", "约 ", "个结果", "更多", "Rewards")


def clean_page_text(value: Any, *, limit: int = 1200) -> str:
    text = str(value or "")
    text = re.sub(r"[ \t ]+", " ", text)
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    collapsed = "\n".join(lines)
    collapsed = re.sub(r"\n{2,}", "\n", collapsed)
    return collapsed[:limit].strip()


def classify_page(snapshot: dict[str, Any] | None) -> PageReading:
    if not isinstance(snapshot, dict):
        return PageReading("error", "", "", "", "浏览器没有返回可读取的页面内容（可能未通过受控浏览器/DOM 打开）。")
    url = str(snapshot.get("url") or "").strip()
    title = str(snapshot.get("title") or "").strip()
    raw_text = str(snapshot.get("text") or "")
    text = clean_page_text(raw_text)
    haystack_head = f"{url}\n{title}".lower()
    haystack_all = f"{url}\n{title}\n{text}".lower()

    if any(marker in haystack_all for marker in _VERIFY_MARKERS):
        return PageReading("verification", url, title, text, "页面出现安全/人机验证，被反爬拦截，未能获取真实数据。")
    if any(marker in haystack_head for marker in _LOGIN_MARKERS) or any(
        marker in text for marker in _LOGIN_TEXT_MARKERS
    ):
        if len(text) < 600:
            return PageReading("login", url, title, text, "页面跳转到登录，未能在未登录状态下获取真实数据。")
    if len(text) < 80:
        return PageReading("empty", url, title, text, "页面几乎没有可读取的文本（可能仍在加载或被拦截）。")
    if _looks_like_search_results_page(url=url, title=title, text=text):
        return PageReading("search_results", url, title, text, "这是搜索结果页，不是可直接引用的攻略正文页。")
    return PageReading("ok", url, title, text, "已成功读取页面文本内容。")


def _looks_like_search_results_page(*, url: str, title: str, text: str) -> bool:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    path = (parsed.path or "").lower()
    if host not in _SEARCH_ENGINE_HOSTS:
        return False
    if not any(path.startswith(item) for item in _SEARCH_ENGINE_PATHS):
        return False
    title_text = f"{title}\n{text[:500]}"
    return any(marker in title_text for marker in _SEARCH_RESULT_TEXT_MARKERS) or " - 搜索" in title


def endpoint_reachable(base_url: str | None, *, timeout: float = 0.35) -> bool:
    raw = str(base_url or "").strip()
    if not raw:
        return False
    if "://" not in raw:
        raw = "http://" + raw
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return False
    host = (parsed.hostname or "").strip()
    if not host:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def model_chat(config: Any, system: str, user: str, *, max_tokens: int = 700) -> str | None:
    """Best-effort chat completion against the configured OpenAI-compatible model.

    Returns the assistant text, or None when the endpoint is not configured /
    reachable / well-formed. Never raises.
    """

    base_url = str(getattr(config, "model_base_url", "") or "").strip()
    if not base_url or not endpoint_reachable(base_url):
        return None
    try:
        import requests  # local import keeps module import light
    except Exception:
        return None

    model_name = str(getattr(config, "model_name", "") or "").strip() or "auto"
    if model_name == "auto":
        model_name = _discover_model_name(requests, base_url, config) or "gpt-3.5-turbo"
    api_key = str(getattr(config, "model_api_key", "") or "").strip()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
        "max_tokens": max_tokens,
        "stream": False,
    }
    try:
        response = requests.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
            timeout=min(float(getattr(config, "model_request_timeout", 60.0) or 60.0), 60.0),
        )
        if response.status_code >= 400:
            return None
        data = response.json()
    except Exception:
        return None
    content = _extract_message_content(data)
    return content or None


def _discover_model_name(requests_module: Any, base_url: str, config: Any) -> str | None:
    try:
        api_key = str(getattr(config, "model_api_key", "") or "").strip()
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        response = requests_module.get(f"{base_url.rstrip('/')}/models", headers=headers, timeout=3.0)
        if response.status_code >= 400:
            return None
        data = response.json()
        items = data.get("data") if isinstance(data, dict) else None
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, dict) and first.get("id"):
                return str(first["id"])
    except Exception:
        return None
    return None


def _extract_message_content(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [str(item.get("text", "")) for item in content if isinstance(item, dict)]
        return "\n".join(part for part in parts if part).strip()
    return ""


# --- light, honest extraction from real page text --------------------------

_PRICE_PATTERN = re.compile(r"(?:¥|￥|RMB|人民币)\s?(\d{2,5}(?:\.\d{1,2})?)|(\d{2,5}(?:\.\d{1,2})?)\s?元")


def extract_prices(text: str, *, limit: int = 12) -> list[str]:
    found: list[str] = []
    for match in _PRICE_PATTERN.finditer(text or ""):
        value = match.group(1) or match.group(2)
        if not value:
            continue
        token = f"¥{value}"
        if token not in found:
            found.append(token)
        if len(found) >= limit:
            break
    return found


def extract_brand_mentions(text: str, brands: tuple[str, ...], *, limit: int = 8) -> list[str]:
    lowered = (text or "").lower()
    hits: list[str] = []
    for brand in brands:
        if brand.lower() in lowered and brand not in hits:
            hits.append(brand)
        if len(hits) >= limit:
            break
    return hits


def excerpt(text: str, *, limit: int = 600) -> str:
    return clean_page_text(text, limit=limit)
