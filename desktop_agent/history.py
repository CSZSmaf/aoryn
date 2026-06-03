from __future__ import annotations

import json
import shutil
import threading
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
            "answer": self.summary_payload.get("answer"),
            "skill": self.summary_payload.get("skill"),
        }


@dataclass(slots=True)
class _CachedRunSummary:
    record: RunRecord
    summary_mtime_ns: int
    summary_size: int


class RunHistoryIndex:
    """Incrementally caches run summaries for overview-style queries."""

    def __init__(self, run_root: Path) -> None:
        self.run_root = run_root.resolve()
        self._entries: dict[str, _CachedRunSummary] = {}
        self._lock = threading.Lock()

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            records = self._refresh_records_locked()
            selected = records[: max(0, int(limit))]
            return [record.to_dict() for record in selected]

    def _refresh_records_locked(self) -> list[RunRecord]:
        if not self.run_root.exists():
            self._entries.clear()
            return []

        seen_run_ids: set[str] = set()
        for summary_path in self.run_root.glob("*/summary.json"):
            run_dir = summary_path.parent
            run_id = run_dir.name
            seen_run_ids.add(run_id)
            try:
                stat = summary_path.stat()
            except OSError:
                self._entries.pop(run_id, None)
                continue

            cached = self._entries.get(run_id)
            if (
                cached is not None
                and cached.summary_mtime_ns == stat.st_mtime_ns
                and cached.summary_size == stat.st_size
            ):
                continue

            payload = _load_summary_payload(summary_path)
            if payload is None:
                self._entries.pop(run_id, None)
                continue

            self._entries[run_id] = _CachedRunSummary(
                record=_build_run_record(
                    run_dir=run_dir,
                    summary_path=summary_path,
                    summary_payload=payload,
                    summary_stat=stat,
                ),
                summary_mtime_ns=stat.st_mtime_ns,
                summary_size=stat.st_size,
            )

        stale_run_ids = [run_id for run_id in self._entries if run_id not in seen_run_ids]
        for run_id in stale_run_ids:
            self._entries.pop(run_id, None)

        records = [entry.record for entry in self._entries.values()]
        records.sort(key=lambda item: item.created_at, reverse=True)
        return records


_RUN_HISTORY_INDEXES: dict[str, RunHistoryIndex] = {}
_RUN_HISTORY_INDEXES_LOCK = threading.Lock()


def list_runs(run_root: Path, limit: int = 20) -> list[dict[str, Any]]:
    return _history_index_for(run_root).list_runs(limit=limit)


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
                "state": step_payload.get("state"),
                "world_model": step_payload.get("world_model"),
                "step_proposal": step_payload.get("step_proposal"),
                "verification": step_payload.get("verification"),
                "timings": step_payload.get("timings"),
            }
        )

    plan_payload = _load_optional_json(run_dir / "plan.json")
    state_payload = _load_optional_json(run_dir / "state.json")
    facts_payload = _load_optional_json(run_dir / "facts.json")

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
        "architecture": summary.get("architecture"),
        "answer": summary.get("answer"),
        "skill": summary.get("skill"),
        "artifacts": [item.name for item in sorted(run_dir.iterdir()) if item.is_file()],
        "timeline": steps,
        "plan": plan_payload,
        "state": state_payload,
        "facts": facts_payload.get("items") if isinstance(facts_payload, dict) else facts_payload,
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


def clear_runs(run_root: Path) -> int:
    resolved_root = run_root.resolve()
    if not resolved_root.exists() or not resolved_root.is_dir():
        return 0
    run_dirs = []
    for summary_path in resolved_root.glob("*/summary.json"):
        if not summary_path.is_file():
            continue
        run_dir = summary_path.parent.resolve()
        try:
            run_dir.relative_to(resolved_root)
        except ValueError:
            continue
        if run_dir == resolved_root:
            continue
        run_dirs.append(run_dir)

    cleared = 0
    for run_dir in sorted(set(run_dirs)):
        try:
            shutil.rmtree(run_dir)
        except OSError:
            continue
        cleared += 1
    return cleared


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


_STEP_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def _find_latest_step_image(run_dir: Path) -> Path | None:
    images = sorted(
        item
        for item in run_dir.glob("step_*.*")
        if item.is_file() and item.suffix.lower() in _STEP_IMAGE_SUFFIXES
    )
    if images:
        return images[-1]
    return None


def _history_index_for(run_root: Path) -> RunHistoryIndex:
    resolved_root = run_root.resolve()
    key = str(resolved_root)
    with _RUN_HISTORY_INDEXES_LOCK:
        index = _RUN_HISTORY_INDEXES.get(key)
        if index is None:
            index = RunHistoryIndex(resolved_root)
            _RUN_HISTORY_INDEXES[key] = index
        return index


def _load_summary_payload(summary_path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _build_run_record(
    *,
    run_dir: Path,
    summary_path: Path,
    summary_payload: dict[str, Any],
    summary_stat,
) -> RunRecord:
    started_at = summary_payload.get("started_at")
    return RunRecord(
        run_id=run_dir.name,
        task=str(summary_payload.get("task", run_dir.name)),
        completed=bool(summary_payload.get("completed", False)),
        steps=int(summary_payload.get("steps", 0) or 0),
        error=summary_payload.get("error"),
        created_at=float(started_at) if isinstance(started_at, (int, float)) else summary_stat.st_mtime,
        summary_payload=summary_payload,
        summary_path=summary_path,
        run_dir=run_dir,
    )


def _load_optional_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
