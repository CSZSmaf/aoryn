from pathlib import Path

from desktop_agent.actions import Action, PlanResult
from desktop_agent.capabilities import (
    CapabilityAdapter,
    CapabilityExecutor,
    CapabilityRegistry,
    build_capability_registry,
    infer_step_risk_level,
)
from desktop_agent.config import AgentConfig
from desktop_agent.drivers import build_driver_registry
from desktop_agent.orchestrator import TaskOrchestrator, task_graph_is_ambiguous, task_graph_risk_level
from desktop_agent.planner import TaskGraphPlanner, classify_task_intent
from desktop_agent.recipes import TaskRecipeMemory, build_recipe_from_state
from desktop_agent.workflow import (
    EvidenceRequirement,
    ExecutionState,
    PendingDecision,
    StepProposal,
    Subgoal,
    TaskGraph,
    VerificationResult,
    WorldModel,
    build_execution_plan_summary,
)


class _PlannerStub:
    def plan(self, task, screenshot_path, history, environment=None):
        if "login" in task.lower():
            return PlanResult(
                status_summary="Click the login button.",
                done=True,
                actions=[Action.from_dict({"type": "browser_dom_click", "text": "Login"})],
            )
        return PlanResult(
            status_summary="Open the browser.",
            done=True,
            actions=[Action.from_dict({"type": "browser_open", "text": "https://openai.com"})],
        )


def test_task_graph_planner_splits_generic_multi_step_task():
    planner = TaskGraphPlanner(AgentConfig())

    graph = planner.plan("open browser and search for python packaging guide and bookmark the best page")

    assert graph.task == "open browser and search for python packaging guide and bookmark the best page"
    assert len(graph.subgoals) >= 2
    assert graph.subgoals[0].id == "subgoal_01"
    assert graph.subgoals[0].success_condition
    assert graph.dependencies.get("subgoal_01") == []
    assert graph.dependencies.get("subgoal_02") == ["subgoal_01"]
    assert graph.completion_summary


def test_task_graph_planner_keeps_plain_chinese_search_as_search_goal():
    planner = TaskGraphPlanner(AgentConfig())

    graph = planner.plan("搜索体育方面新闻")

    assert len(graph.subgoals) == 1
    assert graph.subgoals[0].title == "search for 体育方面新闻"
    assert "shopping" not in graph.subgoals[0].title.lower()


def test_task_intent_classifies_plain_chinese_search_as_information_search():
    intent = classify_task_intent("\u641c\u7d22\u4f53\u80b2\u65b9\u9762\u65b0\u95fb")

    assert intent.task_type == "information_search"
    assert intent.domain == "web"
    assert "browser_dom" in intent.preferred_capabilities
    assert intent.requires_clarification is False


def test_task_intent_classifies_explicit_chinese_shopping():
    intent = classify_task_intent(
        "\u5728\u8d2d\u7269\u7f51\u7ad9\u641c\u7d22\u9ad8\u6027\u4ef7\u6bd4\u7537\u6027\u88e4\u5b50"
    )

    assert intent.task_type == "shopping"
    assert intent.domain == "web"
    assert intent.risk_level == "medium"


def test_chinese_high_risk_terms_are_detected_consistently():
    intent = classify_task_intent("\u8d2d\u4e70\u4e00\u4ef6\u5546\u54c1\u5e76\u4ed8\u6b3e")

    assert intent.risk_level == "high"

    graph = TaskGraphPlanner(AgentConfig()).plan("\u8d2d\u4e70\u4e00\u4ef6\u5546\u54c1\u5e76\u4ed8\u6b3e")
    assert task_graph_risk_level(graph) == "high"
    assert any(subgoal.risk_level == "high" for subgoal in graph.subgoals)

    low_labeled_graph = TaskGraph(
        task="\u767b\u9646\u5e76\u8f93\u5165\u9a8c\u8bc1\u7801",
        subgoals=[
            Subgoal(
                id="subgoal_01",
                title="\u767b\u9646\u5e76\u8f93\u5165\u9a8c\u8bc1\u7801",
                goal="\u767b\u9646\u5e76\u8f93\u5165\u9a8c\u8bc1\u7801",
                risk_level="low",
            )
        ],
        dependencies={"subgoal_01": []},
        intent={"risk_level": "low", "ambiguity": "low"},
    )
    assert task_graph_risk_level(low_labeled_graph) == "high"

    step_risk = infer_step_risk_level(
        "\u70b9\u51fb\u4ed8\u6b3e\u5e76\u63d0\u4ea4\u8ba2\u5355",
        [Action.from_dict({"type": "browser_dom_click", "text": "\u4ed8\u6b3e"})],
    )
    assert step_risk == "high"


def test_task_graph_planner_splits_research_summary_goal():
    planner = TaskGraphPlanner(AgentConfig())

    graph = planner.plan("\u641c\u7d22\u4f53\u80b2\u65b9\u9762\u65b0\u95fb\u5e76\u603b\u7ed3\u4e09\u6761")

    assert graph.intent["task_type"] == "research_summary"
    assert len(graph.subgoals) == 2
    assert graph.subgoals[0].title == "search for \u4f53\u80b2\u65b9\u9762\u65b0\u95fb"
    assert "\u603b\u7ed3" in graph.subgoals[1].title
    assert graph.subgoals[1].prerequisites == ["subgoal_01"]


def test_task_graph_planner_marks_ambiguous_task_for_clarification():
    planner = TaskGraphPlanner(AgentConfig())

    graph = planner.plan("\u5904\u7406\u4e00\u4e0b")

    assert graph.intent["requires_clarification"] is True
    assert graph.subgoals[0].goal_type == "clarify"
    assert graph.subgoals[0].retry_budget == 0


def test_task_graph_planner_limits_long_workflows_to_stage_goals():
    planner = TaskGraphPlanner(AgentConfig(complex_task_planning="heuristic", max_task_subgoals=4))

    graph = planner.plan(
        "open browser then search for release notes then copy the result then open notepad "
        "then paste the summary then save the note then close the window"
    )

    assert len(graph.subgoals) == 4
    assert graph.subgoals[-1].title.startswith("Complete remaining requested work:")
    assert all(subgoal.capability_preference for subgoal in graph.subgoals)
    assert all(subgoal.completion_evidence for subgoal in graph.subgoals)


def test_task_graph_from_model_payload_preserves_explicit_prerequisites():
    planner = TaskGraphPlanner(AgentConfig(complex_task_planning="model", max_task_subgoals=6))
    intent = classify_task_intent("research two sources and write a summary")

    graph = planner._task_graph_from_model_payload(
        task="research two sources and write a summary",
        intent=intent,
        payload={
            "subgoals": [
                {
                    "id": "collect",
                    "title": "Collect two source pages",
                    "goal_type": "read",
                    "success_condition": "Two relevant source pages are available.",
                    "risk_level": "low",
                    "prerequisites": [],
                    "completion_evidence": {"kind": "browser_text", "detail": "Two source pages were inspected."},
                },
                {
                    "id": "outline",
                    "title": "Draft a short outline",
                    "goal_type": "transform",
                    "success_condition": "A usable outline exists.",
                    "risk_level": "low",
                    "prerequisites": ["collect"],
                },
                {
                    "id": "save",
                    "title": "Save the summary",
                    "goal_type": "save",
                    "success_condition": "The summary file is saved.",
                    "risk_level": "medium",
                },
            ],
            "dependencies": {"save": ["outline"]},
        },
        world_model=None,
    )

    assert graph is not None
    assert graph.dependencies["subgoal_01"] == []
    assert graph.dependencies["subgoal_02"] == ["subgoal_01"]
    assert graph.dependencies["subgoal_03"] == ["subgoal_02"]
    assert graph.subgoals[1].prerequisites == ["subgoal_01"]
    assert graph.subgoals[2].prerequisites == ["subgoal_02"]
    assert graph.subgoals[0].completion_evidence == {
        "kind": "browser_text",
        "detail": "Two source pages were inspected.",
    }


def test_task_graph_from_model_payload_drops_unsafe_dependency_refs():
    planner = TaskGraphPlanner(AgentConfig(complex_task_planning="model"))
    intent = classify_task_intent("compare notes and save the result")

    graph = planner._task_graph_from_model_payload(
        task="compare notes and save the result",
        intent=intent,
        payload={
            "subgoals": [
                {
                    "id": "compare",
                    "title": "Compare notes",
                    "goal_type": "read",
                    "success_condition": "Notes are compared.",
                    "risk_level": "low",
                    "prerequisites": ["save"],
                },
                {
                    "id": "save",
                    "title": "Save comparison",
                    "goal_type": "save",
                    "success_condition": "Comparison is saved.",
                    "risk_level": "medium",
                    "prerequisites": ["missing", "save", "compare"],
                },
            ],
        },
        world_model=None,
    )

    assert graph is not None
    assert graph.dependencies["subgoal_01"] == []
    assert graph.dependencies["subgoal_02"] == ["subgoal_01"]


def test_task_graph_from_model_payload_does_not_allow_model_to_downgrade_risk():
    planner = TaskGraphPlanner(AgentConfig(complex_task_planning="model"))
    intent = classify_task_intent("log in and submit the payment")

    graph = planner._task_graph_from_model_payload(
        task="log in and submit the payment",
        intent=intent,
        payload={
            "subgoals": [
                {
                    "id": "login",
                    "title": "Enter the account password",
                    "goal": "Fill the password field.",
                    "goal_type": "fill",
                    "success_condition": "The password is accepted.",
                    "risk_level": "low",
                },
                {
                    "id": "pay",
                    "title": "Submit the payment",
                    "goal_type": "confirm",
                    "success_condition": "Payment is submitted.",
                    "risk_level": "low",
                    "prerequisites": ["login"],
                },
            ],
        },
        world_model=None,
    )

    assert graph is not None
    assert [subgoal.risk_level for subgoal in graph.subgoals] == ["high", "high"]
    assert task_graph_risk_level(graph) == "high"
    assert "Enter the account password" in graph.risk_points
    assert "Submit the payment" in graph.risk_points


def test_task_graph_from_model_payload_keeps_metadata_aligned_when_limited():
    planner = TaskGraphPlanner(AgentConfig(complex_task_planning="model", max_task_subgoals=3))
    intent = classify_task_intent("complete a long research workflow")

    graph = planner._task_graph_from_model_payload(
        task="complete a long research workflow",
        intent=intent,
        payload={
            "subgoals": [
                {
                    "id": "open",
                    "title": "Open research page",
                    "goal_type": "navigate",
                    "success_condition": "Research page is open.",
                    "capability_preference": "browser_dom",
                    "risk_level": "low",
                    "completion_evidence": {"kind": "browser_url_contains", "value": "research"},
                },
                {
                    "id": "collect",
                    "title": "Collect source notes",
                    "goal_type": "extract",
                    "success_condition": "Source notes are collected.",
                    "capability_preference": "browser_dom",
                    "risk_level": "low",
                    "prerequisites": ["open"],
                },
                {
                    "id": "outline",
                    "title": "Build an outline",
                    "goal_type": "transform",
                    "success_condition": "Outline exists.",
                    "capability_preference": "office_com",
                    "risk_level": "low",
                    "prerequisites": ["collect"],
                },
                {
                    "id": "draft",
                    "title": "Draft the report",
                    "goal_type": "fill",
                    "success_condition": "Report draft exists.",
                    "capability_preference": "office_com",
                    "risk_level": "low",
                    "prerequisites": ["outline"],
                },
                {
                    "id": "save",
                    "title": "Save final report",
                    "goal_type": "save",
                    "success_condition": "Report is saved.",
                    "capability_preference": "filesystem",
                    "risk_level": "medium",
                    "prerequisites": ["draft"],
                    "completion_evidence": {"kind": "file_observation", "detail": "Saved report exists."},
                },
            ],
            "dependencies": {"save": ["draft"]},
        },
        world_model=None,
    )

    assert graph is not None
    assert [subgoal.title for subgoal in graph.subgoals] == [
        "Open research page",
        "Collect source notes",
        "Complete remaining requested work: Build an outline; Draft the report; Save final report",
    ]
    assert graph.subgoals[0].success_condition == "Research page is open."
    assert graph.subgoals[1].success_condition == "Source notes are collected."
    assert graph.subgoals[2].success_condition != "Report is saved."
    assert graph.subgoals[2].capability_preference == "browser_dom"
    assert graph.subgoals[2].completion_evidence != {"kind": "file_observation", "detail": "Saved report exists."}
    assert graph.dependencies["subgoal_01"] == []
    assert graph.dependencies["subgoal_02"] == ["subgoal_01"]
    assert graph.dependencies["subgoal_03"] == ["subgoal_02"]


def test_task_graph_planner_handles_cross_app_research_write_workflow():
    planner = TaskGraphPlanner(AgentConfig(complex_task_planning="heuristic"))

    graph = planner.plan("\u641c\u7d22\u4f53\u80b2\u65b9\u9762\u65b0\u95fb\u5e76\u603b\u7ed3\u4e09\u6761\u7136\u540e\u5199\u5165\u8bb0\u4e8b\u672c")

    assert graph.intent["task_type"] in {"research_summary", "multi_step_workflow"}
    assert len(graph.subgoals) >= 2
    assert graph.subgoals[0].capability_preference == "browser_dom"
    assert any("\u603b\u7ed3" in subgoal.title or "write" in subgoal.title.lower() for subgoal in graph.subgoals)


def test_task_graph_planner_contextualizes_close_follow_up_for_calculator():
    planner = TaskGraphPlanner(AgentConfig(complex_task_planning="heuristic"))

    graph = planner.plan("打开计算器计算3加5之后关闭")

    assert len(graph.subgoals) >= 2
    assert graph.subgoals[0].title == "打开计算器计算3加5"
    assert graph.subgoals[1].title == "关闭计算器"


def test_task_graph_planner_expands_wait_then_close_for_calculator():
    planner = TaskGraphPlanner(AgentConfig(complex_task_planning="heuristic"))

    graph = planner.plan("打开计算器计算3加5之后等5秒关闭")

    assert len(graph.subgoals) >= 3
    assert graph.subgoals[0].title == "打开计算器计算3加5"
    assert graph.subgoals[1].title == "等5秒"
    assert graph.subgoals[2].title == "关闭计算器"


def test_task_graph_planner_keeps_wait_seconds_as_single_subgoal():
    planner = TaskGraphPlanner(AgentConfig(complex_task_planning="heuristic"))

    graph = planner.plan("open notepad and type smoke test then wait 1 seconds then close notepad")

    titles = [subgoal.title for subgoal in graph.subgoals]
    assert titles == ["open notepad", "open notepad and type smoke test", "wait 1 seconds", "close notepad"]
    assert all(title != "s" for title in titles)
    assert graph.subgoals[2].completion_evidence == {
        "kind": "action_executed",
        "detail": "The wait action finished for: wait 1 seconds",
    }


def test_task_graph_planner_contextualizes_calculator_expression_follow_up():
    planner = TaskGraphPlanner(AgentConfig(complex_task_planning="heuristic"))

    graph = planner.plan("open calculator then calculate 2+3 then wait 1 seconds then close")

    assert [subgoal.title for subgoal in graph.subgoals] == [
        "open calculator",
        "open calculator and calculate 2+3",
        "wait 1 seconds",
        "close calculator",
    ]
    assert graph.subgoals[1].capability_preference == "windows_uia"
    assert graph.subgoals[1].completion_evidence == {
        "kind": "action_executed",
        "detail": "The calculator expression was submitted for: open calculator and calculate 2+3",
    }


def test_task_graph_planner_preserves_shopping_initial_step_for_follow_ups():
    planner = TaskGraphPlanner(AgentConfig(complex_task_planning="heuristic"))

    graph = planner.plan(
        "shop for high-value men's pants on amazon and sort by customer review and filter by price range"
    )

    assert [subgoal.title for subgoal in graph.subgoals] == [
        "shop for high-value men's pants on amazon",
        "sort by customer review",
        "filter by price range",
    ]
    assert all(subgoal.capability_preference == "browser_dom" for subgoal in graph.subgoals)
    assert graph.subgoals[1].completion_evidence == {
        "kind": "action_executed",
        "detail": "The browser follow-up action was submitted for: sort by customer review",
    }
    assert graph.subgoals[2].completion_evidence == {
        "kind": "action_executed",
        "detail": "The browser follow-up action was submitted for: filter by price range",
    }


def test_browser_capability_uses_overall_task_to_advance_shopping_follow_up():
    task = "shop for high-value men's pants on amazon and sort by customer review and filter by price range"
    config = AgentConfig(complex_task_planning="heuristic")
    graph = TaskGraphPlanner(config).plan(task)
    graph.subgoals[0].status = "completed"
    state = ExecutionState(task=task, run_id="demo", task_graph=graph)
    state.memory.append(
        "Open shopping results for high-value men's pants on amazon. Then continue with: "
        "sort by customer review. Remaining: filter by price range."
    )
    world_model = WorldModel(
        browser_snapshot={"url": "https://www.amazon.com/s?k=high-value+men%27s+pants", "title": "Amazon"},
        active_app="browser",
        active_window_title="Aoryn Browser",
    )
    executor = CapabilityExecutor(
        config=config,
        planner=_PlannerStub(),
        registry=build_capability_registry(),
        driver_registry=build_driver_registry(),
    )

    step = executor.propose_step(execution_state=state, world_model=world_model)

    assert step.capability == "browser_dom"
    assert step.actions[0].type == "browser_dom_click"
    assert step.actions[0].text == "customer review"
    assert "follow-up step 1/2" in step.intent


def test_task_graph_planner_routes_open_word_write_essay_to_authoring():
    planner = TaskGraphPlanner(AgentConfig(complex_task_planning="heuristic"))

    graph = planner.plan("\u6253\u5f00Word\u5199\u4e00\u7bc7\u4f5c\u6587")

    assert graph.intent["task_type"] == "document_authoring"
    assert len(graph.subgoals) == 1
    assert graph.subgoals[0].title == "\u64b0\u5199\u4f5c\u6587\u5230 Word"
    assert graph.subgoals[0].goal_type == "fill"
    assert graph.subgoals[0].capability_preference == "document_authoring"


def test_task_graph_planner_contextualizes_save_follow_up_for_notepad():
    planner = TaskGraphPlanner(AgentConfig(complex_task_planning="heuristic"))

    graph = planner.plan("open notepad, type hello, then save as notes.txt")

    assert [subgoal.title for subgoal in graph.subgoals] == [
        "open notepad",
        "open notepad and type hello",
        "open notepad and save as notes.txt",
    ]
    assert graph.subgoals[2].goal_type == "save"
    assert graph.subgoals[2].completion_evidence == {
        "kind": "file_observation",
        "detail": "A file or saved artifact is observed for: open notepad and save as notes.txt",
    }


def test_desktop_app_open_prefers_windows_capability_over_browser():
    config = AgentConfig(complex_task_planning="heuristic")
    graph = TaskGraphPlanner(config).plan("open calculator then wait 1 seconds then close calculator")
    state = ExecutionState(task=graph.task, run_id="demo", task_graph=graph)
    world_model = WorldModel(screenshot_path=Path("demo.png"), structured_sources=["windows_env"])
    executor = CapabilityExecutor(
        config=config,
        planner=_PlannerStub(),
        registry=build_capability_registry(),
        driver_registry=build_driver_registry(),
    )

    ranked = executor.rank_capabilities(
        subgoal=graph.subgoals[0],
        world_model=world_model,
        execution_state=state,
    )

    assert ranked[0][0].name == "windows_uia"
    assert next(score for capability, score in ranked if capability.name == "browser_dom") < ranked[0][1]


def test_task_graph_planner_keeps_desktop_app_context_for_follow_up_actions():
    planner = TaskGraphPlanner(AgentConfig(complex_task_planning="heuristic"))

    graph = planner.plan("打开微信然后搜索张三然后点击聊天之后关闭")

    titles = [subgoal.title for subgoal in graph.subgoals]
    assert titles[:4] == ["打开微信", "打开微信并搜索张三", "打开微信并点击聊天", "关闭微信"]
    assert graph.subgoals[1].capability_preference == "windows_uia"
    assert graph.subgoals[2].capability_preference == "windows_uia"


def test_task_graph_planner_keeps_english_desktop_app_context_for_follow_up_actions():
    planner = TaskGraphPlanner(AgentConfig(complex_task_planning="heuristic"))

    graph = planner.plan("open slack then search for Alice then click New message")

    titles = [subgoal.title for subgoal in graph.subgoals]
    assert titles[:3] == ["open slack", "open slack and search for Alice", "open slack and click New message"]
    assert all(subgoal.capability_preference == "windows_uia" for subgoal in graph.subgoals[:3])


def test_task_graph_planner_routes_generic_app_close_to_desktop():
    planner = TaskGraphPlanner(AgentConfig(complex_task_planning="heuristic"))

    graph = planner.plan("open slack then search for Alice then click New message then close")

    titles = [subgoal.title for subgoal in graph.subgoals]
    assert titles[:4] == [
        "open slack",
        "open slack and search for Alice",
        "open slack and click New message",
        "close slack",
    ]
    assert all(subgoal.capability_preference == "windows_uia" for subgoal in graph.subgoals[:4])


def test_pending_decision_round_trips_decision_type():
    from desktop_agent.workflow import PendingDecision

    decision = PendingDecision.from_dict(
        {
            "id": "plan-1",
            "summary": "Review plan",
            "reason": "The plan is medium risk.",
            "risk_level": "medium",
            "decision_type": "plan_review",
        }
    )

    assert decision.decision_type == "plan_review"
    assert decision.to_dict()["decision_type"] == "plan_review"


def test_pending_decision_accepts_stage_review_type():
    decision = PendingDecision.from_dict(
        {
            "id": "stage-1",
            "summary": "Review replanned stage",
            "reason": "Risk increased after recovery.",
            "risk_level": "high",
            "decision_type": "stage_review",
        }
    )

    assert decision.decision_type == "stage_review"
    assert decision.to_dict()["decision_type"] == "stage_review"


def test_workflow_from_dict_parses_string_boolean_flags():
    requirement = EvidenceRequirement.from_dict({"kind": "visible_text", "value": "Done", "required": "false"})
    proposal = StepProposal.from_dict(
        {
            "intent": "Click the visible button.",
            "requires_approval": "false",
            "completes_subgoal": "false",
            "expected_evidence": [{"kind": "visible_text", "value": "Done", "required": "false"}],
        }
    )
    approved_proposal = StepProposal.from_dict(
        {
            "intent": "Submit the final form.",
            "requires_approval": "true",
            "completes_subgoal": "true",
        }
    )
    verification = VerificationResult.from_dict({"success": "false", "message": "Still waiting."})
    state = ExecutionState.from_dict(
        {
            "task": "continue a saved workflow",
            "run_id": "run-string-bools",
            "completed": "false",
            "task_graph": {
                "task": "continue a saved workflow",
                "subgoals": [
                    {
                        "id": "subgoal_01",
                        "title": "Continue the saved workflow",
                        "status": "pending",
                    }
                ],
            },
            "last_step": proposal.to_dict(),
            "last_verification": {"success": "false", "message": "Still waiting."},
        }
    )

    assert requirement.required is False
    assert proposal.requires_approval is False
    assert proposal.completes_subgoal is False
    assert proposal.expected_evidence[0].required is False
    assert approved_proposal.requires_approval is True
    assert approved_proposal.completes_subgoal is True
    assert verification.success is False
    assert verification.status == "failed"
    assert state.completed is False
    assert state.last_step is not None
    assert state.last_step.requires_approval is False
    assert state.last_step.completes_subgoal is False
    assert state.last_verification is not None
    assert state.last_verification.success is False
    assert build_execution_plan_summary(state)["plan_health"]["autonomy"]["status"] == "ready"


def test_task_graph_ambiguity_parses_string_clarification_flag():
    graph = TaskGraph(
        task="use a concrete saved plan",
        subgoals=[Subgoal(id="subgoal_01", title="Use the concrete saved plan")],
        intent={"ambiguity": "low", "requires_clarification": "false"},
    )

    assert task_graph_is_ambiguous(graph) is False
    graph.intent["requires_clarification"] = "true"
    assert task_graph_is_ambiguous(graph) is True


def test_execution_state_round_trips_workspace_and_orchestration_fields():
    graph = TaskGraphPlanner(AgentConfig()).plan("search documentation and summarize it")
    state = ExecutionState(task=graph.task, run_id="demo", task_graph=graph)
    state.orchestration_phase = "stage_ready"
    state.active_specialist = "browser_research"
    state.failure_budget = {"subgoal_01": 2}
    state.last_replan_reason = "selector became stale"
    state.workspace.add_note("Collected source candidates.")
    state.workspace.add_evidence({"subgoal_id": "subgoal_01", "status": "success", "specialist": "browser_research"})

    restored = ExecutionState.from_dict(state.to_dict())
    summary = build_execution_plan_summary(restored)

    assert restored.orchestration_phase == "stage_ready"
    assert restored.active_specialist == "browser_research"
    assert restored.failure_budget["subgoal_01"] == 2
    assert restored.workspace.notes == ["Collected source candidates."]
    assert summary["workspace_summary"]["evidence"][0]["specialist"] == "browser_research"
    assert summary["last_replan_reason"] == "selector became stale"


def test_execution_summary_reports_next_continuable_subgoal_for_frontend():
    graph = TaskGraph(
        task="recover and continue",
        subgoals=[
            Subgoal(
                id="subgoal_01",
                title="Recover blocked page",
                status="blocked",
                attempts=3,
                max_attempts=3,
                capability_preference="browser_dom",
            ),
            Subgoal(
                id="subgoal_02",
                title="Continue with independent local notes",
                status="pending",
                capability_preference="desktop_gui",
            ),
        ],
        dependencies={"subgoal_01": [], "subgoal_02": []},
    )
    state = ExecutionState(task=graph.task, run_id="demo", task_graph=graph)
    state.failure_budget = {"subgoal_01": 0, "subgoal_02": 2}

    summary = build_execution_plan_summary(state)

    assert summary["current_subgoal"]["id"] == "subgoal_02"
    assert summary["plan_health"]["next_subgoal_id"] == "subgoal_02"
    assert summary["plan_health"]["counts"]["blocked"] == 1
    assert summary["plan_health"]["counts"]["exhausted"] == 1
    assert summary["plan_health"]["items"][0]["exhausted"] is True
    assert summary["plan_health"]["items"][1]["is_next"] is True


def test_execution_summary_reports_autonomy_readiness_for_frontend():
    graph = TaskGraph(
        task="review before acting",
        subgoals=[
            Subgoal(
                id="subgoal_01",
                title="Open the target page",
                status="pending",
                capability_preference="browser_dom",
                completion_evidence={"kind": "browser_url_contains", "value": "example.com"},
            )
        ],
        dependencies={"subgoal_01": []},
    )
    state = ExecutionState(
        task=graph.task,
        run_id="demo",
        task_graph=graph,
        app_context={"plan_review_status": "pending"},
    )

    summary = build_execution_plan_summary(state)

    autonomy = summary["plan_health"]["autonomy"]
    assert summary["plan_review_status"] == "pending"
    assert autonomy["status"] == "review_required"
    assert autonomy["can_continue"] is False
    assert autonomy["requires_review"] is True
    assert autonomy["next_action"] == "approve_plan"
    assert autonomy["next_subgoal_id"] == "subgoal_01"


def test_cancelled_stage_review_still_requires_review_on_resume():
    graph = TaskGraph(
        task="resume cancelled stage review",
        subgoals=[
            Subgoal(
                id="subgoal_01",
                title="Submit the recovered form",
                status="pending",
                risk_level="high",
                capability_preference="browser_dom",
            )
        ],
        dependencies={"subgoal_01": []},
    )
    state = ExecutionState(
        task=graph.task,
        run_id="demo",
        task_graph=graph,
        app_context={"stage_review_status": "cancelled"},
    )

    class _UnusedGraphPlanner:
        def plan(self, task, history=None, world_model=None):
            return graph

    class _UnusedCapabilityExecutor:
        def observe(self, world_model):
            return []

    orchestrator = TaskOrchestrator(
        config=AgentConfig(),
        task_graph_planner=_UnusedGraphPlanner(),
        capability_executor=_UnusedCapabilityExecutor(),
        recipe_memory=TaskRecipeMemory(path=Path("test_artifacts") / "unused-recipes.json"),
    )

    summary = build_execution_plan_summary(state)

    assert orchestrator.pending_review_type(state) == "stage_review"
    assert summary["stage_review_status"] == "cancelled"
    assert summary["plan_health"]["autonomy"]["status"] == "review_required"
    assert summary["plan_health"]["autonomy"]["requires_review"] is True
    assert summary["plan_health"]["autonomy"]["next_action"] == "approve_stage"


def test_execution_summary_treats_saved_step_approval_phase_as_review_required():
    graph = TaskGraph(
        task="resume cancelled step approval",
        subgoals=[
            Subgoal(
                id="subgoal_01",
                title="Click the guarded confirmation",
                status="pending",
                risk_level="high",
                capability_preference="desktop_gui",
                completion_evidence={"kind": "ui_state", "value": "confirmation clicked"},
            )
        ],
        dependencies={"subgoal_01": []},
    )
    state = ExecutionState(task=graph.task, run_id="demo", task_graph=graph)
    state.orchestration_phase = "awaiting_approval"

    summary = build_execution_plan_summary(state)

    autonomy = summary["plan_health"]["autonomy"]
    assert autonomy["status"] == "review_required"
    assert autonomy["can_continue"] is False
    assert autonomy["requires_review"] is True
    assert autonomy["requires_user"] is False
    assert autonomy["next_action"] == "approve_step"
    assert autonomy["next_subgoal_id"] == "subgoal_01"


def test_execution_summary_treats_blocked_phase_as_failure_inspection():
    graph = TaskGraph(
        task="recover blocked action",
        subgoals=[
            Subgoal(
                id="subgoal_01",
                title="Retry the stale click",
                status="pending",
                capability_preference="browser_dom",
                completion_evidence={"kind": "ui_state", "value": "clicked"},
            )
        ],
        dependencies={"subgoal_01": []},
    )
    state = ExecutionState(
        task=graph.task,
        run_id="demo",
        task_graph=graph,
        app_context={"recovery_reason": "The click target became stale."},
    )
    state.orchestration_phase = "blocked"

    summary = build_execution_plan_summary(state)

    autonomy = summary["plan_health"]["autonomy"]
    assert autonomy["status"] == "blocked"
    assert autonomy["can_continue"] is False
    assert autonomy["requires_review"] is False
    assert autonomy["requires_user"] is False
    assert autonomy["next_action"] == "inspect_failure"
    assert autonomy["next_subgoal_id"] == "subgoal_01"
    assert autonomy["blockers"] == ["The click target became stale."]


def test_orchestrator_records_active_subgoal_for_frontend_and_executor():
    graph = TaskGraph(
        task="continue independent work",
        subgoals=[
            Subgoal(
                id="subgoal_01",
                title="Exhausted blocked work",
                status="blocked",
                attempts=3,
                max_attempts=3,
                capability_preference="browser_dom",
            ),
            Subgoal(
                id="subgoal_02",
                title="Continue independent work",
                status="pending",
                capability_preference="desktop_gui",
            ),
        ],
        dependencies={"subgoal_01": [], "subgoal_02": []},
    )
    state = ExecutionState(
        task=graph.task,
        run_id="demo",
        task_graph=graph,
        failure_budget={"subgoal_01": 0, "subgoal_02": 2},
    )

    class _UnusedGraphPlanner:
        def plan(self, task, history=None, world_model=None):
            return graph

    class _UnusedCapabilityExecutor:
        def observe(self, world_model):
            return []

    orchestrator = TaskOrchestrator(
        config=AgentConfig(),
        task_graph_planner=_UnusedGraphPlanner(),
        capability_executor=_UnusedCapabilityExecutor(),
        recipe_memory=TaskRecipeMemory(path=Path("test_artifacts") / "unused-recipes.json"),
    )

    selected = orchestrator.prepare_stage(state=state, world_model=WorldModel())
    summary = build_execution_plan_summary(state)

    assert selected is not None
    assert selected.id == "subgoal_02"
    assert state.app_context["active_subgoal_id"] == "subgoal_02"
    assert state.current_subgoal().id == "subgoal_02"
    assert summary["current_subgoal"]["id"] == "subgoal_02"
    assert summary["plan_health"]["next_subgoal_id"] == "subgoal_02"


def test_capability_executor_prefers_browser_capability_for_web_subgoal():
    config = AgentConfig()
    graph = TaskGraphPlanner(config).plan("visit openai.com and click login")
    state = ExecutionState(task=graph.task, run_id="demo", task_graph=graph)
    world_model = WorldModel(
        screenshot_path=Path("demo.png"),
        browser_snapshot={"url": "https://openai.com", "title": "OpenAI", "text": "Login"},
        active_app="browser",
        active_window_title="Microsoft Edge",
    )
    state.world_model = world_model
    executor = CapabilityExecutor(
        config=config,
        planner=_PlannerStub(),
        registry=build_capability_registry(),
        driver_registry=build_driver_registry(),
    )

    step = executor.propose_step(execution_state=state, world_model=world_model)

    assert step.capability == "browser_dom"
    assert step.surface_kind == "managed_aoryn_browser"
    assert step.actions
    assert step.expected_evidence
    assert step.progress_signals
    assert step.repair_strategy
    assert step.primary_anchor is not None
    assert step.fallback_anchors
    assert step.rationale
    assert "desktop_gui" in step.fallbacks
    assert state.app_context["capability_ranking"][0]["name"] == "browser_dom"


def test_step_proposal_tracks_subgoal_completion_from_plan_result():
    plan = PlanResult(
        status_summary="Open the browser.",
        done=True,
        actions=[Action.from_dict({"type": "open_app_if_needed", "app": "browser"})],
    )

    proposal = StepProposal.from_plan_result(plan, capability="desktop_gui")

    assert proposal.completes_subgoal is True
    assert proposal.to_plan_result(done=proposal.completes_subgoal).done is True


def test_capability_executor_marks_guarded_shell_recipe_as_approval_required():
    config = AgentConfig()
    graph = TaskGraphPlanner(config).plan("configure a python environment")
    state = ExecutionState(task=graph.task, run_id="demo", task_graph=graph)
    world_model = WorldModel(screenshot_path=Path("demo.png"), active_window_title="Visual Studio Code")
    state.world_model = world_model
    executor = CapabilityExecutor(
        config=config,
        planner=_PlannerStub(),
        registry=build_capability_registry(),
        driver_registry=build_driver_registry(),
    )

    step = executor.propose_step(execution_state=state, world_model=world_model)

    assert step.requires_approval is True
    assert any(action.type == "shell_recipe_request" for action in step.actions)


def test_capability_executor_elevates_low_labeled_sensitive_actions_to_approval():
    class _LowRiskPasswordCapability(CapabilityAdapter):
        name = "browser_dom"

        def can_handle(self, subgoal, world_model):
            return 1.0

        def propose_step(self, *, subgoal, world_model, execution_state, config, planner):
            return StepProposal(
                intent="Fill the saved credential field.",
                actions=[
                    Action.from_dict(
                        {
                            "type": "browser_dom_fill",
                            "selector": "input[name='password']",
                            "text": "hunter2",
                        }
                    )
                ],
                capability=self.name,
                risk_level="low",
                requires_approval=False,
            )

    config = AgentConfig()
    subgoal = Subgoal(
        id="subgoal_01",
        title="Continue the account form",
        goal="Continue the account form",
        goal_type="fill",
        success_condition="The account form is ready to submit.",
        risk_level="low",
    )
    state = ExecutionState(
        task="continue the account form",
        run_id="demo",
        task_graph=TaskGraph(
            task="continue the account form",
            subgoals=[subgoal],
            dependencies={"subgoal_01": []},
        ),
    )
    world_model = WorldModel(
        screenshot_path=Path("demo.png"),
        browser_snapshot={"url": "https://example.test/account", "title": "Account", "text": "Continue"},
        active_app="browser",
        active_window_title="Microsoft Edge",
    )
    executor = CapabilityExecutor(
        config=config,
        planner=_PlannerStub(),
        registry=CapabilityRegistry([_LowRiskPasswordCapability()]),
        driver_registry=build_driver_registry(),
    )

    step = executor.propose_step(execution_state=state, world_model=world_model)

    assert infer_step_risk_level("Continue the form", step.actions) == "high"
    assert step.risk_level == "high"
    assert step.requires_approval is True


def test_capability_executor_keeps_admin_actions_approval_required_in_autonomous_mode():
    class _LowRiskAdminCapability(CapabilityAdapter):
        name = "desktop_gui"

        def can_handle(self, subgoal, world_model):
            return 1.0

        def propose_step(self, *, subgoal, world_model, execution_state, config, planner):
            return StepProposal(
                intent="Open PowerShell with administrator privileges.",
                actions=[
                    Action.from_dict(
                        {
                            "type": "open_app_if_needed",
                            "app": "PowerShell",
                            "text": "Run as administrator",
                        }
                    )
                ],
                capability=self.name,
                risk_level="low",
                requires_approval=False,
            )

    config = AgentConfig(approval_policy="autonomous")
    subgoal = Subgoal(
        id="subgoal_01",
        title="Open PowerShell with administrator privileges",
        goal="Open PowerShell with administrator privileges",
        goal_type="open_app",
        success_condition="PowerShell is open.",
        risk_level="low",
    )
    state = ExecutionState(
        task="open an elevated shell",
        run_id="demo",
        task_graph=TaskGraph(
            task="open an elevated shell",
            subgoals=[subgoal],
            dependencies={"subgoal_01": []},
        ),
    )
    world_model = WorldModel(screenshot_path=Path("demo.png"), active_window_title="Desktop")
    executor = CapabilityExecutor(
        config=config,
        planner=_PlannerStub(),
        registry=CapabilityRegistry([_LowRiskAdminCapability()]),
        driver_registry=build_driver_registry(),
    )

    step = executor.propose_step(execution_state=state, world_model=world_model)

    assert infer_step_risk_level(subgoal.title, step.actions) == "critical"
    assert infer_step_risk_level("以管理员身份打开 PowerShell", []) == "critical"
    assert step.risk_level == "critical"
    assert step.requires_approval is True
    decision = executor.build_pending_decision(step=step, subgoal=subgoal)
    assert decision.approval_policy == "autonomous"
    assert decision.requires_user_presence is True
    assert "administrator" in decision.reason
    assert "person at the screen" in (decision.operator_hint or "")
    assert decision.to_dict()["requires_user_presence"] is True


def test_repair_proposal_uses_same_risk_and_approval_finalization():
    class _LowRiskRepairCapability(CapabilityAdapter):
        name = "browser_dom"

        def can_handle(self, subgoal, world_model):
            return 1.0

        def plan_repair(
            self,
            *,
            subgoal,
            world_model,
            execution_state,
            previous_step,
            verification,
            config,
        ):
            return StepProposal(
                intent="Repair by filling the password field again.",
                actions=[
                    Action.from_dict(
                        {
                            "type": "browser_dom_fill",
                            "selector": "input[type='password']",
                            "text": "hunter2",
                        }
                    )
                ],
                capability=self.name,
                risk_level="low",
                requires_approval=False,
            )

    config = AgentConfig()
    subgoal = Subgoal(
        id="subgoal_01",
        title="Recover the account form",
        goal="Recover the account form",
        goal_type="fill",
        success_condition="The account form is ready.",
    )
    state = ExecutionState(
        task="recover the account form",
        run_id="demo",
        task_graph=TaskGraph(
            task="recover the account form",
            subgoals=[subgoal],
            dependencies={"subgoal_01": []},
        ),
        app_context={"pending_repair": {"subgoal_id": "subgoal_01"}},
        last_step=StepProposal(
            intent="Try the form.",
            actions=[Action.from_dict({"type": "browser_dom_click", "text": "Continue"})],
            capability="browser_dom",
        ),
        last_verification=VerificationResult(
            success=False,
            status="failed",
            failure_kind="verification_failed",
            message="The form did not advance.",
        ),
    )
    world_model = WorldModel(
        screenshot_path=Path("demo.png"),
        browser_snapshot={"url": "https://example.test/account", "title": "Account", "text": "Password"},
        active_app="browser",
        active_window_title="Microsoft Edge",
    )
    executor = CapabilityExecutor(
        config=config,
        planner=_PlannerStub(),
        registry=CapabilityRegistry([_LowRiskRepairCapability()]),
        driver_registry=build_driver_registry(),
    )

    step = executor.propose_step(execution_state=state, world_model=world_model)

    assert step.risk_level == "high"
    assert step.requires_approval is True
    assert step.expected_evidence
    assert step.progress_signals
    assert step.primary_anchor is not None
    assert state.current_surface_kind == "managed_aoryn_browser"


def test_verification_without_completion_evidence_does_not_auto_succeed():
    config = AgentConfig()
    executor = CapabilityExecutor(
        config=config,
        planner=_PlannerStub(),
        registry=build_capability_registry(),
        driver_registry=build_driver_registry(),
    )
    subgoal = Subgoal(
        id="subgoal_01",
        title="confirm the page changed",
        goal="confirm the page changed",
        goal_type="confirm",
        success_condition="The page visibly changes.",
        completion_evidence={"kind": "state_change", "detail": "A visible state change confirms the subgoal."},
    )
    state = ExecutionState(task="confirm the page changed", run_id="demo", task_graph=TaskGraphPlanner(config).plan("confirm the page changed"))
    state.task_graph.subgoals = [subgoal]
    before = WorldModel(screenshot_path=Path("before.png"), active_window_title="Browser", active_app="browser")
    after = WorldModel(screenshot_path=Path("after.png"), active_window_title="Browser", active_app="browser")
    step = StepProposal(
        intent="Wait for confirmation.",
        actions=[Action.from_dict({"type": "wait", "seconds": 0.1})],
        capability="desktop_gui",
        completes_subgoal=True,
    )

    result = executor.verify_step(execution_state=state, step=step, before=before, after=after)

    assert result.status == "failed"
    assert result.success is False


def test_verification_requires_required_evidence_before_completion():
    config = AgentConfig()
    executor = CapabilityExecutor(
        config=config,
        planner=_PlannerStub(),
        registry=build_capability_registry(),
        driver_registry=build_driver_registry(),
    )
    subgoal = Subgoal(
        id="subgoal_01",
        title="Complete a silent action",
        goal="Complete a silent action",
        goal_type="handoff",
        success_condition="The silent action is complete.",
    )
    state = ExecutionState(
        task="Complete a silent action",
        run_id="demo",
        task_graph=TaskGraph(task="Complete a silent action", subgoals=[subgoal], dependencies={"subgoal_01": []}),
    )
    before = WorldModel(screenshot_path=Path("before.png"), active_window_title="Editor", active_app="editor")
    after = WorldModel(screenshot_path=Path("after.png"), active_window_title="Editor", active_app="editor")
    step = StepProposal(
        intent="Run a silent action.",
        actions=[Action.from_dict({"type": "wait", "seconds": 0.1})],
        capability="desktop_gui",
        completes_subgoal=True,
    )

    result = executor.verify_step(execution_state=state, step=step, before=before, after=after)

    assert result.status == "failed"
    assert result.failure_kind == "verification_failed"
    assert "No required evidence" in (result.message or "")


def test_verification_treats_progress_without_required_evidence_as_partial():
    config = AgentConfig()
    executor = CapabilityExecutor(
        config=config,
        planner=_PlannerStub(),
        registry=build_capability_registry(),
        driver_registry=build_driver_registry(),
    )
    subgoal = Subgoal(
        id="subgoal_01",
        title="Move to the next screen",
        goal="Move to the next screen",
        goal_type="handoff",
        success_condition="The next screen is reached.",
    )
    state = ExecutionState(
        task="Move to the next screen",
        run_id="demo",
        task_graph=TaskGraph(task="Move to the next screen", subgoals=[subgoal], dependencies={"subgoal_01": []}),
    )
    before = WorldModel(screenshot_path=Path("before.png"), active_window_title="Step 1", active_app="browser")
    after = WorldModel(screenshot_path=Path("after.png"), active_window_title="Step 2", active_app="browser")
    step = StepProposal(
        intent="Advance to the next screen.",
        actions=[Action.from_dict({"type": "press", "key": "enter"})],
        capability="desktop_gui",
        completes_subgoal=True,
    )

    result = executor.verify_step(execution_state=state, step=step, before=before, after=after)

    assert result.status == "partial_progress"
    assert result.success is False
    assert "no required evidence" in (result.message or "").lower()


def test_verification_accepts_localized_calculator_window_for_active_app_evidence():
    config = AgentConfig()
    executor = CapabilityExecutor(
        config=config,
        planner=_PlannerStub(),
        registry=build_capability_registry(),
        driver_registry=build_driver_registry(),
    )
    subgoal = Subgoal(
        id="subgoal_01",
        title="打开计算器",
        goal="打开计算器",
        goal_type="navigate",
        success_condition="计算器已打开。",
        completion_evidence={"kind": "active_app_is", "value": "calculator"},
    )
    state = ExecutionState(task="打开计算器", run_id="demo", task_graph=TaskGraphPlanner(config).plan("打开计算器"))
    state.task_graph.subgoals = [subgoal]
    before = WorldModel(screenshot_path=Path("before.png"), active_window_title="Aoryn", active_app="browser")
    after = WorldModel(
        screenshot_path=Path("after.png"),
        active_window_title="MSCTFIME UI",
        active_app="msctfime ui",
        visible_windows=[{"title": "计算器", "process_name": "calc.exe"}],
    )
    step = StepProposal(
        intent="打开计算器",
        actions=[Action.from_dict({"type": "open_app_if_needed", "app": "calculator"})],
        expected_evidence=[EvidenceRequirement(kind="active_app_is", value="calculator", required=True)],
        capability="windows_uia",
        completes_subgoal=True,
    )

    result = executor.verify_step(execution_state=state, step=step, before=before, after=after)

    assert result.status == "success"
    assert result.success is True


def test_capability_ranking_penalizes_recent_failures():
    config = AgentConfig()
    graph = TaskGraphPlanner(config).plan("visit openai.com and click login")
    state = ExecutionState(task=graph.task, run_id="demo", task_graph=graph)
    world_model = WorldModel(
        screenshot_path=Path("demo.png"),
        browser_snapshot={"url": "https://openai.com", "title": "OpenAI", "text": "Login"},
        active_app="browser",
        active_window_title="Microsoft Edge",
        structured_sources=["browser_dom"],
    )
    state.capability_failures["subgoal_01:browser_dom"] = ["failed", "partial_progress"]
    executor = CapabilityExecutor(
        config=config,
        planner=_PlannerStub(),
        registry=build_capability_registry(),
        driver_registry=build_driver_registry(),
    )

    ranked = executor.rank_capabilities(
        subgoal=graph.subgoals[0],
        world_model=world_model,
        execution_state=state,
    )
    scores = {cap.name: score for cap, score in ranked}

    assert scores["browser_dom"] < 1.05


def test_orchestrator_routes_specialist_and_requests_stage_review_after_risk_increase():
    config = AgentConfig(stage_review_policy="risk_change")

    class _GraphPlanner:
        def plan(self, task, history=None, world_model=None):
            return TaskGraph(
                task=task,
                subgoals=[
                    Subgoal(
                        id="subgoal_01",
                        title="Search product details",
                        goal_type="read",
                        capability_preference="browser_dom",
                        risk_level="low",
                    )
                ],
                dependencies={"subgoal_01": []},
                intent={"task_type": "information_search", "risk_level": "low", "ambiguity": "low"},
            )

        def replan_remaining(self, execution_state, world_model, failure):
            graph = execution_state.task_graph
            graph.subgoals[0].title = "Submit the recovered form"
            graph.subgoals[0].goal = "Submit the recovered form"
            graph.subgoals[0].risk_level = "high"
            graph.risk_points = ["Submit the recovered form"]
            graph.intent = {"task_type": "multi_step_workflow", "risk_level": "high", "ambiguity": "low"}
            return graph

    class _CapabilityExecutor:
        def observe(self, world_model):
            return []

        def propose_step(self, execution_state, world_model):
            return StepProposal(intent="Search the page.", capability="browser_dom")

    orchestrator = TaskOrchestrator(
        config=config,
        task_graph_planner=_GraphPlanner(),
        capability_executor=_CapabilityExecutor(),
        recipe_memory=TaskRecipeMemory(path=Path("test_artifacts") / "unused-recipes.json"),
    )
    world_model = WorldModel(browser_snapshot={"url": "https://example.com", "title": "Example"})
    state = orchestrator.initialize_state(task="search product details", run_id="demo", world_model=world_model)

    assert state.active_specialist == "browser_research"

    changed = orchestrator.replan_remaining(
        state=state,
        world_model=world_model,
        failure=VerificationResult(success=False, status="failed", failure_kind="blocked_by_ui", message="popup"),
    )

    assert changed is True
    assert state.app_context["stage_review_status"] == "pending"
    assert orchestrator.pending_review_type(state) == "stage_review"
    assert state.last_replan_reason == "popup"


def test_recipe_records_specialist_sequence_and_sanitizes_summary():
    graph = TaskGraphPlanner(AgentConfig()).plan("search docs and summarize them")
    state = ExecutionState(task=graph.task, run_id="demo", task_graph=graph)
    state.completed = True
    for subgoal in state.task_graph.subgoals:
        subgoal.status = "completed"
    state.task_graph.completion_summary = "Saved summary from https://secret.example/token abcdefghijklmnopqrstuvwxyz123456"
    state.evidence_ledger.append(
        {
            "subgoal_id": "subgoal_01",
            "capability": "browser_dom",
            "status": "success",
            "evidence": [{"kind": "browser_text_contains"}],
        }
    )
    state.workspace.add_evidence(
        {
            "subgoal_id": "subgoal_01",
            "specialist": "browser_research",
            "capability": "browser_dom",
            "status": "success",
        }
    )

    recipe = build_recipe_from_state(state)

    assert recipe is not None
    assert recipe.specialist_sequence == ["browser_research"]
    assert recipe.verified_evidence_kinds == ["browser_text_contains"]
    assert "<url>" in (recipe.summary or "")
    assert "abcdefghijklmnopqrstuvwxyz123456" not in (recipe.summary or "")
