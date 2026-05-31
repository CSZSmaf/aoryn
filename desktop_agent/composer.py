"""Document synthesis ("thinking") engine.

This module turns accumulated research notes plus the user's goal into a
structured, long-form document. It is the "brain" step between gathering
information (eyes) and writing it into an app (hands): it reuses the configured
OpenAI-compatible / LM Studio endpoint to reason over the notes, and always
falls back to a deterministic outline so dry-run, offline, and benchmark paths
still produce a coherent artifact.

The output is intentionally a simple Markdown-ish shape (a title line followed by
``## heading`` sections) rather than strict JSON, because small local models are
far more reliable at prose than at schema-constrained output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from desktop_agent.config import AgentConfig


_COMPOSER_SYSTEM_PROMPT = (
    "You are a writing assistant inside a desktop agent. You receive a goal and "
    "research notes, and you produce a clear, well-structured document the user "
    "can read directly. Write in the same language as the goal. Begin with a "
    "single title line, then organise the body with '## ' section headings and "
    "concise paragraphs or '- ' bullet points. Use only the information in the "
    "notes plus general knowledge; never invent fake citations, prices, or "
    "personal data. Do not output JSON, code fences, or commentary about the "
    "task itself."
)


@dataclass(slots=True)
class DocumentSection:
    heading: str
    body: str

    def to_dict(self) -> dict[str, Any]:
        return {"heading": self.heading, "body": self.body}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DocumentSection":
        return cls(
            heading=str(payload.get("heading", "")).strip(),
            body=str(payload.get("body", "")).strip(),
        )


@dataclass(slots=True)
class DocumentArtifact:
    """A composed, structured document ready to be authored into an app."""

    title: str
    sections: list[DocumentSection] = field(default_factory=list)
    goal: str | None = None
    source: str = "fallback"  # "model" | "fallback"

    def to_plain_text(self) -> str:
        lines: list[str] = []
        if self.title:
            lines.append(self.title.strip())
            lines.append("")
        for section in self.sections:
            heading = section.heading.strip()
            body = section.body.strip()
            if heading:
                lines.append(heading)
            if body:
                lines.append(body)
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    def to_markdown(self) -> str:
        lines: list[str] = []
        if self.title:
            lines.append(f"# {self.title.strip()}")
            lines.append("")
        for section in self.sections:
            if section.heading.strip():
                lines.append(f"## {section.heading.strip()}")
            if section.body.strip():
                lines.append(section.body.strip())
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    @property
    def word_count(self) -> int:
        return len(self.to_plain_text())

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "sections": [item.to_dict() for item in self.sections],
            "goal": self.goal,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DocumentArtifact":
        return cls(
            title=str(payload.get("title", "")).strip(),
            sections=[
                DocumentSection.from_dict(item)
                for item in payload.get("sections", []) or []
                if isinstance(item, dict)
            ],
            goal=_optional_str(payload.get("goal")),
            source=str(payload.get("source", "fallback")).strip() or "fallback",
        )


class DocumentComposer:
    """Synthesize research notes + a goal into a structured document."""

    def __init__(self, config: AgentConfig | None = None) -> None:
        self.config = config or AgentConfig()

    def compose(
        self,
        *,
        goal: str,
        notes: list[str] | None = None,
        history: list[str] | None = None,
        doc_type: str | None = None,
    ) -> DocumentArtifact:
        cleaned_goal = " ".join(str(goal or "").split()).strip() or "Untitled document"
        cleaned_notes = _clean_notes(notes)
        artifact: DocumentArtifact | None = None
        if self._model_enabled():
            artifact = self._compose_with_model(cleaned_goal, cleaned_notes, doc_type)
        if artifact is None or not artifact.sections:
            artifact = self._compose_fallback(cleaned_goal, cleaned_notes, doc_type)
        artifact.goal = cleaned_goal
        return artifact

    # -- model path -----------------------------------------------------------

    def _model_enabled(self) -> bool:
        return bool(getattr(self.config, "composition_enabled", True)) and bool(
            str(self.config.model_base_url or "").strip()
        )

    def _compose_with_model(
        self,
        goal: str,
        notes: list[str],
        doc_type: str | None,
    ) -> DocumentArtifact | None:
        try:
            from desktop_agent.planner import (
                _build_request_headers,
                _extract_message_content,
                _import_requests,
                _normalize_api_base_url,
                _resolve_text_model_name,
            )

            requests = _import_requests()
            if requests is None:
                return None
            api_base = _normalize_api_base_url(self.config.model_base_url)
            model_name = _resolve_text_model_name(self.config, requests, api_base)
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": _COMPOSER_SYSTEM_PROMPT},
                    {"role": "user", "content": _build_compose_prompt(goal, notes, doc_type)},
                ],
                "temperature": 0.4,
                "stream": False,
            }
            response = requests.post(
                f"{api_base}/chat/completions",
                headers=_build_request_headers(self.config.model_api_key),
                json=payload,
                timeout=self.config.model_request_timeout,
            )
            if response.status_code >= 400:
                return None
            content = _extract_message_content(response.json())
        except Exception:
            return None

        artifact = parse_document_text(content, goal=goal)
        if artifact is None or not artifact.sections:
            return None
        artifact.source = "model"
        return artifact

    # -- deterministic fallback ----------------------------------------------

    def _compose_fallback(
        self,
        goal: str,
        notes: list[str],
        doc_type: str | None,
    ) -> DocumentArtifact:
        zh = _contains_cjk(goal) or any(_contains_cjk(note) for note in notes)
        labels = _FALLBACK_LABELS_ZH if zh else _FALLBACK_LABELS_EN
        title = _derive_title(goal, zh)
        sections: list[DocumentSection] = []

        overview = (
            f"本文档围绕“{goal}”整理而成，"
            f"综合了已收集到的 {len(notes)} 条参考信息后给出结构化结果。"
            if zh
            else (
                f'This document addresses "{goal}", '
                f"synthesizing {len(notes)} gathered note(s) into a structured result."
            )
        )
        sections.append(DocumentSection(heading=f"## {labels['overview']}", body=overview))

        key_points = _notes_to_bullets(notes)
        if key_points:
            sections.append(DocumentSection(heading=f"## {labels['key_points']}", body=key_points))
        else:
            empty_body = (
                "暂未收集到外部资料，以下内容基于目标本身整理，建议补充联网检索后再完善。"
                if zh
                else (
                    "No external material was gathered yet; the points below are derived from the "
                    "goal itself. Consider adding web research to enrich them."
                )
            )
            sections.append(DocumentSection(heading=f"## {labels['key_points']}", body=empty_body))

        sources = _notes_to_sources(notes)
        if sources:
            sections.append(DocumentSection(heading=f"## {labels['sources']}", body=sources))

        next_steps = (
            "- 核对关键信息的时效性与准确性\n- 根据实际需求补充细节并调整结构"
            if zh
            else "- Verify the freshness and accuracy of key facts\n- Add details and adjust structure to fit your needs"
        )
        sections.append(DocumentSection(heading=f"## {labels['next_steps']}", body=next_steps))

        return DocumentArtifact(title=title, sections=sections, goal=goal, source="fallback")


# -- module-level parsing/helpers --------------------------------------------


def parse_document_text(content: str | None, *, goal: str = "") -> DocumentArtifact | None:
    """Parse a Markdown-ish model response into a structured artifact."""

    text = str(content or "").strip()
    if not text:
        return None
    text = _strip_code_fences(text)
    lines = text.splitlines()

    title = ""
    sections: list[DocumentSection] = []
    current_heading: str | None = None
    current_body: list[str] = []
    preamble: list[str] = []

    def flush() -> None:
        nonlocal current_heading, current_body
        if current_heading is not None:
            sections.append(
                DocumentSection(
                    heading=current_heading.strip(),
                    body="\n".join(current_body).strip(),
                )
            )
        current_heading = None
        current_body = []

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()
            if level == 1 and not title and current_heading is None and not sections:
                title = heading_text
                continue
            flush()
            current_heading = f"## {heading_text}"
            continue
        if current_heading is None:
            if stripped:
                preamble.append(stripped)
        else:
            current_body.append(line)
    flush()

    if not title:
        if preamble:
            title = preamble[0]
            preamble = preamble[1:]
        else:
            title = _derive_title(goal, _contains_cjk(goal))

    if preamble:
        intro_heading = "## 概述" if _contains_cjk(goal or title) else "## Overview"
        sections.insert(0, DocumentSection(heading=intro_heading, body="\n".join(preamble).strip()))

    if not sections:
        body = "\n".join(line for line in lines if line.strip() and not line.strip().startswith("#")).strip()
        if not body:
            return None
        content_heading = "## 正文" if _contains_cjk(goal or title) else "## Content"
        sections = [DocumentSection(heading=content_heading, body=body)]

    return DocumentArtifact(title=title.strip(), sections=sections, goal=goal or None, source="model")


_FALLBACK_LABELS_ZH = {
    "overview": "概述",
    "key_points": "要点整理",
    "sources": "参考来源",
    "next_steps": "后续建议",
}
_FALLBACK_LABELS_EN = {
    "overview": "Overview",
    "key_points": "Key Points",
    "sources": "Sources",
    "next_steps": "Next Steps",
}


def _build_compose_prompt(goal: str, notes: list[str], doc_type: str | None) -> str:
    lines = [f"Goal: {goal}"]
    if doc_type:
        lines.append(f"Document type: {doc_type}")
    if notes:
        lines.append("")
        lines.append("Research notes:")
        for index, note in enumerate(notes, start=1):
            lines.append(f"{index}. {note}")
    else:
        lines.append("")
        lines.append("No research notes were gathered; rely on general knowledge for the goal.")
    lines.append("")
    lines.append(
        "Write the document now. Start with the title line, then use '## ' section "
        "headings. Keep it focused and practical."
    )
    return "\n".join(lines)


def _clean_notes(notes: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for note in notes or []:
        text = " ".join(str(note or "").split()).strip()
        if not text:
            continue
        trimmed = text[:600]
        key = trimmed.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(trimmed)
    return cleaned[:16]


def _notes_to_bullets(notes: list[str]) -> str:
    bullets: list[str] = []
    seen: set[str] = set()
    for note in notes:
        cleaned = re.sub(r"^\[[a-z]+\]\s*", "", note).strip()
        # Drop URL-only / search-engine breadcrumbs and inline URLs — they belong
        # in Sources, not in the key-points body.
        if not cleaned or re.fullmatch(r"https?://\S+", cleaned):
            continue
        cleaned = re.sub(r"https?://\S+", "", cleaned).strip(" -–·•|")
        if len(cleaned) < 4:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        bullets.append(f"- {cleaned}")
        if len(bullets) >= 10:
            break
    return "\n".join(bullets)


def _notes_to_sources(notes: list[str]) -> str:
    sources: list[str] = []
    seen: set[str] = set()
    for note in notes:
        for match in re.findall(r"https?://[^\s]+", note):
            url = match.rstrip(".,;)")
            if url not in seen:
                seen.add(url)
                sources.append(f"- {url}")
    return "\n".join(sources[:8])


def _derive_title(goal: str, zh: bool) -> str:
    cleaned = " ".join(str(goal or "").split()).strip()
    if not cleaned:
        return "未命名文档" if zh else "Untitled Document"
    cleaned = re.sub(
        r"^(?:请|帮我|帮忙|然后|并且|并|再|把|将|please|then|and)\s*",
        "",
        cleaned,
        flags=re.I,
    ).strip()
    # Drop a trailing "write into Word"-style authoring clause for a cleaner title.
    cleaned = re.split(
        r"\s*(?:然后|并且|并|再|接着|之后|最后|，|,)\s*(?:整理|写入|写到|写进|记录|保存|生成|存到|放到|"
        r"and then|then|and)\b.*$",
        cleaned,
        maxsplit=1,
        flags=re.I,
    )[0].strip()
    return (cleaned or goal)[:80]


def _strip_code_fences(text: str) -> str:
    fence = re.match(r"^```[a-zA-Z]*\s*\n(.*)\n```$", text.strip(), re.S)
    if fence:
        return fence.group(1).strip()
    return text


def _contains_cjk(text: str | None) -> bool:
    return bool(re.search(r"[一-鿿]", str(text or "")))


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
