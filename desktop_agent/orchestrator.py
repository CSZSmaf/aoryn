from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from desktop_agent.capabilities import CapabilityExecutor
from desktop_agent.config import AgentConfig
from desktop_agent.planner import TaskGraphPlanner
from desktop_agent.recipes import TaskRecipeMemory
from desktop_agent.workflow import (
    ExecutionState,
    ObservedFact,
    StepProposal,
    Subgoal,
    TaskGraph,
    VerificationResult,
    WorldModel,
)


_RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
_RISK_TERMS = (
    "login",
    "log in",
    "sign in",
    "password",
    "otp",
    "checkout",
    "purchase",
    "buy",
    "pay",
    "submit",
    "send",
    "delete",
    "remove",
    "overwrite",
    "install",
    "shell",
    "terminal",
    "powershell",
    "cmd",
    "permission",
    "private",
    "secret",
    "token",
    "登录",
    "登陆",
    "验证码",
    "支付",
    "付款",
    "购买",
    "买",
    "购物车",
    "结账",
    "下单",
    "提交",
    "发送",
    "删除",
    "移除",
    "覆盖",
    "安装",
    "卸载",
    "授权",
    "权限",
    "隐私",
    "密码",
    "终端",
    "命令",
    "命令行",
    "注册表",
)
_FAILURE_ALIASES = {
    "blocked_by_ui": "blocked_ui",
    "goal_ambiguous": "verification_failed",
    "transient_failure": "verification_failed",
    "requires_human": "requires_user",
    "requires_auth": "requires_user",
    "requires_clarification": "requires_user",
    "approval_rejected": "safety_gate",
}
_STANDARD_FAILURE_KINDS = {
    "stale_target",
    "blocked_ui",
    "missing_data",
    "capability_mismatch",
    "verification_failed",
    "safety_gate",
    "requires_user",
}


@dataclass(slots=True)
class TaskOrchestrator:
    config: AgentConfig
    task_graph_planner: TaskGraphPlanner
    capability_executor: CapabilityExecutor
    recipe_memory: TaskRecipeMemory

    def initialize_state(self, *, task: str, run_id: str, world_model: WorldModel) -> ExecutionState:
        task_graph = self.task_graph_planner.plan(task, history=[], world_model=world_model)
        return self.initialize_state_from_graph(
            task=task,
            run_id=run_id,
            task_graph=task_graph,
            world_model=world_model,
            plan_source="planner",
        )

    def initialize_state_from_graph(
        self,
        *,
        task: str,
        run_id: str,
        task_graph: TaskGraph,
        world_model: WorldModel,
        plan_source: str = "planner",
    ) -> ExecutionState:
        task_graph = TaskGraph.from_dict(task_graph.to_dict())
        task_graph.task = task
        try:
            self.recipe_memory.apply_hints(task_graph)
        except Exception:
            pass
        state = ExecutionState(
            task=task,
            run_id=run_id,
            task_graph=task_graph,
            world_model=world_model,
            app_context={"pending_repair": None, "plan_source": plan_source},
            current_surface_kind=world_model.surface_kind,
            started_at=time.time(),
            updated_at=time.time(),
        )
        self.prime_state(state, world_model=world_model)
        return state

    def prime_state(self, state: ExecutionState, *, world_model: WorldModel | None = None) -> None:
        if not self.config.task_workspace_enabled:
            return
        for subgoal in state.task_graph.subgoals:
            state.failure_budget.setdefault(subgoal.id, max(1, int(self.config.max_failures_per_subgoal)))
        if not state.orchestration_phase:
            state.orchestration_phase = "planning"
        if state.current_subgoal() is None:
            state.orchestration_phase = "complete" if state.task_graph.is_complete() else "blocked"
        elif state.orchestration_phase == "planning":
            state.orchestration_phase = "stage_ready"
        if world_model is not None:
            state.workspace.add_world_model(world_model)
        state.active_specialist = state.active_specialist or self.select_specialist(
            subgoal=state.current_subgoal(),
            world_model=world_model,
        )
        state.updated_at = time.time()

    def observe_world(self, *, state: ExecutionState, world_model: WorldModel) -> list[ObservedFact]:
        state.orchestration_phase = "observing"
        facts = self.capability_executor.observe(world_model)
        if self.config.task_workspace_enabled:
            state.workspace.add_world_model(world_model)
            state.workspace.add_facts(facts)
        state.updated_at = time.time()
        return facts

    def pending_review_type(self, state: ExecutionState) -> str | None:
        if state.pending_decision is not None:
            pending_type = str(state.pending_decision.decision_type or "").strip().lower()
            if pending_type not in {"plan_review", "stage_review"}:
                return None
        stage_status = str(state.app_context.get("stage_review_status") or "").strip().lower()
        if stage_status in {"pending", "cancelled", "canceled"}:
            return "stage_review"
        if self._plan_review_required(state):
            return "plan_review"
        return None

    def prepare_stage(self, *, state: ExecutionState, world_model: WorldModel) -> Subgoal | None:
        self.prime_state(state, world_model=world_model)
        subgoal = self._next_continuable_subgoal(state)
        if subgoal is None:
            state.orchestration_phase = "complete" if state.task_graph.is_complete() else "blocked"
            state.active_specialist = None
            state.app_context.pop("active_subgoal_id", None)
            return None
        state.orchestration_phase = "stage_ready"
        state.app_context["active_subgoal_id"] = subgoal.id
        state.active_specialist = self.select_specialist(subgoal=subgoal, world_model=world_model)
        state.updated_at = time.time()
        return subgoal

    def propose_step(self, *, state: ExecutionState, world_model: WorldModel) -> StepProposal:
        state.orchestration_phase = "proposing_step"
        proposal = self.capability_executor.propose_step(execution_state=state, world_model=world_model)
        state.active_specialist = self.select_specialist(
            subgoal=state.current_subgoal(),
            world_model=world_model,
            capability=proposal.capability,
        )
        state.orchestration_phase = "awaiting_approval" if proposal.requires_approval else "executing"
        if self.config.task_workspace_enabled:
            state.workspace.add_note(f"Specialist {state.active_specialist} proposed: {proposal.intent}")
        state.updated_at = time.time()
        return proposal

    def record_decision(
        self,
        *,
        state: ExecutionState,
        decision_type: str,
        status: str,
        risk_level: str,
        summary: str,
        note: str | None = None,
    ) -> None:
        payload = {
            "decision_type": decision_type,
            "status": status,
            "risk_level": risk_level,
            "summary": summary,
            "note": note,
            "recorded_at": time.time(),
        }
        state.stage_decisions.append(payload)
        del state.stage_decisions[:-20]
        if self.config.task_workspace_enabled:
            state.workspace.add_decision(payload)
        state.orchestration_phase = "stage_ready" if status == "approved" else "awaiting_approval"
        state.updated_at = time.time()

    def record_step_result(
        self,
        *,
        state: ExecutionState,
        step: StepProposal,
        verification: VerificationResult,
        world_model: WorldModel,
    ) -> None:
        standard_kind = standardize_failure_kind(verification.failure_kind)
        if verification.status == "failed":
            self.decrement_failure_budget(state=state, subgoal=state.current_subgoal())
            state.orchestration_phase = "recovering"
        elif verification.status == "partial_progress":
            state.orchestration_phase = "stage_ready"
        else:
            state.orchestration_phase = "verifying"
        state.active_specialist = self.select_specialist(
            subgoal=state.current_subgoal(),
            world_model=world_model,
            capability=step.capability,
        )
        if self.config.task_workspace_enabled:
            state.workspace.add_world_model(world_model)
            state.workspace.add_evidence(
                {
                    "subgoal_id": getattr(state.current_subgoal(), "id", None),
                    "specialist": state.active_specialist,
                    "capability": step.capability,
                    "status": verification.status,
                    "failure_kind": standard_kind,
                    "message": verification.message,
                    "verified_at": verification.verified_at,
                }
            )
        state.updated_at = time.time()

    def replan_remaining(
        self,
        *,
        state: ExecutionState,
        world_model: WorldModel | None,
        failure: VerificationResult,
    ) -> bool:
        replan_count = int(state.app_context.get("replan_count", 0) or 0)
        if replan_count >= max(0, int(self.config.max_replans_per_run)):
            state.last_replan_reason = "Replan budget exhausted."
            state.app_context["recovery_reason"] = state.last_replan_reason
            state.orchestration_phase = "blocked"
            return False
        old_risk = task_graph_risk_level(state.task_graph)
        new_graph = self.task_graph_planner.replan_remaining(state, world_model, failure)
        state.task_graph = new_graph
        try:
            self.recipe_memory.apply_hints(state.task_graph)
        except Exception:
            pass
        refreshed_budget = max(1, int(self.config.max_failures_per_subgoal))
        for subgoal in state.task_graph.subgoals:
            if subgoal.status == "completed":
                state.failure_budget.setdefault(subgoal.id, refreshed_budget)
                continue
            subgoal.attempts = 0
            state.failure_budget[subgoal.id] = refreshed_budget
        new_risk = task_graph_risk_level(state.task_graph)
        reason = failure.message or standardize_failure_kind(failure.failure_kind) or "verification_failed"
        state.last_replan_reason = reason
        state.app_context["last_replan_at"] = time.time()
        state.app_context["last_replan_reason"] = reason
        state.app_context["replan_count"] = replan_count + 1
        if self._stage_review_required_after_replan(old_risk=old_risk, new_risk=new_risk):
            state.app_context["stage_review_status"] = "pending"
            state.app_context["stage_review_reason"] = (
                f"Replanned remaining work after {reason}; risk changed from {old_risk} to {new_risk}."
            )
            state.orchestration_phase = "stage_review"
        else:
            state.orchestration_phase = "stage_ready"
        state.updated_at = time.time()
        return True

    def decrement_failure_budget(self, *, state: ExecutionState, subgoal: Subgoal | None) -> None:
        if subgoal is None:
            return
        state.failure_budget.setdefault(subgoal.id, max(1, int(self.config.max_failures_per_subgoal)))
        state.failure_budget[subgoal.id] = max(0, state.failure_budget[subgoal.id] - 1)

    def can_retry_subgoal(self, *, state: ExecutionState, subgoal: Subgoal) -> bool:
        remaining = state.failure_budget.get(subgoal.id, max(1, int(self.config.max_failures_per_subgoal)))
        return remaining > 0 and subgoal.can_retry()

    def _can_continue_subgoal(self, *, state: ExecutionState, subgoal: Subgoal) -> bool:
        pending_repair = state.app_context.get("pending_repair") if isinstance(state.app_context, dict) else None
        if isinstance(pending_repair, dict) and str(pending_repair.get("subgoal_id")) == subgoal.id:
            return True
        return self.can_retry_subgoal(state=state, subgoal=subgoal)

    def _next_continuable_subgoal(self, state: ExecutionState) -> Subgoal | None:
        for status in ("in_progress", "pending", "blocked"):
            for subgoal in state.task_graph.subgoals:
                if subgoal.status != status or not state.task_graph.is_ready(subgoal):
                    continue
                if self._can_continue_subgoal(state=state, subgoal=subgoal):
                    return subgoal
                self._mark_retry_exhausted(state=state, subgoal=subgoal)
        return None

    def _mark_retry_exhausted(self, *, state: ExecutionState, subgoal: Subgoal) -> None:
        subgoal.status = "blocked"
        message = f"Subgoal {subgoal.id} is blocked because its retry budget is exhausted."
        if message not in subgoal.notes:
            subgoal.notes.append(message)
        if state.app_context.get("active_subgoal_id") == subgoal.id:
            state.app_context.pop("active_subgoal_id", None)
        state.app_context["recovery_reason"] = message
        state.updated_at = time.time()

    def mark_complete(self, state: ExecutionState) -> None:
        state.orchestration_phase = "complete"
        state.active_specialist = None
        state.app_context.pop("active_subgoal_id", None)
        state.updated_at = time.time()

    def select_specialist(
        self,
        *,
        subgoal: Subgoal | None,
        world_model: WorldModel | None = None,
        capability: str | None = None,
    ) -> str | None:
        if subgoal is None:
            return None
        capability_name = str(capability or subgoal.capability_preference or "").strip().lower()
        goal_type = str(subgoal.goal_type or "").strip().lower()
        title = str(subgoal.title or "").strip().lower()
        if capability_name == "guarded_shell_recipe":
            return "shell_recipe"
        if capability_name in {"filesystem", "office_com"} or goal_type in {"save", "transfer"}:
            return "file_workspace"
        if capability_name == "clipboard":
            return "file_workspace"
        if capability_name in {"browser_dom"} or (world_model is not None and world_model.browser_snapshot):
            if goal_type in {"read", "extract"} or any(term in title for term in ("search", "news", "summar", "research", "搜索", "总结")):
                return "browser_research"
            return "browser_operator"
        if goal_type in {"read", "extract", "transform"} or any(term in title for term in ("summar", "总结", "整理")):
            return "summarizer"
        return "desktop_operator"

    def _plan_review_required(self, state: ExecutionState) -> bool:
        status = str(state.app_context.get("plan_review_status") or "").strip().lower()
        if status in {"approved", "rejected"}:
            return False
        policy = str(getattr(self.config, "plan_review_policy", "low_risk_auto") or "low_risk_auto").strip().lower()
        if policy == "never":
            return False
        current_subgoal = state.current_subgoal()
        if current_subgoal is not None and current_subgoal.goal_type == "clarify":
            return False
        if policy == "always":
            return True
        return task_graph_risk_level(state.task_graph) != "low" or task_graph_is_ambiguous(state.task_graph)

    def _stage_review_required_after_replan(self, *, old_risk: str, new_risk: str) -> bool:
        policy = str(getattr(self.config, "stage_review_policy", "risk_change") or "risk_change").strip().lower()
        if policy == "never":
            return False
        if policy == "always":
            return True
        return _RISK_ORDER.get(new_risk, 0) > _RISK_ORDER.get(old_risk, 0)


def task_graph_risk_level(task_graph: TaskGraph) -> str:
    highest = "low"
    intent = task_graph.intent if isinstance(task_graph.intent, dict) else {}
    intent_risk = str(intent.get("risk_level") or "low").strip().lower()
    if intent_risk in _RISK_ORDER:
        highest = intent_risk
    for subgoal in task_graph.subgoals:
        risk = str(subgoal.risk_level or "low").strip().lower()
        if risk in _RISK_ORDER and _RISK_ORDER[risk] > _RISK_ORDER[highest]:
            highest = risk
        text = f"{subgoal.title} {subgoal.goal or ''}".lower()
        if any(term in text for term in _RISK_TERMS) and _RISK_ORDER[highest] < _RISK_ORDER["high"]:
            highest = "high"
    if task_graph.risk_points and highest == "low":
        highest = "medium"
    return highest


def task_graph_is_ambiguous(task_graph: TaskGraph) -> bool:
    intent = task_graph.intent if isinstance(task_graph.intent, dict) else {}
    ambiguity = str(intent.get("ambiguity") or "low").strip().lower()
    return ambiguity in {"medium", "high"} or _optional_bool(intent.get("requires_clarification")) is True


def _optional_bool(value: object) -> bool | None:
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


def standardize_failure_kind(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    if normalized in _STANDARD_FAILURE_KINDS:
        return normalized
    return _FAILURE_ALIASES.get(normalized, "verification_failed")
