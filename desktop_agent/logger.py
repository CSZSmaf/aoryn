from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from desktop_agent.actions import Action, PlanResult


@dataclass(slots=True)
class RunLogger:
    run_root: Path

    def create_run_dir(self, task: str) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = _slugify(task)[:36]
        run_dir = self.run_root / f"{timestamp}_{slug}"
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def log_step(
        self,
        run_dir: Path,
        step_index: int,
        task: str,
        screenshot_path: Path,
        plan: PlanResult,
        executed_actions: list[Action],
        error: str | None = None,
        challenge: dict | None = None,
        captured_at: float | None = None,
        environment: dict | None = None,
        state: dict[str, Any] | None = None,
        world_model: dict[str, Any] | None = None,
        step_proposal: dict[str, Any] | None = None,
        verification: dict[str, Any] | None = None,
    ) -> Path:
        payload = {
            "step": step_index,
            "task": task,
            "screenshot": screenshot_path.name,
            "captured_at": captured_at if captured_at is not None else time.time(),
            "environment": environment,
            "plan": plan.to_dict(),
            "executed_actions": [item.to_dict() for item in executed_actions],
            "error": error,
            "challenge": challenge,
            "state": state,
            "world_model": world_model,
            "step_proposal": step_proposal,
            "verification": verification,
        }
        output = run_dir / f"step_{step_index:02d}.json"
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output

    def log_execution_state(
        self,
        *,
        run_dir: Path,
        task_graph: dict[str, Any] | None,
        state: dict[str, Any] | None,
        facts: list[dict[str, Any]] | None,
    ) -> None:
        self._write_json(run_dir / "plan.json", task_graph or {})
        self._write_json(run_dir / "state.json", state or {})
        self._write_json(run_dir / "facts.json", {"items": list(facts or [])})

    def log_summary(
        self,
        run_dir: Path,
        task: str,
        completed: bool,
        steps: int,
        dry_run: bool,
        planner_mode: str,
        error: str | None = None,
        cancelled: bool = False,
        cancel_reason: str | None = None,
        requires_human: bool = False,
        interruption_kind: str | None = None,
        interruption_reason: str | None = None,
        started_at: float | None = None,
        finished_at: float | None = None,
        architecture: str = "generic_agent_v1",
    ) -> Path:
        payload = {
            "task": task,
            "completed": completed,
            "steps": steps,
            "dry_run": dry_run,
            "planner_mode": planner_mode,
            "error": error,
            "cancelled": cancelled,
            "cancel_reason": cancel_reason,
            "requires_human": requires_human,
            "interruption_kind": interruption_kind,
            "interruption_reason": interruption_reason,
            "started_at": started_at,
            "finished_at": finished_at if finished_at is not None else time.time(),
            "architecture": architecture,
        }
        output = run_dir / "summary.json"
        self._write_json(output, payload)
        return output

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _slugify(text: str) -> str:
    text = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", text.strip(), flags=re.U)
    return text.strip("_") or "task"
