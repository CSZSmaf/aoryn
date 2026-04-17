from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class RunRecord:
    run_id: str
    task: str
    completed: bool
    steps: int
    error: str | None
    created_at: float
    summary_payload: dict[str, Any]
    summary_path: Path
    run_dir: Path

    def to_dict(self) -> dict[str, Any]:
        latest_step_image = _find_latest_step_image(self.run_dir)
        return {
            "id": self.run_id,
            "task": self.task,
            "completed": self.completed,
            "steps": self.steps,
            "dry_run": self.summary_payload.get("dry_run"),
            "planner_mode": self.summary_payload.get("planner_mode"),
            "cancelled": bool(self.summary_payload.get("cancelled", False)),
            "cancel_reason": self.summary_payload.get("cancel_reason"),
            "requires_human": bool(self.summary_payload.get("requires_human", False)),
            "interruption_kind": self.summary_payload.get("interruption_kind"),
            "interruption_reason": self.summary_payload.get("interruption_reason"),
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.summary_payload.get("started_at", self.created_at),
            "finished_at": self.summary_payload.get("finished_at", self.created_at),
            "preview_image": latest_step_image.name if latest_step_image else None,
        }


def list_runs(run_root: Path, limit: int = 20) -> list[dict[str, Any]]:
    records: list[RunRecord] = []
    if not run_root.exists():
        return []

    for summary_path in run_root.glob("*/summary.json"):
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        run_dir = summary_path.parent
        stat = summary_path.stat()
        started_at = payload.get("started_at")
        records.append(
            RunRecord(
                run_id=run_dir.name,
                task=str(payload.get("task", run_dir.name)),
                completed=bool(payload.get("completed", False)),
                steps=int(payload.get("steps", 0) or 0),
                error=payload.get("error"),
                created_at=float(started_at) if isinstance(started_at, (int, float)) else stat.st_mtime,
                summary_payload=payload,
                summary_path=summary_path,
                run_dir=run_dir,
            )
        )

    records.sort(key=lambda item: item.created_at, reverse=True)
    return [record.to_dict() for record in records[:limit]]


def load_run_details(run_root: Path, run_id: str) -> dict[str, Any] | None:
    run_dir = _resolve_run_dir(run_root, run_id)
    if run_dir is None:
        return None

    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        return None

    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    summary_stat = summary_path.stat()

    steps: list[dict[str, Any]] = []
    for step_path in sorted(run_dir.glob("step_*.json")):
        try:
            step_payload = json.loads(step_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        screenshot_name = step_payload.get("screenshot")
        step_stat = step_path.stat()
        steps.append(
            {
                "step": int(step_payload.get("step", 0) or 0),
                "task": step_payload.get("task"),
                "error": step_payload.get("error"),
                "screenshot": screenshot_name,
                "captured_at": step_payload.get("captured_at", step_stat.st_mtime),
                "plan": step_payload.get("plan", {}),
                "executed_actions": step_payload.get("executed_actions", []),
                "challenge": step_payload.get("challenge"),
            }
        )

    return {
        "id": run_id,
        "task": summary.get("task"),
        "completed": bool(summary.get("completed", False)),
        "steps": int(summary.get("steps", 0) or 0),
        "dry_run": summary.get("dry_run"),
        "planner_mode": summary.get("planner_mode"),
        "cancelled": bool(summary.get("cancelled", False)),
        "cancel_reason": summary.get("cancel_reason"),
        "requires_human": bool(summary.get("requires_human", False)),
        "interruption_kind": summary.get("interruption_kind"),
        "interruption_reason": summary.get("interruption_reason"),
        "started_at": summary.get("started_at", summary_stat.st_mtime),
        "finished_at": summary.get("finished_at", summary_stat.st_mtime),
        "error": summary.get("error"),
        "artifacts": [item.name for item in sorted(run_dir.iterdir()) if item.is_file()],
        "timeline": steps,
    }


def resolve_artifact_path(run_root: Path, run_id: str, artifact_name: str) -> Path | None:
    if not artifact_name or "/" in artifact_name or "\\" in artifact_name:
        return None
    run_dir = _resolve_run_dir(run_root, run_id)
    if run_dir is None:
        return None

    artifact_path = (run_dir / artifact_name).resolve()
    try:
        artifact_path.relative_to(run_dir.resolve())
    except ValueError:
        return None
    if not artifact_path.exists() or not artifact_path.is_file():
        return None
    return artifact_path


def _resolve_run_dir(run_root: Path, run_id: str) -> Path | None:
    if not run_id or "/" in run_id or "\\" in run_id:
        return None
    run_dir = (run_root / run_id).resolve()
    try:
        run_dir.relative_to(run_root.resolve())
    except ValueError:
        return None
    if not run_dir.exists() or not run_dir.is_dir():
        return None
    return run_dir


def _find_latest_step_image(run_dir: Path) -> Path | None:
    images = sorted(run_dir.glob("step_*.png"))
    if images:
        return images[-1]
    return None
