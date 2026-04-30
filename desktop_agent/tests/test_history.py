import json
import shutil
import uuid
from pathlib import Path

from desktop_agent.history import list_runs, load_run_details, resolve_artifact_path


def test_history_lists_runs_and_loads_details():
    scratch_root = Path("test_history_artifacts")
    run_root = scratch_root / uuid.uuid4().hex
    run_dir = run_root / "20260409_000001_demo"
    run_dir.mkdir(parents=True, exist_ok=True)

    try:
        (run_dir / "summary.json").write_text(
            json.dumps(
                {
                    "task": "打开记事本并输入 demo",
                    "completed": True,
                    "steps": 1,
                    "dry_run": True,
                    "planner_mode": "auto",
                    "error": None,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (run_dir / "step_01.json").write_text(
            json.dumps(
                {
                    "step": 1,
                    "task": "打开记事本并输入 demo",
                    "screenshot": "step_01.png",
                    "plan": {"status_summary": "done"},
                    "executed_actions": [{"type": "launch_app", "app": "notepad"}],
                    "error": None,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (run_dir / "step_01.png").write_bytes(b"fake-png")

        runs = list_runs(run_root, limit=10)
        assert runs[0]["id"] == "20260409_000001_demo"
        assert runs[0]["preview_image"] == "step_01.png"
        assert runs[0]["dry_run"] is True
        assert runs[0]["planner_mode"] == "auto"
        assert isinstance(runs[0]["started_at"], float)
        assert isinstance(runs[0]["finished_at"], float)

        details = load_run_details(run_root, "20260409_000001_demo")
        assert details is not None
        assert details["timeline"][0]["screenshot"] == "step_01.png"
        assert details["dry_run"] is True
        assert details["planner_mode"] == "auto"
        assert isinstance(details["started_at"], float)
        assert isinstance(details["finished_at"], float)
        assert isinstance(details["timeline"][0]["captured_at"], float)

        artifact = resolve_artifact_path(run_root, "20260409_000001_demo", "step_01.png")
        assert artifact is not None
        assert artifact.name == "step_01.png"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_history_index_refreshes_when_runs_change():
    scratch_root = Path("test_history_artifacts")
    run_root = scratch_root / uuid.uuid4().hex
    first_run_dir = run_root / "20260409_000001_first"
    second_run_dir = run_root / "20260409_000002_second"
    first_run_dir.mkdir(parents=True, exist_ok=True)

    try:
        (first_run_dir / "summary.json").write_text(
            json.dumps(
                {
                    "task": "first task",
                    "completed": False,
                    "steps": 1,
                    "started_at": 100.0,
                    "finished_at": 101.0,
                }
            ),
            encoding="utf-8",
        )

        initial_runs = list_runs(run_root, limit=10)
        assert [item["id"] for item in initial_runs] == ["20260409_000001_first"]
        assert initial_runs[0]["steps"] == 1

        (first_run_dir / "summary.json").write_text(
            json.dumps(
                {
                    "task": "first task updated",
                    "completed": True,
                    "steps": 3,
                    "started_at": 100.0,
                    "finished_at": 103.0,
                }
            ),
            encoding="utf-8",
        )

        second_run_dir.mkdir(parents=True, exist_ok=True)
        (second_run_dir / "summary.json").write_text(
            json.dumps(
                {
                    "task": "second task",
                    "completed": True,
                    "steps": 2,
                    "started_at": 200.0,
                    "finished_at": 201.0,
                }
            ),
            encoding="utf-8",
        )

        updated_runs = list_runs(run_root, limit=10)
        assert [item["id"] for item in updated_runs] == [
            "20260409_000002_second",
            "20260409_000001_first",
        ]
        assert updated_runs[1]["task"] == "first task updated"
        assert updated_runs[1]["steps"] == 3

        shutil.rmtree(second_run_dir, ignore_errors=True)

        after_delete_runs = list_runs(run_root, limit=10)
        assert [item["id"] for item in after_delete_runs] == ["20260409_000001_first"]
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)
