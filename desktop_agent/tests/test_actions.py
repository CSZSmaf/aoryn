import pytest

from desktop_agent.actions import ActionValidationError, PlanResult


def test_plan_result_parses_optional_decomposition_fields():
    plan = PlanResult.from_payload(
        {
            "status_summary": "Continue with the next sub-goal.",
            "done": False,
            "current_focus": "click login",
            "reasoning": "The page is already open, so the next visible control is login.",
            "remaining_steps": ["enter credentials", "submit the form"],
            "actions": [{"type": "browser_dom_click", "text": "login"}],
        }
    )

    assert plan.current_focus == "click login"
    assert plan.reasoning == "The page is already open, so the next visible control is login."
    assert plan.remaining_steps == ["enter credentials", "submit the form"]


def test_plan_result_rejects_invalid_remaining_steps():
    with pytest.raises(ActionValidationError):
        PlanResult.from_payload(
            {
                "status_summary": "Invalid plan",
                "done": False,
                "remaining_steps": {"step": "not-a-list"},
                "actions": [],
            }
        )


def test_plan_result_accepts_window_governance_actions():
    plan = PlanResult.from_payload(
        {
            "status_summary": "Focus Calculator before typing.",
            "done": False,
            "actions": [
                {"type": "focus_window", "title": "Calculator"},
                {"type": "minimize_window", "title": "Chat"},
                {"type": "maximize_window", "title": "Calculator"},
                {"type": "wait_for_window", "title": "Calculator", "seconds": 1.5},
            ],
        }
    )

    assert [item.type for item in plan.actions] == [
        "focus_window",
        "minimize_window",
        "maximize_window",
        "wait_for_window",
    ]


def test_plan_result_accepts_relative_click_action():
    plan = PlanResult.from_payload(
        {
            "status_summary": "Click inside Calculator using window-relative coordinates.",
            "done": False,
            "actions": [
                {
                    "type": "relative_click",
                    "title": "Calculator",
                    "relative_x": 0.5,
                    "relative_y": 0.25,
                }
            ],
        }
    )

    assert plan.actions[0].type == "relative_click"
    assert plan.actions[0].relative_x == 0.5
    assert plan.actions[0].relative_y == 0.25
