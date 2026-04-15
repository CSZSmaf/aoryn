import shutil
from pathlib import Path
from uuid import uuid4

from desktop_agent.actions import Action, PlanResult
from desktop_agent.config import AgentConfig
from desktop_agent.controller import DesktopAgent
from desktop_agent.history import load_run_details
from desktop_agent.human_verification import BrowserSnapshot, detect_human_verification
from desktop_agent.logger import RunLogger
from desktop_agent.perception import ScreenInfo
from desktop_agent.safety import ActionGuard


def test_detect_human_verification_recognizes_google_sorry_page():
    signal = detect_human_verification(
        BrowserSnapshot(
            url="https://www.google.com/sorry/index?continue=/search",
            text="Our systems have detected unusual traffic from your computer network.",
        )
    )

    assert signal is not None
    assert signal.kind == "google_unusual_traffic"
    assert signal.requires_human is True


class _PlannerStub:
    def plan(self, task, screenshot_path, history, environment=None):
        return PlanResult(
            status_summary="Search the web for OpenAI desktop agent.",
            done=True,
            actions=[Action.from_dict({"type": "browser_search", "text": "OpenAI desktop agent"})],
        )


class _ExecutorStub:
    def __init__(self) -> None:
        self.has_executed = False

    def execute_many(self, actions, pause_after_action):
        self.has_executed = True

    def browser_snapshot(self):
        if not self.has_executed:
            return None
        return {
            "url": "https://www.google.com/sorry/index?continue=/search",
            "title": "Google Search",
            "text": "Our systems have detected unusual traffic from your computer network.",
        }


class _PerceptionStub:
    def capture(self, output_path: Path) -> ScreenInfo:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-png")
        return ScreenInfo(width=1280, height=720)


def test_desktop_agent_pauses_for_human_verification():
    scratch_root = Path("test_artifacts") / f"human_verification_{uuid4().hex}"
    run_root = scratch_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)

    try:
        config = AgentConfig(dry_run=False, run_root=run_root)
        agent = DesktopAgent(
            config=config,
            planner=_PlannerStub(),
            executor=_ExecutorStub(),
            perception=_PerceptionStub(),
            logger=RunLogger(run_root),
            guard=ActionGuard(config),
        )

        result = agent.run("search for OpenAI desktop agent")

        assert result.completed is False
        assert result.error is None
        assert result.requires_human is True
        assert result.interruption_kind == "google_unusual_traffic"

        details = load_run_details(run_root, result.run_dir.name)
        assert details is not None
        assert details["requires_human"] is True
        assert details["interruption_kind"] == "google_unusual_traffic"
        assert details["timeline"][0]["challenge"]["kind"] == "google_unusual_traffic"
        assert details["timeline"][0]["executed_actions"][0]["type"] == "browser_search"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)
