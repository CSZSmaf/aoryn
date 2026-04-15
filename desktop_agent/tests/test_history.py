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
