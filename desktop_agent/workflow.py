from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import time
from typing import Any

from desktop_agent.actions import Action, PlanResult
from desktop_agent.surfaces import TargetAnchor, UserDesktopSession, normalize_surface_kind
from desktop_agent.windows_env import DesktopEnvironment


RISK_LEVELS = {"low", "medium", "high", "critical"}
FAILURE_KINDS = {
    "transient_failure",
    "blocked_by_ui",
    "blocked_ui",
    "stale_target",
    "missing_data",
    "verification_failed",
    "safety_gate",
    "requires_user",
    "requires_auth",
    "requires_human",
    "requires_clarification",
    "capability_mismatch",
    "goal_ambiguous",
    "approval_rejected",
}
SUBGOAL_STATUSES = {"pending", "in_progress", "completed", "failed", "blocked"}
VERIFICATION_STATUSES = {"success", "partial_progress", "failed"}
GOAL_TYPES = {
    "navigate",
    "locate",
    "read",
    "extract",
    "transform",
    "fill",
    "confirm",
    "transfer",
    "save",
    "clarify",
    "handoff",
}


def _normalize_risk_level(value: str | None) -> str:
    normalized = str(value or "low").strip().lower()
    return normalized if normalized in RISK_LEVELS else "low"


def _normalize_failure_kind(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in FAILURE_KINDS else None


def _normalize_subgoal_status(value: str | None) -> str:
    normalized = str(value or "pending").strip().lower()
    return normalized if normalized in SUBGOAL_STATUSES else "pending"


def _normalize_verification_status(value: str | None, success: bool | None = None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in VERIFICATION_STATUSES:
        return normalized
    if _optional_bool(success) is True:
        return "success"
    return "failed"


def _normalize_goal_type(value: str | None) -> str:
    normalized = str(value or "handoff").strip().lower()
    return normalized if normalized in GOAL_TYPES else "handoff"


@dataclass(slots=True)
class ObservedFact:
    source: str
    key: str
    value: str
    confidence: float = 1.0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ObservedFact":
        return cls(
            source=str(payload.get("source", "")).strip() or "unknown",
            key=str(payload.get("key", "")).strip() or "fact",
            value=str(payload.get("value", "")).strip(),
            confidence=float(payload.get("confidence", 1.0) or 1.0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "key": self.key,
            "value": self.value,
            "confidence": self.confidence,
        }


@dataclass(slots=True)
class EvidenceRequirement:
    kind: str
    value: str | None = None
    detail: str | None = None
    selector: str | None = None
    required: bool = True

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EvidenceRequirement":
        return cls(
            kind=str(payload.get("kind", "")).strip().lower() or "action_executed",
            value=_optional_str(payload.get("value")),
            detail=_optional_str(payload.get("detail")),
            selector=_optional_str(payload.get("selector")),
            required=_bool_value(payload.get("required"), default=True),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": self.value,
            "detail": self.detail,
            "selector": self.selector,
            "required": self.required,
        }


@dataclass(slots=True)
class VerificationResult:
    success: bool | None = None
    status: str = "failed"
    evidence: list[dict[str, Any]] = field(default_factory=list)
    failure_kind: str | None = None
    message: str | None = None
    verified_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        self.success = _optional_bool(self.success)
        self.status = _normalize_verification_status(self.status, self.success)
        if self.success is None:
            self.success = self.status == "success"
        elif self.success:
            self.status = "success"
        elif self.status == "success":
            self.status = "failed"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "VerificationResult":
        success = _optional_bool(payload.get("success"))
        return cls(
            success=success,
            status=_normalize_verification_status(payload.get("status"), success),
            evidence=list(payload.get("evidence", []) or []),
            failure_kind=_normalize_failure_kind(payload.get("failure_kind")),
            message=_optional_str(payload.get("message")),
            verified_at=float(payload.get("verified_at", time.time()) or time.time()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "status": self.status,
            "evidence": list(self.evidence),
            "failure_kind": self.failure_kind,
            "message": self.message,
            "verified_at": self.verified_at,
        }

    @property
    def made_progress(self) -> bool:
        return self.status in {"success", "partial_progress"}


@dataclass(slots=True)
class StepProposal:
    intent: str
    actions: list[Action] = field(default_factory=list)
    expected_evidence: list[EvidenceRequirement] = field(default_factory=list)
    progress_signals: list[str] = field(default_factory=list)
    repair_strategy: list[str] = field(default_factory=list)
    risk_level: str = "low"
    fallbacks: list[str] = field(default_factory=list)
    timeout: float | None = None
    cost_hint: str | None = None
    capability: str = "desktop_gui"
    requires_approval: bool = False
    target_scope: str | None = None
    surface_kind: str = "current_user_desktop"
    primary_anchor: TargetAnchor | None = None
    fallback_anchors: list[TargetAnchor] = field(default_factory=list)
    rationale: str | None = None
    current_focus: str | None = None
    remaining_steps: list[str] = field(default_factory=list)
    completes_subgoal: bool = False

    @classmethod
    def from_plan_result(
        cls,
        plan: PlanResult,
        *,
        capability: str,
        risk_level: str = "low",
        expected_evidence: list[EvidenceRequirement] | None = None,
        requires_approval: bool = False,
        target_scope: str | None = None,
    ) -> "StepProposal":
        return cls(
            intent=plan.status_summary,
            actions=list(plan.actions),
            expected_evidence=list(expected_evidence or []),
            risk_level=_normalize_risk_level(risk_level),
            progress_signals=list(plan.remaining_steps[:2]),
            capability=capability,
            requires_approval=requires_approval,
            target_scope=target_scope,
            surface_kind="current_user_desktop",
            rationale=plan.reasoning,
            current_focus=plan.current_focus,
            remaining_steps=list(plan.remaining_steps),
            completes_subgoal=bool(plan.done),
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StepProposal":
        return cls(
            intent=str(payload.get("intent", "")).strip() or "No intent provided.",
            actions=[Action.from_dict(item) for item in payload.get("actions", []) or []],
            expected_evidence=[
                EvidenceRequirement.from_dict(item)
                for item in payload.get("expected_evidence", []) or []
                if isinstance(item, dict)
            ],
            progress_signals=[str(item).strip() for item in payload.get("progress_signals", []) or [] if str(item).strip()],
            repair_strategy=[str(item).strip() for item in payload.get("repair_strategy", []) or [] if str(item).strip()],
            risk_level=_normalize_risk_level(payload.get("risk_level")),
            fallbacks=[str(item).strip() for item in payload.get("fallbacks", []) or [] if str(item).strip()],
            timeout=_optional_float(payload.get("timeout")),
            cost_hint=_optional_str(payload.get("cost_hint")),
            capability=str(payload.get("capability", "desktop_gui")).strip() or "desktop_gui",
            requires_approval=_bool_value(payload.get("requires_approval")),
            target_scope=_optional_str(payload.get("target_scope")),
            surface_kind=normalize_surface_kind(payload.get("surface_kind")),
            primary_anchor=TargetAnchor.from_dict(payload["primary_anchor"])
            if isinstance(payload.get("primary_anchor"), dict)
            else None,
            fallback_anchors=[
                TargetAnchor.from_dict(item)
                for item in payload.get("fallback_anchors", []) or []
                if isinstance(item, dict)
            ],
            rationale=_optional_str(payload.get("rationale")),
            current_focus=_optional_str(payload.get("current_focus")),
            remaining_steps=[str(item).strip() for item in payload.get("remaining_steps", []) or [] if str(item).strip()],
            completes_subgoal=_bool_value(payload.get("completes_subgoal")),
        )

    def to_plan_result(self, *, done: bool = False) -> PlanResult:
        return PlanResult(
            status_summary=self.intent,
            done=done,
            actions=list(self.actions),
            current_focus=self.current_focus,
            reasoning=self.rationale,
            remaining_steps=list(self.remaining_steps),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "actions": [action.to_dict() for action in self.actions],
            "expected_evidence": [item.to_dict() for item in self.expected_evidence],
            "progress_signals": list(self.progress_signals),
            "repair_strategy": list(self.repair_strategy),
            "risk_level": self.risk_level,
            "fallbacks": list(self.fallbacks),
            "timeout": self.timeout,
            "cost_hint": self.cost_hint,
            "capability": self.capability,
            "requires_approval": self.requires_approval,
            "target_scope": self.target_scope,
            "surface_kind": self.surface_kind,
            "primary_anchor": self.primary_anchor.to_dict() if self.primary_anchor is not None else None,
            "fallback_anchors": [item.to_dict() for item in self.fallback_anchors],
            "rationale": self.rationale,
            "current_focus": self.current_focus,
            "remaining_steps": list(self.remaining_steps),
            "completes_subgoal": self.completes_subgoal,
        }


@dataclass(slots=True)
class Subgoal:
    id: str
    title: str
    success_condition: str = "Confirm the subgoal has been completed."
    goal: str | None = None
    goal_type: str = "handoff"
    prerequisites: list[str] = field(default_factory=list)
    fallback_goal: str | None = None
    capability_preference: str | None = None
    risk_level: str = "low"
    retry_budget: int = 2
    max_attempts: int = 3
    status: str = "pending"
    attempts: int = 0
    notes: list[str] = field(default_factory=list)
    failed_capabilities: list[str] = field(default_factory=list)
    completion_evidence: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Subgoal":
        return cls(
            id=str(payload.get("id", "")).strip() or "subgoal",
            title=str(payload.get("title", "")).strip() or "Untitled subgoal",
            goal=_optional_str(payload.get("goal")) or _optional_str(payload.get("title")),
            goal_type=_normalize_goal_type(payload.get("goal_type")),
            success_condition=str(payload.get("success_condition", "")).strip() or "Confirm the subgoal has been completed.",
            prerequisites=[str(item).strip() for item in payload.get("prerequisites", []) or [] if str(item).strip()],
            fallback_goal=_optional_str(payload.get("fallback_goal")),
            capability_preference=_optional_str(payload.get("capability_preference")),
            risk_level=_normalize_risk_level(payload.get("risk_level")),
            retry_budget=max(0, int(payload.get("retry_budget", 2) or 0)),
            max_attempts=max(1, int(payload.get("max_attempts", (payload.get("retry_budget", 2) or 0) + 1) or 1)),
            status=_normalize_subgoal_status(payload.get("status")),
            attempts=max(0, int(payload.get("attempts", 0) or 0)),
            notes=[str(item).strip() for item in payload.get("notes", []) or [] if str(item).strip()],
            failed_capabilities=[
                str(item).strip() for item in payload.get("failed_capabilities", []) or [] if str(item).strip()
            ],
            completion_evidence=payload.get("completion_evidence"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "goal": self.goal or self.title,
            "goal_type": self.goal_type,
            "success_condition": self.success_condition,
            "prerequisites": list(self.prerequisites),
            "fallback_goal": self.fallback_goal,
            "capability_preference": self.capability_preference,
            "risk_level": self.risk_level,
            "retry_budget": self.retry_budget,
            "max_attempts": self.max_attempts,
            "status": self.status,
            "attempts": self.attempts,
            "notes": list(self.notes),
            "failed_capabilities": list(self.failed_capabilities),
            "completion_evidence": self.completion_evidence,
        }

    def can_retry(self) -> bool:
        return self.attempts < max(1, self.max_attempts)


@dataclass(slots=True)
class TaskGraph:
    task: str
    subgoals: list[Subgoal] = field(default_factory=list)
    dependencies: dict[str, list[str]] = field(default_factory=dict)
    success_criteria: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    risk_points: list[str] = field(default_factory=list)
    completion_summary: str | None = None
    intent: dict[str, Any] | None = None
    recipes: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TaskGraph":
        return cls(
            task=str(payload.get("task", "")).strip(),
            subgoals=[Subgoal.from_dict(item) for item in payload.get("subgoals", []) or [] if isinstance(item, dict)],
            dependencies={
                str(key).strip(): [str(item).strip() for item in value or [] if str(item).strip()]
                for key, value in dict(payload.get("dependencies", {}) or {}).items()
                if str(key).strip()
            },
            success_criteria=[
                str(item).strip() for item in payload.get("success_criteria", []) or [] if str(item).strip()
            ],
            constraints=[str(item).strip() for item in payload.get("constraints", []) or [] if str(item).strip()],
            risk_points=[str(item).strip() for item in payload.get("risk_points", []) or [] if str(item).strip()],
            completion_summary=_optional_str(payload.get("completion_summary")),
            intent=dict(payload.get("intent") or {}) if isinstance(payload.get("intent"), dict) else None,
            recipes=[dict(item) for item in payload.get("recipes", []) or [] if isinstance(item, dict)],
            created_at=float(payload.get("created_at", time.time()) or time.time()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "subgoals": [item.to_dict() for item in self.subgoals],
            "dependencies": {key: list(value) for key, value in self.dependencies.items()},
            "success_criteria": list(self.success_criteria),
            "constraints": list(self.constraints),
            "risk_points": list(self.risk_points),
            "completion_summary": self.completion_summary,
            "intent": dict(self.intent) if isinstance(self.intent, dict) else None,
            "recipes": [dict(item) for item in self.recipes],
            "created_at": self.created_at,
        }

    def current_subgoal(self) -> Subgoal | None:
        prioritized_statuses = ("in_progress", "blocked", "pending")
        for status in prioritized_statuses:
            for subgoal in self.subgoals:
                if subgoal.status != status:
                    continue
                if self.is_ready(subgoal):
                    return subgoal
        return None

    def prerequisites_for(self, subgoal: Subgoal | str) -> list[str]:
        subgoal_id = subgoal if isinstance(subgoal, str) else subgoal.id
        explicit = list(self.dependencies.get(subgoal_id, []))
        if isinstance(subgoal, Subgoal):
            for item in subgoal.prerequisites:
                if item not in explicit:
                    explicit.append(item)
        return explicit

    def is_ready(self, subgoal: Subgoal | str) -> bool:
        target = subgoal if isinstance(subgoal, Subgoal) else next((item for item in self.subgoals if item.id == subgoal), None)
        if target is None:
            return False
        for prerequisite in self.prerequisites_for(target):
            dependency = next((item for item in self.subgoals if item.id == prerequisite), None)
            if dependency is None or dependency.status != "completed":
                return False
        return True

    def mark_in_progress(self, subgoal_id: str) -> None:
        for subgoal in self.subgoals:
            if subgoal.id == subgoal_id and subgoal.status in {"pending", "blocked"}:
                subgoal.status = "in_progress"
                return

    def mark_completed(self, subgoal_id: str, *, evidence: dict[str, Any] | None = None) -> None:
        for subgoal in self.subgoals:
            if subgoal.id == subgoal_id:
                subgoal.status = "completed"
                subgoal.completion_evidence = evidence
                return

    def mark_failed(self, subgoal_id: str, *, note: str | None = None) -> None:
        for subgoal in self.subgoals:
            if subgoal.id == subgoal_id:
                subgoal.status = "failed"
                if note:
                    subgoal.notes.append(note)
                return

    def is_complete(self) -> bool:
        return bool(self.subgoals) and all(item.status == "completed" for item in self.subgoals)


@dataclass(slots=True)
class PendingDecision:
    id: str
    summary: str
    reason: str
    risk_level: str
    decision_type: str = "step_approval"
    actions: list[Action] = field(default_factory=list)
    approval_policy: str | None = None
    requires_user_presence: bool = False
    operator_hint: str | None = None
    requested_at: float = field(default_factory=time.time)
    status: str = "pending"
    response_note: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PendingDecision":
        return cls(
            id=str(payload.get("id", "")).strip() or "decision",
            summary=str(payload.get("summary", "")).strip() or "Approval required.",
            reason=str(payload.get("reason", "")).strip() or "The agent needs a decision before continuing.",
            risk_level=_normalize_risk_level(payload.get("risk_level")),
            decision_type=_normalize_decision_type(payload.get("decision_type")),
            actions=[Action.from_dict(item) for item in payload.get("actions", []) or []],
            approval_policy=_optional_str(payload.get("approval_policy")),
            requires_user_presence=_bool_value(payload.get("requires_user_presence")),
            operator_hint=_optional_str(payload.get("operator_hint")),
            requested_at=float(payload.get("requested_at", time.time()) or time.time()),
            status=str(payload.get("status", "pending")).strip() or "pending",
            response_note=_optional_str(payload.get("response_note")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "summary": self.summary,
            "reason": self.reason,
            "risk_level": self.risk_level,
            "decision_type": self.decision_type,
            "actions": [item.to_dict() for item in self.actions],
            "approval_policy": self.approval_policy,
            "requires_user_presence": self.requires_user_presence,
            "operator_hint": self.operator_hint,
            "requested_at": self.requested_at,
            "status": self.status,
            "response_note": self.response_note,
        }


@dataclass(slots=True)
class WorldModel:
    screenshot_path: Path | None = None
    environment: DesktopEnvironment | None = None
    browser_snapshot: dict[str, Any] | None = None
    uia_tree: list[dict[str, Any]] = field(default_factory=list)
    visible_windows: list[dict[str, Any]] = field(default_factory=list)
    downloads: list[dict[str, Any]] = field(default_factory=list)
    facts: list[ObservedFact] = field(default_factory=list)
    fact_sources: list[str] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    state_delta: dict[str, Any] = field(default_factory=dict)
    active_app: str | None = None
    active_window_title: str | None = None
    target_window_title: str | None = None
    foreground_window_handle: int | None = None
    focused_control: str | None = None
    clipboard_text: str | None = None
    active_driver: str | None = None
    surface_kind: str = "current_user_desktop"
    surface_id: str | None = None
    session_id: str | None = None
    dom_available: bool = False
    uia_available: bool = False
    structured_sources: list[str] = field(default_factory=list)
    visual_sources: list[str] = field(default_factory=list)
    anchor_candidates: list[str] = field(default_factory=list)
    selection_text: str | None = None
    file_observations: list[dict[str, Any]] = field(default_factory=list)
    browser_observation: dict[str, Any] | None = None
    user_desktop_session: UserDesktopSession | None = None
    step_index: int = 0
    captured_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "screenshot_path": str(self.screenshot_path) if self.screenshot_path else None,
            "environment": self.environment.to_dict() if self.environment is not None else None,
            "browser_snapshot": self.browser_snapshot,
            "uia_tree": list(self.uia_tree),
            "visible_windows": list(self.visible_windows),
            "downloads": list(self.downloads),
            "facts": [item.to_dict() for item in self.facts],
            "fact_sources": list(self.fact_sources),
            "observations": list(self.observations),
            "state_delta": dict(self.state_delta),
            "active_app": self.active_app,
            "active_window_title": self.active_window_title,
            "target_window_title": self.target_window_title,
            "foreground_window_handle": self.foreground_window_handle,
            "focused_control": self.focused_control,
            "clipboard_text": self.clipboard_text,
            "active_driver": self.active_driver,
            "surface_kind": self.surface_kind,
            "surface_id": self.surface_id,
            "session_id": self.session_id,
            "dom_available": self.dom_available,
            "uia_available": self.uia_available,
            "structured_sources": list(self.structured_sources),
            "visual_sources": list(self.visual_sources),
            "anchor_candidates": list(self.anchor_candidates),
            "selection_text": self.selection_text,
            "file_observations": list(self.file_observations),
            "browser_observation": self.browser_observation,
            "user_desktop_session": self.user_desktop_session.to_dict()
            if self.user_desktop_session is not None
            else None,
            "step_index": self.step_index,
            "captured_at": self.captured_at,
        }


@dataclass(slots=True)
class TaskWorkspace:
    notes: list[str] = field(default_factory=list)
    facts: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    anchors: list[dict[str, Any]] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "TaskWorkspace":
        if not isinstance(payload, dict):
            return cls()
        return cls(
            notes=[str(item).strip() for item in payload.get("notes", []) or [] if str(item).strip()],
            facts=[dict(item) for item in payload.get("facts", []) or [] if isinstance(item, dict)],
            sources=[dict(item) for item in payload.get("sources", []) or [] if isinstance(item, dict)],
            artifacts=[dict(item) for item in payload.get("artifacts", []) or [] if isinstance(item, dict)],
            open_questions=[
                str(item).strip() for item in payload.get("open_questions", []) or [] if str(item).strip()
            ],
            decisions=[dict(item) for item in payload.get("decisions", []) or [] if isinstance(item, dict)],
            evidence=[dict(item) for item in payload.get("evidence", []) or [] if isinstance(item, dict)],
            anchors=[dict(item) for item in payload.get("anchors", []) or [] if isinstance(item, dict)],
            updated_at=float(payload.get("updated_at", time.time()) or time.time()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "notes": list(self.notes),
            "facts": [dict(item) for item in self.facts],
            "sources": [dict(item) for item in self.sources],
            "artifacts": [dict(item) for item in self.artifacts],
            "open_questions": list(self.open_questions),
            "decisions": [dict(item) for item in self.decisions],
            "evidence": [dict(item) for item in self.evidence],
            "anchors": [dict(item) for item in self.anchors],
            "updated_at": self.updated_at,
        }

    def add_note(self, note: str | None) -> None:
        text = _optional_str(note)
        if not text or text in self.notes:
            return
        self.notes.append(text)
        del self.notes[:-12]
        self.updated_at = time.time()

    def add_facts(self, facts: list[ObservedFact]) -> None:
        for fact in facts:
            payload = fact.to_dict()
            if payload not in self.facts:
                self.facts.append(payload)
        del self.facts[:-24]
        self.updated_at = time.time()

    def add_decision(self, payload: dict[str, Any]) -> None:
        self.decisions.append(dict(payload))
        del self.decisions[:-12]
        self.updated_at = time.time()

    def add_evidence(self, payload: dict[str, Any]) -> None:
        self.evidence.append(dict(payload))
        del self.evidence[:-24]
        self.updated_at = time.time()

    def add_world_model(self, world_model: WorldModel) -> None:
        browser = world_model.browser_snapshot or {}
        if browser:
            source = {
                "kind": "browser",
                "url": browser.get("url"),
                "title": browser.get("title"),
                "captured_at": world_model.captured_at,
            }
            if source not in self.sources:
                self.sources.append(source)
        if world_model.file_observations:
            for item in world_model.file_observations[:6]:
                if isinstance(item, dict) and item not in self.artifacts:
                    self.artifacts.append(dict(item))
        for anchor in world_model.anchor_candidates[:8]:
            payload = {"value": str(anchor), "captured_at": world_model.captured_at}
            if payload not in self.anchors:
                self.anchors.append(payload)
        del self.sources[:-16]
        del self.artifacts[:-16]
        del self.anchors[:-24]
        self.updated_at = time.time()

    def summary(self) -> dict[str, Any]:
        return {
            "notes": list(self.notes[-3:]),
            "facts": [dict(item) for item in self.facts[-5:]],
            "sources": [dict(item) for item in self.sources[-4:]],
            "artifacts": [dict(item) for item in self.artifacts[-4:]],
            "open_questions": list(self.open_questions[-3:]),
            "decisions": [dict(item) for item in self.decisions[-3:]],
            "evidence": [dict(item) for item in self.evidence[-5:]],
            "anchors": [dict(item) for item in self.anchors[-5:]],
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class ExecutionState:
    task: str
    run_id: str
    task_graph: TaskGraph
    orchestration_phase: str = "planning"
    active_specialist: str | None = None
    workspace: TaskWorkspace = field(default_factory=TaskWorkspace)
    stage_decisions: list[dict[str, Any]] = field(default_factory=list)
    failure_budget: dict[str, int] = field(default_factory=dict)
    last_replan_reason: str | None = None
    world_model: WorldModel | None = None
    memory: list[str] = field(default_factory=list)
    facts: list[ObservedFact] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)
    pending_decision: PendingDecision | None = None
    last_step: StepProposal | None = None
    last_verification: VerificationResult | None = None
    evidence_ledger: list[dict[str, Any]] = field(default_factory=list)
    stuck_rounds: int = 0
    capability_failures: dict[str, list[str]] = field(default_factory=dict)
    stable_targets: list[str] = field(default_factory=list)
    app_context: dict[str, Any] = field(default_factory=dict)
    last_progress_at: float | None = None
    repair_history: list[dict[str, Any]] = field(default_factory=list)
    current_surface_kind: str = "current_user_desktop"
    completed: bool = False
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ExecutionState":
        return cls(
            task=str(payload.get("task", "")).strip(),
            run_id=str(payload.get("run_id", "")).strip(),
            task_graph=TaskGraph.from_dict(payload.get("task_graph", {}) or {}),
            orchestration_phase=str(payload.get("orchestration_phase", "planning")).strip() or "planning",
            active_specialist=_optional_str(payload.get("active_specialist")),
            workspace=TaskWorkspace.from_dict(payload.get("workspace") if isinstance(payload, dict) else None),
            stage_decisions=list(payload.get("stage_decisions", []) or []),
            failure_budget={
                str(key).strip(): max(0, int(value or 0))
                for key, value in dict(payload.get("failure_budget", {}) or {}).items()
                if str(key).strip()
            },
            last_replan_reason=_optional_str(payload.get("last_replan_reason")),
            world_model=None,
            memory=[str(item).strip() for item in payload.get("memory", []) or [] if str(item).strip()],
            facts=[ObservedFact.from_dict(item) for item in payload.get("facts", []) or [] if isinstance(item, dict)],
            failures=list(payload.get("failures", []) or []),
            pending_decision=PendingDecision.from_dict(payload["pending_decision"])
            if isinstance(payload.get("pending_decision"), dict)
            else None,
            last_step=StepProposal.from_dict(payload["last_step"]) if isinstance(payload.get("last_step"), dict) else None,
            last_verification=VerificationResult.from_dict(payload["last_verification"])
            if isinstance(payload.get("last_verification"), dict)
            else None,
            evidence_ledger=list(payload.get("evidence_ledger", []) or []),
            stuck_rounds=max(0, int(payload.get("stuck_rounds", 0) or 0)),
            capability_failures={
                str(key).strip(): [str(item).strip() for item in value or [] if str(item).strip()]
                for key, value in dict(payload.get("capability_failures", {}) or {}).items()
                if str(key).strip()
            },
            stable_targets=[str(item).strip() for item in payload.get("stable_targets", []) or [] if str(item).strip()],
            app_context=dict(payload.get("app_context", {}) or {}),
            last_progress_at=_optional_float(payload.get("last_progress_at")),
            repair_history=list(payload.get("repair_history", []) or []),
            current_surface_kind=normalize_surface_kind(payload.get("current_surface_kind")),
            completed=_bool_value(payload.get("completed")),
            started_at=float(payload.get("started_at", time.time()) or time.time()),
            updated_at=float(payload.get("updated_at", time.time()) or time.time()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "run_id": self.run_id,
            "task_graph": self.task_graph.to_dict(),
            "orchestration_phase": self.orchestration_phase,
            "active_specialist": self.active_specialist,
            "workspace": self.workspace.to_dict(),
            "stage_decisions": [dict(item) for item in self.stage_decisions],
            "failure_budget": dict(self.failure_budget),
            "last_replan_reason": self.last_replan_reason,
            "world_model": self.world_model.to_dict() if self.world_model is not None else None,
            "memory": list(self.memory),
            "facts": [item.to_dict() for item in self.facts],
            "failures": list(self.failures),
            "pending_decision": self.pending_decision.to_dict() if self.pending_decision is not None else None,
            "last_step": self.last_step.to_dict() if self.last_step is not None else None,
            "last_verification": self.last_verification.to_dict() if self.last_verification is not None else None,
            "evidence_ledger": list(self.evidence_ledger),
            "stuck_rounds": self.stuck_rounds,
            "capability_failures": {key: list(value) for key, value in self.capability_failures.items()},
            "stable_targets": list(self.stable_targets),
            "app_context": dict(self.app_context),
            "last_progress_at": self.last_progress_at,
            "repair_history": list(self.repair_history),
            "current_surface_kind": self.current_surface_kind,
            "completed": self.completed,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
        }

    def current_subgoal(self) -> Subgoal | None:
        return _active_subgoal_from_context(self) or self.task_graph.current_subgoal()


def build_execution_plan_summary(state: ExecutionState) -> dict[str, Any]:
    current_subgoal = _active_subgoal_from_context(state) or _select_summary_subgoal(state)
    plan_health = _build_plan_health(state, next_subgoal=current_subgoal)
    last_step = state.last_step
    last_verification = state.last_verification
    pending_repair = state.app_context.get("pending_repair") if isinstance(state.app_context, dict) else None
    manual_resume_status = (
        str(state.app_context.get("manual_resume_status") or "").strip().lower()
        if isinstance(state.app_context, dict)
        else ""
    )
    manual_resume_cleared = manual_resume_status in {"resumed", "complete", "completed", "cleared"}
    recovery_reason = None
    if isinstance(pending_repair, dict):
        recovery_reason = _optional_str(pending_repair.get("failure_kind")) or _optional_str(pending_repair.get("message"))
    if recovery_reason is None and state.failures and not manual_resume_cleared:
        latest_failure = state.failures[-1]
        if isinstance(latest_failure, dict):
            recovery_reason = _optional_str(latest_failure.get("message")) or _optional_str(latest_failure.get("failure_kind"))
    if recovery_reason is None and isinstance(state.app_context, dict):
        recovery_reason = _optional_str(state.app_context.get("recovery_reason")) or _optional_str(
            state.app_context.get("human_handoff_reason")
        )
    return {
        "task": state.task,
        "completed": state.completed,
        "intent": dict(state.task_graph.intent) if isinstance(state.task_graph.intent, dict) else None,
        "orchestration_phase": state.orchestration_phase,
        "active_specialist": state.active_specialist,
        "plan_health": plan_health,
        "workspace_summary": state.workspace.summary(),
        "plan_review_status": state.app_context.get("plan_review_status") if isinstance(state.app_context, dict) else None,
        "stage_review_status": state.app_context.get("stage_review_status") if isinstance(state.app_context, dict) else None,
        "last_replan_reason": state.last_replan_reason,
        "current_goal": current_subgoal.title if current_subgoal is not None else None,
        "chosen_capability": last_step.capability if last_step is not None else None,
        "verification_status": last_verification.status if last_verification is not None else None,
        "recovery_reason": recovery_reason,
        "current_subgoal": current_subgoal.to_dict() if current_subgoal is not None else None,
        "completion_summary": state.task_graph.completion_summary,
        "subgoals": [item.to_dict() for item in state.task_graph.subgoals],
        "dependencies": {key: list(value) for key, value in state.task_graph.dependencies.items()},
        "pending_decision": state.pending_decision.to_dict() if state.pending_decision is not None else None,
        "last_step": state.last_step.to_dict() if state.last_step is not None else None,
        "last_verification": state.last_verification.to_dict() if state.last_verification is not None else None,
        "facts": [item.to_dict() for item in state.facts],
        "evidence_ledger": list(state.evidence_ledger[-10:]),
        "stuck_rounds": state.stuck_rounds,
        "capability_failures": {key: list(value) for key, value in state.capability_failures.items()},
        "stable_targets": list(state.stable_targets),
        "app_context": dict(state.app_context),
        "last_progress_at": state.last_progress_at,
        "repair_history": list(state.repair_history[-10:]),
        "current_surface_kind": state.current_surface_kind,
        "updated_at": state.updated_at,
    }


def _select_summary_subgoal(state: ExecutionState) -> Subgoal | None:
    active_subgoal = _active_subgoal_from_context(state)
    if active_subgoal is not None:
        return active_subgoal
    for status in ("in_progress", "pending", "blocked"):
        for subgoal in state.task_graph.subgoals:
            if subgoal.status != status or not state.task_graph.is_ready(subgoal):
                continue
            if _subgoal_can_continue_for_summary(state, subgoal):
                return subgoal
    for subgoal in state.task_graph.subgoals:
        if subgoal.status != "completed" and state.task_graph.is_ready(subgoal):
            return subgoal
    return None


def _active_subgoal_from_context(state: ExecutionState) -> Subgoal | None:
    active_id = None
    if isinstance(state.app_context, dict):
        active_id = _optional_str(state.app_context.get("active_subgoal_id"))
    if not active_id:
        return None
    subgoal = next((item for item in state.task_graph.subgoals if item.id == active_id), None)
    if subgoal is None or subgoal.status == "completed" or not state.task_graph.is_ready(subgoal):
        return None
    pending_repair = state.app_context.get("pending_repair") if isinstance(state.app_context, dict) else None
    if isinstance(pending_repair, dict) and str(pending_repair.get("subgoal_id") or "") == subgoal.id:
        return subgoal
    if subgoal.status == "blocked" and _summary_retry_remaining(state, subgoal) <= 0 and not subgoal.can_retry():
        return None
    return subgoal


def _build_plan_health(state: ExecutionState, *, next_subgoal: Subgoal | None) -> dict[str, Any]:
    subgoals = list(state.task_graph.subgoals)
    counts = {
        "total": len(subgoals),
        "completed": 0,
        "pending": 0,
        "in_progress": 0,
        "blocked": 0,
        "failed": 0,
        "ready": 0,
        "exhausted": 0,
    }
    items: list[dict[str, Any]] = []
    for subgoal in subgoals:
        status = subgoal.status
        if status in counts:
            counts[status] += 1
        ready = state.task_graph.is_ready(subgoal)
        retry_remaining = _summary_retry_remaining(state, subgoal)
        exhausted = subgoal.status != "completed" and retry_remaining <= 0
        if exhausted:
            counts["exhausted"] += 1
        if ready and subgoal.status != "completed" and not exhausted:
            counts["ready"] += 1
        items.append(
            {
                "id": subgoal.id,
                "title": subgoal.title,
                "status": subgoal.status,
                "goal_type": subgoal.goal_type,
                "risk_level": subgoal.risk_level,
                "capability_preference": subgoal.capability_preference,
                "ready": ready,
                "attempts": subgoal.attempts,
                "max_attempts": subgoal.max_attempts,
                "retry_remaining": retry_remaining,
                "exhausted": exhausted,
                "is_next": next_subgoal is not None and subgoal.id == next_subgoal.id,
                "prerequisites": state.task_graph.prerequisites_for(subgoal),
                "notes": list(subgoal.notes[-2:]),
            }
        )
    blocked_reason = _plan_blocked_reason(state, items)
    return {
        "counts": counts,
        "next_subgoal_id": next_subgoal.id if next_subgoal is not None else None,
        "next_subgoal": next_subgoal.to_dict() if next_subgoal is not None else None,
        "remaining": max(0, counts["total"] - counts["completed"]),
        "blocked_reason": blocked_reason,
        "autonomy": _build_autonomy_readiness(
            state,
            items=items,
            next_subgoal=next_subgoal,
            blocked_reason=blocked_reason,
        ),
        "items": items,
    }


def _build_autonomy_readiness(
    state: ExecutionState,
    *,
    items: list[dict[str, Any]],
    next_subgoal: Subgoal | None,
    blocked_reason: str | None,
) -> dict[str, Any]:
    app_context = state.app_context if isinstance(state.app_context, dict) else {}
    phase = str(state.orchestration_phase or "").strip().lower()
    pending_decision = state.pending_decision
    pending_type = (
        _normalize_decision_type(getattr(pending_decision, "decision_type", None))
        if pending_decision is not None
        else None
    )
    plan_review_status = str(app_context.get("plan_review_status") or "").strip().lower()
    stage_review_status = str(app_context.get("stage_review_status") or "").strip().lower()
    plan_review_pending = plan_review_status in {"pending", "cancelled", "canceled"}
    stage_review_pending = stage_review_status in {"pending", "cancelled", "canceled"}
    warnings: list[str] = []
    blockers: list[str] = []
    next_action = "execute"
    status = "ready"
    can_continue = True
    requires_review = False
    requires_user = False

    human_reason = _optional_str(app_context.get("human_handoff_reason"))
    if phase == "awaiting_user" or human_reason:
        status = "waiting_user"
        next_action = "resume_after_user"
        can_continue = False
        requires_user = True
        blockers.append(human_reason or "Waiting for the user before automation can continue.")
    elif pending_type in {"plan_review", "stage_review", "step_approval"} or plan_review_pending or stage_review_pending:
        review_type = pending_type or ("stage_review" if stage_review_pending else "plan_review")
        status = "review_required"
        next_action = {
            "stage_review": "approve_stage",
            "step_approval": "approve_step",
        }.get(review_type, "approve_plan")
        can_continue = False
        requires_review = True
        blockers.append(_review_blocker_message(review_type))
    elif phase == "awaiting_approval":
        status = "review_required"
        next_action = "approve_step"
        can_continue = False
        requires_review = True
        blockers.append(_review_blocker_message("step_approval"))
    elif state.completed or state.task_graph.is_complete():
        status = "complete"
        next_action = "done"
        can_continue = False
    elif phase == "blocked":
        status = "blocked"
        next_action = "inspect_failure"
        can_continue = False
        requires_review = False
        requires_user = False
        blockers.append(
            _optional_str(app_context.get("recovery_reason"))
            or _optional_str(app_context.get("standard_recovery_kind"))
            or blocked_reason
            or "Inspect the failed run before automation can continue."
        )
    elif next_subgoal is None:
        status = "blocked"
        next_action = "recover_or_replan"
        can_continue = False
        blockers.append(blocked_reason or "No continuable subgoal is ready.")
    elif next_subgoal.goal_type == "clarify":
        status = "needs_clarification"
        next_action = "ask_user"
        can_continue = False
        requires_user = True
        blockers.append(next_subgoal.success_condition or "The task needs clarification before automation continues.")
    else:
        pending_repair = app_context.get("pending_repair")
        if isinstance(pending_repair, dict) and str(pending_repair.get("subgoal_id") or "") == next_subgoal.id:
            status = "recovering"
            next_action = "repair"
        exhausted_ids = [str(item.get("id")) for item in items if item.get("exhausted")]
        if exhausted_ids:
            warnings.append(f"Retry budget exhausted for {', '.join(exhausted_ids[:3])}.")
        if not next_subgoal.capability_preference:
            warnings.append("The next subgoal has no preferred capability.")
        if not next_subgoal.completion_evidence:
            warnings.append("The next subgoal has no explicit completion evidence requirement.")

    return {
        "status": status,
        "can_continue": can_continue,
        "requires_review": requires_review,
        "requires_user": requires_user,
        "next_action": next_action,
        "next_subgoal_id": next_subgoal.id if next_subgoal is not None else None,
        "blockers": blockers[:4],
        "warnings": warnings[:4],
    }


def _review_blocker_message(review_type: str | None) -> str:
    if review_type == "stage_review":
        return "A replanned stage is waiting for review before execution continues."
    if review_type == "step_approval":
        return "The next action is waiting for approval before execution continues."
    return "The generated plan is waiting for review before execution starts."


def _summary_retry_remaining(state: ExecutionState, subgoal: Subgoal) -> int:
    if subgoal.status == "completed":
        return 0
    if subgoal.id in state.failure_budget:
        return max(0, int(state.failure_budget.get(subgoal.id, 0) or 0))
    return max(0, int(subgoal.max_attempts or 1) - int(subgoal.attempts or 0))


def _subgoal_can_continue_for_summary(state: ExecutionState, subgoal: Subgoal) -> bool:
    pending_repair = state.app_context.get("pending_repair") if isinstance(state.app_context, dict) else None
    if isinstance(pending_repair, dict) and str(pending_repair.get("subgoal_id") or "") == subgoal.id:
        return True
    return _summary_retry_remaining(state, subgoal) > 0 and subgoal.can_retry()


def _plan_blocked_reason(state: ExecutionState, items: list[dict[str, Any]]) -> str | None:
    if state.task_graph.is_complete():
        return None
    if any(item.get("is_next") for item in items):
        return None
    exhausted = [item["id"] for item in items if item.get("exhausted")]
    waiting = [
        item["id"]
        for item in items
        if item.get("status") != "completed" and not item.get("ready") and not item.get("exhausted")
    ]
    if exhausted:
        return f"Retry budget exhausted for {', '.join(exhausted[:3])}."
    if waiting:
        return f"Waiting on prerequisites for {', '.join(waiting[:3])}."
    if state.task_graph.subgoals:
        return "No remaining subgoal is ready to execute."
    return "The task graph has no subgoals."


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if not lowered:
            return None
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        return None
    return bool(value)


def _bool_value(value: Any, *, default: bool = False) -> bool:
    parsed = _optional_bool(value)
    return default if parsed is None else parsed


def _normalize_decision_type(value: Any) -> str:
    normalized = str(value or "step_approval").strip().lower()
    return normalized if normalized in {"plan_review", "stage_review", "step_approval"} else "step_approval"


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
