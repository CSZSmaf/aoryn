from __future__ import annotations

import re

from desktop_agent.actions import Action
from desktop_agent.capabilities import CapabilityAdapter
from desktop_agent.drivers import AppDriver
from desktop_agent.workflow import ObservedFact, StepProposal, Subgoal, WorldModel


class NotepadDriver(AppDriver):
    name = "notepad"

    def matches(self, world_model: WorldModel) -> bool:
        title = _normalize(world_model.active_window_title)
        app = _normalize(world_model.active_app)
        return app == "notepad" or "notepad" in title or "\u8bb0\u4e8b\u672c" in title

    def describe(self, world_model: WorldModel) -> list[ObservedFact]:
        title = str(world_model.active_window_title or "").strip()
        return [ObservedFact(source=self.name, key="notepad_window", value=title)] if title else []

    def preferred_capabilities(self) -> list[str]:
        return ["notepad_text", "clipboard", "windows_uia", "desktop_gui"]


class NotepadTextCapability(CapabilityAdapter):
    name = "notepad_text"

    def can_handle(self, subgoal: Subgoal, world_model: WorldModel) -> float:
        if not NotepadDriver().matches(world_model):
            return 0.0
        text = _extract_requested_text(subgoal)
        return 0.9 if text else 0.45

    def plan_step(self, *, subgoal, world_model, execution_state, config, planner):
        text = _extract_requested_text(subgoal)
        if not text:
            return None
        return StepProposal(
            intent="Type text into Notepad using the Notepad plugin.",
            actions=[Action.from_dict({"type": "type", "text": text})],
            capability=self.name,
            risk_level="low",
            completes_subgoal=True,
        )


def register_plugin(context) -> None:
    context.register_driver(NotepadDriver())
    context.register_capability(NotepadTextCapability())


def _extract_requested_text(subgoal: Subgoal) -> str | None:
    text = str(subgoal.goal or subgoal.title or "").strip()
    patterns = [
        r"(?:write|type|insert|enter)\s+(?P<text>.+)",
        r"(?:input|add)\s+(?P<text>.+)",
        r"(?:\u8f93\u5165|\u5199\u5165|\u586b\u5165|\u8bb0\u5f55)\s*(?P<text>.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            candidate = match.group("text").strip().strip("'\"")
            return candidate[:200] if candidate else None
    return None


def _normalize(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())
