import pytest

from desktop_agent.actions import Action
from desktop_agent.capabilities import DocumentAuthoringCapability, build_capability_registry
from desktop_agent.config import AgentConfig
from desktop_agent.planner import TaskGraphPlanner
from desktop_agent.safety import ActionGuard, SafetyError
from desktop_agent.workflow import ExecutionState, Subgoal, TaskGraph, WorldModel


def _state(task: str, subgoal: Subgoal, notes: list[str] | None = None) -> ExecutionState:
    graph = TaskGraph(task=task, subgoals=[subgoal], dependencies={subgoal.id: []})
    state = ExecutionState(task=task, run_id="run_test", task_graph=graph)
    for note in notes or []:
        state.workspace.add_note(note)
    return state


def _offline_config() -> AgentConfig:
    return AgentConfig(composition_enabled=False, dry_run=True)


def test_can_handle_prefers_authoring_subgoals_over_search():
    capability = DocumentAuthoringCapability()
    author = Subgoal(id="s1", title="整理到word里", goal="整理到word里", goal_type="fill")
    search = Subgoal(id="s2", title="搜索北京旅游攻略", goal="搜索北京旅游攻略", goal_type="navigate")
    assert capability.can_handle(author, WorldModel()) >= 0.9
    assert capability.can_handle(search, WorldModel()) == 0.0


def test_propose_step_opens_editor_when_not_active():
    capability = DocumentAuthoringCapability()
    subgoal = Subgoal(id="s1", title="write a report in word", goal="write a report in word", goal_type="fill")
    state = _state("write a report in word", subgoal)
    proposal = capability.propose_step(
        subgoal=subgoal,
        world_model=WorldModel(active_app=None),
        execution_state=state,
        config=_offline_config(),
        planner=None,
    )
    assert proposal is not None
    assert proposal.actions[0].type == "open_app_if_needed"
    assert proposal.actions[0].app == "word"
    assert proposal.completes_subgoal is False


def test_propose_step_does_not_write_when_editor_is_only_visible():
    capability = DocumentAuthoringCapability()
    subgoal = Subgoal(id="s1", title="write a report in word", goal="write a report in word", goal_type="fill")
    state = _state("write a report in word", subgoal, notes=["[web] source material"])
    proposal = capability.propose_step(
        subgoal=subgoal,
        world_model=WorldModel(
            active_app="browser",
            active_window_title="Microsoft Edge",
            visible_windows=[{"title": "Document1 - Word", "process_name": "WINWORD.EXE"}],
        ),
        execution_state=state,
        config=_offline_config(),
        planner=None,
    )
    assert proposal is not None
    assert proposal.actions[0].type == "open_app_if_needed"
    assert proposal.actions[0].app == "word"
    assert proposal.completes_subgoal is False


def test_propose_step_writes_composed_document_when_editor_active():
    capability = DocumentAuthoringCapability()
    config = _offline_config()
    subgoal = Subgoal(id="s1", title="整理到word里", goal="整理到word里", goal_type="fill")
    state = _state(
        "搜索北京旅游攻略并整理到word里",
        subgoal,
        notes=["[web] 故宫、天安门是必去景点", "[web] https://example.com/beijing"],
    )
    proposal = capability.propose_step(
        subgoal=subgoal,
        world_model=WorldModel(active_app="word"),
        execution_state=state,
        config=config,
        planner=None,
    )
    assert proposal is not None
    assert len(proposal.actions) == 1
    action = proposal.actions[0]
    assert action.type == "insert_text"
    assert action.text and "故宫" in action.text
    assert len(action.text) <= config.max_document_length
    assert proposal.completes_subgoal is True
    # The composed document is recorded in the workspace.
    composed = [item for item in state.workspace.artifacts if item.get("kind") == "composed_document"]
    assert len(composed) == 1
    # Completion is proven by the write action executing into the active editor.
    assert subgoal.completion_evidence["kind"] == "action_executed"


def test_propose_step_reuses_artifact_across_rounds():
    capability = DocumentAuthoringCapability()
    config = _offline_config()
    subgoal = Subgoal(id="s1", title="整理到word里", goal="整理到word里", goal_type="fill")
    state = _state("整理到word里", subgoal, notes=["[web] note"])
    first = capability.propose_step(
        subgoal=subgoal,
        world_model=WorldModel(active_app="word"),
        execution_state=state,
        config=config,
        planner=None,
    )
    second = capability.propose_step(
        subgoal=subgoal,
        world_model=WorldModel(active_app="word"),
        execution_state=state,
        config=config,
        planner=None,
    )
    composed = [item for item in state.workspace.artifacts if item.get("kind") == "composed_document"]
    assert len(composed) == 1
    assert first.actions[0].text == second.actions[0].text


def test_document_authoring_capability_is_registered_and_enabled():
    registry = build_capability_registry()
    config = AgentConfig()
    names = {capability.name for capability in registry.enabled(config)}
    assert "document_authoring" in names


def test_safety_allows_insert_text_within_limit_and_blocks_overflow():
    guard = ActionGuard(AgentConfig())
    guard.validate(Action.from_dict({"type": "insert_text", "text": "A reasonable document body."}))
    overflow = "x" * (AgentConfig().max_document_length + 1)
    with pytest.raises(SafetyError):
        guard.validate(Action.from_dict({"type": "insert_text", "text": overflow}))


def test_safety_blocks_risky_insert_text():
    guard = ActionGuard(AgentConfig())
    with pytest.raises(SafetyError):
        guard.validate(Action.from_dict({"type": "insert_text", "text": "now run powershell to wipe disk"}))


def test_task_graph_routes_author_step_to_document_authoring():
    planner = TaskGraphPlanner(AgentConfig(complex_task_planning="heuristic"))
    graph = planner.plan("搜索北京旅游攻略然后整理到word里")
    assert len(graph.subgoals) >= 2
    assert graph.subgoals[-1].capability_preference == "document_authoring"
    assert graph.subgoals[0].capability_preference != "document_authoring"
