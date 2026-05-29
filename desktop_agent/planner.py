from __future__ import annotations

import base64
import json
import re
import socket
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from desktop_agent.actions import ActionValidationError, PlanResult
from desktop_agent.config import AgentConfig
from desktop_agent.prompts import SYSTEM_PROMPT
from desktop_agent.web_agent import WebAgent, WebCommand
from desktop_agent.workflow import Subgoal, TaskGraph, WorldModel
from desktop_agent.windows_env import DesktopEnvironment


@dataclass(slots=True)
class TaskIntent:
    """Semantic view of the user request before low-level action planning."""

    task_type: str
    primary_goal: str
    domain: str | None = None
    entities: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    risk_level: str = "low"
    ambiguity: str = "low"
    requires_clarification: bool = False
    clarification_prompt: str | None = None
    preferred_capabilities: list[str] = field(default_factory=list)
    success_hints: list[str] = field(default_factory=list)
    planning_strategy: str = "rule_first"
    confidence: float = 0.65
    source: str = "heuristic"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TaskIntent":
        return cls(
            task_type=str(payload.get("task_type", "general")).strip() or "general",
            primary_goal=str(payload.get("primary_goal", "")).strip(),
            domain=_optional_str(payload.get("domain")),
            entities=[str(item).strip() for item in payload.get("entities", []) or [] if str(item).strip()],
            constraints=[str(item).strip() for item in payload.get("constraints", []) or [] if str(item).strip()],
            risk_level=_normalize_intent_risk(payload.get("risk_level")),
            ambiguity=_normalize_ambiguity(payload.get("ambiguity")),
            requires_clarification=bool(payload.get("requires_clarification", False)),
            clarification_prompt=_optional_str(payload.get("clarification_prompt")),
            preferred_capabilities=[
                str(item).strip()
                for item in payload.get("preferred_capabilities", []) or []
                if str(item).strip()
            ],
            success_hints=[str(item).strip() for item in payload.get("success_hints", []) or [] if str(item).strip()],
            planning_strategy=str(payload.get("planning_strategy", "rule_first")).strip() or "rule_first",
            confidence=float(payload.get("confidence", 0.65) or 0.65),
            source=str(payload.get("source", "heuristic")).strip() or "heuristic",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type,
            "primary_goal": self.primary_goal,
            "domain": self.domain,
            "entities": list(self.entities),
            "constraints": list(self.constraints),
            "risk_level": self.risk_level,
            "ambiguity": self.ambiguity,
            "requires_clarification": self.requires_clarification,
            "clarification_prompt": self.clarification_prompt,
            "preferred_capabilities": list(self.preferred_capabilities),
            "success_hints": list(self.success_hints),
            "planning_strategy": self.planning_strategy,
            "confidence": self.confidence,
            "source": self.source,
        }


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_intent_risk(value: Any) -> str:
    normalized = str(value or "low").strip().lower()
    return normalized if normalized in {"low", "medium", "high", "critical"} else "low"


def _normalize_ambiguity(value: Any) -> str:
    normalized = str(value or "low").strip().lower()
    return normalized if normalized in {"low", "medium", "high"} else "low"


class PlannerError(RuntimeError):
    """Raised when planner cannot generate a valid plan."""


class StructuredOutputUnsupportedError(RuntimeError):
    """Raised when the upstream model rejects structured output settings."""


class BasePlanner(ABC):
    @abstractmethod
    def plan(
        self,
        task: str,
        screenshot_path: Path | None,
        history: list[str],
        environment: DesktopEnvironment | None = None,
    ) -> PlanResult:
        raise NotImplementedError


class RulePlanner(BasePlanner):
    """Deterministic planner for common demo tasks."""

    _NOTEPAD_OPEN_PATTERN = re.compile(
        r"^(?:\u6253\u5f00|open)\s*(?:\u4e00\u4e2a\s*|(?:an?|the)\s+)?(?:\u8bb0\u4e8b\u672c|notepad)\s*$",
        re.I,
    )
    _NOTEPAD_PATTERN = re.compile(
        r"^(?:\u6253\u5f00|open)\s*(?:\u4e00\u4e2a\s*|(?:an?|the)\s+)?(?:\u8bb0\u4e8b\u672c|notepad)\s*"
        r"(?:(?:\u5e76|\u7136\u540e)|and(?:\s+then)?)?\s*(?:\u8f93\u5165|type)\s*(?P<text>.+)$",
        re.I,
    )
    _CALCULATOR_PATTERN = re.compile(
        r"^(?:\u6253\u5f00|open)\s*(?:\u4e00\u4e2a\s*|(?:an?|the)\s+)?(?:\u8ba1\u7b97\u5668|calculator|calc)\s*$",
        re.I,
    )
    _CALCULATOR_EXPRESSION_PATTERNS = (
        re.compile(
            r"^(?:\u6253\u5f00|open)\s*(?:\u4e00\u4e2a\s*|(?:an?|the)\s+)?(?:\u8ba1\u7b97\u5668|calculator|calc)\s*"
            r"(?:(?:\u5e76|\u7136\u540e)|and(?:\s+then)?)?\s*(?:\u8ba1\u7b97|calculate|compute|evaluate)\s*(?P<expr>.+)$",
            re.I,
        ),
        re.compile(
            r"^(?:\u7528|\u4f7f\u7528|with|use)\s*(?:\u8ba1\u7b97\u5668|calculator|calc)\s*"
            r"(?:\u8ba1\u7b97|calculate|compute|evaluate)\s*(?P<expr>.+)$",
            re.I,
        ),
        re.compile(
            r"^(?:calculate|compute|evaluate)\s*(?P<expr>.+?)\s*(?:with|using)\s*(?:calculator|calc)\s*$",
            re.I,
        ),
    )
    _STANDALONE_CALCULATOR_EXPRESSION_PATTERN = re.compile(
        r"^(?:calculate|compute|evaluate)\s+(?P<expr>.+)$",
        re.I,
    )
    _EXPLORER_PATTERN = re.compile(
        r"^(?:\u6253\u5f00|open)\s*(?:\u4e00\u4e2a\s*|(?:an?|the)\s+)?"
        r"(?:\u8d44\u6e90\u7ba1\u7406\u5668|\u6587\u4ef6\u8d44\u6e90\u7ba1\u7406\u5668|explorer)\s*$",
        re.I,
    )
    _BROWSER_APP_PATTERN = re.compile(
        r"^(?:\u6253\u5f00|open)\s*(?:\u4e00\u4e2a\s*|(?:an?|the)\s+)?(?:\u6d4f\u89c8\u5668|browser|edge|chrome|firefox)\s*$",
        re.I,
    )
    _GENERIC_OPEN_APP_PATTERN = re.compile(
        r"^(?:\u6253\u5f00|open)\s*(?:\u4e00\u4e2a\s*|(?:an?|the)\s+)?(?P<app>[\w\u4e00-\u9fff][\w\u4e00-\u9fff ._-]{0,78})\s*$",
        re.I,
    )
    _CLOSE_APP_PATTERN = re.compile(
        r"^(?:\u5173\u95ed|close)\s*(?:(?:\u5f53\u524d|current)\s*)?(?P<target>(?:\u8ba1\u7b97\u5668|\u8bb0\u4e8b\u672c|\u8d44\u6e90\u7ba1\u7406\u5668|\u6d4f\u89c8\u5668|calculator|calc|notepad|explorer|browser))?(?:\s*(?:\u7a97\u53e3|window))?\s*$",
        re.I,
    )
    _GENERIC_CLOSE_APP_PATTERN = re.compile(
        r"^(?:\u5173\u95ed|close)\s*(?P<target>[\w\u4e00-\u9fff][\w\u4e00-\u9fff ._-]{0,78})(?:\s*(?:\u7a97\u53e3|window))?\s*$",
        re.I,
    )
    _WAIT_PATTERN = re.compile(
        r"^(?:\u7b49\u5f85|\u7b49|wait)\s*(?P<seconds>[0-9]+(?:\.[0-9]+)?)\s*(?:\u79d2|seconds?|s)?\s*$",
        re.I,
    )
    _TYPE_PATTERN = re.compile(r"^(?:\u8f93\u5165|\u952e\u5165|type)\s*(?P<text>.+)$", re.I)
    _PRESS_PATTERN = re.compile(r"^(?:press|hit|tap)\s+(?P<key>[\w +-]{1,40})\s*$", re.I)
    _SAVE_AS_PATTERN = re.compile(
        r"^(?:save(?:\s+(?:as|to))?|\u4fdd\u5b58(?:\u4e3a|\u5230)?)\s+(?P<path>.+)$",
        re.I,
    )
    _OPEN_URL_PATTERN = re.compile(r"^(?:open|launch)\s+(?P<target>https?://\S+|www\.\S+|\S+\.\S+)\s*$", re.I)
    _BROWSER_CLICK_PATTERN = re.compile(r"^(?:click|select|choose|tap)\s+(?P<target>.+)$", re.I)
    _GENERIC_APP_SAVE_AS_PATTERN = re.compile(
        r"^(?:\u6253\u5f00|open|launch)\s*(?:\u4e00\u4e2a\s*|(?:an?|the)\s+)?"
        r"(?P<app>[\w\u4e00-\u9fff][\w\u4e00-\u9fff ._-]{0,78})\s*"
        r"(?:(?:\u5e76|\u7136\u540e|\u518d)|and(?:\s+then)?|then)\s*"
        r"(?:save(?:\s+(?:as|to))?|\u4fdd\u5b58(?:\u4e3a|\u5230)?)\s*(?P<path>.+)$",
        re.I,
    )
    _GENERIC_APP_TYPE_PATTERN = re.compile(
        r"^(?:\u6253\u5f00|open|launch)\s*(?:\u4e00\u4e2a\s*|(?:an?|the)\s+)?"
        r"(?P<app>[\w\u4e00-\u9fff][\w\u4e00-\u9fff ._-]{0,78})\s*"
        r"(?:(?:\u5e76|\u7136\u540e|\u518d)|and(?:\s+then)?|then)\s*"
        r"(?:\u8f93\u5165|\u952e\u5165|\u5199\u5165|type|enter|write)\s*(?P<text>.+)$",
        re.I,
    )
    _GENERIC_APP_SEARCH_PATTERN = re.compile(
        r"^(?:"
        r"(?:\u6253\u5f00|open|launch)\s*(?:\u4e00\u4e2a\s*|(?:an?|the)\s+)?"
        r"(?P<open_app>[\w\u4e00-\u9fff][\w\u4e00-\u9fff ._-]{0,78})\s*"
        r"(?:(?:\u5e76|\u7136\u540e|\u518d)|and(?:\s+then)?|then)\s*"
        r"(?:\u641c\u7d22|\u67e5\u627e|search(?:\s+for)?|find)"
        r"|(?:\u5728|with|use)\s*(?P<with_app>[\w\u4e00-\u9fff][\w\u4e00-\u9fff ._-]{0,78})\s*(?:\u91cc|\u4e2d|in)?\s*"
        r"(?:\u641c\u7d22|\u67e5\u627e|search(?:\s+for)?|find)"
        r")\s*(?P<query>.+)$",
        re.I,
    )
    _GENERIC_APP_CLICK_PATTERN = re.compile(
        r"^(?:\u6253\u5f00|open|launch)\s*(?:\u4e00\u4e2a\s*|(?:an?|the)\s+)?"
        r"(?P<app>[\w\u4e00-\u9fff][\w\u4e00-\u9fff ._-]{0,78})\s*"
        r"(?:(?:\u5e76|\u7136\u540e|\u518d)|and(?:\s+then)?|then)\s*"
        r"(?:\u70b9\u51fb|\u6253\u5f00|\u9009\u62e9|click|open|select|choose|tap)\s*(?P<target>.+)$",
        re.I,
    )
    _GENERIC_APP_FILL_PATTERN = re.compile(
        r"^(?:\u6253\u5f00|open|launch)\s*(?:\u4e00\u4e2a\s*|(?:an?|the)\s+)?"
        r"(?P<app>[\w\u4e00-\u9fff][\w\u4e00-\u9fff ._-]{0,78})\s*"
        r"(?:(?:\u5e76|\u7136\u540e|\u518d)|and(?:\s+then)?|then)\s*"
        r"(?:\u5728|fill|set|enter)\s*(?P<field>[\w\u4e00-\u9fff ._-]{1,80})\s*"
        r"(?:\u586b\u5199|\u8f93\u5165|\u8bbe\u4e3a|with|to|as|=|:)\s*(?P<value>.+)$",
        re.I,
    )
    _GENERIC_APP_PRESS_PATTERN = re.compile(
        r"^(?:\u6253\u5f00|open|launch)\s*(?:\u4e00\u4e2a\s*|(?:an?|the)\s+)?"
        r"(?P<app>[\w\u4e00-\u9fff][\w\u4e00-\u9fff ._-]{0,78})\s*"
        r"(?:(?:\u5e76|\u7136\u540e|\u518d)|and(?:\s+then)?|then)\s*"
        r"(?:\u6309|press)\s*(?P<key>[\w\u4e00-\u9fff +-]{1,40})\s*$",
        re.I,
    )

    def __init__(self) -> None:
        self.web_agent = WebAgent()

    def plan(
        self,
        task: str,
        screenshot_path: Path | None,
        history: list[str],
        environment: DesktopEnvironment | None = None,
    ) -> PlanResult:
        stripped = task.strip()

        if self._NOTEPAD_OPEN_PATTERN.match(stripped):
            return _build_result(
                "Rule task: open Notepad.",
                [
                    {"type": "open_app_if_needed", "app": "notepad"},
                    {"type": "wait", "seconds": 0.8},
                ],
            )

        if match := self._NOTEPAD_PATTERN.match(stripped):
            return _build_result(
                "Rule task: open Notepad and type text.",
                [
                    {"type": "open_app_if_needed", "app": "notepad"},
                    {"type": "wait", "seconds": 1.0},
                    {"type": "type", "text": _clean_tail_text(match.group("text"))},
                ],
            )

        if self._CALCULATOR_PATTERN.match(stripped):
            return _build_result(
                "Rule task: open Calculator.",
                [
                    {"type": "open_app_if_needed", "app": "calculator"},
                    {"type": "wait", "seconds": 0.8},
                ],
            )

        if calculator_plan := self._build_calculator_expression_result(stripped):
            return calculator_plan

        if generic_app_task_plan := self._build_generic_app_task_result(stripped):
            return generic_app_task_plan

        if save_plan := self._build_save_as_result(stripped):
            return save_plan

        if self._EXPLORER_PATTERN.match(stripped):
            return _build_result(
                "Rule task: open Explorer.",
                [
                    {"type": "open_app_if_needed", "app": "explorer"},
                    {"type": "wait", "seconds": 0.8},
                ],
            )

        if self._BROWSER_APP_PATTERN.match(stripped):
            return _build_result(
                "Rule task: open a local browser window.",
                [
                    {"type": "open_app_if_needed", "app": "browser"},
                    {"type": "wait", "seconds": 0.8},
                ],
            )

        if open_url_plan := self._build_open_url_result(stripped):
            return open_url_plan

        if generic_open_plan := self._build_generic_open_app_result(stripped):
            return generic_open_plan

        if close_plan := self._build_close_result(stripped):
            return close_plan

        if generic_close_plan := self._build_generic_close_result(stripped):
            return generic_close_plan

        if web_plan := self.web_agent.try_plan(stripped):
            return web_plan

        if browser_click_plan := self._build_browser_click_result(stripped):
            return browser_click_plan

        if match := self._WAIT_PATTERN.match(stripped):
            return _build_result(
                "Rule task: wait.",
                [{"type": "wait", "seconds": float(match.group("seconds"))}],
            )

        if press_plan := self._build_press_result(stripped):
            return press_plan

        if match := self._TYPE_PATTERN.match(stripped):
            return _build_result(
                "Rule task: type into the current focused window.",
                [{"type": "type", "text": _clean_tail_text(match.group("text"))}],
            )

        raise PlannerError("RulePlanner does not support this task.")

    def _build_calculator_expression_result(self, task: str) -> PlanResult | None:
        for pattern in self._CALCULATOR_EXPRESSION_PATTERNS:
            match = pattern.match(task)
            if not match:
                continue
            expression = _normalize_calculator_expression(match.group("expr"))
            if not expression:
                raise PlannerError("Calculator task did not contain a safe arithmetic expression.")
            return _build_result(
                f"Rule task: calculate {expression} in Calculator.",
                [
                    {"type": "open_app_if_needed", "app": "calculator"},
                    {"type": "wait", "seconds": 0.8},
                    {"type": "type", "text": expression},
                    {"type": "press", "key": "enter"},
                ],
            )
        match = self._STANDALONE_CALCULATOR_EXPRESSION_PATTERN.match(task)
        if not match:
            return None
        expression = _normalize_calculator_expression(match.group("expr"))
        if not expression:
            return None
        return _build_result(
            f"Rule task: calculate {expression} in Calculator.",
            [
                {"type": "open_app_if_needed", "app": "calculator"},
                {"type": "wait", "seconds": 0.8},
                {"type": "type", "text": expression},
                {"type": "press", "key": "enter"},
            ],
        )

    def _build_generic_app_task_result(self, task: str) -> PlanResult | None:
        if match := self._GENERIC_APP_SAVE_AS_PATTERN.match(task):
            app_name = _clean_app_name(match.group("app"))
            path = _clean_save_path(match.group("path"))
            if not _is_generic_desktop_app_name(app_name) or not path:
                return None
            return _build_result(
                f"Rule task: open {app_name} and save as {path}.",
                _open_app_actions(app_name) + _save_as_actions(path),
                current_focus=f"save {app_name} content as {path}",
                reasoning="Use the app's standard save shortcut, then enter the requested path or file name.",
            )

        if match := self._GENERIC_APP_FILL_PATTERN.match(task):
            app_name = _clean_app_name(match.group("app"))
            field = _clean_tail_text(match.group("field"))
            value = _clean_tail_text(match.group("value"))
            if not _is_generic_desktop_app_name(app_name) or not field or not value:
                return None
            return _build_result(
                f"Rule task: open {app_name} and fill {field}.",
                _open_app_actions(app_name)
                + [{"type": "uia_set_value", "selector": _build_uia_name_selector(field), "text": value}],
                current_focus=f"fill {field} in {app_name}",
                reasoning="Use UI Automation against the active app window after opening it.",
            )

        if match := self._GENERIC_APP_SEARCH_PATTERN.match(task):
            app_name = _clean_app_name(match.group("open_app") or match.group("with_app") or "")
            query = _clean_tail_text(match.group("query"))
            if not _is_generic_desktop_app_name(app_name) or not query:
                return None
            return _build_result(
                f"Rule task: open {app_name} and search for {query}.",
                _open_app_actions(app_name)
                + [
                    {"type": "hotkey", "keys": ["ctrl", "f"]},
                    {"type": "type", "text": query},
                    {"type": "press", "key": "enter"},
                ],
                current_focus=f"search inside {app_name}",
                reasoning="Use the standard in-app Find shortcut, then enter the query.",
            )

        if match := self._GENERIC_APP_CLICK_PATTERN.match(task):
            app_name = _clean_app_name(match.group("app"))
            target = _clean_tail_text(match.group("target"))
            if not _is_generic_desktop_app_name(app_name) or not target:
                return None
            return _build_result(
                f"Rule task: open {app_name} and invoke {target}.",
                _open_app_actions(app_name) + [{"type": "uia_invoke", "text": target}],
                current_focus=f"invoke {target} in {app_name}",
                reasoning="Use UI Automation to invoke a named control in the active app window.",
            )

        if match := self._GENERIC_APP_PRESS_PATTERN.match(task):
            app_name = _clean_app_name(match.group("app"))
            raw_key = match.group("key")
            hotkey_keys = _normalize_hotkey_keys(raw_key)
            key = _normalize_press_key(raw_key)
            if not _is_generic_desktop_app_name(app_name) or not (hotkey_keys or key):
                return None
            key_action = {"type": "hotkey", "keys": hotkey_keys} if hotkey_keys else {"type": "press", "key": key}
            return _build_result(
                f"Rule task: open {app_name} and press {_clean_tail_text(raw_key)}.",
                _open_app_actions(app_name) + [key_action],
                current_focus=f"press {_clean_tail_text(raw_key)} in {app_name}",
            )

        if match := self._GENERIC_APP_TYPE_PATTERN.match(task):
            app_name = _clean_app_name(match.group("app"))
            text = _clean_tail_text(match.group("text"))
            if not _is_generic_desktop_app_name(app_name) or not text:
                return None
            return _build_result(
                f"Rule task: open {app_name} and type text.",
                _open_app_actions(app_name) + [{"type": "type", "text": text}],
                current_focus=f"type into {app_name}",
            )

        return None

    def _build_save_as_result(self, task: str) -> PlanResult | None:
        match = self._SAVE_AS_PATTERN.match(task)
        if not match:
            return None
        path = _clean_save_path(match.group("path"))
        if not path:
            return None
        return _build_result(
            f"Rule task: save the current document as {path}.",
            _save_as_actions(path),
            current_focus=f"save as {path}",
            reasoning="Use the standard save shortcut and type the requested path or file name.",
        )

    def _build_open_url_result(self, task: str) -> PlanResult | None:
        match = self._OPEN_URL_PATTERN.match(task)
        if not match:
            return None
        target = _clean_tail_text(match.group("target"))
        if not _looks_like_open_target_url(target):
            return None
        return _build_result(
            f"Rule task: open {target} in the browser.",
            [{"type": "browser_open", "text": _ensure_browser_target_url(target)}],
            current_focus=f"open {target}",
        )

    def _build_browser_click_result(self, task: str) -> PlanResult | None:
        match = self._BROWSER_CLICK_PATTERN.match(task)
        if not match:
            return None
        target = _clean_tail_text(match.group("target"))
        if not target or _looks_like_open_target_url(target):
            return None
        return _build_result(
            f"Rule task: click {target} in the browser.",
            [{"type": "browser_dom_click", "text": target}],
            current_focus=f"click {target}",
            reasoning="Treat a standalone named click as a browser DOM follow-up after navigation.",
        )

    def _build_press_result(self, task: str) -> PlanResult | None:
        match = self._PRESS_PATTERN.match(task)
        if not match:
            return None
        raw_key = match.group("key")
        hotkey_keys = _normalize_hotkey_keys(raw_key)
        if hotkey_keys:
            return _build_result(
                f"Rule task: press {_clean_tail_text(raw_key)}.",
                [{"type": "hotkey", "keys": hotkey_keys}],
            )
        key = _normalize_press_key(raw_key)
        if not key:
            return None
        return _build_result(
            f"Rule task: press {key}.",
            [{"type": "press", "key": key}],
        )

    def _build_close_result(self, task: str) -> PlanResult | None:
        match = self._CLOSE_APP_PATTERN.match(task)
        if not match:
            return None
        target = _clean_tail_text(match.group("target") or "")
        if not target:
            return _build_result(
                "Rule task: close the current window.",
                [{"type": "hotkey", "keys": ["alt", "f4"]}],
            )
        return _build_result(
            f"Rule task: close {target}.",
            [{"type": "close_window", "title": target}],
        )

    def _build_generic_close_result(self, task: str) -> PlanResult | None:
        match = self._GENERIC_CLOSE_APP_PATTERN.match(task)
        if not match:
            return None
        target = _clean_app_name(match.group("target"))
        if not _is_generic_desktop_app_name(target):
            return None
        return _build_result(
            f"Rule task: close {target}.",
            [{"type": "close_window", "title": target}],
        )

    def _build_generic_open_app_result(self, task: str) -> PlanResult | None:
        match = self._GENERIC_OPEN_APP_PATTERN.match(task)
        if not match:
            return None
        app_name = _clean_tail_text(match.group("app"))
        if not app_name:
            return None
        lowered = app_name.lower()
        if re.search(r"\b(?:and\s+then|then|after\s+that|next|finally)\b", lowered, re.I):
            return None
        if lowered in {"notepad", "calculator", "calc", "explorer", "browser", "edge", "chrome", "firefox"}:
            return None
        if _looks_like_open_target_url(app_name) or any(token in lowered for token in ("http://", "https://", "www.", "/", "\\", "search ", "搜索")):
            return None
        return _build_result(
            f"Rule task: open local app {app_name}.",
            [
                {"type": "open_app_if_needed", "app": app_name},
                {"type": "wait", "seconds": 0.8},
            ],
        )


class VLMPlanner(BasePlanner):
    """Planner backed by an OpenAI-compatible VLM endpoint such as LM Studio."""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.web_agent = WebAgent(request_timeout=min(float(config.model_request_timeout), 3.0))
        self._model_name_cache: dict[tuple[str, str, bool, str], str] = {}
        self._structured_output_unsupported_modes: set[str] = set()

    def plan(
        self,
        task: str,
        screenshot_path: Path | None,
        history: list[str],
        environment: DesktopEnvironment | None = None,
    ) -> PlanResult:
        browser_command = self.web_agent.parse(task)
        if _should_use_browser_shortcut(task, history, browser_command):
            if web_plan := self.web_agent.try_plan(task):
                return web_plan

        requests = _import_requests()
        if screenshot_path is None or not screenshot_path.exists():
            raise PlannerError("VLMPlanner requires a screenshot.")

        api_base = _normalize_api_base_url(self.config.model_base_url)
        model_name = self._resolve_model_name(requests, api_base)
        image_b64 = base64.b64encode(screenshot_path.read_bytes()).decode("utf-8")
        browser_command = self.web_agent.parse(task)
        history_text = _format_history_for_prompt(history)
        browser_context = self.web_agent.build_task_context(task)
        decomposition_text = _build_task_decomposition(task, history, browser_command)
        environment_context = _build_environment_context(environment)

        response_format_mode = _normalize_structured_output_mode(self.config.model_structured_output)
        if response_format_mode in self._structured_output_unsupported_modes:
            response_format_mode = "off"
        payload = _build_vlm_payload(
            model_name=model_name,
            task=task,
            history_text=history_text,
            decomposition_text=decomposition_text,
            image_b64=image_b64,
            browser_context=browser_context,
            environment_context=environment_context,
            response_format_mode=response_format_mode,
        )

        try:
            content = self._request_plan_text(
                requests=requests,
                api_base=api_base,
                payload=payload,
                response_format_mode=response_format_mode,
            )
        except StructuredOutputUnsupportedError:
            self._structured_output_unsupported_modes.add(response_format_mode)
            fallback_payload = _build_vlm_payload(
                model_name=model_name,
                task=task,
                history_text=history_text,
                decomposition_text=decomposition_text,
                image_b64=image_b64,
                browser_context=browser_context,
                environment_context=environment_context,
                response_format_mode="off",
            )
            content = self._request_plan_text(
                requests=requests,
                api_base=api_base,
                payload=fallback_payload,
                response_format_mode="off",
            )

        try:
            plan_payload = _extract_json(content)
            return PlanResult.from_payload(plan_payload, raw_response=content)
        except (ActionValidationError, json.JSONDecodeError) as exc:
            raise PlannerError(
                "The VLM response could not be parsed into a valid action plan. "
                "Please confirm you loaded a vision-capable chat model in LM Studio."
            ) from exc

    def _resolve_model_name(self, requests_module, api_base: str) -> str:
        configured_model = (self.config.model_name or "").strip()
        if not _needs_model_discovery(configured_model) and not self.config.model_auto_discover:
            return configured_model
        cache_key = (
            api_base.rstrip("/"),
            configured_model.lower(),
            bool(self.config.model_auto_discover),
            str(self.config.model_api_key or ""),
        )
        if cache_key in self._model_name_cache:
            return self._model_name_cache[cache_key]

        available_models = self._fetch_models(requests_module, api_base)
        model_name = _pick_model_name(configured_model, available_models)
        self._model_name_cache[cache_key] = model_name
        return model_name

    def _fetch_models(self, requests_module, api_base: str) -> list[dict]:
        models_url = f"{api_base}/models"
        headers = _build_request_headers(self.config.model_api_key)
        try:
            response = requests_module.get(
                models_url,
                headers=headers,
                timeout=self.config.model_request_timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests_module.RequestException as exc:
            raise PlannerError(_build_connection_hint(api_base, exc)) from exc
        except ValueError as exc:
            raise PlannerError("LM Studio returned an invalid /models response.") from exc

        data = payload.get("data")
        if not isinstance(data, list) or not data:
            raise PlannerError(
                "LM Studio responded successfully, but no models were available at /v1/models. "
                "Load a model and start the local server first."
            )
        return data

    def _request_plan_text(
        self,
        *,
        requests,
        api_base: str,
        payload: dict,
        response_format_mode: str,
    ) -> str:
        url = f"{api_base}/chat/completions"
        headers = _build_request_headers(self.config.model_api_key)
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.config.model_request_timeout,
            )
        except requests.RequestException as exc:
            raise PlannerError(_build_connection_hint(api_base, exc)) from exc

        if response.status_code >= 400:
            body_text = response.text.strip()
            if response_format_mode != "off" and _looks_like_structured_output_rejection(body_text):
                raise StructuredOutputUnsupportedError(body_text)
            raise PlannerError(
                f"LM Studio request failed with HTTP {response.status_code}. "
                f"Response: {body_text or '<empty>'}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise PlannerError("LM Studio returned invalid JSON for chat/completions.") from exc

        return _extract_message_content(data)


class AutoPlanner(BasePlanner):
    """Try rule planner first, then fall back to the VLM planner."""

    def __init__(self, config: AgentConfig):
        self.rule = RulePlanner()
        self.vlm = VLMPlanner(config)

    def plan(
        self,
        task: str,
        screenshot_path: Path | None,
        history: list[str],
        environment: DesktopEnvironment | None = None,
    ) -> PlanResult:
        browser_command = self.rule.web_agent.parse(task)
        intent = classify_task_intent(task, history=history, browser_command=browser_command)
        if intent.requires_clarification:
            raise PlannerError(intent.clarification_prompt or "The task needs clarification before it can be executed.")
        planner_order = (
            (self.vlm, self.rule)
            if _intent_requires_model_reasoning(intent)
            or _task_requires_vlm_reasoning(task, history, browser_command)
            else (self.rule, self.vlm)
        )
        last_error: Exception | None = None
        for planner in planner_order:
            try:
                return planner.plan(task, screenshot_path, history, environment)
            except PlannerError as exc:
                last_error = exc
                continue
        raise PlannerError(str(last_error) if last_error is not None else "Unable to plan the task.")


class TaskGraphPlanner:
    """Split a broad task into generic, verifiable subgoals."""

    def __init__(self, config: AgentConfig | None = None) -> None:
        self.config = config or AgentConfig()
        self.web_agent = WebAgent()
        self._text_model_name_cache: dict[tuple[str, str, str], str] = {}
        self._structured_output_unsupported_modes: set[str] = set()

    def plan(self, task: str, *, history: list[str] | None = None, world_model: WorldModel | None = None) -> TaskGraph:
        browser_command = self.web_agent.parse(task)
        intent = classify_task_intent(
            task,
            history=history or [],
            world_model=world_model,
            browser_command=browser_command,
        )
        if intent.requires_clarification:
            return self._build_clarification_graph(task, intent)

        if _should_use_structured_task_graph(
            config=self.config,
            task=task,
            intent=intent,
            browser_command=browser_command,
        ):
            model_graph = self._plan_with_structured_model(
                task=task,
                intent=intent,
                history=history or [],
                world_model=world_model,
            )
            if model_graph is not None:
                return model_graph

        return self._build_heuristic_graph(
            task=task,
            intent=intent,
            browser_command=browser_command,
            world_model=world_model,
        )

    def replan_remaining(
        self,
        execution_state,
        world_model: WorldModel | None,
        failure,
    ) -> TaskGraph:
        current = execution_state.task_graph
        completed = [item for item in current.subgoals if item.status == "completed"]
        incomplete = [item for item in current.subgoals if item.status != "completed"]
        if not incomplete:
            return current

        failure_message = _optional_str(getattr(failure, "message", None))
        replacement_titles: list[str] = []
        for index, subgoal in enumerate(incomplete):
            title = subgoal.fallback_goal or subgoal.goal or subgoal.title
            if index == 0 and failure_message:
                title = f"{title} after resolving: {failure_message}"
            replacement_titles.append(title)

        replacement_titles = _limit_subgoal_titles(
            replacement_titles,
            max_count=max(1, self.config.max_task_subgoals - len(completed)),
        )
        rebuilt = self._build_graph_from_titles(
            task=current.task,
            titles=replacement_titles,
            intent=TaskIntent.from_dict(current.intent or {}),
            world_model=world_model,
            start_index=len(completed) + 1,
            first_prerequisite=completed[-1].id if completed else None,
        )
        completed_ids = {item.id for item in completed}
        dependencies = {
            key: list(value)
            for key, value in current.dependencies.items()
            if key in completed_ids
        }
        dependencies.update(rebuilt.dependencies)
        subgoals = [*completed, *rebuilt.subgoals]
        return TaskGraph(
            task=current.task,
            subgoals=subgoals,
            dependencies=dependencies,
            success_criteria=[item.success_condition for item in subgoals],
            constraints=_dedupe_strings([*current.constraints, "Replanned remaining work after a failed subgoal."]),
            risk_points=[item.title for item in subgoals if item.risk_level in {"medium", "high", "critical"}],
            completion_summary=_build_completion_summary(current.task, subgoals),
            intent=dict(current.intent) if isinstance(current.intent, dict) else None,
            recipes=list(current.recipes),
        )

    def _build_clarification_graph(self, task: str, intent: TaskIntent) -> TaskGraph:
        clarification_title = intent.clarification_prompt or "Clarify the requested task before acting."
        subgoal = Subgoal(
            id="subgoal_01",
            title=clarification_title,
            goal=clarification_title,
            goal_type="clarify",
            success_condition="Wait for the user to clarify the intended goal before automation continues.",
            risk_level="medium",
            retry_budget=0,
            max_attempts=1,
            completion_evidence={
                "kind": "requires_clarification",
                "detail": "The task does not have enough information to run safely.",
            },
        )
        return TaskGraph(
            task=task.strip(),
            subgoals=[subgoal],
            dependencies={subgoal.id: []},
            success_criteria=[subgoal.success_condition],
            constraints=["Ask for clarification before executing desktop or browser actions."],
            risk_points=[subgoal.title],
            completion_summary="The task is intentionally paused until the user clarifies the goal.",
            intent=intent.to_dict(),
        )

    def _build_heuristic_graph(
        self,
        *,
        task: str,
        intent: TaskIntent,
        browser_command: WebCommand | None,
        world_model: WorldModel | None,
    ) -> TaskGraph:
        raw_subgoals = _extract_semantic_sub_goals(task, browser_command, intent)
        if not raw_subgoals:
            raw_subgoals = _extract_task_sub_goals(task, browser_command)
        if not raw_subgoals:
            raw_subgoals = [task.strip()]
        raw_subgoals = _limit_subgoal_titles(raw_subgoals, max_count=self.config.max_task_subgoals)
        return self._build_graph_from_titles(
            task=task,
            titles=raw_subgoals,
            intent=intent,
            world_model=world_model,
        )

    def _build_graph_from_titles(
        self,
        *,
        task: str,
        titles: list[str],
        intent: TaskIntent,
        world_model: WorldModel | None,
        start_index: int = 1,
        first_prerequisite: str | None = None,
    ) -> TaskGraph:
        subgoals: list[Subgoal] = []
        dependencies: dict[str, list[str]] = {}
        previous_subgoal_id: str | None = first_prerequisite
        preferred_fallback = intent.preferred_capabilities[0] if intent.preferred_capabilities else "desktop_gui"
        for offset, item in enumerate(titles):
            title = item.strip()
            if not title:
                continue
            subgoal_id = f"subgoal_{start_index + offset:02d}"
            goal_type = _infer_goal_type(title)
            prerequisites = [previous_subgoal_id] if previous_subgoal_id else []
            capability_preference = _infer_capability_preference(title, world_model=world_model) or preferred_fallback
            subgoals.append(
                Subgoal(
                    id=subgoal_id,
                    title=title,
                    goal=title,
                    goal_type=goal_type,
                    success_condition=_build_subgoal_success_condition(title, world_model=world_model),
                    prerequisites=prerequisites,
                    fallback_goal=_build_fallback_goal(title, goal_type),
                    capability_preference=capability_preference,
                    risk_level=_max_risk(_infer_subgoal_risk(title), intent.risk_level if offset == 0 else "low"),
                    retry_budget=max(1, int(self.config.max_subgoal_retries or 1)),
                    max_attempts=max(2, int(self.config.max_subgoal_retries or 1) + 1),
                    completion_evidence=_infer_completion_evidence(title, goal_type=goal_type, world_model=world_model),
                )
            )
            dependencies[subgoal_id] = list(prerequisites)
            previous_subgoal_id = subgoal_id

        if not subgoals:
            subgoal_id = f"subgoal_{start_index:02d}"
            subgoals.append(
                Subgoal(
                    id=subgoal_id,
                    title=task.strip() or "Complete the task.",
                    goal=task.strip() or "Complete the task.",
                    goal_type="handoff",
                    success_condition="Confirm that the requested task is completed.",
                    capability_preference=preferred_fallback,
                    completion_evidence={"kind": "state_change", "detail": "Confirm the requested outcome is visible."},
                    retry_budget=max(1, int(self.config.max_subgoal_retries or 1)),
                    max_attempts=max(2, int(self.config.max_subgoal_retries or 1) + 1),
                )
            )
            dependencies[subgoal_id] = [first_prerequisite] if first_prerequisite else []

        success_criteria = [item.success_condition for item in subgoals]
        constraints = [
            "Use guarded actions only.",
            "Switch capability when verification repeatedly fails.",
            "Only mark subgoals complete when completion evidence is satisfied.",
        ]
        if intent.constraints:
            constraints.extend(item for item in intent.constraints if item not in constraints)
        risk_points = [item.title for item in subgoals if item.risk_level in {"medium", "high", "critical"}]
        return TaskGraph(
            task=task.strip(),
            subgoals=subgoals,
            dependencies=dependencies,
            success_criteria=success_criteria,
            constraints=constraints,
            risk_points=risk_points,
            completion_summary=_build_completion_summary(task, subgoals),
            intent=intent.to_dict(),
        )

    def _plan_with_structured_model(
        self,
        *,
        task: str,
        intent: TaskIntent,
        history: list[str],
        world_model: WorldModel | None,
    ) -> TaskGraph | None:
        try:
            requests = _import_requests()
            api_base = _normalize_api_base_url(self.config.model_base_url)
            model_name = self._resolve_text_model_name(requests, api_base)
            response_format_mode = _normalize_structured_output_mode(self.config.model_structured_output)
            if response_format_mode in self._structured_output_unsupported_modes:
                response_format_mode = "off"
            payload = _build_task_graph_payload(
                model_name=model_name,
                task=task,
                intent=intent,
                history=history,
                world_model=world_model,
                max_subgoals=self.config.max_task_subgoals,
                response_format_mode=response_format_mode,
            )
            try:
                content = _request_task_graph_text(
                    config=self.config,
                    requests=requests,
                    api_base=api_base,
                    payload=payload,
                    response_format_mode=response_format_mode,
                )
            except StructuredOutputUnsupportedError:
                self._structured_output_unsupported_modes.add(response_format_mode)
                fallback_payload = _build_task_graph_payload(
                    model_name=model_name,
                    task=task,
                    intent=intent,
                    history=history,
                    world_model=world_model,
                    max_subgoals=self.config.max_task_subgoals,
                    response_format_mode="off",
                )
                content = _request_task_graph_text(
                    config=self.config,
                    requests=requests,
                    api_base=api_base,
                    payload=fallback_payload,
                    response_format_mode="off",
                )
            graph_payload = _extract_json(content)
            return self._task_graph_from_model_payload(
                task=task,
                intent=intent,
                payload=graph_payload,
                world_model=world_model,
            )
        except Exception:
            return None

    def _resolve_text_model_name(self, requests_module, api_base: str) -> str:
        configured_model = (self.config.model_name or "").strip()
        if not _needs_model_discovery(configured_model):
            return configured_model
        cache_key = (
            api_base.rstrip("/"),
            configured_model.lower(),
            str(self.config.model_api_key or ""),
        )
        if cache_key in self._text_model_name_cache:
            return self._text_model_name_cache[cache_key]
        model_name = _resolve_text_model_name(self.config, requests_module, api_base)
        self._text_model_name_cache[cache_key] = model_name
        return model_name

    def _task_graph_from_model_payload(
        self,
        *,
        task: str,
        intent: TaskIntent,
        payload: dict[str, Any],
        world_model: WorldModel | None,
    ) -> TaskGraph | None:
        items = payload.get("subgoals")
        if not isinstance(items, list):
            return None
        titles: list[str] = []
        for item in items:
            if isinstance(item, dict):
                title = _optional_str(item.get("title") or item.get("goal"))
            else:
                title = _optional_str(item)
            if title:
                titles.append(title)
        titles = _limit_subgoal_titles(titles, max_count=self.config.max_task_subgoals)
        if not titles:
            return None
        graph = self._build_graph_from_titles(
            task=task,
            titles=titles,
            intent=intent,
            world_model=world_model,
        )
        for subgoal, raw_item in zip(graph.subgoals, items):
            if not isinstance(raw_item, dict):
                continue
            subgoal.goal_type = _normalize_model_goal_type(raw_item.get("goal_type"), fallback=subgoal.goal_type)
            subgoal.success_condition = _optional_str(raw_item.get("success_condition")) or subgoal.success_condition
            subgoal.capability_preference = _optional_str(raw_item.get("capability_preference")) or subgoal.capability_preference
            subgoal.risk_level = _normalize_model_risk(raw_item.get("risk_level"), fallback=subgoal.risk_level)
            if isinstance(raw_item.get("completion_evidence"), dict):
                subgoal.completion_evidence = dict(raw_item["completion_evidence"])
        graph.constraints = _dedupe_strings(
            [
                *graph.constraints,
                *[str(item).strip() for item in payload.get("constraints", []) or [] if str(item).strip()],
            ]
        )
        graph.risk_points = _dedupe_strings(
            [
                *graph.risk_points,
                *[str(item).strip() for item in payload.get("risk_points", []) or [] if str(item).strip()],
            ]
        )
        graph.completion_summary = _optional_str(payload.get("completion_summary")) or graph.completion_summary
        graph.intent = intent.to_dict()
        return graph


class SubgoalPlanner:
    """Plan low-level guarded actions for a single current subgoal."""

    def __init__(self, config: AgentConfig, *, base_planner: BasePlanner | None = None):
        self.config = config
        self.base_planner = base_planner or build_planner(config)

    def plan_subgoal(self, subgoal: Subgoal, world_model: WorldModel, history: list[str]) -> PlanResult:
        return self.base_planner.plan(
            task=subgoal.title,
            screenshot_path=world_model.screenshot_path,
            history=history,
            environment=world_model.environment,
        )


def build_planner(config: AgentConfig) -> BasePlanner:
    mode = config.planner_mode.lower().strip()
    if mode == "rule":
        return RulePlanner()
    if mode == "vlm":
        return VLMPlanner(config)
    return AutoPlanner(config)


def _build_result(
    summary: str,
    actions: list[dict],
    done: bool = True,
    *,
    current_focus: str | None = None,
    reasoning: str | None = None,
    remaining_steps: list[str] | None = None,
) -> PlanResult:
    return PlanResult.from_payload(
        {
            "status_summary": summary,
            "done": done,
            "actions": actions,
            "current_focus": current_focus,
            "reasoning": reasoning,
            "remaining_steps": remaining_steps or [],
        }
    )


def _clean_tail_text(text: str) -> str:
    return text.strip().strip("\"' ")


def _clean_app_name(text: str) -> str:
    cleaned = _clean_tail_text(text)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _is_generic_desktop_app_name(app_name: str) -> bool:
    cleaned = _clean_app_name(app_name)
    if not cleaned:
        return False
    lowered = cleaned.lower()
    if lowered in {"browser", "edge", "chrome", "firefox", "calculator", "calc", "explorer"}:
        return False
    if cleaned in {"浏览器", "计算器", "资源管理器", "文件资源管理器"}:
        return False
    if _looks_like_open_target_url(cleaned):
        return False
    return not any(token in lowered for token in ("http://", "https://", "www.", "/", "\\"))


def _open_app_actions(app_name: str) -> list[dict]:
    return [
        {"type": "open_app_if_needed", "app": _clean_app_name(app_name)},
        {"type": "wait", "seconds": 0.8},
    ]


def _save_as_actions(path: str) -> list[dict]:
    cleaned_path = _clean_save_path(path)
    actions: list[dict] = [
        {"type": "hotkey", "keys": ["ctrl", "s"]},
        {"type": "wait", "seconds": 0.4},
    ]
    if cleaned_path:
        actions.extend(
            [
                {"type": "type", "text": cleaned_path},
                {"type": "press", "key": "enter"},
            ]
        )
    return actions


def _clean_save_path(path: str) -> str:
    cleaned = _clean_tail_text(path)
    cleaned = cleaned.rstrip(".。")
    return cleaned[:180].strip()


def _build_uia_name_selector(name: str) -> str:
    return f"name={_clean_tail_text(name)}"


def _normalize_hotkey_keys(key: str) -> list[str] | None:
    normalized = _clean_tail_text(key).lower()
    replacements = {
        "control": "ctrl",
        "windows": "win",
        "command": "win",
        "cmd": "win",
    }
    for source, target in replacements.items():
        normalized = re.sub(rf"\b{re.escape(source)}\b", target, normalized)
    parts = [part for part in re.split(r"\s*(?:\+|-)\s*|\s+", normalized) if part]
    if len(parts) < 2:
        return None
    modifiers = {"ctrl", "alt", "shift", "win"}
    if not any(part in modifiers for part in parts[:-1]):
        return None
    aliases = {"escape": "esc", "return": "enter"}
    cleaned_parts = [aliases.get(part, part) for part in parts]
    if not all(re.fullmatch(r"[a-z0-9]{1,12}", part) for part in cleaned_parts):
        return None
    return cleaned_parts


def _normalize_press_key(key: str) -> str | None:
    normalized = _clean_tail_text(key).lower().replace("+", " ")
    normalized = " ".join(normalized.split())
    aliases = {
        "enter": "enter",
        "return": "enter",
        "回车": "enter",
        "确认": "enter",
        "tab": "tab",
        "制表": "tab",
        "esc": "esc",
        "escape": "esc",
        "退出": "esc",
        "backspace": "backspace",
        "退格": "backspace",
        "space": "space",
        "空格": "space",
        "up": "up",
        "上": "up",
        "down": "down",
        "下": "down",
        "left": "left",
        "左": "left",
        "right": "right",
        "右": "right",
    }
    return aliases.get(normalized)


def _normalize_calculator_expression(text: str) -> str | None:
    normalized = _clean_tail_text(text)
    replacements = (
        ("（", "("),
        ("）", ")"),
        ("×", "*"),
        ("x", "*"),
        ("X", "*"),
        ("÷", "/"),
        ("\u4e58\u4ee5", "*"),
        ("\u4e58", "*"),
        ("\u52a0", "+"),
        ("\u51cf\u53bb", "-"),
        ("\u51cf", "-"),
        ("\u9664\u4ee5", "/"),
        ("\u9664", "/"),
        ("\u7b49\u4e8e\u591a\u5c11", ""),
        ("\u7b49\u4e8e", ""),
        ("\u591a\u5c11", ""),
        ("=", ""),
        ("?", ""),
        ("\uff1f", ""),
        ("\u3002", ""),
    )
    for source, target in replacements:
        normalized = normalized.replace(source, target)
    normalized = re.sub(r"\s+", "", normalized)
    if not normalized:
        return None
    if not re.fullmatch(r"[0-9+\-*/().]+", normalized):
        return None
    if not re.search(r"[+\-*/]", normalized):
        return None
    return normalized


def _format_history_for_prompt(history: list[str]) -> str:
    if not history:
        return "Round 0:\n  No prior execution history."

    recent_history = history[-4:]
    start_index = len(history) - len(recent_history) + 1
    blocks: list[str] = []
    for round_index, entry in enumerate(recent_history, start=start_index):
        lines = [line.strip() for line in str(entry).splitlines() if line.strip()]
        if not lines:
            blocks.append(f"Round {round_index}:\n  <empty>")
            continue
        indented = "\n  ".join(lines)
        blocks.append(f"Round {round_index}:\n  {indented}")
    return "\n".join(blocks)


def _should_use_structured_task_graph(
    *,
    config: AgentConfig,
    task: str,
    intent: TaskIntent,
    browser_command: WebCommand | None,
) -> bool:
    mode = str(getattr(config, "complex_task_planning", "hybrid") or "hybrid").strip().lower()
    if mode in {"off", "heuristic"}:
        return False
    if not _task_graph_model_endpoint_available(config):
        return False
    if mode == "model":
        return True
    sub_goals = _extract_semantic_sub_goals(task, browser_command, intent) or _extract_task_sub_goals(task, browser_command)
    return (
        _intent_requires_model_reasoning(intent)
        or intent.confidence < 0.72
        or len(sub_goals) >= 3
        or intent.task_type in {"cross_app_workflow", "multi_step_workflow", "research_summary"}
    )


def _task_graph_model_endpoint_available(config: AgentConfig) -> bool:
    base_url = str(getattr(config, "model_base_url", "") or "").strip()
    if not base_url:
        return False
    try:
        parsed = urlsplit(_normalize_api_base_url(base_url))
    except Exception:
        return False
    host = (parsed.hostname or "").strip().lower()
    if host in {"127.0.0.1", "localhost", "::1"}:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            with socket.create_connection((host, port), timeout=0.08):
                return True
        except OSError:
            return False
    return bool(str(getattr(config, "model_api_key", "") or "").strip() or str(getattr(config, "model_provider", "") or "").strip() != "lmstudio_local")


def _limit_subgoal_titles(titles: list[str], *, max_count: int) -> list[str]:
    cleaned = _dedupe_strings([_clean_sub_goal_part(item) for item in titles if _clean_sub_goal_part(item)])
    max_count = max(1, int(max_count or 1))
    if len(cleaned) <= max_count:
        return cleaned
    if max_count == 1:
        return [f"Complete the staged workflow: {'; '.join(cleaned)}"]
    head = cleaned[: max_count - 1]
    tail = "; ".join(cleaned[max_count - 1 :])
    head.append(f"Complete remaining requested work: {tail}")
    return head


def _max_risk(left: str, right: str) -> str:
    order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    left_normalized = _normalize_model_risk(left, fallback="low")
    right_normalized = _normalize_model_risk(right, fallback="low")
    return left_normalized if order[left_normalized] >= order[right_normalized] else right_normalized


def _normalize_model_goal_type(value: Any, *, fallback: str) -> str:
    normalized = str(value or fallback or "handoff").strip().lower()
    return normalized if normalized in {
        "navigate",
        "locate",
        "read",
        "extract",
        "transform",
        "fill",
        "confirm",
        "transfer",
        "save",
        "clarify",
        "handoff",
    } else fallback


def _normalize_model_risk(value: Any, *, fallback: str) -> str:
    normalized = str(value or fallback or "low").strip().lower()
    return normalized if normalized in {"low", "medium", "high", "critical"} else fallback


def _resolve_text_model_name(config: AgentConfig, requests_module, api_base: str) -> str:
    configured_model = (config.model_name or "").strip()
    if not _needs_model_discovery(configured_model):
        return configured_model
    response = requests_module.get(
        f"{api_base}/models",
        headers=_build_request_headers(config.model_api_key),
        timeout=_task_graph_model_timeout(config),
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        raise PlannerError("No model is available for structured task graph planning.")
    return _pick_model_name(configured_model, data)


def _task_graph_model_timeout(config: AgentConfig) -> float:
    try:
        request_timeout = float(config.model_request_timeout)
    except (TypeError, ValueError):
        request_timeout = 90.0
    try:
        graph_budget = float(getattr(config, "task_graph_request_timeout", 12.0))
    except (TypeError, ValueError):
        graph_budget = 12.0
    # Allow the structured task-graph call enough headroom to actually return a
    # decomposition for complex tasks, while never exceeding the overall request
    # timeout. The previous hard 3s cap forced almost every complex task to fall
    # back to heuristic planning.
    return max(0.5, min(request_timeout, graph_budget))


def _build_task_graph_payload(
    *,
    model_name: str,
    task: str,
    intent: TaskIntent,
    history: list[str],
    world_model: WorldModel | None,
    max_subgoals: int,
    response_format_mode: str,
) -> dict[str, Any]:
    user_text = (
        f"Task: {task.strip()}\n"
        f"Intent: {json.dumps(intent.to_dict(), ensure_ascii=False, sort_keys=True)}\n"
        f"Recent execution memory:\n{_format_history_for_prompt(history)}\n"
        f"Current world model:\n{_task_graph_world_model_context(world_model)}\n"
        f"Create a commercial-grade task graph with at most {max_subgoals} subgoals. "
        "Each subgoal must be verifiable, ordered by prerequisites, and scoped to a meaningful work objective rather than one raw click. "
        "Use low risk only for read-only/navigation work. Mark login, purchase, submit, delete, install, or shell work as high risk. "
        "Return JSON only."
    )
    payload: dict[str, Any] = {
        "model": model_name,
        "temperature": 0.1,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You design task graphs for a local desktop agent. Return only JSON with keys: "
                    "subgoals, success_criteria, constraints, risk_points, completion_summary. "
                    "Each subgoal includes title, goal_type, success_condition, capability_preference, risk_level, completion_evidence."
                ),
            },
            {"role": "user", "content": user_text},
        ],
    }
    response_format = _build_task_graph_response_format(response_format_mode)
    if response_format is not None:
        payload["response_format"] = response_format
    return payload


def _task_graph_world_model_context(world_model: WorldModel | None) -> str:
    if world_model is None:
        return "No live world model is available yet."
    browser = world_model.browser_snapshot or {}
    lines = [
        f"active_app={world_model.active_app or ''}",
        f"active_window_title={world_model.active_window_title or ''}",
        f"structured_sources={', '.join(world_model.structured_sources)}",
    ]
    if browser:
        lines.append(f"browser_url={browser.get('url') or ''}")
        lines.append(f"browser_title={browser.get('title') or ''}")
    if world_model.anchor_candidates:
        lines.append("anchors=" + " | ".join(world_model.anchor_candidates[:6]))
    return "\n".join(lines)


def _build_task_graph_response_format(mode: str) -> dict[str, Any] | None:
    if mode == "off":
        return None
    if mode == "json_object":
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "desktop_agent_task_graph",
            "schema": _task_graph_json_schema(),
        },
    }


def _task_graph_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "subgoals": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "goal_type": {"type": "string"},
                        "success_condition": {"type": "string"},
                        "capability_preference": {"type": "string"},
                        "risk_level": {"type": "string"},
                        "completion_evidence": {
                            "type": "object",
                            "additionalProperties": True,
                        },
                    },
                    "required": ["title", "goal_type", "success_condition", "risk_level"],
                    "additionalProperties": True,
                },
            },
            "success_criteria": {"type": "array", "items": {"type": "string"}},
            "constraints": {"type": "array", "items": {"type": "string"}},
            "risk_points": {"type": "array", "items": {"type": "string"}},
            "completion_summary": {"type": "string"},
        },
        "required": ["subgoals"],
        "additionalProperties": True,
    }


def _request_task_graph_text(
    *,
    config: AgentConfig,
    requests,
    api_base: str,
    payload: dict[str, Any],
    response_format_mode: str,
) -> str:
    response = requests.post(
        f"{api_base}/chat/completions",
        headers=_build_request_headers(config.model_api_key),
        json=payload,
        timeout=_task_graph_model_timeout(config),
    )
    if response.status_code >= 400:
        body_text = response.text.strip()
        if response_format_mode != "off" and _looks_like_structured_output_rejection(body_text):
            raise StructuredOutputUnsupportedError(body_text)
        raise PlannerError(f"Task graph planning failed with HTTP {response.status_code}. Response: {body_text or '<empty>'}")
    return _extract_message_content(response.json())


def classify_task_intent(
    task: str,
    *,
    history: list[str] | None = None,
    world_model: WorldModel | None = None,
    browser_command: WebCommand | None = None,
) -> TaskIntent:
    """Classify the user's goal before choosing deterministic or model planning."""

    stripped = task.strip()
    if not stripped:
        return _clarification_intent("Please describe the task you want Aoryn to complete.")

    browser_command = browser_command if browser_command is not None else WebAgent().parse(stripped)
    risk_level = _infer_intent_risk(stripped)
    constraints = _infer_task_constraints(stripped)
    preferred = _infer_intent_capabilities(stripped, world_model=world_model)
    entities: list[str] = []
    success_hints: list[str] = []
    task_type = "general"
    domain = "desktop"
    confidence = 0.62
    planning_strategy = "rule_first"

    if _task_needs_clarification(stripped):
        return _clarification_intent(
            "I need a more specific goal before acting. Please name the app, website, file, or result you want.",
            primary_goal=stripped,
            risk_level=risk_level,
        )

    research_query, research_follow_up = _extract_research_goal(stripped)
    if research_query:
        task_type = "research_summary"
        domain = "web"
        entities.append(research_query)
        preferred = _merge_preferred_capabilities(["browser_dom", "clipboard", "desktop_gui"], preferred)
        success_hints.extend(
            [
                f"Search results or page content mention {research_query}.",
                research_follow_up or "A concise summary or extracted answer is produced.",
            ]
        )
        confidence = 0.84
        planning_strategy = "model_assisted"
    elif browser_command is not None:
        domain = "web"
        preferred = _merge_preferred_capabilities(["browser_dom", "desktop_gui"], preferred)
        if browser_command.intent == "shopping_search":
            task_type = "shopping"
            if browser_command.shopping_query:
                entities.append(browser_command.shopping_query)
            success_hints.append("Shopping or marketplace results are visible before any purchase action.")
            risk_level = "medium" if risk_level == "low" else risk_level
            confidence = 0.88
        elif browser_command.intent == "search":
            task_type = "information_search"
            if browser_command.target:
                entities.append(browser_command.target)
            success_hints.append("Search results or relevant page text are visible.")
            confidence = 0.86
        elif browser_command.intent == "open_url":
            task_type = "web_navigation"
            if browser_command.target:
                entities.append(browser_command.target)
            success_hints.append("The requested web destination is open.")
            confidence = 0.88
        elif browser_command.intent == "launch":
            task_type = "app_launch"
            entities.append("browser")
            success_hints.append("The browser window is active.")
            confidence = 0.9
        if browser_command.follow_up_steps:
            planning_strategy = "model_assisted"
    elif _looks_like_shopping_task(stripped):
        task_type = "shopping"
        domain = "web"
        preferred = _merge_preferred_capabilities(["browser_dom", "desktop_gui"], preferred)
        entities.extend(_extract_named_entities(stripped))
        success_hints.append("Shopping or marketplace results are visible before any purchase action.")
        risk_level = "medium" if risk_level == "low" else risk_level
        confidence = 0.76
    elif _looks_like_web_research(stripped):
        task_type = "information_search"
        domain = "web"
        preferred = _merge_preferred_capabilities(["browser_dom", "desktop_gui"], preferred)
        entities.extend(_extract_named_entities(stripped))
        success_hints.append("Relevant web information is visible.")
        confidence = 0.72
    elif _looks_like_cross_app_task(stripped):
        task_type = "cross_app_workflow"
        domain = "desktop"
        preferred = _merge_preferred_capabilities(["browser_dom", "windows_uia", "clipboard", "desktop_gui"], preferred)
        success_hints.append("Each app-specific subgoal completes and the final requested artifact is visible.")
        confidence = 0.78
        planning_strategy = "model_assisted"

    if _contains_multi_step_markers(stripped):
        planning_strategy = "model_assisted"
        if task_type == "general":
            task_type = "multi_step_workflow"
        success_hints.append("All detected subgoals are completed in order.")

    ambiguity = "medium" if planning_strategy == "model_assisted" and confidence < 0.8 else "low"
    if not preferred:
        preferred = ["windows_uia", "desktop_gui"]
    if not success_hints:
        success_hints.append("The visible desktop state satisfies the user's requested outcome.")

    return TaskIntent(
        task_type=task_type,
        primary_goal=stripped,
        domain=domain,
        entities=_dedupe_strings(entities)[:6],
        constraints=_dedupe_strings(constraints),
        risk_level=risk_level,
        ambiguity=ambiguity,
        preferred_capabilities=preferred,
        success_hints=_dedupe_strings(success_hints)[:6],
        planning_strategy=planning_strategy,
        confidence=confidence,
        source="hybrid_heuristic",
    )


def _clarification_intent(
    prompt: str,
    *,
    primary_goal: str = "",
    risk_level: str = "low",
) -> TaskIntent:
    return TaskIntent(
        task_type="clarification",
        primary_goal=primary_goal,
        domain=None,
        risk_level=risk_level,
        ambiguity="high",
        requires_clarification=True,
        clarification_prompt=prompt,
        preferred_capabilities=[],
        success_hints=["The user provides the missing goal or target."],
        planning_strategy="ask_user",
        confidence=0.95,
        source="hybrid_heuristic",
    )


def _intent_requires_model_reasoning(intent: TaskIntent) -> bool:
    if intent.requires_clarification:
        return False
    if intent.planning_strategy == "model_assisted":
        return True
    return intent.ambiguity in {"medium", "high"} or intent.task_type in {
        "cross_app_workflow",
        "multi_step_workflow",
        "research_summary",
    }


def _extract_semantic_sub_goals(
    task: str,
    browser_command: WebCommand | None,
    intent: TaskIntent,
) -> list[str]:
    research_query, research_follow_up = _extract_research_goal(task)
    if research_query:
        follow_up = research_follow_up or "summarize the findings"
        return [f"search for {research_query}", follow_up]

    if browser_command is not None and browser_command.follow_up_steps:
        initial_step = _describe_browser_initial_step(browser_command)
        browser_steps = [initial_step] if initial_step else []
        browser_steps.extend(step for step in browser_command.follow_up_steps if step)
        return browser_steps[:12]

    if intent.task_type in {"cross_app_workflow", "multi_step_workflow"}:
        return _split_task_segments(task)

    return []


def _build_task_decomposition(
    task: str,
    history: list[str],
    browser_command: WebCommand | None,
) -> str:
    intent = classify_task_intent(task, history=history, browser_command=browser_command)
    sub_goals = _extract_semantic_sub_goals(task, browser_command, intent)
    if not sub_goals:
        sub_goals = _extract_task_sub_goals(task, browser_command)
    if not sub_goals:
        return "No explicit sub-goal split was detected. Focus on the next visible prerequisite."

    lines = [
        f"Overall goal: {task.strip()}",
        "Candidate sub-goals:",
    ]
    for index, sub_goal in enumerate(sub_goals, start=1):
        lines.append(f"{index}. {sub_goal}")
    if history:
        lines.append(
            "Planning policy: use the execution memory and screenshot to continue from the first unmet sub-goal instead of restarting."
        )
    else:
        lines.append("Planning policy: start from the first prerequisite sub-goal and keep later work in remaining_steps.")
    return "\n".join(lines)


def _extract_task_sub_goals(task: str, browser_command: WebCommand | None) -> list[str]:
    if browser_command is not None:
        initial_step = _describe_browser_initial_step(browser_command)
        browser_steps = [initial_step] if initial_step else []
        browser_steps.extend(step for step in browser_command.follow_up_steps if step)
        return browser_steps[:12]

    normalized = task.strip()
    if not normalized:
        return []

    separator = " ||| "
    split_patterns = (
        re.compile(r"\s*(?:,|;|->|=>)\s+(?=(?:open|launch|visit|go to|search|click|type|press|scroll|wait|select|choose|filter|sort|fill|submit|download|upload|find|check|compare|summarize|write|copy|paste)\b)", re.I),
        re.compile(r"\s+(?:and then|then|after that|next|finally)\s+", re.I),
        re.compile(r"\s+and\s+(?=(?:open|launch|visit|go|search|click|type|press|scroll|wait|select|choose|filter|sort|fill|submit|download|upload|find|check|compare|summarize|write|copy|paste)\b)", re.I),
        re.compile(r"\s*(?:\u7136\u540e|\u63a5\u7740|\u4e4b\u540e|\u6700\u540e|\u518d)\s*"),
        re.compile(r"\s*(?:\u5e76\u4e14|\u5e76)\s*(?=(?:\u6253\u5f00|\u542f\u52a8|\u8bbf\u95ee|\u641c\u7d22|\u70b9\u51fb|\u8f93\u5165|\u6309|\u6eda\u52a8|\u7b49\u5f85|\u9009\u62e9|\u7b5b\u9009|\u6392\u5e8f|\u586b\u5199|\u63d0\u4ea4|\u4e0b\u8f7d|\u4e0a\u4f20|\u67e5\u627e|\u68c0\u67e5|\u6bd4\u8f83|\u603b\u7ed3|\u6574\u7406|\u5199|\u590d\u5236|\u7c98\u8d34))"),
        re.compile(r"\s*(?:然后|接着|之后|再|最后)\s*"),
        re.compile(r"\s*(?:并且|并)\s*(?=(?:打开|启动|访问|搜索|点击|输入|按|滚动|等待|选择|筛选|排序|填写|提交|下载|上传|查找|检查|比较))"),
    )
    for pattern in split_patterns:
        normalized = pattern.sub(separator, normalized)

    parts = [_clean_sub_goal_part(part) for part in normalized.split(separator)]
    parts = _contextualize_follow_up_parts(parts)
    unique_parts: list[str] = []
    for part in parts:
        if part and part not in unique_parts:
            unique_parts.append(part)
    return unique_parts[:12]


def _split_task_segments(task: str) -> list[str]:
    return _extract_task_sub_goals(task, None)


def _contextualize_follow_up_parts(parts: list[str]) -> list[str]:
    contextualized: list[str] = []
    previous_part: str | None = None
    active_app_context: str | None = None
    for raw_part in parts:
        part = _clean_sub_goal_part(raw_part)
        if not part:
            continue
        expanded_parts = _expand_wait_then_follow_up_parts(part, previous_part=previous_part)
        if len(expanded_parts) > 1:
            for expanded_part in expanded_parts:
                expanded_part = _contextualize_app_follow_up(
                    expanded_part,
                    app_name=active_app_context,
                    prefer_zh=_contains_cjk(previous_part or expanded_part),
                )
                contextualized.append(expanded_part)
                active_app_context = _update_active_app_context(expanded_part, active_app_context)
                previous_part = expanded_part
            continue
        normalized = part.strip().lower()
        if normalized in {"close", "close window", "close current window", "关闭", "关闭窗口", "关闭当前窗口"}:
            app_name = active_app_context or _extract_target_app_name(previous_part or "")
            if app_name:
                part = _build_close_follow_up_title(app_name, prefer_zh=_contains_cjk(previous_part or part))
        else:
            part = _contextualize_app_follow_up(
                part,
                app_name=active_app_context,
                prefer_zh=_contains_cjk(previous_part or part),
            )
        contextualized.append(part)
        active_app_context = _update_active_app_context(part, active_app_context)
        previous_part = part
    return contextualized


def _update_active_app_context(part: str, current_app: str | None) -> str | None:
    canonical_app_name = _extract_target_app_name(part)
    if not canonical_app_name:
        return current_app
    if canonical_app_name == "browser":
        return None
    return _extract_target_app_display_name(part) or canonical_app_name


def _contextualize_app_follow_up(part: str, *, app_name: str | None, prefer_zh: bool) -> str:
    if not app_name or app_name == "browser":
        return part
    if _extract_target_app_name(part) or _looks_like_open_target_url(part):
        return part
    if not _is_app_follow_up_operation(part):
        return part
    if prefer_zh or _contains_cjk(app_name):
        return f"打开{app_name}并{part}"
    return f"open {app_name} and {part}"


def _is_app_follow_up_operation(part: str) -> bool:
    stripped = _clean_sub_goal_part(part)
    if not stripped:
        return False
    operation_patterns = (
        r"^(?:search(?:\s+for)?|find)\s+.+$",
        r"^(?:click|open|select|choose|tap)\s+.+$",
        r"^(?:type|enter|write)\s+.+$",
        r"^(?:fill|set)\s+.+$",
        r"^(?:calculate|compute|evaluate)\s+.+$",
        r"^save(?:\s+(?:as|to))?\s+.+$",
        r"^press\s+.+$",
        r"^(?:搜索|查找|点击|打开|选择|输入|键入|写入|填写|在|按).+$",
    )
    return any(re.match(pattern, stripped, re.I) for pattern in operation_patterns)


def _extract_target_app_display_name(title: str) -> str | None:
    canonical = _extract_target_app_name(title)
    if canonical:
        zh_labels = {
            "calculator": "计算器",
            "notepad": "记事本",
            "explorer": "资源管理器",
            "browser": "浏览器",
            "excel": "Excel",
            "powerpoint": "PowerPoint",
            "word": "Word",
            "paint": "画图",
            "settings": "设置",
            "wechat": "微信",
            "dingtalk": "钉钉",
            "wps": "WPS",
            "vscode": "Visual Studio Code",
        }
        en_labels = {
            "calculator": "calculator",
            "notepad": "notepad",
            "explorer": "explorer",
            "browser": "browser",
            "excel": "excel",
            "powerpoint": "powerpoint",
            "word": "word",
            "paint": "paint",
            "settings": "settings",
            "wechat": "wechat",
            "dingtalk": "dingtalk",
            "wps": "wps",
            "vscode": "vscode",
        }
        if canonical in zh_labels:
            return zh_labels[canonical] if _contains_cjk(title) else en_labels[canonical]
    if match := re.match(
        r"^(?:打开|启动|open|launch)\s*(?:一个\s*|(?:an?|the)\s+)?"
        r"(?P<app>[\w\u4e00-\u9fff][\w\u4e00-\u9fff ._-]{0,78}?)"
        r"(?=\s*(?:并且|并|然后|再|and(?:\s+then)?|then|$))",
        title.strip(),
        re.I,
    ):
        app_name = _clean_app_name(match.group("app"))
        if app_name:
            return app_name
    return None


def _build_close_follow_up_title(app_name: str, *, prefer_zh: bool) -> str:
    zh_labels = {
        "calculator": "关闭计算器",
        "notepad": "关闭记事本",
        "explorer": "关闭资源管理器",
        "browser": "关闭浏览器",
        "excel": "关闭 Excel",
        "powerpoint": "关闭 PowerPoint",
        "word": "关闭 Word",
    }
    en_labels = {
        "calculator": "close calculator",
        "notepad": "close notepad",
        "explorer": "close explorer",
        "browser": "close browser",
        "excel": "close excel",
        "powerpoint": "close powerpoint",
        "word": "close word",
    }
    labels = zh_labels if prefer_zh else en_labels
    if app_name in labels:
        return labels[app_name]
    return f"关闭{app_name}" if prefer_zh else f"close {app_name}"


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", str(text or "")))


def _expand_wait_then_follow_up_parts(part: str, *, previous_part: str | None) -> list[str]:
    stripped = _clean_sub_goal_part(part)
    if not stripped:
        return []
    if re.match(
        r"^(?:\u7b49\u5f85|\u7b49|wait)\s*(?P<seconds>[0-9]+(?:\.[0-9]+)?)\s*(?:\u79d2|seconds?|s)?\s*$",
        stripped,
        re.I,
    ):
        return [stripped]
    match = re.match(
        r"^(?:\u7b49\u5f85|\u7b49)\s*(?P<seconds>[0-9]+(?:\.[0-9]+)?)\s*(?:\u79d2|s)?\s*(?P<follow>.+)$",
        stripped,
        re.I,
    ) or re.match(
        r"^wait\s*(?P<seconds>[0-9]+(?:\.[0-9]+)?)\s*(?:seconds?|s)?\s+(?P<follow>.+)$",
        stripped,
        re.I,
    )
    if not match:
        return [stripped]
    seconds = match.group("seconds")
    follow_up = _clean_sub_goal_part(match.group("follow"))
    if not follow_up:
        return [stripped]
    expanded = [f"等{seconds}秒" if _contains_cjk(stripped) else f"wait {seconds} seconds"]
    normalized_follow = follow_up.strip().lower()
    if normalized_follow in {"close", "close window", "close current window", "关闭", "关闭窗口", "关闭当前窗口"}:
        app_name = _extract_target_app_name(previous_part or "")
        if app_name:
            follow_up = _build_close_follow_up_title(app_name, prefer_zh=_contains_cjk(previous_part or stripped))
    expanded.append(follow_up)
    return expanded


def _infer_intent_risk(task: str) -> str:
    lowered = task.lower()
    high_terms = (
        "login",
        "sign in",
        "password",
        "checkout",
        "purchase",
        "pay",
        "submit",
        "delete",
        "remove",
        "install",
        "terminal",
        "shell",
        "\u767b\u5f55",
        "\u5bc6\u7801",
        "\u652f\u4ed8",
        "\u4e0b\u5355",
        "\u63d0\u4ea4",
        "\u5220\u9664",
        "\u5b89\u88c5",
        "\u7ec8\u7aef",
        "\u547d\u4ee4\u884c",
    )
    medium_terms = (
        "save",
        "download",
        "upload",
        "send",
        "bookmark",
        "\u4fdd\u5b58",
        "\u4e0b\u8f7d",
        "\u4e0a\u4f20",
        "\u53d1\u9001",
        "\u6536\u85cf",
        "\u8d2d\u4e70",
        "\u4e70",
    )
    if any(term in lowered for term in high_terms):
        return "high"
    if any(term in lowered for term in medium_terms):
        return "medium"
    return "low"


def _infer_task_constraints(task: str) -> list[str]:
    lowered = task.lower()
    constraints: list[str] = []
    if any(term in lowered for term in ("do not buy", "don't buy", "\u4e0d\u8981\u4e0b\u5355", "\u4e0d\u8981\u8d2d\u4e70")):
        constraints.append("Do not purchase or submit orders.")
    if any(term in lowered for term in ("summarize", "summary", "\u603b\u7ed3", "\u6458\u8981")):
        constraints.append("Preserve the user's requested summary format.")
    if any(term in lowered for term in ("compare", "\u6bd4\u8f83", "\u5bf9\u6bd4")):
        constraints.append("Compare candidates before choosing.")
    return constraints


def _infer_intent_capabilities(task: str, *, world_model: WorldModel | None = None) -> list[str]:
    lowered = task.lower()
    preferred: list[str] = []
    if _contains_any(
        lowered,
        (
            "browser",
            "website",
            "web",
            "search",
            "visit",
            "url",
            "\u6d4f\u89c8\u5668",
            "\u7f51\u9875",
            "\u7f51\u7ad9",
            "\u641c\u7d22",
            "\u67e5\u627e",
            "\u67e5\u8be2",
            "\u8bbf\u95ee",
            "\u8d44\u6599",
        ),
    ):
        preferred.append("browser_dom")
    if _contains_any(lowered, ("file", "folder", "download", "save", "\u6587\u4ef6", "\u6587\u4ef6\u5939", "\u4fdd\u5b58")):
        preferred.append("filesystem")
    if _contains_any(lowered, ("copy", "paste", "clipboard", "\u590d\u5236", "\u7c98\u8d34", "\u526a\u8d34\u677f")):
        preferred.append("clipboard")
    if _contains_any(lowered, ("excel", "powerpoint", "ppt", "word")):
        preferred.append("office_com")
    if _contains_any(lowered, ("notepad", "calculator", "explorer", "\u8bb0\u4e8b\u672c", "\u8ba1\u7b97\u5668", "\u8d44\u6e90\u7ba1\u7406\u5668")):
        preferred.append("windows_uia")
    if world_model is not None and world_model.active_app == "browser":
        preferred.append("browser_dom")
    preferred.append("desktop_gui")
    return _dedupe_strings(preferred)


def _merge_preferred_capabilities(primary: list[str], secondary: list[str]) -> list[str]:
    return _dedupe_strings([*primary, *secondary])


def _task_needs_clarification(task: str) -> bool:
    stripped = task.strip()
    if len(stripped) <= 2:
        return True
    lowered = stripped.lower()
    vague_phrases = (
        "do it",
        "handle it",
        "fix it",
        "continue",
        "\u5904\u7406\u4e00\u4e0b",
        "\u5f04\u4e00\u4e0b",
        "\u5e2e\u6211\u641e\u5b9a",
        "\u7ee7\u7eed",
    )
    if any(lowered == phrase for phrase in vague_phrases):
        return True
    missing_target_patterns = (
        r"^(?:open|search|find|click|type|write)\s*$",
        r"^(?:\u6253\u5f00|\u641c\u7d22|\u67e5\u627e|\u70b9\u51fb|\u8f93\u5165|\u5199)\s*$",
    )
    return any(re.match(pattern, stripped, re.I) for pattern in missing_target_patterns)


def _extract_research_goal(task: str) -> tuple[str | None, str | None]:
    stripped = task.strip()
    patterns = (
        re.compile(
            r"^(?:open\s+(?:the\s+)?browser\s+and\s+)?(?:search(?:\s+for)?|find|look\s+up)\s+"
            r"(?P<query>.+?)\s+(?:and\s+then|then|and)\s+"
            r"(?P<follow>(?:summarize|summarise|list|write|collect|extract|compare).+)$",
            re.I,
        ),
        re.compile(
            r"^(?:\u6253\u5f00\s*(?:\u6d4f\u89c8\u5668|edge|chrome|browser)\s*(?:\u5e76|\u7136\u540e)?)?"
            r"(?:\u641c\u7d22|\u641c\u4e00\u4e0b|\u67e5\u627e|\u67e5\u8be2)\s*"
            r"(?P<query>.+?)\s*(?:\u5e76\u4e14|\u5e76|\u7136\u540e|\u518d)\s*"
            r"(?P<follow>(?:\u603b\u7ed3|\u6574\u7406|\u5217\u51fa|\u5199|\u63d0\u53d6|\u5bf9\u6bd4|\u6bd4\u8f83).+)$"
        ),
    )
    for pattern in patterns:
        match = pattern.match(stripped)
        if not match:
            continue
        query = _clean_sub_goal_part(match.group("query"))
        follow = _clean_sub_goal_part(match.group("follow"))
        if query:
            return query, follow or None
    return None, None


def _looks_like_shopping_task(task: str) -> bool:
    lowered = task.lower()
    return _contains_any(
        lowered,
        (
            "shop",
            "shopping",
            "buy",
            "cart",
            "amazon",
            "taobao",
            "tmall",
            "jd",
            "\u8d2d\u7269",
            "\u7535\u5546",
            "\u5546\u54c1",
            "\u8d2d\u4e70",
            "\u4e70",
            "\u6311\u9009",
            "\u9ad8\u6027\u4ef7\u6bd4",
            "\u6dd8\u5b9d",
            "\u4eac\u4e1c",
            "\u5929\u732b",
        ),
    )


def _looks_like_web_research(task: str) -> bool:
    lowered = task.lower()
    return _contains_any(
        lowered,
        (
            "search",
            "find",
            "lookup",
            "research",
            "news",
            "\u641c\u7d22",
            "\u641c\u4e00\u4e0b",
            "\u67e5\u627e",
            "\u67e5\u8be2",
            "\u8d44\u6599",
            "\u65b0\u95fb",
        ),
    )


def _looks_like_cross_app_task(task: str) -> bool:
    lowered = task.lower()
    app_hits = 0
    for marker in (
        "browser",
        "notepad",
        "calculator",
        "explorer",
        "excel",
        "word",
        "\u6d4f\u89c8\u5668",
        "\u8bb0\u4e8b\u672c",
        "\u8ba1\u7b97\u5668",
        "\u6587\u4ef6",
    ):
        if marker in lowered:
            app_hits += 1
    return app_hits >= 2 or (
        _contains_multi_step_markers(task)
        and _contains_any(lowered, ("copy", "paste", "write", "\u590d\u5236", "\u7c98\u8d34", "\u5199\u5230"))
    )


def _contains_multi_step_markers(task: str) -> bool:
    lowered = task.lower()
    return _contains_any(
        lowered,
        (
            "and then",
            "then",
            "after that",
            "finally",
            " and ",
            "\u7136\u540e",
            "\u63a5\u7740",
            "\u4e4b\u540e",
            "\u6700\u540e",
            "\u5e76",
            "\u518d",
        ),
    )


def _extract_named_entities(task: str) -> list[str]:
    cleaned = _clean_sub_goal_part(task)
    if not cleaned:
        return []
    url_match = re.search(r"https?://[^\s]+|(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/[^\s]*)?", cleaned, re.I)
    if url_match:
        return [url_match.group(0).rstrip(".,;)")]
    research_query, _follow = _extract_research_goal(cleaned)
    if research_query:
        return [research_query]
    search_match = re.search(r"(?:search(?:\s+for)?|find|lookup|\u641c\u7d22|\u67e5\u627e|\u67e5\u8be2)\s*(?P<query>.+)$", cleaned, re.I)
    if search_match:
        return [_clean_sub_goal_part(search_match.group("query"))]
    return [cleaned[:120]]


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term and term in text for term in terms)


def _keyword_matches_text(text: str, keyword: str) -> bool:
    candidate = str(keyword or "").strip().lower()
    if not candidate:
        return False
    if candidate.isascii() and re.search(r"[a-z0-9]", candidate):
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(candidate)}(?![a-z0-9])", text, re.I))
    return candidate in text


def _looks_like_open_target_url(value: str) -> bool:
    cleaned = str(value or "").strip()
    if not cleaned:
        return False
    return bool(
        re.match(
            r"^(?:https?://|www\.)[^\s]+$|^(?:[a-z0-9-]+\.)+[a-z0-9-]+(?:/[^\s]*)?$",
            cleaned,
            re.I,
        )
    )


def _ensure_browser_target_url(value: str) -> str:
    cleaned = _clean_tail_text(value)
    if re.match(r"^https?://", cleaned, re.I):
        return cleaned
    return f"https://{cleaned}"


def _dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = " ".join(str(value or "").split()).strip()
        lowered = cleaned.lower()
        if not cleaned or lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(cleaned)
    return deduped


def _task_requires_vlm_reasoning(
    task: str,
    history: list[str],
    browser_command: WebCommand | None,
) -> bool:
    if history:
        return True
    if browser_command is not None and browser_command.follow_up_steps:
        return True
    lowered = task.strip().lower()
    if not lowered:
        return False
    app_markers = 0
    for marker in ("browser", "edge", "chrome", "firefox", "notepad", "calculator", "calc", "explorer", "file explorer"):
        if marker in lowered:
            app_markers += 1
    if app_markers >= 2:
        return True
    sub_goals = _extract_task_sub_goals(task, browser_command)
    if len(sub_goals) >= 3:
        return True
    if len(sub_goals) >= 2 and any(
        keyword in lowered
        for keyword in (
            "switch",
            "focus",
            "window",
            "minimize",
            "close",
            "copy",
            "paste",
            "record",
            "整理",
            "切换",
            "窗口",
            "最小化",
            "关闭",
        )
    ):
        return True
    return False


def _should_use_browser_shortcut(
    task: str,
    history: list[str],
    browser_command: WebCommand | None,
) -> bool:
    if history or browser_command is None:
        return False
    if browser_command.follow_up_steps:
        return False
    return not _task_requires_vlm_reasoning(task, history, browser_command)


def _describe_browser_initial_step(command: WebCommand) -> str | None:
    if command.intent == "launch":
        return "open the browser"
    if command.intent == "open_url" and command.target:
        return f"open {command.target}"
    if command.intent == "search" and command.target:
        return f"search for {command.target}"
    if command.intent == "shopping_search" and command.shopping_query:
        return f"open shopping results for {command.shopping_query}"
    return command.follow_up or command.target


def _clean_sub_goal_part(text: str) -> str:
    cleaned = text.strip().strip("\"' ")
    cleaned = cleaned.strip(",;:，；。")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _build_subgoal_success_condition(title: str, *, world_model: WorldModel | None = None) -> str:
    normalized = title.strip()
    lowered = normalized.lower()
    if any(token in lowered for token in ("save", "download", "upload", "export", "\u4fdd\u5b58", "\u4e0b\u8f7d", "\u4e0a\u4f20")):
        return f"Verify that the requested file or artifact was saved for: {normalized}"
    if any(token in lowered for token in ("calculate", "compute", "evaluate", "\u8ba1\u7b97")):
        return f"Verify that the requested calculation or transformation is visible for: {normalized}"
    if any(token in lowered for token in ("type", "fill", "enter", "input", "paste", "\u8f93\u5165", "\u586b\u5199", "\u7c98\u8d34")):
        return f"Verify that the requested content was entered for: {normalized}"
    if any(token in lowered for token in ("click", "select", "choose", "\u70b9\u51fb", "\u9009\u62e9")):
        return f"Verify that the requested control changed state after: {normalized}"
    if any(token in lowered for token in ("open ", "launch ", "visit ", "\u6253\u5f00", "\u542f\u52a8", "\u8bbf\u95ee")):
        return f"Verify that the requested destination or application is open: {normalized}"
    if any(token in lowered for token in ("search", "find", "lookup", "\u641c\u7d22", "\u67e5\u627e", "\u67e5\u8be2")):
        return f"Verify that visible results or page content correspond to: {normalized}"
    if any(token in lowered for token in ("type", "fill", "enter", "\u8f93\u5165", "\u586b\u5199")):
        return f"Verify that the requested content was entered for: {normalized}"
    if any(token in lowered for token in ("click", "select", "choose", "\u70b9\u51fb", "\u9009\u62e9")):
        return f"Verify that the requested control changed state after: {normalized}"
    if any(token in lowered for token in ("open ", "launch ", "visit ", "打开", "启动", "访问")):
        return f"Verify that the requested destination or application is open: {normalized}"
    if any(token in lowered for token in ("search", "find", "lookup", "搜索", "查找", "检索")):
        return f"Verify that visible results or page content correspond to: {normalized}"
    if any(token in lowered for token in ("type", "fill", "enter", "输入", "填写")):
        return f"Verify that the requested content was entered for: {normalized}"
    if any(token in lowered for token in ("click", "select", "choose", "点击", "选择")):
        return f"Verify that the requested control changed state after: {normalized}"
    if world_model is not None and world_model.active_window_title:
        return f"Verify that progress is visible in {world_model.active_window_title} after: {normalized}"
    return f"Verify that the subgoal is completed: {normalized}"


def _infer_goal_type(title: str) -> str:
    lowered = title.strip().lower()
    if any(keyword in lowered for keyword in ("save", "download", "upload", "export", "bookmark", "\u4fdd\u5b58", "\u4e0b\u8f7d", "\u4e0a\u4f20")):
        return "save"
    if any(keyword in lowered for keyword in ("calculate", "compute", "evaluate", "\u8ba1\u7b97")):
        return "transform"
    if any(keyword in lowered for keyword in ("type", "fill", "enter", "input", "paste", "\u8f93\u5165", "\u586b\u5199", "\u7c98\u8d34")):
        return "fill"
    if any(keyword in lowered for keyword in ("click", "select", "choose", "submit", "\u70b9\u51fb", "\u9009\u62e9", "\u63d0\u4ea4")):
        return "confirm"
    supplemental_mapping = (
        ("navigate", ("open ", "launch ", "visit ", "go to", "navigate", "search", "\u641c\u7d22", "\u6253\u5f00", "\u542f\u52a8", "\u8bbf\u95ee")),
        ("locate", ("find", "locate", "look for", "\u67e5\u627e", "\u5b9a\u4f4d")),
        ("read", ("read", "review", "inspect", "look at", "\u9605\u8bfb", "\u67e5\u770b", "\u8d44\u6599")),
        ("extract", ("extract", "collect", "capture", "record", "summarize", "\u63d0\u53d6", "\u6536\u96c6", "\u8bb0\u5f55", "\u603b\u7ed3", "\u6458\u8981")),
        ("transform", ("transform", "edit", "clean", "sort", "filter", "compare", "calculate", "compute", "evaluate", "\u6574\u7406", "\u7f16\u8f91", "\u6392\u5e8f", "\u7b5b\u9009", "\u6bd4\u8f83", "\u8ba1\u7b97")),
        ("fill", ("type", "fill", "enter", "input", "paste", "\u8f93\u5165", "\u586b\u5199", "\u7c98\u8d34", "\u5199")),
        ("confirm", ("click", "select", "choose", "confirm", "approve", "submit", "\u70b9\u51fb", "\u9009\u62e9", "\u786e\u8ba4", "\u63d0\u4ea4")),
        ("transfer", ("copy", "move", "send", "share", "\u590d\u5236", "\u79fb\u52a8", "\u53d1\u9001")),
        ("save", ("save", "download", "upload", "export", "bookmark", "\u6536\u85cf", "\u4fdd\u5b58", "\u4e0b\u8f7d", "\u4e0a\u4f20", "\u5bfc\u51fa")),
    )
    for goal_type, keywords in supplemental_mapping:
        if any(keyword in lowered for keyword in keywords):
            return goal_type
    mapping = (
        ("navigate", ("open ", "launch ", "visit ", "go to", "navigate", "search", "搜索", "打开", "启动", "访问")),
        ("locate", ("find", "locate", "look for", "查找", "定位")),
        ("read", ("read", "review", "inspect", "look at", "阅读", "查看")),
        ("extract", ("extract", "collect", "capture", "record", "summarize", "提取", "收集", "记录", "总结")),
        ("transform", ("transform", "edit", "clean", "sort", "filter", "compare", "calculate", "compute", "evaluate", "整理", "编辑", "排序", "筛选", "比较", "计算")),
        ("fill", ("type", "fill", "enter", "input", "paste", "输入", "填写", "粘贴")),
        ("confirm", ("click", "select", "choose", "confirm", "approve", "submit", "点击", "选择", "确认", "提交")),
        ("transfer", ("copy", "move", "send", "share", "复制", "移动", "发送")),
        ("save", ("save", "download", "upload", "export", "bookmark", "收藏", "保存", "下载", "上传", "导出")),
    )
    for goal_type, keywords in mapping:
        if any(keyword in lowered for keyword in keywords):
            return goal_type
    return "handoff"


def _build_fallback_goal(title: str, goal_type: str) -> str:
    if goal_type == "navigate":
        return f"Re-open or refocus the target destination for: {title}"
    if goal_type in {"fill", "confirm"}:
        return f"Relocate the target control before retrying: {title}"
    if goal_type in {"extract", "read"}:
        return f"Recover the relevant page, window, or selection for: {title}"
    if goal_type == "save":
        return f"Verify the target path and save location for: {title}"
    return f"Re-establish the prerequisites for: {title}"


def _infer_completion_evidence(
    title: str,
    *,
    goal_type: str,
    world_model: WorldModel | None = None,
) -> dict[str, str]:
    lowered = title.strip().lower()
    if re.match(r"^(?:\u7b49\u5f85|\u7b49|wait)\s*[0-9]+(?:\.[0-9]+)?\s*(?:\u79d2|seconds?|s)?\s*$", lowered, re.I):
        return {"kind": "action_executed", "detail": f"The wait action finished for: {title}"}
    if goal_type == "navigate":
        if app_name := _extract_target_app_name(title):
            return {"kind": "active_app_is", "value": app_name, "detail": f"The target application becomes active for: {title}"}
        if browser_target := _extract_browser_target(title):
            evidence_kind = "browser_text_contains" if any(token in lowered for token in ("search", "搜索")) else "browser_url_contains"
            return {"kind": evidence_kind, "value": browser_target, "detail": f"The browser reflects the requested destination for: {title}"}
        if any(token in lowered for token in ("shopping", "results", "search", "browser", "website", "web", "网页", "网站", "搜索", "购物")):
            return {"kind": "browser_available", "detail": f"A browser destination is visible after: {title}"}
        if any(token in lowered for token in ("browser", "website", "web", "search", "visit", "网页", "网站", "搜索", "访问")):
            return {"kind": "browser_available", "detail": f"A browser destination is visible after: {title}"}
        return {"kind": "window_contains", "value": _clean_sub_goal_part(title), "detail": f"The target window is visible for: {title}"}
    if goal_type in {"read", "extract", "transform"}:
        if content_hint := _extract_content_hint(title):
            return {"kind": "fact_contains", "value": content_hint, "detail": f"Structured facts should confirm visible progress for: {title}"}
        return {"kind": "fact_contains", "value": title, "detail": f"Structured facts should confirm visible progress for: {title}"}
    if goal_type == "fill":
        if content_hint := _extract_content_hint(title):
            return {"kind": "fact_contains", "value": content_hint, "detail": f"The intended input should be visible for: {title}"}
        return {"kind": "clipboard_or_input_changed", "detail": f"The intended input is visible for: {title}"}
    if goal_type == "save":
        return {"kind": "file_observation", "detail": f"A file or saved artifact is observed for: {title}"}
    if goal_type == "confirm":
        return {"kind": "state_change", "detail": f"The target control or page state changes for: {title}"}
    if world_model is not None and world_model.active_window_title:
        return {"kind": "window_contains", "value": world_model.active_window_title, "detail": f"Visible progress persists in {world_model.active_window_title}."}
    return {"kind": "state_change", "detail": f"Visible state changes confirm: {title}"}


def _build_completion_summary(task: str, subgoals: list[Subgoal]) -> str:
    if not subgoals:
        return f"Complete the task: {task.strip()}"
    joined = "; ".join(f"{item.id}: {item.success_condition}" for item in subgoals)
    return f"Task complete when every subgoal satisfies its success condition. {joined}"


def _extract_target_app_name(title: str) -> str | None:
    lowered = title.strip().lower()
    app_aliases = {
        "notepad": ("notepad", "记事本"),
        "calculator": ("calculator", "calc", "计算器"),
        "explorer": ("explorer", "file explorer", "资源管理器"),
        "browser": ("browser", "edge", "chrome", "firefox", "浏览器"),
        "vscode": ("visual studio code", "vscode", "cursor"),
        "excel": ("excel",),
        "powerpoint": ("powerpoint", "ppt"),
        "word": ("word",),
        "paint": ("paint", "mspaint", "画图"),
        "settings": ("settings", "设置"),
        "wechat": ("wechat", "weixin", "微信"),
        "dingtalk": ("dingtalk", "钉钉"),
        "wps": ("wps",),
    }
    for app_name, keywords in app_aliases.items():
        if any(_keyword_matches_text(lowered, keyword) for keyword in keywords):
            return app_name
    if match := re.match(
        r"^(?:打开|启动|open|launch)\s*(?:一个\s*|(?:an?|the)\s+)?"
        r"(?P<app>[\w\u4e00-\u9fff][\w\u4e00-\u9fff ._-]{0,78}?)"
        r"(?=\s*(?:并且|并|然后|再|and(?:\s+then)?|then|$))",
        title.strip(),
        re.I,
    ):
        app_name = _clean_app_name(match.group("app"))
        if _is_generic_desktop_app_name(app_name):
            return app_name
    if match := re.match(
        r"^(?:关闭|close)\s*(?:(?:当前|current)\s*)?"
        r"(?P<app>[\w\u4e00-\u9fff][\w\u4e00-\u9fff ._-]{0,78}?)(?:\s*(?:窗口|window))?$",
        title.strip(),
        re.I,
    ):
        app_name = _clean_app_name(match.group("app"))
        if _is_generic_desktop_app_name(app_name):
            return app_name
    return None


def _extract_browser_target(title: str) -> str | None:
    stripped = title.strip()
    if match := re.search(r"https?://[^\s]+", stripped, re.I):
        return match.group(0).rstrip(".,;)")
    if match := re.search(r"(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/[^\s]*)?", stripped, re.I):
        return match.group(0).rstrip(".,;)")
    if match := re.search(r"(?:search\s+for|\u641c\u7d22|\u67e5\u627e|\u67e5\u8be2)\s+(?P<query>.+)$", stripped, re.I):
        query = _clean_sub_goal_part(match.group("query"))
        return query.split()[0] if query else None
    if match := re.search(r"(?:search\s+for|搜索)\s+(?P<query>.+)$", stripped, re.I):
        query = _clean_sub_goal_part(match.group("query"))
        return query.split()[0] if query else None
    return None


def _extract_content_hint(title: str) -> str | None:
    stripped = title.strip()
    patterns = (
        re.compile(r"^(?:type|fill|enter|input|paste|calculate|compute|evaluate)\s+(?P<content>.+)$", re.I),
        re.compile(r"^.*(?:type|fill|enter|input|paste|calculate|compute|evaluate)\s+(?P<content>.+)$", re.I),
        re.compile(r"^(?:\u8f93\u5165|\u586b\u5199|\u7c98\u8d34|\u8ba1\u7b97|\u5199)\s*(?P<content>.+)$"),
        re.compile(r"^(?:search\s+for|find|look\s+for|\u641c\u7d22|\u67e5\u627e|\u67e5\u8be2)\s*(?P<content>.+)$", re.I),
        re.compile(r"^(?:输入|填写|粘贴|计算)\s*(?P<content>.+)$"),
        re.compile(r"^(?:search\s+for|find|look\s+for)\s+(?P<content>.+)$", re.I),
    )
    for pattern in patterns:
        match = pattern.match(stripped)
        if not match:
            continue
        content = _clean_sub_goal_part(match.group("content"))
        if content:
            return content[:120]
    return None


def _infer_capability_preference(title: str, *, world_model: WorldModel | None = None) -> str | None:
    lowered = title.strip().lower()
    target_app = _extract_target_app_name(title)
    if target_app and target_app != "browser":
        if target_app in {"excel", "powerpoint", "word"}:
            return "office_com"
        return "windows_uia"
    if any(token in lowered for token in ("browser", "website", "web", "search", "visit", "\u6d4f\u89c8\u5668", "\u7f51\u9875", "\u7f51\u7ad9", "\u641c\u7d22", "\u67e5\u627e", "\u67e5\u8be2", "\u8bbf\u95ee", "\u8d44\u6599")):
        return "browser_dom"
    if any(token in lowered for token in ("copy", "paste", "clipboard", "\u590d\u5236", "\u7c98\u8d34", "\u526a\u8d34\u677f")):
        return "clipboard"
    if any(token in lowered for token in ("terminal", "shell", "python env", "venv", "\u7ec8\u7aef", "\u547d\u4ee4\u884c")):
        return "guarded_shell_recipe"
    if any(token in lowered for token in ("browser", "website", "web", "search", "visit", "网页", "网站", "搜索", "访问")):
        return "browser_dom"
    if any(token in lowered for token in ("copy", "paste", "clipboard", "复制", "粘贴")):
        return "clipboard"
    if any(token in lowered for token in ("excel", "powerpoint", "word", "spreadsheet", "slide", "ppt")):
        return "office_com"
    if any(token in lowered for token in ("terminal", "shell", "python env", "venv", "命令行", "终端")):
        return "guarded_shell_recipe"
    if world_model is not None and world_model.active_app == "browser":
        return "browser_dom"
    return None


def _infer_subgoal_risk(title: str) -> str:
    lowered = title.strip().lower()
    if any(
        token in lowered
        for token in (
            "\u767b\u5f55",
            "\u5bc6\u7801",
            "\u8d2d\u7269\u8f66",
            "\u4e0b\u5355",
            "\u652f\u4ed8",
            "\u63d0\u4ea4",
            "\u53d1\u9001",
            "\u5220\u9664",
            "\u5b89\u88c5",
        )
    ):
        return "high"
    if any(token in lowered for token in ("\u4fdd\u5b58", "\u4e0b\u8f7d", "\u6536\u85cf")):
        return "medium"
    if any(
        token in lowered
        for token in (
            "login",
            "sign in",
            "password",
            "cart",
            "checkout",
            "pay",
            "submit",
            "send",
            "delete",
            "remove",
            "install",
            "登录",
            "密码",
            "购物车",
            "下单",
            "支付",
            "提交",
            "发送",
            "删除",
            "安装",
        )
    ):
        return "high"
    if any(token in lowered for token in ("save", "download", "bookmark", "保存", "下载", "收藏")):
        return "medium"
    return "low"


class _PooledRequests:
    """Proxy that routes ``get``/``post`` through a keep-alive session.

    All other attribute lookups (``RequestException``, ``adapters``, ...) fall
    through to the underlying :mod:`requests` module, so existing call sites that
    reference ``requests.RequestException`` keep working unchanged. Reusing a
    pooled session avoids opening a fresh TCP/TLS connection on every LLM
    round-trip, which is the dominant per-step latency for remote endpoints.
    """

    __slots__ = ("_module", "_session")

    def __init__(self, module, session):
        self._module = module
        self._session = session

    def get(self, *args, **kwargs):
        return self._session.get(*args, **kwargs)

    def post(self, *args, **kwargs):
        return self._session.post(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._module, name)


_POOLED_REQUESTS: _PooledRequests | None = None
_POOLED_REQUESTS_LOCK = threading.Lock()


def _import_requests():
    global _POOLED_REQUESTS
    if _POOLED_REQUESTS is not None:
        return _POOLED_REQUESTS
    try:
        import requests
    except ModuleNotFoundError as exc:
        raise PlannerError(
            "VLMPlanner requires the requests package. "
            "Run `python -m pip install requests` or install from requirements.txt."
        ) from exc
    with _POOLED_REQUESTS_LOCK:
        if _POOLED_REQUESTS is None:
            session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=4,
                pool_maxsize=8,
                max_retries=0,
            )
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            _POOLED_REQUESTS = _PooledRequests(requests, session)
    return _POOLED_REQUESTS


def _normalize_api_base_url(base_url: str) -> str:
    raw = (base_url or "").strip()
    if not raw:
        raw = "http://127.0.0.1:1234/v1"
    if "://" not in raw:
        raw = f"http://{raw}"

    parsed = urlsplit(raw)
    path = parsed.path.rstrip("/")

    if path.endswith("/chat/completions"):
        path = path[: -len("/chat/completions")]
    elif path.endswith("/models"):
        path = path[: -len("/models")]

    if not path:
        path = "/v1"
    elif path != "/v1" and not path.endswith("/v1"):
        path = f"{path}/v1"

    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _needs_model_discovery(model_name: str | None) -> bool:
    return not (model_name or "").strip() or (model_name or "").strip().lower() in {"auto", "first"}


def _pick_model_name(configured_model: str | None, available_models: list[dict]) -> str:
    available_ids = [str(item.get("id", "")).strip() for item in available_models if str(item.get("id", "")).strip()]
    if not available_ids:
        raise PlannerError("No model identifiers were returned by /v1/models.")

    configured = (configured_model or "").strip()
    if _needs_model_discovery(configured):
        return available_ids[0]

    if configured in available_ids:
        return configured

    raise PlannerError(
        f"The configured model `{configured}` was not returned by /v1/models. "
        f"Available models: {', '.join(available_ids[:8])}"
    )


def _normalize_structured_output_mode(mode: str | None) -> str:
    normalized = (mode or "auto").strip().lower()
    if normalized in {"off", "none", "false"}:
        return "off"
    if normalized == "json_object":
        return "json_object"
    if normalized in {"auto", "json_schema"}:
        return "json_schema"
    return "off"


def _build_vlm_payload(
    *,
    model_name: str,
    task: str,
    history_text: str,
    decomposition_text: str,
    image_b64: str,
    browser_context: str | None,
    environment_context: str | None,
    response_format_mode: str,
) -> dict:
    user_text = (
        f"Task: {task}\n"
        f"Recent execution memory:\n{history_text}\n"
        f"Task decomposition hints:\n{decomposition_text}\n"
        + (f"Browser context:\n{browser_context}\n" if browser_context else "")
        + (f"Desktop environment:\n{environment_context}\n" if environment_context else "")
        + "Use the screenshot and execution memory to choose the next unmet sub-goal.\n"
        + "Keep actions focused on the current sub-goal, explain it with current_focus/reasoning when helpful, "
        + "and place unfinished future work in remaining_steps.\n"
        + "Return the next action plan as JSON."
    )
    payload = {
        "model": model_name,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_b64}",
                        },
                    },
                ],
            },
        ],
    }
    response_format = _build_response_format(response_format_mode)
    if response_format is not None:
        payload["response_format"] = response_format
    return payload


def _build_response_format(mode: str) -> dict | None:
    if mode == "off":
        return None
    if mode == "json_object":
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "desktop_agent_plan",
            "schema": _planner_json_schema(),
        },
    }


def _planner_json_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "status_summary": {"type": "string"},
            "done": {"type": "boolean"},
            "current_focus": {"type": "string"},
            "reasoning": {"type": "string"},
            "remaining_steps": {
                "type": "array",
                "items": {"type": "string"},
            },
            "actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "app": {"type": "string"},
                        "keys": {"type": "array", "items": {"type": "string"}},
                        "key": {"type": "string"},
                        "text": {"type": "string"},
                        "selector": {"type": "string"},
                        "title": {"type": "string"},
                        "x": {"type": "integer"},
                        "y": {"type": "integer"},
                        "width": {"type": "integer"},
                        "height": {"type": "integer"},
                        "end_x": {"type": "integer"},
                        "end_y": {"type": "integer"},
                        "relative_x": {"type": "number"},
                        "relative_y": {"type": "number"},
                        "button": {"type": "string"},
                        "clicks": {"type": "integer"},
                        "seconds": {"type": "number"},
                        "amount": {"type": "integer"},
                        "risk_level": {"type": "string"},
                        "expected_evidence": {
                            "type": "array",
                            "items": {"type": "object"},
                        },
                        "target_scope": {"type": "string"},
                        "recipe": {"type": "string"},
                    },
                    "required": ["type"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["status_summary", "done", "actions"],
        "additionalProperties": False,
    }


def _build_request_headers(api_key: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _build_connection_hint(api_base: str, exc: Exception) -> str:
    return (
        f"Could not connect to the OpenAI-compatible server at {api_base}. "
        "If you are using LM Studio, start the local server first and make sure the base URL "
        "matches the server port. Original error: "
        f"{exc}"
    )


def _build_environment_context(environment: DesktopEnvironment | None) -> str | None:
    if environment is None:
        return None

    lines = [f"Platform: {environment.platform}"]
    lines.append(
        "Virtual desktop bounds: "
        f"{environment.virtual_bounds.left},{environment.virtual_bounds.top} "
        f"to {environment.virtual_bounds.right},{environment.virtual_bounds.bottom}"
    )
    if environment.current_monitor is not None:
        monitor = environment.current_monitor
        lines.append(
            f"Current monitor: {monitor.device_name} "
            f"work area {monitor.work_area.left},{monitor.work_area.top} "
            f"{monitor.work_area.width}x{monitor.work_area.height}"
        )
    if environment.taskbar is not None:
        lines.append(
            f"Taskbar: position={environment.taskbar.position or 'unknown'}, "
            f"auto_hide={'yes' if environment.taskbar.auto_hide else 'no'}, "
            f"occupies_work_area={'yes' if environment.taskbar.occupies_work_area else 'no'}"
        )
    lines.append(f"DPI scale: {environment.dpi_scale}")
    if environment.foreground_window is not None:
        foreground = environment.foreground_window
        title = foreground.title or "<untitled>"
        rect = foreground.rect
        rect_text = (
            f"{rect.left},{rect.top} {rect.width}x{rect.height}"
            if rect is not None
            else "unknown"
        )
        lines.append(
            f"Foreground window: {title}; minimized={'yes' if foreground.is_minimized else 'no'}; "
            f"maximized={'yes' if foreground.is_maximized else 'no'}; rect={rect_text}"
        )
    if environment.visible_windows:
        window_titles = [item.title for item in environment.visible_windows if item.title][:8]
        if window_titles:
            lines.append("Visible windows: " + ", ".join(window_titles))
    lines.append(
        "Planning policy: prefer reusing or focusing an existing target window, minimize unrelated windows before closing them, "
        "dismiss only obvious blockers, avoid assuming the taskbar or viewport consumes the full screenshot height, "
        "and prefer relative_click inside a known target window over fragile full-screen absolute click coordinates."
    )
    return "\n".join(lines)


def _looks_like_structured_output_rejection(body_text: str) -> bool:
    lowered = body_text.lower()
    phrases = (
        "response_format",
        "json_schema",
        "json_object",
        "structured output",
        "unsupported",
        "schema",
    )
    return any(phrase in lowered for phrase in phrases)


def _extract_message_content(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise PlannerError("Planner response contains no choices.")
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "\n".join(parts)
    raise PlannerError("Unsupported message content format.")


def _extract_json(text: str) -> dict:
    stripped = text.strip()
    if not stripped:
        raise PlannerError("Empty planner response.")
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", stripped, flags=re.S)
    if fenced:
        return json.loads(fenced.group(1))
    brace = _find_braced_object(stripped)
    if brace:
        return json.loads(brace)
    raise PlannerError("Unable to parse planner JSON output.")


def _find_braced_object(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]
