from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class BrowserSnapshot:
    url: str | None = None
    title: str | None = None
    text: str | None = None


@dataclass(slots=True)
class HumanVerificationSignal:
    kind: str
    summary: str
    detail: str
    url: str | None = None
    title: str | None = None
    matched: str | None = None
    requires_human: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "summary": self.summary,
            "detail": self.detail,
            "url": self.url,
            "title": self.title,
            "matched": self.matched,
            "requires_human": self.requires_human,
        }


@dataclass(frozen=True, slots=True)
class _Rule:
    kind: str
    detail: str
    url_markers: tuple[str, ...] = ()
    text_markers: tuple[str, ...] = ()


_RULES: tuple[_Rule, ...] = (
    _Rule(
        kind="google_unusual_traffic",
        detail=(
            "Google presented an unusual-traffic human verification page. "
            "Pause automation and ask the user to complete it manually in the browser."
        ),
        url_markers=("google.com/sorry/index", "sorry/index"),
        text_markers=(
            "unusual traffic",
            "not a robot",
            "our systems have detected",
            "不是自动程序发出的",
            "异常流量",
            "进行人机身份验证",
        ),
    ),
    _Rule(
        kind="recaptcha",
        detail=(
            "A reCAPTCHA challenge is on screen. Pause automation and wait for "
            "the user to complete the verification manually."
        ),
        url_markers=("recaptcha",),
        text_markers=("recaptcha", "i'm not a robot", "i am not a robot", "进行人机身份验证"),
    ),
    _Rule(
        kind="hcaptcha",
        detail=(
            "An hCaptcha challenge is on screen. Pause automation and wait for "
            "the user to complete the verification manually."
        ),
        url_markers=("hcaptcha",),
        text_markers=("hcaptcha", "verify you are human", "请完成安全验证", "真人验证"),
    ),
    _Rule(
        kind="cloudflare_verification",
        detail=(
            "Cloudflare browser verification was detected. Pause automation and "
            "wait for the user to finish the check manually."
        ),
        url_markers=("cdn-cgi/challenge-platform", "cf-chl", "cf_clearance"),
        text_markers=("cloudflare", "checking your browser", "verify you are human", "attention required"),
    ),
    _Rule(
        kind="generic_human_verification",
        detail=(
            "A human-verification or CAPTCHA page was detected. Pause automation "
            "and ask the user to complete the check manually before resuming."
        ),
        url_markers=("captcha", "/challenge", "/verify"),
        text_markers=(
            "captcha",
            "human verification",
            "verify you are human",
            "security check",
            "安全验证",
            "人机验证",
            "人机身份验证",
        ),
    ),
)


def detect_human_verification(
    snapshot: BrowserSnapshot | dict[str, Any] | None,
) -> HumanVerificationSignal | None:
    resolved = _coerce_snapshot(snapshot)
    if resolved is None:
        return None

    url = (resolved.url or "").strip()
    title = (resolved.title or "").strip()
    text = (resolved.text or "").strip()
    haystacks = tuple(part.lower() for part in (url, title, text) if part)

    if not haystacks:
        return None

    for rule in _RULES:
        matched = _match_rule(rule, url=url, haystacks=haystacks)
        if matched is None:
            continue
        return HumanVerificationSignal(
            kind=rule.kind,
            summary="Human verification detected. Pause automation and wait for manual completion.",
            detail=rule.detail,
            url=url or None,
            title=title or None,
            matched=matched,
        )
    return None


def _coerce_snapshot(snapshot: BrowserSnapshot | dict[str, Any] | None) -> BrowserSnapshot | None:
    if snapshot is None:
        return None
    if isinstance(snapshot, BrowserSnapshot):
        return snapshot
    if isinstance(snapshot, dict):
        return BrowserSnapshot(
            url=_optional_text(snapshot.get("url")),
            title=_optional_text(snapshot.get("title")),
            text=_optional_text(snapshot.get("text")),
        )
    return None


def _match_rule(rule: _Rule, *, url: str, haystacks: tuple[str, ...]) -> str | None:
    lowered_url = url.lower()
    for marker in rule.url_markers:
        if marker and marker.lower() in lowered_url:
            return marker
    for marker in rule.text_markers:
        lowered_marker = marker.lower()
        for haystack in haystacks:
            if lowered_marker in haystack:
                return marker
    return None


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
