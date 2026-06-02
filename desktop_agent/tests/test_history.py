import json
import os
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
                    "task_graph_request_timeout": 9.5,
                    "max_steps": 8,
                    "max_run_seconds": 120,
                    "pause_after_action": 0.25,
                    "desktop_autonomy_mode": "autonomous",
                    "complex_task_planning": "model",
                    "approval_policy": "autonomous",
                    "plan_review_policy": "never",
                    "stage_review_policy": "never",
                    "max_task_subgoals": 10,
                    "max_subgoal_retries": 4,
                    "max_replans_per_run": 5,
                    "max_failures_per_subgoal": 5,
                    "replan_on_recoverable_error": True,
                    "recoverable_error_retry_limit": 4,
                    "browser_control_mode": "hybrid",
                    "browser_dom_backend": "playwright",
                    "browser_dom_timeout": 6.5,
                    "browser_headless": "true",
                    "browser_channel": "chrome",
                    "browser_executable_path": "C:\\Tools\\browser.exe",
                    "cursor_motion_enabled": "true",
                    "cursor_motion_duration": 0.4,
                    "display_override_enabled": "true",
                    "display_override_monitor_device_name": "DISPLAY2",
                    "display_override_dpi_scale": 1.25,
                    "display_override_work_area_left": 10,
                    "display_override_work_area_top": 20,
                    "display_override_work_area_width": 1280,
                    "display_override_work_area_height": 720,
                    "generic_app_launch_enabled": "false",
                    "shell_recipe_policy": "approval_required",
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
        (run_dir / "execution_state.json").write_text(
            json.dumps(
                {
                    "orchestration_phase": "complete",
                    "plan_health": {
                        "counts": {"total": 1, "completed": 1},
                        "next_subgoal_id": None,
                    },
                    "evidence_ledger": [{"subgoal_id": "subgoal_01", "status": "success"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        runs = list_runs(run_root, limit=10)
        assert runs[0]["id"] == "20260409_000001_demo"
        assert runs[0]["preview_image"] == "step_01.png"
        assert runs[0]["dry_run"] is True
        assert runs[0]["planner_mode"] == "auto"
        assert runs[0]["execution_budget"] == {
            "task_graph_request_timeout": 9.5,
            "max_steps": 8,
            "max_run_seconds": 120,
            "pause_after_action": 0.25,
            "desktop_autonomy_mode": "autonomous",
            "approval_policy": "autonomous",
            "complex_task_planning": "model",
            "plan_review_policy": "never",
            "max_task_subgoals": 10,
            "max_subgoal_retries": 4,
            "stage_review_policy": "never",
            "max_replans_per_run": 5,
            "max_failures_per_subgoal": 5,
            "replan_on_recoverable_error": True,
            "recoverable_error_retry_limit": 4,
        }
        assert runs[0]["max_steps"] == 8
        assert runs[0]["max_run_seconds"] == 120
        assert runs[0]["pause_after_action"] == 0.25
        assert runs[0]["desktop_autonomy_mode"] == "autonomous"
        assert runs[0]["complex_task_planning"] == "model"
        assert runs[0]["approval_policy"] == "autonomous"
        assert runs[0]["plan_review_policy"] == "never"
        assert runs[0]["stage_review_policy"] == "never"
        assert runs[0]["max_task_subgoals"] == 10
        assert runs[0]["max_subgoal_retries"] == 4
        assert runs[0]["max_replans_per_run"] == 5
        assert runs[0]["max_failures_per_subgoal"] == 5
        assert runs[0]["replan_on_recoverable_error"] is True
        assert runs[0]["recoverable_error_retry_limit"] == 4
        assert runs[0]["execution_environment"] == {
            "browser_control_mode": "hybrid",
            "browser_dom_backend": "playwright",
            "browser_dom_timeout": 6.5,
            "browser_headless": True,
            "browser_channel": "chrome",
            "browser_executable_path": "C:\\Tools\\browser.exe",
            "cursor_motion_enabled": True,
            "cursor_motion_duration": 0.4,
            "display_override_enabled": True,
            "display_override_monitor_device_name": "DISPLAY2",
            "display_override_dpi_scale": 1.25,
            "display_override_work_area_left": 10,
            "display_override_work_area_top": 20,
            "display_override_work_area_width": 1280,
            "display_override_work_area_height": 720,
            "generic_app_launch_enabled": False,
            "shell_recipe_policy": "approval_required",
        }
        assert runs[0]["browser_control_mode"] == "hybrid"
        assert runs[0]["browser_dom_backend"] == "playwright"
        assert runs[0]["browser_dom_timeout"] == 6.5
        assert runs[0]["browser_headless"] is True
        assert runs[0]["browser_channel"] == "chrome"
        assert runs[0]["browser_executable_path"] == "C:\\Tools\\browser.exe"
        assert runs[0]["cursor_motion_enabled"] is True
        assert runs[0]["cursor_motion_duration"] == 0.4
        assert runs[0]["display_override_enabled"] is True
        assert runs[0]["display_override_monitor_device_name"] == "DISPLAY2"
        assert runs[0]["display_override_dpi_scale"] == 1.25
        assert runs[0]["display_override_work_area_left"] == 10
        assert runs[0]["display_override_work_area_top"] == 20
        assert runs[0]["display_override_work_area_width"] == 1280
        assert runs[0]["display_override_work_area_height"] == 720
        assert runs[0]["generic_app_launch_enabled"] is False
        assert runs[0]["shell_recipe_policy"] == "approval_required"
        assert runs[0]["can_resume"] is False
        assert runs[0]["resume_mode"] is None
        assert isinstance(runs[0]["started_at"], float)
        assert isinstance(runs[0]["finished_at"], float)
        assert isinstance(runs[0]["details_updated_at"], float)

        details = load_run_details(run_root, "20260409_000001_demo")
        assert details is not None
        assert details["timeline"][0]["screenshot"] == "step_01.png"
        assert details["dry_run"] is True
        assert details["planner_mode"] == "auto"
        assert details["execution_budget"] == runs[0]["execution_budget"]
        assert details["max_steps"] == 8
        assert details["max_run_seconds"] == 120
        assert details["pause_after_action"] == 0.25
        assert details["desktop_autonomy_mode"] == "autonomous"
        assert details["complex_task_planning"] == "model"
        assert details["approval_policy"] == "autonomous"
        assert details["plan_review_policy"] == "never"
        assert details["stage_review_policy"] == "never"
        assert details["max_task_subgoals"] == 10
        assert details["max_subgoal_retries"] == 4
        assert details["max_replans_per_run"] == 5
        assert details["max_failures_per_subgoal"] == 5
        assert details["replan_on_recoverable_error"] is True
        assert details["recoverable_error_retry_limit"] == 4
        assert details["execution_environment"] == runs[0]["execution_environment"]
        assert details["browser_control_mode"] == "hybrid"
        assert details["browser_dom_backend"] == "playwright"
        assert details["browser_dom_timeout"] == 6.5
        assert details["browser_headless"] is True
        assert details["browser_channel"] == "chrome"
        assert details["browser_executable_path"] == "C:\\Tools\\browser.exe"
        assert details["cursor_motion_enabled"] is True
        assert details["cursor_motion_duration"] == 0.4
        assert details["display_override_enabled"] is True
        assert details["display_override_monitor_device_name"] == "DISPLAY2"
        assert details["display_override_dpi_scale"] == 1.25
        assert details["display_override_work_area_left"] == 10
        assert details["display_override_work_area_top"] == 20
        assert details["display_override_work_area_width"] == 1280
        assert details["display_override_work_area_height"] == 720
        assert details["generic_app_launch_enabled"] is False
        assert details["shell_recipe_policy"] == "approval_required"
        assert details["can_resume"] is False
        assert details["resume_mode"] is None
        assert details["execution_state"]["plan_health"]["counts"]["completed"] == 1
        assert details["execution_state"]["evidence_ledger"][0]["status"] == "success"
        assert isinstance(details["started_at"], float)
        assert isinstance(details["finished_at"], float)
        assert isinstance(details["details_updated_at"], float)
        assert isinstance(details["timeline"][0]["captured_at"], float)

        artifact = resolve_artifact_path(run_root, "20260409_000001_demo", "step_01.png")
        assert artifact is not None
        assert artifact.name == "step_01.png"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_history_accepts_nested_execution_contract_snapshots(tmp_path):
    run_root = tmp_path / "runs"
    run_dir = run_root / "20260409_000010_nested_contract"
    run_dir.mkdir(parents=True)
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "task": "Track nested execution contract",
                "completed": False,
                "steps": 0,
                "execution_budget": {
                    "max_steps": 5,
                    "max_run_seconds": 90,
                    "pause_after_action": 0.1,
                    "desktop_autonomy_mode": "review_first",
                    "approval_policy": "tiered",
                    "complex_task_planning": "hybrid",
                    "plan_review_policy": "always",
                    "max_task_subgoals": 6,
                    "max_subgoal_retries": 1,
                    "stage_review_policy": "risk_change",
                    "max_replans_per_run": 2,
                    "max_failures_per_subgoal": 3,
                    "replan_on_recoverable_error": "false",
                    "recoverable_error_retry_limit": 1,
                },
                "execution_environment": {
                    "browser_control_mode": "dom",
                    "browser_dom_backend": "playwright",
                    "browser_dom_timeout": 4.5,
                    "browser_headless": "false",
                    "cursor_motion_enabled": "true",
                    "cursor_motion_duration": 0.2,
                    "generic_app_launch_enabled": "false",
                    "shell_recipe_policy": "strict",
                },
            }
        ),
        encoding="utf-8",
    )

    runs = list_runs(run_root, limit=10)
    assert len(runs) == 1
    details = load_run_details(run_root, "20260409_000010_nested_contract")
    assert details is not None

    for payload in (runs[0], details):
        assert payload["max_steps"] == 5
        assert payload["max_run_seconds"] == 90
        assert payload["pause_after_action"] == 0.1
        assert payload["desktop_autonomy_mode"] == "review_first"
        assert payload["plan_review_policy"] == "always"
        assert payload["max_task_subgoals"] == 6
        assert payload["replan_on_recoverable_error"] is False
        assert payload["recoverable_error_retry_limit"] == 1
        assert payload["execution_budget"]["max_steps"] == 5
        assert payload["execution_budget"]["replan_on_recoverable_error"] is False
        assert payload["browser_control_mode"] == "dom"
        assert payload["browser_dom_timeout"] == 4.5
        assert payload["browser_headless"] is False
        assert payload["cursor_motion_enabled"] is True
        assert payload["generic_app_launch_enabled"] is False
        assert payload["execution_environment"]["browser_headless"] is False
        assert payload["execution_environment"]["shell_recipe_policy"] == "strict"


def test_history_state_summary_omits_empty_plan_health(tmp_path):
    run_root = tmp_path / "runs"
    run_dir = run_root / "20260409_000002_empty_plan_health"
    run_dir.mkdir(parents=True)
    (run_dir / "summary.json").write_text(
        json.dumps({"task": "Track empty plan health", "completed": False}),
        encoding="utf-8",
    )
    (run_dir / "state.json").write_text(
        json.dumps(
            {
                "current_goal": "Track empty plan health",
                "plan_health": {
                    "counts": {"total": None, "completed": None},
                    "autonomy": {},
                    "items": [{}],
                },
            }
        ),
        encoding="utf-8",
    )

    runs = list_runs(run_root, limit=10)
    details = load_run_details(run_root, "20260409_000002_empty_plan_health")

    assert runs[0]["state"]["current_goal"] == "Track empty plan health"
    assert "plan_health" not in runs[0]["state"]
    assert details["state"]["plan_health"]["autonomy"] == {}


def test_history_state_summary_preserves_minimal_plan_health_signals(tmp_path):
    run_root = tmp_path / "runs"
    run_dir = run_root / "20260409_000003_plan_health_signal"
    run_dir.mkdir(parents=True)
    (run_dir / "summary.json").write_text(
        json.dumps({"task": "Track minimal plan health", "completed": False}),
        encoding="utf-8",
    )
    (run_dir / "state.json").write_text(
        json.dumps(
            {
                "current_goal": "Track minimal plan health",
                "plan_health": {
                    "blocked_reason": "Waiting for sign-in.",
                    "counts": {"total": 0},
                    "autonomy": {"can_continue": False, "requires_user": False},
                    "items": [{}],
                },
            }
        ),
        encoding="utf-8",
    )

    runs = list_runs(run_root, limit=10)
    plan_health = runs[0]["state"]["plan_health"]

    assert plan_health["blocked_reason"] == "Waiting for sign-in."
    assert plan_health["counts"]["total"] == 0
    assert plan_health["autonomy"]["can_continue"] is False
    assert plan_health["autonomy"]["requires_user"] is False
    assert "items" not in plan_health


def test_history_state_summary_ignores_empty_pending_decision(tmp_path):
    run_root = tmp_path / "runs"
    run_dir = run_root / "20260409_000004_empty_pending_decision"
    run_dir.mkdir(parents=True)
    (run_dir / "summary.json").write_text(
        json.dumps({"task": "Ignore empty pending decision", "completed": False, "requires_human": False}),
        encoding="utf-8",
    )
    (run_dir / "execution_state.json").write_text(
        json.dumps({"orchestration_phase": "stage_ready", "pending_decision": {}}),
        encoding="utf-8",
    )
    (run_dir / "state.json").write_text(
        json.dumps({"current_goal": "Keep running", "pending_decision": {}}),
        encoding="utf-8",
    )

    runs = list_runs(run_root, limit=10)
    details = load_run_details(run_root, "20260409_000004_empty_pending_decision")

    assert runs[0]["requires_human"] is False
    assert runs[0]["can_resume"] is False
    assert runs[0]["resume_mode"] is None
    assert "pending_decision" not in runs[0]["state"]
    assert details["state"]["pending_decision"] == {}


def test_history_state_summary_prefers_real_pending_decision_over_empty_display_shell(tmp_path):
    run_root = tmp_path / "runs"
    run_dir = run_root / "20260409_000005_nested_pending_decision"
    run_dir.mkdir(parents=True)
    (run_dir / "summary.json").write_text(
        json.dumps({"task": "Review nested pending decision", "completed": False, "requires_human": False}),
        encoding="utf-8",
    )
    (run_dir / "execution_state.json").write_text(
        json.dumps(
            {
                "orchestration_phase": "plan_review",
                "pending_decision": {
                    "decision_type": "plan_review",
                    "summary": "Review the generated task plan.",
                },
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "state.json").write_text(
        json.dumps({"current_goal": "Review nested pending decision", "pending_decision": {}}),
        encoding="utf-8",
    )

    runs = list_runs(run_root, limit=10)
    state_summary = runs[0]["state"]

    assert runs[0]["requires_human"] is True
    assert runs[0]["can_resume"] is True
    assert runs[0]["resume_mode"] == "manual"
    assert state_summary["pending_decision"]["summary"] == "Review the generated task plan."
    assert state_summary["current_goal"] == "Review nested pending decision"


def test_history_state_summary_ignores_empty_display_shells_over_full_state(tmp_path):
    run_root = tmp_path / "runs"
    run_dir = run_root / "20260409_000006_empty_display_shells"
    run_dir.mkdir(parents=True)
    (run_dir / "summary.json").write_text(
        json.dumps({"task": "Preserve full state shells", "completed": False}),
        encoding="utf-8",
    )
    (run_dir / "execution_state.json").write_text(
        json.dumps(
            {
                "current_goal": "Full state goal",
                "workspace_summary": {
                    "facts": [{"key": "route", "value": "Full state route is usable."}],
                },
                "task_graph": {
                    "task": "Preserve full state shells",
                    "subgoals": [{"id": "subgoal_01", "title": "Use preserved full state"}],
                },
                "last_verification": {
                    "status": "partial_progress",
                    "message": "Full state verification remains useful.",
                },
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "state.json").write_text(
        json.dumps(
            {
                "current_goal": "Display state goal",
                "workspace_summary": {"facts": [], "sources": [], "evidence": [], "notes": []},
                "task_graph": {},
                "last_verification": {},
                "evidence_ledger": [],
                "repair_history": [],
            }
        ),
        encoding="utf-8",
    )

    runs = list_runs(run_root, limit=10)
    state_summary = runs[0]["state"]

    assert state_summary["current_goal"] == "Display state goal"
    assert state_summary["workspace_summary"]["facts"][0]["value"] == "Full state route is usable."
    assert state_summary["task_graph"]["subgoals"][0]["title"] == "Use preserved full state"
    assert state_summary["last_verification"]["message"] == "Full state verification remains useful."
    assert "evidence_ledger" not in state_summary
    assert "repair_history" not in state_summary


def test_history_parses_string_boolean_summary_flags_for_resume():
    scratch_root = Path("test_history_artifacts")
    run_root = scratch_root / uuid.uuid4().hex
    resumable_dir = run_root / "20260409_000002_string_false"
    completed_dir = run_root / "20260409_000003_string_true"
    resumable_dir.mkdir(parents=True, exist_ok=True)
    completed_dir.mkdir(parents=True, exist_ok=True)

    try:
        (resumable_dir / "summary.json").write_text(
            json.dumps(
                {
                    "task": "continue a paused run",
                    "completed": "false",
                    "cancelled": "false",
                    "requires_human": "false",
                    "dry_run": "false",
                    "replan_on_recoverable_error": "false",
                    "steps": 2,
                    "started_at": 200.0,
                    "finished_at": 201.0,
                }
            ),
            encoding="utf-8",
        )
        (resumable_dir / "plan.json").write_text(
            json.dumps({"subgoals": [{"id": "subgoal_01", "title": "Continue", "status": "pending"}]}),
            encoding="utf-8",
        )
        (completed_dir / "summary.json").write_text(
            json.dumps(
                {
                    "task": "completed run with saved plan",
                    "completed": "true",
                    "cancelled": "false",
                    "requires_human": "false",
                    "dry_run": "true",
                    "replan_on_recoverable_error": "true",
                    "steps": 3,
                    "started_at": 100.0,
                    "finished_at": 101.0,
                }
            ),
            encoding="utf-8",
        )
        (completed_dir / "plan.json").write_text(
            json.dumps({"subgoals": [{"id": "subgoal_01", "title": "Already done", "status": "completed"}]}),
            encoding="utf-8",
        )

        runs = {item["id"]: item for item in list_runs(run_root, limit=10)}
        resumable_details = load_run_details(run_root, "20260409_000002_string_false")
        completed_details = load_run_details(run_root, "20260409_000003_string_true")

        assert runs["20260409_000002_string_false"]["completed"] is False
        assert runs["20260409_000002_string_false"]["cancelled"] is False
        assert runs["20260409_000002_string_false"]["requires_human"] is False
        assert runs["20260409_000002_string_false"]["dry_run"] is False
        assert runs["20260409_000002_string_false"]["replan_on_recoverable_error"] is False
        assert runs["20260409_000002_string_false"]["can_resume"] is True
        assert runs["20260409_000002_string_false"]["resume_mode"] == "plan"
        assert resumable_details is not None
        assert resumable_details["completed"] is False
        assert resumable_details["cancelled"] is False
        assert resumable_details["requires_human"] is False
        assert resumable_details["dry_run"] is False
        assert resumable_details["replan_on_recoverable_error"] is False
        assert resumable_details["can_resume"] is True
        assert resumable_details["resume_mode"] == "plan"

        assert runs["20260409_000003_string_true"]["completed"] is True
        assert runs["20260409_000003_string_true"]["dry_run"] is True
        assert runs["20260409_000003_string_true"]["replan_on_recoverable_error"] is True
        assert runs["20260409_000003_string_true"]["can_resume"] is False
        assert runs["20260409_000003_string_true"]["resume_mode"] is None
        assert completed_details is not None
        assert completed_details["completed"] is True
        assert completed_details["dry_run"] is True
        assert completed_details["replan_on_recoverable_error"] is True
        assert completed_details["can_resume"] is False
        assert completed_details["resume_mode"] is None
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_history_overview_marks_execution_state_detail_updates():
    scratch_root = Path("test_history_artifacts")
    run_root = scratch_root / uuid.uuid4().hex
    run_dir = run_root / "20260409_000003_state"
    run_dir.mkdir(parents=True, exist_ok=True)

    try:
        summary_path = run_dir / "summary.json"
        execution_state_path = run_dir / "execution_state.json"
        summary_path.write_text(
            json.dumps(
                {
                    "task": "keep plan health fresh",
                    "completed": False,
                    "steps": 1,
                    "started_at": 100.0,
                    "finished_at": 100.0,
                }
            ),
            encoding="utf-8",
        )
        execution_state_path.write_text(
            json.dumps({"plan_health": {"counts": {"total": 2, "completed": 0}}}),
            encoding="utf-8",
        )
        os.utime(summary_path, (100.0, 100.0))
        os.utime(execution_state_path, (100.0, 100.0))

        initial_runs = list_runs(run_root, limit=10)
        assert initial_runs[0]["details_updated_at"] == 100.0

        execution_state_path.write_text(
            json.dumps({"plan_health": {"counts": {"total": 2, "completed": 1}}}),
            encoding="utf-8",
        )
        os.utime(execution_state_path, (200.0, 200.0))

        refreshed_runs = list_runs(run_root, limit=10)
        assert refreshed_runs[0]["steps"] == 1
        assert refreshed_runs[0]["details_updated_at"] == 200.0
        details = load_run_details(run_root, "20260409_000003_state")
        assert details is not None
        assert details["details_updated_at"] == 200.0
        assert details["execution_state"]["plan_health"]["counts"]["completed"] == 1
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_history_treats_legacy_interruption_as_manual_continuation():
    scratch_root = Path("test_history_artifacts")
    run_root = scratch_root / uuid.uuid4().hex
    run_dir = run_root / "20260409_000004_legacy_interrupt"
    run_dir.mkdir(parents=True, exist_ok=True)

    try:
        (run_dir / "summary.json").write_text(
            json.dumps(
                {
                    "task": "finish login before continuing",
                    "completed": False,
                    "steps": 2,
                    "requires_human": False,
                    "interruption_kind": "login",
                    "interruption_reason": "A login prompt needs user input.",
                    "started_at": 100.0,
                    "finished_at": 101.0,
                }
            ),
            encoding="utf-8",
        )

        runs = list_runs(run_root, limit=10)
        details = load_run_details(run_root, "20260409_000004_legacy_interrupt")

        assert runs[0]["requires_human"] is True
        assert runs[0]["can_resume"] is True
        assert runs[0]["resume_mode"] == "manual"
        assert details is not None
        assert details["requires_human"] is True
        assert details["can_resume"] is True
        assert details["resume_mode"] == "manual"
        assert details["interruption_kind"] == "login"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_history_treats_execution_state_handoff_context_as_manual_continuation():
    scratch_root = Path("test_history_artifacts")
    run_root = scratch_root / uuid.uuid4().hex
    run_dir = run_root / "20260409_000004_state_handoff"
    run_dir.mkdir(parents=True, exist_ok=True)

    try:
        (run_dir / "summary.json").write_text(
            json.dumps(
                {
                    "task": "finish login before continuing",
                    "completed": False,
                    "steps": 2,
                    "requires_human": False,
                    "started_at": 100.0,
                    "finished_at": 101.0,
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "execution_state.json").write_text(
            json.dumps(
                {
                    "orchestration_phase": "awaiting_user",
                    "app_context": {
                        "human_handoff_kind": "login",
                        "human_handoff_reason": "A login prompt needs user input.",
                        "standard_recovery_kind": "requires_user",
                    },
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "state.json").write_text(
            json.dumps(
                {
                    "current_goal": "Resume after sign-in",
                    "orchestration_phase": "running",
                    "app_context": {
                        "manual_resume_status": "resumed",
                        "manual_resume_reason": "Previous display state was already refreshed.",
                    },
                }
            ),
            encoding="utf-8",
        )

        runs = list_runs(run_root, limit=10)
        details = load_run_details(run_root, "20260409_000004_state_handoff")

        assert runs[0]["requires_human"] is True
        assert runs[0]["can_resume"] is True
        assert runs[0]["resume_mode"] == "manual"
        assert details is not None
        assert details["requires_human"] is True
        assert details["can_resume"] is True
        assert details["resume_mode"] == "manual"
        assert details["execution_state"]["app_context"]["human_handoff_kind"] == "login"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_history_treats_pending_decision_state_as_manual_continuation():
    scratch_root = Path("test_history_artifacts")
    run_root = scratch_root / uuid.uuid4().hex
    run_dir = run_root / "20260409_000005_pending_decision"
    run_dir.mkdir(parents=True, exist_ok=True)

    try:
        (run_dir / "summary.json").write_text(
            json.dumps(
                {
                    "task": "review generated task plan",
                    "completed": False,
                    "steps": 2,
                    "requires_human": False,
                    "started_at": 100.0,
                    "finished_at": 101.0,
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "execution_state.json").write_text(
            json.dumps(
                {
                    "orchestration_phase": "plan_review",
                    "pending_decision": {
                        "decision_type": "plan_review",
                        "summary": "Review the generated task plan.",
                    },
                }
            ),
            encoding="utf-8",
        )

        runs = list_runs(run_root, limit=10)
        details = load_run_details(run_root, "20260409_000005_pending_decision")

        assert runs[0]["requires_human"] is True
        assert runs[0]["can_resume"] is True
        assert runs[0]["resume_mode"] == "manual"
        assert runs[0]["state"]["pending_decision"]["decision_type"] == "plan_review"
        assert details is not None
        assert details["requires_human"] is True
        assert details["can_resume"] is True
        assert details["resume_mode"] == "manual"
        assert details["execution_state"]["pending_decision"]["summary"] == "Review the generated task plan."
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_history_treats_saved_step_approval_phase_as_manual_continuation():
    scratch_root = Path("test_history_artifacts")
    run_root = scratch_root / uuid.uuid4().hex
    run_dir = run_root / "20260409_000006_step_approval"
    run_dir.mkdir(parents=True, exist_ok=True)

    try:
        (run_dir / "summary.json").write_text(
            json.dumps(
                {
                    "task": "resume guarded confirmation",
                    "completed": False,
                    "steps": 1,
                    "requires_human": False,
                    "started_at": 100.0,
                    "finished_at": 101.0,
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "execution_state.json").write_text(
            json.dumps(
                {
                    "orchestration_phase": "awaiting_approval",
                    "task_graph": {
                        "task": "resume guarded confirmation",
                        "subgoals": [
                            {
                                "id": "subgoal_01",
                                "title": "Click the guarded confirmation",
                                "status": "pending",
                            }
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )

        runs = list_runs(run_root, limit=10)
        details = load_run_details(run_root, "20260409_000006_step_approval")

        assert runs[0]["requires_human"] is True
        assert runs[0]["can_resume"] is True
        assert runs[0]["resume_mode"] == "manual"
        assert runs[0]["state"]["orchestration_phase"] == "awaiting_approval"
        assert details is not None
        assert details["requires_human"] is True
        assert details["can_resume"] is True
        assert details["resume_mode"] == "manual"
        assert details["execution_state"]["orchestration_phase"] == "awaiting_approval"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_history_ignores_stale_pending_decision_for_terminal_runs():
    scratch_root = Path("test_history_artifacts")
    run_root = scratch_root / uuid.uuid4().hex
    completed_dir = run_root / "20260409_000006_completed_stale_review"
    failed_dir = run_root / "20260409_000007_failed_stale_review"
    completed_dir.mkdir(parents=True, exist_ok=True)
    failed_dir.mkdir(parents=True, exist_ok=True)
    stale_state = {
        "orchestration_phase": "plan_review",
        "pending_decision": {
            "decision_type": "plan_review",
            "summary": "Stale approval should not require manual continuation.",
        },
        "task_graph": {
            "task": "recover stale approval",
            "subgoals": [{"id": "subgoal_01", "title": "Recover stale approval"}],
        },
    }

    try:
        (completed_dir / "summary.json").write_text(
            json.dumps(
                {
                    "task": "completed despite stale approval",
                    "completed": True,
                    "steps": 3,
                    "started_at": 100.0,
                    "finished_at": 101.0,
                }
            ),
            encoding="utf-8",
        )
        (completed_dir / "execution_state.json").write_text(json.dumps(stale_state), encoding="utf-8")
        (failed_dir / "summary.json").write_text(
            json.dumps(
                {
                    "task": "failed after stale approval",
                    "completed": False,
                    "steps": 3,
                    "error": "Planner crashed after approval cleanup.",
                    "started_at": 200.0,
                    "finished_at": 201.0,
                }
            ),
            encoding="utf-8",
        )
        (failed_dir / "execution_state.json").write_text(json.dumps(stale_state), encoding="utf-8")

        runs = {item["id"]: item for item in list_runs(run_root, limit=10)}
        completed_details = load_run_details(run_root, "20260409_000006_completed_stale_review")
        failed_details = load_run_details(run_root, "20260409_000007_failed_stale_review")

        assert runs["20260409_000006_completed_stale_review"]["requires_human"] is False
        assert runs["20260409_000006_completed_stale_review"]["can_resume"] is False
        assert runs["20260409_000006_completed_stale_review"]["resume_mode"] is None
        assert completed_details is not None
        assert completed_details["requires_human"] is False
        assert completed_details["can_resume"] is False
        assert completed_details["resume_mode"] is None

        assert runs["20260409_000007_failed_stale_review"]["requires_human"] is False
        assert runs["20260409_000007_failed_stale_review"]["can_resume"] is True
        assert runs["20260409_000007_failed_stale_review"]["resume_mode"] == "execution_state"
        assert failed_details is not None
        assert failed_details["requires_human"] is False
        assert failed_details["can_resume"] is True
        assert failed_details["resume_mode"] == "execution_state"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_history_marks_cancelled_review_with_saved_state_as_resumable():
    scratch_root = Path("test_history_artifacts")
    run_root = scratch_root / uuid.uuid4().hex
    run_dir = run_root / "20260409_000008_cancelled_review"
    run_dir.mkdir(parents=True, exist_ok=True)
    execution_state = {
        "task": "resume a cancelled review",
        "orchestration_phase": "plan_review",
        "pending_decision": None,
        "app_context": {"plan_review_status": "pending"},
        "stage_decisions": [
            {
                "decision_type": "plan_review",
                "status": "cancelled",
                "risk_level": "high",
                "summary": "plan_review cancelled before approval.",
            }
        ],
        "task_graph": {
            "task": "resume a cancelled review",
            "subgoals": [
                {
                    "id": "subgoal_01",
                    "title": "Continue reviewed task",
                    "goal": "Continue reviewed task",
                    "status": "pending",
                }
            ],
        },
    }

    try:
        (run_dir / "summary.json").write_text(
            json.dumps(
                {
                    "task": "resume a cancelled review",
                    "completed": False,
                    "cancelled": True,
                    "cancel_reason": "Review later.",
                    "steps": 1,
                    "started_at": 300.0,
                    "finished_at": 301.0,
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "execution_state.json").write_text(json.dumps(execution_state), encoding="utf-8")

        runs = {item["id"]: item for item in list_runs(run_root, limit=10)}
        details = load_run_details(run_root, "20260409_000008_cancelled_review")

        assert runs["20260409_000008_cancelled_review"]["cancelled"] is True
        assert runs["20260409_000008_cancelled_review"]["requires_human"] is False
        assert runs["20260409_000008_cancelled_review"]["can_resume"] is True
        assert runs["20260409_000008_cancelled_review"]["resume_mode"] == "execution_state"
        assert details is not None
        assert details["cancelled"] is True
        assert details["requires_human"] is False
        assert details["can_resume"] is True
        assert details["resume_mode"] == "execution_state"
        assert details["execution_state"]["app_context"]["plan_review_status"] == "pending"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_history_marks_failed_saved_execution_state_as_resumable():
    scratch_root = Path("test_history_artifacts")
    run_root = scratch_root / uuid.uuid4().hex
    resumable_dir = run_root / "20260409_000005_saved_state"
    failed_dir = run_root / "20260409_000006_no_state"
    resumable_dir.mkdir(parents=True, exist_ok=True)
    failed_dir.mkdir(parents=True, exist_ok=True)

    try:
        (resumable_dir / "summary.json").write_text(
            json.dumps(
                {
                    "task": "recover saved checkout",
                    "completed": False,
                    "steps": 4,
                    "error": "Subgoal became stuck.",
                    "started_at": 100.0,
                    "finished_at": 101.0,
                }
            ),
            encoding="utf-8",
        )
        (resumable_dir / "execution_state.json").write_text(
            json.dumps(
                {
                    "task_graph": {
                        "task": "recover saved checkout",
                        "subgoals": [{"id": "subgoal_01", "title": "Recover checkout"}],
                    }
                }
            ),
            encoding="utf-8",
        )
        (failed_dir / "summary.json").write_text(
            json.dumps(
                {
                    "task": "failed before planning",
                    "completed": False,
                    "steps": 1,
                    "error": "Failed before a plan was saved.",
                    "started_at": 200.0,
                    "finished_at": 201.0,
                }
            ),
            encoding="utf-8",
        )

        runs = {item["id"]: item for item in list_runs(run_root, limit=10)}
        resumable_details = load_run_details(run_root, "20260409_000005_saved_state")
        failed_details = load_run_details(run_root, "20260409_000006_no_state")

        assert runs["20260409_000005_saved_state"]["can_resume"] is True
        assert runs["20260409_000005_saved_state"]["resume_mode"] == "execution_state"
        assert runs["20260409_000006_no_state"]["can_resume"] is False
        assert runs["20260409_000006_no_state"]["resume_mode"] is None
        assert resumable_details is not None
        assert failed_details is not None
        assert resumable_details["can_resume"] is True
        assert resumable_details["resume_mode"] == "execution_state"
        assert failed_details["can_resume"] is False
        assert failed_details["resume_mode"] is None
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def test_history_overview_includes_lightweight_execution_state_summary():
    scratch_root = Path("test_history_artifacts")
    run_root = scratch_root / uuid.uuid4().hex
    run_dir = run_root / "20260409_000007_recoverable_state"
    run_dir.mkdir(parents=True, exist_ok=True)

    try:
        (run_dir / "summary.json").write_text(
            json.dumps(
                {
                    "task": "recover the blocked route",
                    "completed": False,
                    "steps": 3,
                    "error": "The route stalled before completion.",
                    "started_at": 300.0,
                    "finished_at": 301.0,
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "execution_state.json").write_text(
            json.dumps(
                {
                    "task_graph": {
                        "task": "recover the blocked route",
                        "subgoals": [
                            {"id": "subgoal_01", "title": "Recover blocked page", "status": "blocked"},
                            {"id": "subgoal_02", "title": "Continue local notes", "status": "pending"},
                        ],
                    },
                    "last_step": {
                        "intent": "Click the continue button after repair.",
                        "capability": "browser_dom",
                        "risk_level": "medium",
                        "surface_kind": "managed_aoryn_browser",
                        "actions": [{"type": "browser_dom_click", "selector": "#continue"}],
                    },
                    "last_verification": {
                        "status": "partial_progress",
                        "failure_kind": "needs_more_evidence",
                        "message": "The page recovered but final evidence is incomplete.",
                        "evidence": [{"kind": "selector", "selector": "#continue"}],
                    },
                    "evidence_ledger": [
                        {
                            "subgoal_id": "subgoal_02",
                            "capability": "browser_dom",
                            "status": "partial_progress",
                            "message": "Continue button found.",
                            "evidence": [{"kind": "selector", "selector": "#continue"}],
                        }
                    ],
                    "app_context": {"pending_repair": {"subgoal_id": "subgoal_02"}},
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "state.json").write_text(
            json.dumps(
                {
                    "current_goal": "Continue local notes",
                    "orchestration_phase": "recovering",
                    "active_specialist": "desktop_operator",
                    "current_surface_kind": "managed_aoryn_browser",
                    "last_progress_at": 300.5,
                    "plan_review_status": "approved",
                    "last_replan_reason": "The original route stalled.",
                    "verification_status": "failed",
                    "recovery_reason": "Recover blocked page",
                    "workspace_summary": {
                        "facts": [{"key": "recovery-status", "value": "Recovered enough context."}],
                        "sources": [{"title": "Local run notes", "url": "file:///run-notes.md"}],
                    },
                    "plan_health": {
                        "counts": {"total": 2, "completed": 0, "blocked": 1, "ready": 1},
                        "next_subgoal_id": "subgoal_02",
                        "autonomy": {"status": "recovering", "next_action": "repair", "can_continue": True},
                        "items": [
                            {"id": "subgoal_01", "title": "Recover blocked page", "status": "blocked"},
                            {"id": "subgoal_02", "title": "Continue local notes", "status": "pending", "is_next": True},
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )

        runs = list_runs(run_root, limit=10)
        details = load_run_details(run_root, "20260409_000007_recoverable_state")

        assert runs[0]["can_resume"] is True
        assert runs[0]["resume_mode"] == "execution_state"
        assert runs[0]["current_goal"] == "Continue local notes"
        assert runs[0]["active_specialist"] == "desktop_operator"
        assert runs[0]["current_surface_kind"] == "managed_aoryn_browser"
        assert runs[0]["last_progress_at"] == 300.5
        assert runs[0]["plan_review_status"] == "approved"
        assert runs[0]["last_replan_reason"] == "The original route stalled."
        assert runs[0]["recovery_reason"] == "Recover blocked page"
        assert runs[0]["workspace_summary"]["facts"][0]["value"] == "Recovered enough context."
        assert runs[0]["state"]["plan_review_status"] == "approved"
        assert runs[0]["state"]["workspace_summary"]["sources"][0]["title"] == "Local run notes"
        assert runs[0]["state"]["current_surface_kind"] == "managed_aoryn_browser"
        assert runs[0]["state"]["last_progress_at"] == 300.5
        assert runs[0]["state"]["plan_health"]["next_subgoal_id"] == "subgoal_02"
        assert runs[0]["state"]["task_graph"]["subgoals"][1]["title"] == "Continue local notes"
        assert runs[0]["state"]["last_step"]["actions"][0]["selector"] == "#continue"
        assert runs[0]["state"]["last_verification"]["status"] == "partial_progress"
        assert runs[0]["state"]["last_verification"]["evidence"][0]["kind"] == "selector"
        assert runs[0]["state"]["evidence_ledger"][0]["status"] == "partial_progress"
        assert details is not None
        assert details["execution_state"]["task_graph"]["subgoals"][0]["title"] == "Recover blocked page"
        assert details["state"]["plan_health"]["autonomy"]["next_action"] == "repair"
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


def test_history_preview_image_supports_common_screenshot_formats():
    scratch_root = Path("test_history_artifacts")
    run_root = scratch_root / uuid.uuid4().hex
    run_dir = run_root / "20260409_000003_webp"
    run_dir.mkdir(parents=True, exist_ok=True)

    try:
        (run_dir / "summary.json").write_text(
            json.dumps(
                {
                    "task": "webp screenshot",
                    "completed": True,
                    "steps": 1,
                    "started_at": 300.0,
                    "finished_at": 301.0,
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "step_01.webp").write_bytes(b"fake-webp")

        runs = list_runs(run_root, limit=10)

        assert runs[0]["preview_image"] == "step_01.webp"
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)
