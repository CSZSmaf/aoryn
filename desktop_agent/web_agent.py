from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import quote_plus

from desktop_agent.actions import Action, PlanResult


@dataclass(slots=True)
class PopupHint:
    kind: str
    policy: str
    labels: tuple[str, ...] = ()


@dataclass(slots=True)
class WebPageInfo:
    requested_url: str
    resolved_url: str
    title: str | None = None
    description: str | None = None
    headings: tuple[str, ...] = ()
    action_labels: tuple[str, ...] = ()
    popup_hints: tuple[PopupHint, ...] = ()


@dataclass(slots=True)
class WebCommand:
    intent: str
    target: str | None = None
    follow_up: str | None = None
    follow_up_steps: tuple[str, ...] = ()
    marketplace: str | None = None
    shopping_query: str | None = None
    page_info: WebPageInfo | None = None


class WebAgent:
    """Parse browser-oriented tasks into explicit browser actions and hints."""

    SEARCH_PATTERNS = (
        re.compile(
            r"^(?:"
            r"\u6253\u5f00\s*(?:\u4e00\u4e2a\s*)?(?:\u6d4f\u89c8\u5668|edge|chrome|browser)\s*(?:\u5e76|\u7136\u540e)?\s*(?:\u641c\u7d22|\u641c\u4e00\u4e0b|\u67e5\u627e)"
            r"|(?:\u5728\s*)?(?:\u6d4f\u89c8\u5668|browser)\s*(?:\u91cc|\u4e2d)?\s*(?:\u641c\u7d22|\u641c\u4e00\u4e0b|\u67e5\u627e)"
            r"|(?:\u641c\u7d22|\u641c\u4e00\u4e0b|\u67e5\u627e)"
            r"|search(?:\s+for)?"
            r")\s*(?P<query>.+)$",
            re.I,
        ),
    )
    OPEN_PATTERNS = (
        re.compile(
            r"^(?:"
            r"\u6253\u5f00\s*(?:\u4e00\u4e2a\s*)?(?:\u6d4f\u89c8\u5668|edge|chrome|browser)\s*(?:\u5e76|\u7136\u540e)?\s*(?:\u8bbf\u95ee|\u8fdb\u5165|\u524d\u5f80)"
            r"|(?:\u8bbf\u95ee|\u8fdb\u5165|\u524d\u5f80)"
            r"|go\s+to|visit"
            r")\s*(?P<target>.+)$",
            re.I,
        ),
    )
    LAUNCH_PATTERNS = (
        re.compile(
            r"^(?:"
            r"\u6253\u5f00\s*(?:\u4e00\u4e2a\s*)?(?:\u6d4f\u89c8\u5668|edge|chrome|browser)"
            r"|open\s*(?:the\s*)?(?:browser|edge|chrome)"
            r")$",
            re.I,
        ),
    )

    def __init__(self, *, requests_module=None, request_timeout: float = 3.0) -> None:
        self.requests_module = requests_module
        self.request_timeout = request_timeout

    def try_plan(self, task: str) -> PlanResult | None:
        command = self.parse(task)
        if command is None or command.follow_up_steps:
            return None

        enriched = self.enrich(command)
        return PlanResult(
            status_summary=self._build_status(enriched),
            done=True,
            actions=self._build_actions(enriched),
            current_focus=_describe_web_focus(enriched),
            reasoning="The task can be completed directly with a deterministic browser action.",
            remaining_steps=[],
        )

    def build_navigation_plan(self, task: str) -> PlanResult | None:
        command = self.parse(task)
        if command is None or not command.follow_up_steps:
            return None

        enriched = self.enrich(command)
        actions = self._build_actions(enriched)
        summary = self._build_status(enriched)
        follow_up_text = _format_follow_up_sequence(enriched.follow_up_steps)
        if follow_up_text:
            summary = f"{summary} Then continue with: {follow_up_text}."
        initial_focus = _describe_web_focus(enriched)
        return PlanResult(
            status_summary=summary,
            done=False,
            actions=actions,
            current_focus=initial_focus,
            reasoning="The destination page must be opened before the follow-up UI action can be attempted.",
            remaining_steps=list(enriched.follow_up_steps),
        )

    def build_dom_follow_up_plan(self, task: str, history: list[str]) -> PlanResult | None:
        command = self.parse(task)
        if command is None or not command.follow_up_steps:
            return None

        enriched = self.enrich(command)
        popup_plan = _build_popup_resolution_plan(enriched, history)
        if popup_plan is not None:
            return popup_plan

        completed_steps = _count_completed_follow_up_steps(enriched.follow_up_steps, history)
        if completed_steps >= len(enriched.follow_up_steps):
            return None

        current_step = enriched.follow_up_steps[completed_steps]
        remaining_steps = enriched.follow_up_steps[completed_steps + 1 :]
        follow_up_action = _parse_follow_up_dom_action(current_step)
        if follow_up_action is None:
            return None
        follow_up_action = _refine_dom_follow_up_action(follow_up_action, enriched.page_info)
        return PlanResult(
            status_summary=_build_follow_up_step_summary(
                current_step=current_step,
                step_index=completed_steps,
                total_steps=len(enriched.follow_up_steps),
                remaining_steps=remaining_steps,
            ),
            done=not remaining_steps and _follow_up_action_completes_task(follow_up_action),
            actions=[follow_up_action],
            current_focus=current_step,
            reasoning="Advance the next unmet browser follow-up step while preserving the remaining sequence.",
            remaining_steps=list(remaining_steps),
        )

    def parse(self, task: str) -> WebCommand | None:
        stripped = task.strip()
        if not stripped:
            return None

        if shopping_command := _parse_shopping_command(stripped):
            return shopping_command

        if self._matches_any(stripped, self.LAUNCH_PATTERNS):
            return WebCommand(intent="launch")

        if query := self._match_patterns(stripped, self.SEARCH_PATTERNS, "query"):
            clean_query, follow_up = _split_follow_up(query)
            follow_up_steps = _normalize_follow_up_steps(follow_up)
            return WebCommand(
                intent="search",
                target=clean_query,
                follow_up=_format_follow_up_sequence(follow_up_steps) if follow_up_steps else None,
                follow_up_steps=follow_up_steps,
            )

        if target := self._match_patterns(stripped, self.OPEN_PATTERNS, "target"):
            clean_target, follow_up = _split_follow_up(target)
            follow_up_steps = _normalize_follow_up_steps(follow_up)
            if _looks_like_url(clean_target):
                return WebCommand(
                    intent="open_url",
                    target=_ensure_url_scheme(clean_target),
                    follow_up=_format_follow_up_sequence(follow_up_steps) if follow_up_steps else None,
                    follow_up_steps=follow_up_steps,
                )
            return WebCommand(
                intent="search",
                target=target,
                follow_up=_format_follow_up_sequence(follow_up_steps) if follow_up_steps else None,
                follow_up_steps=follow_up_steps,
            )

        return None

    def enrich(self, command: WebCommand) -> WebCommand:
        if command.intent != "open_url" or not command.target:
            return command

        page_info = self.inspect_target(command.target)
        if page_info is not None:
            command.page_info = page_info
            command.target = page_info.resolved_url
        return command

    def inspect_target(self, target: str) -> WebPageInfo | None:
        requests = self.requests_module or _import_requests()
        if requests is None:
            return None

        headers = {
            "User-Agent": "DesktopAgent/1.0 (+browser preflight)",
            "Accept": "text/html,application/xhtml+xml",
        }
        try:
            response = requests.get(
                target,
                headers=headers,
                timeout=self.request_timeout,
                allow_redirects=True,
            )
            response.raise_for_status()
        except Exception:
            return None

        resolved_url = _ensure_url_scheme(str(getattr(response, "url", "")).strip() or target)
        headers_map = getattr(response, "headers", {}) or {}
        content_type = str(headers_map.get("Content-Type") or headers_map.get("content-type") or "")
        if "html" not in content_type.lower():
            return WebPageInfo(requested_url=target, resolved_url=resolved_url)

        raw_html = str(getattr(response, "text", "") or "")[:200_000]
        parser = _HTMLMetadataParser()
        parser.feed(raw_html)
        parser.close()
        return WebPageInfo(
            requested_url=target,
            resolved_url=resolved_url,
            title=parser.title,
            description=parser.description,
            headings=tuple(parser.headings[:3]),
            action_labels=tuple(parser.action_labels[:12]),
            popup_hints=_detect_popup_hints(raw_html, tuple(parser.action_labels[:20])),
        )

    def build_task_context(self, task: str) -> str | None:
        command = self.parse(task)
        if command is None:
            return None

        enriched = self.enrich(command)
        lines = [
            f"Browser intent: {enriched.intent}",
            "Browser popup policy: dismiss translate/password-save/notification popups first. "
            "For cookie banners prefer reject, close, dismiss, or necessary-only over accept-all unless consent is required.",
        ]
        if enriched.target:
            lines.append(f"Browser target: {enriched.target}")
        if enriched.follow_up:
            lines.append(f"Browser follow-up goal: {enriched.follow_up}")
        if enriched.intent == "shopping_search" and enriched.shopping_query:
            lines.append(f"Shopping goal: {enriched.shopping_query}")
            if enriched.marketplace:
                lines.append(f"Preferred marketplace: {enriched.marketplace}")
            lines.append(
                "Shopping policy: search and compare products first; do not add items to cart or check out unless explicitly asked."
            )
        if enriched.page_info and enriched.page_info.title:
            lines.append(f"Fetched page title: {enriched.page_info.title}")
        if enriched.page_info and enriched.page_info.description:
            lines.append(f"Fetched description: {enriched.page_info.description}")
        if enriched.page_info and enriched.page_info.headings:
            lines.append(f"Fetched headings: {', '.join(enriched.page_info.headings)}")
        if enriched.page_info and enriched.page_info.action_labels:
            lines.append(f"Visible page action labels from HTML: {', '.join(enriched.page_info.action_labels[:8])}")
        if enriched.page_info and enriched.page_info.popup_hints:
            for hint in enriched.page_info.popup_hints:
                lines.append(_format_popup_hint(hint))
        return "\n".join(lines)

    def _build_status(self, command: WebCommand) -> str:
        if command.intent == "launch":
            return "Launch the browser."
        if command.intent == "shopping_search":
            if _looks_like_url(command.target or ""):
                location = command.marketplace or "the marketplace"
                return f"Open shopping results for {command.shopping_query or command.target} on {location}."
            return f"Search shopping results for {command.shopping_query or command.target}."
        if command.intent == "open_url":
            details = [f"Open {command.target} in the browser."]
            if command.page_info and command.page_info.title:
                details.append(f"Expected page title: {command.page_info.title}.")
            elif command.page_info and command.page_info.description:
                details.append(f"Expected page description: {command.page_info.description}.")
            if command.page_info and command.page_info.popup_hints:
                details.append(f"Potential blockers: {', '.join(hint.kind for hint in command.page_info.popup_hints)}.")
            return " ".join(details)
        return f"Search the web for {command.target}."

    def _build_actions(self, command: WebCommand) -> list[Action]:
        if command.intent == "launch":
            return [
                Action.from_dict({"type": "open_app_if_needed", "app": "browser"}),
                Action.from_dict({"type": "wait", "seconds": 1.0}),
            ]
        if command.intent == "shopping_search":
            if _looks_like_url(command.target or ""):
                return [Action.from_dict({"type": "browser_open", "text": command.target})]
            return [Action.from_dict({"type": "browser_search", "text": command.target})]
        if command.intent == "open_url":
            return [Action.from_dict({"type": "browser_open", "text": command.target})]
        return [Action.from_dict({"type": "browser_search", "text": command.target})]

    @staticmethod
    def _match_patterns(task: str, patterns: tuple[re.Pattern[str], ...], group: str) -> str | None:
        for pattern in patterns:
            match = pattern.match(task)
            if match:
                value = _clean_target(match.group(group))
                if value:
                    return value
        return None

    @staticmethod
    def _matches_any(task: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
        return any(pattern.match(task) for pattern in patterns)


class _HTMLMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self.description: str | None = None
        self.headings: list[str] = []
        self.action_labels: list[str] = []
        self._in_title = False
        self._heading_tag: str | None = None
        self._action_tag: str | None = None
        self._title_parts: list[str] = []
        self._heading_parts: list[str] = []
        self._action_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        attrs_map = {key.lower(): (value or "") for key, value in attrs}
        if lowered == "title":
            self._in_title = True
            return
        if lowered in {"h1", "h2", "h3"} and len(self.headings) < 3:
            self._heading_tag = lowered
            self._heading_parts = []
            return
        if lowered in {"button", "a"} and len(self.action_labels) < 20:
            self._action_tag = lowered
            self._action_parts = []
            aria_label = _normalize_text(attrs_map.get("aria-label", ""))
            if aria_label:
                self._push_action_label(aria_label)
            return
        if lowered == "input" and len(self.action_labels) < 20:
            input_type = attrs_map.get("type", "").lower()
            if input_type in {"button", "submit"}:
                self._push_action_label(attrs_map.get("value", ""))
        if lowered != "meta" or self.description:
            return

        label = (attrs_map.get("name") or attrs_map.get("property") or "").lower()
        if label in {"description", "og:description", "twitter:description"}:
            description = _normalize_text(attrs_map.get("content", ""))
            if description:
                self.description = _clip_text(description, limit=180)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered == "title":
            self._in_title = False
            title = _normalize_text("".join(self._title_parts))
            if title and self.title is None:
                self.title = _clip_text(title, limit=120)
            self._title_parts = []
            return
        if self._heading_tag == lowered:
            heading = _normalize_text("".join(self._heading_parts))
            if heading and heading not in self.headings:
                self.headings.append(_clip_text(heading, limit=120))
            self._heading_tag = None
            self._heading_parts = []
            return
        if self._action_tag == lowered:
            label = _normalize_text("".join(self._action_parts))
            self._push_action_label(label)
            self._action_tag = None
            self._action_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        if self._heading_tag:
            self._heading_parts.append(data)
        if self._action_tag:
            self._action_parts.append(data)

    def _push_action_label(self, label: str) -> None:
        normalized = _normalize_text(label)
        if not normalized:
            return
        clipped = _clip_text(normalized, limit=60)
        if clipped not in self.action_labels:
            self.action_labels.append(clipped)


def _clean_target(text: str) -> str:
    cleaned = text.strip()
    cleaned = cleaned.strip("\"' ")
    return cleaned.rstrip("\u3002\uff01\uff1f!?")


def _looks_like_url(target: str) -> bool:
    cleaned = target.strip()
    if re.match(r"^https?://\S+$", cleaned, re.I):
        return True
    return bool(
        re.match(
            r"^(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/[^\s]*)?$",
            cleaned,
            re.I,
        )
    )


def _ensure_url_scheme(target: str) -> str:
    cleaned = target.strip()
    if re.match(r"^https?://", cleaned, re.I):
        return cleaned
    return f"https://{cleaned}"


def _split_follow_up(text: str) -> tuple[str, str | None]:
    stripped = _clean_target(text)
    patterns = (
        r"^(?P<target>.+?)\s+(?:and then|then|and)\s+(?P<follow>(?:click|open|press|type|fill|sign|log|submit|search|scroll|sort|filter|choose|pick).+)$",
        r"^(?P<target>.+?)(?:\s*(?:\u7136\u540e|\u5e76|\u5e76\u4e14|\u518d))\s*(?P<follow>(?:\u70b9\u51fb|\u6253\u5f00|\u8f93\u5165|\u641c\u7d22|\u6eda\u52a8|\u767b\u5f55|\u63d0\u4ea4|\u7b5b\u9009|\u6392\u5e8f|\u9009\u62e9|\u6309).+)$",
    )
    for pattern in patterns:
        match = re.match(pattern, stripped, re.I)
        if match:
            return _clean_target(match.group("target")), _clip_text(_clean_target(match.group("follow")), limit=140)
    return stripped, None


def _normalize_follow_up_steps(follow_up: str | None) -> tuple[str, ...]:
    if not follow_up:
        return ()

    parts = re.split(
        r"\s+(?:and then|then|and)\s+(?=(?:click|open|press|type|fill|submit|search(?:\s+for)?|scroll(?:\s+to)?|sort\s+by|filter\s+by|choose|pick|select|tap)\b)|"
        r"\s*(?:\u7136\u540e|\u5e76\u4e14|\u518d|\u5e76)\s*(?=(?:\u70b9\u51fb|\u6253\u5f00|\u8f93\u5165|\u641c\u7d22|\u6eda\u52a8|\u63d0\u4ea4|\u7b5b\u9009|\u6392\u5e8f|\u9009\u62e9|\u6309))",
        _clean_target(follow_up),
        flags=re.I,
    )
    normalized: list[str] = []
    for part in parts:
        cleaned = _clip_text(_clean_target(part), limit=140)
        if cleaned:
            normalized.append(cleaned)
    return tuple(normalized)


def _format_follow_up_sequence(steps: tuple[str, ...]) -> str | None:
    if not steps:
        return None
    if len(steps) == 1:
        return steps[0]
    return f"{steps[0]}. Remaining: {' -> '.join(steps[1:])}"


def _follow_up_history_marker(*, current_step: str, step_index: int, total_steps: int) -> str:
    return f"follow-up step {step_index + 1}/{total_steps}: {current_step}"


def _build_follow_up_step_summary(
    *,
    current_step: str,
    step_index: int,
    total_steps: int,
    remaining_steps: tuple[str, ...],
) -> str:
    marker = _follow_up_history_marker(current_step=current_step, step_index=step_index, total_steps=total_steps)
    if not remaining_steps:
        return f"Complete the browser task with {marker}."
    return f"Complete the browser task with {marker}. Remaining: {' -> '.join(remaining_steps)}."


def _count_completed_follow_up_steps(steps: tuple[str, ...], history: list[str]) -> int:
    lowered_history = [item.lower() for item in history[-8:]]
    completed = 0
    for index, step in enumerate(steps):
        marker = _follow_up_history_marker(
            current_step=step,
            step_index=index,
            total_steps=len(steps),
        ).lower()
        if any(marker in item for item in lowered_history):
            completed += 1
            continue
        break
    return completed


def _parse_shopping_command(task: str) -> WebCommand | None:
    stripped = _clean_target(task)
    if not stripped:
        return None
    base_task, base_follow_up = _split_follow_up(stripped)

    english_patterns = (
        re.compile(
            r"^(?:shop|buy|find|browse|look\s+for)\s+(?:for\s+)?(?P<product>.+?)(?:\s+on\s+(?P<site>amazon|ebay|walmart|target|jd|taobao|tmall|temu|aliexpress))?$",
            re.I,
        ),
    )
    chinese_patterns = (
        re.compile(
            r"^(?:(?:在|去|上)?(?P<site>淘宝|京东|天猫|亚马逊|amazon|ebay|walmart|target|jd|taobao|tmall|temu|aliexpress|购物网站|电商网站)?(?:上)?)"
            r"?(?:搜索|找|挑|挑选|看看|购买)(?P<product>.+)$",
            re.I,
        ),
    )

    for pattern in english_patterns + chinese_patterns:
        match = pattern.match(base_task)
        if not match:
            continue
        raw_product = _clean_target(match.group("product"))
        if not raw_product:
            continue

        shopping_query, inline_follow_up = _split_follow_up(raw_product)
        follow_up = base_follow_up or inline_follow_up
        follow_up_steps = _normalize_follow_up_steps(follow_up)
        marketplace = _normalize_marketplace(match.groupdict().get("site"))
        target = _build_shopping_target(shopping_query, marketplace)
        return WebCommand(
            intent="shopping_search",
            target=target,
            follow_up=_format_follow_up_sequence(follow_up_steps) if follow_up_steps else None,
            follow_up_steps=follow_up_steps,
            marketplace=marketplace,
            shopping_query=shopping_query,
        )

    return None


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _clip_text(text: str, *, limit: int) -> str:
    cleaned = _normalize_text(text)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _format_popup_hint(hint: PopupHint) -> str:
    labels = ", ".join(hint.labels) if hint.labels else "no specific labels detected"
    return f"Possible popup: {hint.kind}. Suggested labels: {labels}. Policy: {hint.policy}"


def _build_popup_resolution_plan(command: WebCommand, history: list[str]) -> PlanResult | None:
    page_info = command.page_info
    if page_info is None or not page_info.popup_hints:
        return None
    if _history_mentions_popup_resolution(history):
        return None

    hint = page_info.popup_hints[0]
    preferred_label = _pick_popup_label(hint)
    if preferred_label:
        return PlanResult(
            status_summary=f"Dismiss the {hint.kind} popup by clicking {preferred_label}.",
            done=False,
            actions=[Action.from_dict({"type": "browser_dom_click", "text": preferred_label})],
            current_focus=f"dismiss the {hint.kind} popup",
            reasoning="The popup blocks access to the intended page controls.",
            remaining_steps=list(command.follow_up_steps),
        )

    if hint.kind in {"notification_prompt", "ad_overlay"}:
        return PlanResult(
            status_summary=f"Dismiss the {hint.kind} popup before continuing.",
            done=False,
            actions=[Action.from_dict({"type": "press", "key": "esc"})],
            current_focus=f"dismiss the {hint.kind} popup",
            reasoning="The popup should be cleared before continuing with the requested browser task.",
            remaining_steps=list(command.follow_up_steps),
        )
    return None


def _describe_web_focus(command: WebCommand) -> str:
    if command.intent == "launch":
        return "open the browser"
    if command.intent == "open_url" and command.target:
        return f"open {command.target}"
    if command.intent == "search" and command.target:
        return f"search for {command.target}"
    if command.intent == "shopping_search" and command.shopping_query:
        return f"open shopping results for {command.shopping_query}"
    return command.follow_up or command.target or command.intent


def _pick_popup_label(hint: PopupHint) -> str | None:
    priorities = {
        "cookie_consent": ("reject", "necessary", "preferences", "settings", "decline", "close", "dismiss"),
        "newsletter_modal": ("no thanks", "not now", "skip", "close", "dismiss"),
        "notification_prompt": ("block", "not now", "later", "close", "dismiss"),
        "ad_overlay": ("close", "skip", "continue to site", "dismiss"),
    }
    labels = hint.labels
    if not labels:
        return None
    for keyword in priorities.get(hint.kind, ("close", "dismiss", "skip")):
        for label in labels:
            if keyword in label.lower():
                return label
    return labels[0]


def _history_mentions_popup_resolution(history: list[str]) -> bool:
    joined = "\n".join(history[-5:]).lower()
    markers = ("dismiss the", "cookie popup", "cookie_consent", "newsletter_modal", "notification_prompt", "ad_overlay")
    return any(marker in joined for marker in markers)


def _parse_follow_up_dom_action(follow_up: str) -> Action | None:
    stripped = _normalize_text(follow_up)
    patterns = (
        r"^(?:click|open|select|tap)\s+(?P<label>.+)$",
        r"^(?:sort\s+by|filter\s+by|choose|pick)\s+(?P<label>.+)$",
        r"^(?:\u70b9\u51fb|\u6253\u5f00|\u9009\u62e9)\s*(?P<label>.+)$",
        r"^(?:\u6309|\u7b5b\u9009|\u9009)\s*(?P<label>.+?)(?:\u6392\u5e8f|\u7b5b\u9009)?$",
    )
    for pattern in patterns:
        match = re.match(pattern, stripped, re.I)
        if not match:
            continue
        label = _clean_target(match.group("label"))
        if not label:
            continue
        return Action.from_dict({"type": "browser_dom_click", "text": label})
    return None


def _refine_dom_follow_up_action(action: Action, page_info: WebPageInfo | None) -> Action:
    if action.type != "browser_dom_click" or action.selector or page_info is None:
        return action

    target_label = (action.text or "").strip()
    if not target_label or not page_info.action_labels:
        return action

    best_label = _best_matching_action_label(target_label, page_info.action_labels)
    if best_label is None:
        return action
    return Action.from_dict({"type": "browser_dom_click", "text": best_label})


def _detect_popup_hints(raw_html: str, action_labels: tuple[str, ...]) -> tuple[PopupHint, ...]:
    lowered = raw_html.lower()
    lowered_labels = tuple(label.lower() for label in action_labels)
    hints: list[PopupHint] = []

    rules = (
        (
            "cookie_consent",
            ("cookie", "consent", "gdpr", "privacy preferences", "cookiebot", "onetrust"),
            ("reject", "decline", "necessary", "preferences", "settings", "accept"),
            "Prefer reject, necessary-only, manage preferences, or close over accept-all unless consent is required.",
        ),
        (
            "newsletter_modal",
            ("newsletter", "subscribe", "sign up", "signup", "join our mailing", "email updates"),
            ("close", "no thanks", "not now", "skip", "continue"),
            "Close, skip, or choose no thanks unless the task explicitly asks to subscribe.",
        ),
        (
            "notification_prompt",
            ("notification", "allow notifications", "enable notifications", "turn on notifications"),
            ("block", "not now", "later", "no thanks", "close"),
            "Dismiss or deny notification prompts unless notifications are required for the task.",
        ),
        (
            "ad_overlay",
            ("advertisement", "sponsored", "promo", "interstitial", "skip ad", "continue to site"),
            ("close", "skip", "continue to site", "dismiss"),
            "Close the ad, interstitial, or promo overlay before continuing.",
        ),
    )

    for kind, markers, label_keywords, policy in rules:
        marker_match = any(marker in lowered for marker in markers)
        if kind == "cookie_consent":
            marker_match = marker_match or _looks_like_cookie_labels(lowered_labels)
        if not marker_match:
            continue
        labels = _filter_labels(action_labels, label_keywords)
        hints.append(PopupHint(kind=kind, policy=policy, labels=labels))

    return tuple(hints)


def _best_matching_action_label(target_label: str, action_labels: tuple[str, ...]) -> str | None:
    normalized_target = _normalize_compare_text(target_label)
    if not normalized_target:
        return None

    best_label: str | None = None
    best_score = -1
    target_tokens = set(normalized_target.split())
    squashed_target = normalized_target.replace(" ", "")

    for label in action_labels:
        normalized_label = _normalize_compare_text(label)
        if not normalized_label:
            continue
        squashed_label = normalized_label.replace(" ", "")
        score = 0
        if normalized_target == normalized_label:
            score += 100
        if squashed_target == squashed_label:
            score += 95
        if squashed_target in squashed_label or squashed_label in squashed_target:
            score += 60

        shared_tokens = target_tokens & set(normalized_label.split())
        score += len(shared_tokens) * 10

        if score > best_score:
            best_label = label
            best_score = score

    if best_score <= 0:
        return None
    return best_label


def _filter_labels(labels: tuple[str, ...], keywords: tuple[str, ...]) -> tuple[str, ...]:
    matches: list[str] = []
    for label in labels:
        lowered = label.lower()
        if any(keyword in lowered for keyword in keywords):
            matches.append(label)
    return tuple(matches[:4])


def _looks_like_cookie_labels(labels: tuple[str, ...]) -> bool:
    has_accept = any("accept" in label or "agree" in label for label in labels)
    has_reject = any(
        keyword in label
        for label in labels
        for keyword in ("reject", "decline", "necessary", "preferences", "settings")
    )
    return has_accept and has_reject


def _normalize_compare_text(text: str) -> str:
    normalized = _normalize_text(text).lower()
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _follow_up_action_completes_task(action: Action) -> bool:
    return action.type == "browser_dom_click"


_MARKETPLACE_ALIASES = {
    "amazon": "amazon",
    "亚马逊": "amazon",
    "ebay": "ebay",
    "walmart": "walmart",
    "target": "target",
    "jd": "jd",
    "京东": "jd",
    "taobao": "taobao",
    "淘宝": "taobao",
    "tmall": "tmall",
    "天猫": "tmall",
    "temu": "temu",
    "aliexpress": "aliexpress",
}


_MARKETPLACE_SEARCH_URLS = {
    "amazon": "https://www.amazon.com/s?k={query}",
    "ebay": "https://www.ebay.com/sch/i.html?_nkw={query}",
    "walmart": "https://www.walmart.com/search?q={query}",
    "target": "https://www.target.com/s?searchTerm={query}",
    "jd": "https://search.jd.com/Search?keyword={query}",
    "taobao": "https://s.taobao.com/search?q={query}",
    "tmall": "https://list.tmall.com/search_product.htm?q={query}",
    "temu": "https://www.temu.com/search_result.html?search_key={query}",
    "aliexpress": "https://www.aliexpress.com/wholesale?SearchText={query}",
}


def _normalize_marketplace(site: str | None) -> str | None:
    raw = _normalize_text(site or "")
    if not raw:
        return None
    return _MARKETPLACE_ALIASES.get(raw.lower()) or _MARKETPLACE_ALIASES.get(raw)


def _build_shopping_target(shopping_query: str, marketplace: str | None) -> str:
    query = _normalize_text(shopping_query)
    if marketplace and marketplace in _MARKETPLACE_SEARCH_URLS:
        return _MARKETPLACE_SEARCH_URLS[marketplace].format(query=quote_plus(query))
    if any(token in query.lower() for token in ("pants", "trousers", "jeans", "men", "male")):
        return f"{query} shopping deals"
    if any(token in query for token in ("\u88e4", "\u7537", "\u6027\u4ef7\u6bd4")):
        return f"{query} 购物"
    return f"{query} shopping"


def _import_requests():
    try:
        import requests
    except ModuleNotFoundError:
        return None
    return requests
