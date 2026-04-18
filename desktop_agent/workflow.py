from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import time
from typing import Any

from desktop_agent.actions import Action, PlanResult
from desktop_agent.windows_env import DesktopEnvironment


RISK_LEVELS = {"low", "medium", "high", "critical"}
FAILURE_KINDS = {
    "transient_failure",
    "blocked_by_ui",
    "requires_auth",
    "requires_human",
    "capability_mismatch",
    "goal_ambiguous",
    "approval_rejected",
}
SUBGOAL_STATUSES = {"pending", "in_progress", "completed", "failed", "blocked"}


def _normalize_risk_level(value: str | None) -> str:
    normalized = str(value or "low").strip().lower()
    return normalized if normalized in RISK_LEVELS else "low"


def _normalize_failure_kind(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in FAILURE_KINDS else None


def _normalize_subgoal_status(value: str | None) -> str:
    normalized = str(value or "pending").strip().lower()
    return normalized if normalized in SUBGOAL_STATUSES else "pending"


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
            required=bool(payload.get("required", True)),
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
    success: bool
    evidence: list[dict[str, Any]] = field(default_factory=list)
    failure_kind: str | None = None
    message: str | None = None
    verified_at: float = field(default_factory=time.time)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "VerificationResult":
        return cls(
            success=bool(payload.get("success", False)),
            evidence=list(payload.get("evidence", []) or []),
            failure_kind=_normalize_failure_kind(payload.get("failure_kind")),
            message=_optional_str(payload.get("message")),
            verified_at=float(payload.get("verified_at", time.time()) or time.time()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "evidence": list(self.evidence),
            "failure_kind": self.failure_kind,
            "message": self.message,
            "verified_at": self.verified_at,
        }


@dataclass(slots=True)
class StepProposal:
    intent: str
    actions: list[Action] = field(default_factory=list)
    expected_evidence: list[EvidenceRequirement] = field(default_factory=list)
    risk_level: str = "low"
    fallbacks: list[str] = field(default_factory=list)
    timeout: float | None = None
    capability: str = "desktop_gui"
    requires_approval: bool = False
    target_scope: str | None = None
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
            capability=capability,
            requires_approval=requires_approval,
            target_scope=target_scope,
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
            risk_level=_normalize_risk_level(payload.get("risk_level")),
            fallbacks=[str(item).strip() for item in payload.get("fallbacks", []) or [] if str(item).strip()],
            timeout=_optional_float(payload.get("timeout")),
            capability=str(payload.get("capability", "desktop_gui")).strip() or "desktop_gui",
            requires_approval=bool(payload.get("requires_approval", False)),
            target_scope=_optional_str(payload.get("target_scope")),
            rationale=_optional_str(payload.get("rationale")),
            current_focus=_optional_str(payload.get("current_focus")),
            remaining_steps=[str(item).strip() for item in payload.get("remaining_steps", []) or [] if str(item).strip()],
            completes_subgoal=bool(payload.get("completes_subgoal", False)),
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
            "risk_level": self.risk_level,
            "fallbacks": list(self.fallbacks),
            "timeout": self.timeout,
            "capability": self.capability,
            "requires_approval": self.requires_approval,
            "target_scope": self.target_scope,
            "rationale": self.rationale,
            "current_focus": self.current_focus,
            "remaining_steps": list(self.remaining_steps),
            "completes_subgoal": self.completes_subgoal,
        }


@dataclass(slots=True)
class Subgoal:
    id: str
    title: str
    success_condition: str
    capability_preference: str | None = None
    risk_level: str = "low"
    retry_budget: int = 2
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
            success_condition=str(payload.get("success_condition", "")).strip() or "Confirm the subgoal has been completed.",
            capability_preference=_optional_str(payload.get("capability_preference")),
            risk_level=_normalize_risk_level(payload.get("risk_level")),
            retry_budget=max(0, int(payload.get("retry_budget", 2) or 0)),
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
            "success_condition": self.success_condition,
            "capability_preference": self.capability_preference,
            "risk_level": self.risk_level,
            "retry_budget": self.retry_budget,
            "status": self.status,
            "attempts": self.attempts,
            "notes": list(self.notes),
            "failed_capabilities": list(self.failed_capabilities),
            "completion_evidence": self.completion_evidence,
        }


@dataclass(slots=True)
class TaskGraph:
    task: str
    subgoals: list[Subgoal] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    risk_points: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TaskGraph":
        return cls(
            task=str(payload.get("task", "")).strip(),
            subgoals=[Subgoal.from_dict(item) for item in payload.get("subgoals", []) or [] if isinstance(item, dict)],
            success_criteria=[
                str(item).strip() for item in payload.get("success_criteria", []) or [] if str(item).strip()
            ],
            constraints=[str(item).strip() for item in payload.get("constraints", []) or [] if str(item).strip()],
            risk_points=[str(item).strip() for item in payload.get("risk_points", []) or [] if str(item).strip()],
            created_at=float(payload.get("created_at", time.time()) or time.time()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "subgoals": [item.to_dict() for item in self.subgoals],
            "success_criteria": list(self.success_criteria),
            "constraints": list(self.constraints),
            "risk_points": list(self.risk_points),
            "created_at": self.created_at,
        }

    def current_subgoal(self) -> Subgoal | None:
        for subgoal in self.subgoals:
            if subgoal.status in {"pending", "in_progress", "blocked"}:
                return subgoal
        return None

    def mark_in_progress(self, subgoal_id: str) -> None:
        for subgoal in self.subgoals:
            if subgoal.id == subgoal_id and subgoal.status == "pending":
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
    actions: list[Action] = field(default_factory=list)
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
            actions=[Action.from_dict(item) for item in payload.get("actions", []) or []],
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
            "actions": [item.to_dict() for item in self.actions],
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
    observations: list[str] = field(default_factory=list)
    active_app: str | None = None
    active_window_title: str | None = None
    clipboard_text: str | None = None
    active_driver: str | None = None
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
            "observations": list(self.observations),
            "active_app": self.active_app,
            "active_window_title": self.active_window_title,
            "clipboard_text": self.clipboard_text,
            "active_driver": self.active_driver,
            "step_index": self.step_index,
            "captured_at": self.captured_at,
        }


@dataclass(slots=True)
class ExecutionState:
    task: str
    run_id: str
    task_graph: TaskGraph
    world_model: WorldModel | None = None
    memory: list[str] = field(default_factory=list)
    facts: list[ObservedFact] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)
    pending_decision: PendingDecision | None = None
    last_step: StepProposal | None = None
    last_verification: VerificationResult | None = None
    completed: bool = False
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ExecutionState":
        return cls(
            task=str(payload.get("task", "")).strip(),
            run_id=str(payload.get("run_id", "")).strip(),
            task_graph=TaskGraph.from_dict(payload.get("task_graph", {}) or {}),
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
            completed=bool(payload.get("completed", False)),
            started_at=float(payload.get("started_at", time.time()) or time.time()),
            updated_at=float(payload.get("updated_at", time.time()) or time.time()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "run_id": self.run_id,
            "task_graph": self.task_graph.to_dict(),
            "world_model": self.world_model.to_dict() if self.world_model is not None else None,
            "memory": list(self.memory),
            "facts": [item.to_dict() for item in self.facts],
            "failures": list(self.failures),
            "pending_decision": self.pending_decision.to_dict() if self.pending_decision is not None else None,
            "last_step": self.last_step.to_dict() if self.last_step is not None else None,
            "last_verification": self.last_verification.to_dict() if self.last_verification is not None else None,
            "completed": self.completed,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
        }

    def current_subgoal(self) -> Subgoal | None:
        return self.task_graph.current_subgoal()


def build_execution_plan_summary(state: ExecutionState) -> dict[str, Any]:
    current_subgoal = state.current_subgoal()
    return {
        "task": state.task,
        "completed": state.completed,
        "current_subgoal": current_subgoal.to_dict() if current_subgoal is not None else None,
        "subgoals": [item.to_dict() for item in state.task_graph.subgoals],
        "pending_decision": state.pending_decision.to_dict() if state.pending_decision is not None else None,
        "last_step": state.last_step.to_dict() if state.last_step is not None else None,
        "last_verification": state.last_verification.to_dict() if state.last_verification is not None else None,
        "facts": [item.to_dict() for item in state.facts],
        "updated_at": state.updated_at,
    }


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
