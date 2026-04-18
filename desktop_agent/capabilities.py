from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any
from urllib.parse import urlparse

from desktop_agent.actions import Action, PlanResult
from desktop_agent.config import AgentConfig
from desktop_agent.drivers import DriverRegistry
from desktop_agent.planner import PlannerError
from desktop_agent.web_agent import WebAgent
from desktop_agent.workflow import (
    EvidenceRequirement,
    ExecutionState,
    ObservedFact,
    PendingDecision,
    StepProposal,
    Subgoal,
    VerificationResult,
    WorldModel,
)


_HIGH_RISK_TERMS = (
    "login",
    "log in",
    "sign in",
    "sign-in",
    "password",
    "otp",
    "auth",
    "checkout",
    "purchase",
    "buy",
    "cart",
    "pay",
    "submit",
    "send",
    "delete",
    "remove",
    "overwrite",
    "install",
    "powershell",
    "terminal",
    "shell",
    "cmd",
    "registry",
    "权限",
    "登录",
    "支付",
    "购物车",
    "下单",
    "提交",
    "发送",
    "删除",
    "覆盖",
    "安装",
    "终端",
    "命令行",
)

_MEDIUM_RISK_TERMS = (
    "save",
    "download",
    "upload",
    "bookmark",
    "favorite",
    "收藏",
    "保存",
    "下载",
    "上传",
)


def _normalize_text(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _extract_domain(target: str) -> str:
    parsed = urlparse(target if "://" in target else f"https://{target}")
    return str(parsed.netloc or parsed.path).strip().lower()


def infer_step_risk_level(text: str, actions: list[Action]) -> str:
    haystacks = [_normalize_text(text)]
    haystacks.extend(_normalize_text(action.text) for action in actions if action.text)
    haystacks.extend(_normalize_text(action.title) for action in actions if action.title)
    joined = " ".join(item for item in haystacks if item)
    if any(term in joined for term in _HIGH_RISK_TERMS):
        return "high"
    if any(term in joined for term in _MEDIUM_RISK_TERMS):
        return "medium"
    if any(action.type == "shell_recipe_request" for action in actions):
        return "high"
    return "low"


def approval_required_for_policy(policy: str, risk_level: str, actions: list[Action]) -> bool:
    normalized_policy = _normalize_text(policy) or "tiered"
    normalized_risk = _normalize_text(risk_level) or "low"
    if normalized_policy in {"strict", "always"}:
        return bool(actions)
    if normalized_policy in {"high autonomy", "autonomous"}:
        return normalized_risk == "critical"
    return normalized_risk in {"high", "critical"} or any(action.type == "shell_recipe_request" for action in actions)


class CapabilityAdapter:
    name = "desktop_gui"

    def observe(self, world_model: WorldModel) -> list[ObservedFact]:
        return []

    def extract_anchors(self, world_model: WorldModel) -> list[str]:
        anchors: list[str] = []
        if world_model.active_window_title:
            anchors.append(str(world_model.active_window_title))
        for fact in world_model.facts:
            if fact.value:
                anchors.append(str(fact.value))
        return anchors[:8]

    def can_handle(self, subgoal: Subgoal, world_model: WorldModel) -> float:
        return 0.0

    def plan_step(
        self,
        *,
        subgoal: Subgoal,
        world_model: WorldModel,
        execution_state: ExecutionState,
        config: AgentConfig,
        planner,
    ) -> StepProposal | None:
        return None

    def propose_step(
        self,
        *,
        subgoal: Subgoal,
        world_model: WorldModel,
        execution_state: ExecutionState,
        config: AgentConfig,
        planner,
    ) -> StepProposal | None:
        return self.plan_step(
            subgoal=subgoal,
            world_model=world_model,
            execution_state=execution_state,
            config=config,
            planner=planner,
        )

    def build_expected_evidence(
        self,
        *,
        subgoal: Subgoal,
        world_model: WorldModel,
        actions: list[Action],
    ) -> list[EvidenceRequirement]:
        evidence: list[EvidenceRequirement] = []
        for action in actions:
            if action.type in {"launch_app", "open_app_if_needed"} and action.app:
                evidence.append(
                    EvidenceRequirement(
                        kind="active_app_is",
                        value=action.app,
                        detail=f"The active app should become {action.app}.",
                    )
                )
            elif action.type in {"focus_window", "wait_for_window"} and (action.title or action.text):
                evidence.append(
                    EvidenceRequirement(
                        kind="window_contains",
                        value=action.title or action.text,
                        detail="The target window should be present or focused.",
                    )
                )
            elif action.type == "browser_open" and action.text:
                evidence.append(
                    EvidenceRequirement(
                        kind="browser_url_contains",
                        value=_extract_domain(action.text),
                        detail="The browser should open the requested destination.",
                    )
                )
            elif action.type == "browser_search" and action.text:
                evidence.append(
                    EvidenceRequirement(
                        kind="browser_text_contains",
                        value=action.text.split()[0],
                        detail="The search results should mention the query.",
                        required=False,
                    )
                )
            elif action.type in {
                "browser_dom_click",
                "browser_dom_fill",
                "browser_dom_select",
                "browser_dom_wait",
                "browser_dom_extract",
            }:
                evidence.append(
                    EvidenceRequirement(
                        kind="browser_available",
                        value=action.selector or action.text,
                        detail="A browser DOM context should remain available.",
                        required=False,
                    )
                )
            elif action.type in {"uia_invoke", "uia_set_value", "uia_select", "uia_expand"}:
                evidence.append(
                    EvidenceRequirement(
                        kind="window_contains",
                        value=action.title or world_model.active_window_title,
                        detail="The target desktop window should still be active.",
                        required=False,
                    )
                )
        return evidence

    def build_progress_signals(
        self,
        *,
        subgoal: Subgoal,
        world_model: WorldModel,
        actions: list[Action],
    ) -> list[str]:
        signals = [subgoal.success_condition]
        if world_model.active_window_title:
            signals.append(world_model.active_window_title)
        for action in actions:
            target = action.selector or action.text or action.title or action.app
            if target:
                signals.append(str(target))
        return [item for item in signals if item][:6]

    def plan_repair(
        self,
        *,
        subgoal: Subgoal,
        world_model: WorldModel,
        execution_state: ExecutionState,
        previous_step: StepProposal | None,
        verification: VerificationResult | None,
        config: AgentConfig,
    ) -> StepProposal | None:
        if verification is not None and verification.failure_kind == "blocked_by_ui":
            focus_target = world_model.active_window_title or (previous_step.current_focus if previous_step else None)
            if focus_target:
                action = Action.from_dict({"type": "focus_window", "title": focus_target})
                return StepProposal(
                    intent=f"Refocus the target window before retrying: {subgoal.title}",
                    actions=[action],
                    expected_evidence=[
                        EvidenceRequirement(
                            kind="window_contains",
                            value=focus_target,
                            detail="The target window should become active again.",
                        )
                    ],
                    progress_signals=[focus_target],
                    repair_strategy=["retry_with_fresh_observation"],
                    risk_level="low",
                    capability=self.name,
                    current_focus=focus_target,
                )
        return None

    def verify_step(
        self,
        *,
        subgoal: Subgoal,
        step: StepProposal,
        before: WorldModel,
        after: WorldModel,
    ) -> VerificationResult:
        evidence_results: list[dict[str, Any]] = []
        all_required_satisfied = True
        any_satisfied = False
        for requirement in step.expected_evidence:
            satisfied = _evaluate_evidence(requirement, after)
            evidence_results.append(
                {
                    "kind": requirement.kind,
                    "value": requirement.value,
                    "detail": requirement.detail,
                    "required": requirement.required,
                    "satisfied": satisfied,
                }
            )
            any_satisfied = any_satisfied or satisfied
            if requirement.required and not satisfied:
                all_required_satisfied = False

        completion_requirement = _completion_requirement(subgoal)
        completion_satisfied = True
        if completion_requirement is not None:
            completion_satisfied = _evaluate_completion_evidence(
                requirement=completion_requirement,
                before=before,
                after=after,
            )
            evidence_results.append(
                {
                    "kind": completion_requirement.kind,
                    "value": completion_requirement.value,
                    "detail": completion_requirement.detail,
                    "required": True,
                    "satisfied": completion_satisfied,
                    "scope": "subgoal_completion",
                }
            )

        if all_required_satisfied and completion_satisfied:
            return VerificationResult(
                success=True,
                status="success",
                evidence=evidence_results,
                message="Evidence requirements were satisfied.",
            )

        progress_detected = any_satisfied or _detect_progress_signals(step.progress_signals, before=before, after=after)
        if progress_detected:
            return VerificationResult(
                success=False,
                status="partial_progress",
                evidence=evidence_results,
                failure_kind="transient_failure" if completion_satisfied else "goal_ambiguous",
                message=f"Observed partial progress for {subgoal.title}, but completion evidence is still missing.",
            )

        return VerificationResult(
            success=False,
            status="failed",
            evidence=evidence_results,
            failure_kind="capability_mismatch",
            message=f"Could not verify subgoal progress for {subgoal.title}.",
        )


class BrowserDOMCapability(CapabilityAdapter):
    name = "browser_dom"

    def __init__(self) -> None:
        self.web_agent = WebAgent()

    def observe(self, world_model: WorldModel) -> list[ObservedFact]:
        browser_snapshot = world_model.browser_snapshot or {}
        facts: list[ObservedFact] = []
        if browser_snapshot.get("url"):
            facts.append(ObservedFact(source=self.name, key="url", value=str(browser_snapshot["url"])))
        if browser_snapshot.get("title"):
            facts.append(ObservedFact(source=self.name, key="title", value=str(browser_snapshot["title"])))
        if browser_snapshot.get("text"):
            facts.append(ObservedFact(source=self.name, key="text", value=str(browser_snapshot["text"])[:400], confidence=0.8))
        return facts

    def extract_anchors(self, world_model: WorldModel) -> list[str]:
        browser_snapshot = world_model.browser_snapshot or {}
        anchors: list[str] = []
        for key in ("title", "url", "text"):
            value = str(browser_snapshot.get(key) or "").strip()
            if value:
                anchors.append(value[:200])
        return anchors[:6]

    def can_handle(self, subgoal: Subgoal, world_model: WorldModel) -> float:
        text = _normalize_text(subgoal.title)
        browser_like = any(
            token in text
            for token in ("browser", "website", "web", "search", "visit", "open ", "click link", "网页", "网站", "搜索", "访问")
        )
        if browser_like:
            return 0.95
        if world_model.browser_snapshot:
            return 0.75
        if world_model.active_app == "browser":
            return 0.8
        return 0.0

    def propose_step(
        self,
        *,
        subgoal: Subgoal,
        world_model: WorldModel,
        execution_state: ExecutionState,
        config: AgentConfig,
        planner,
    ) -> StepProposal | None:
        if navigation_plan := self.web_agent.build_navigation_plan(subgoal.title):
            return StepProposal.from_plan_result(
                navigation_plan,
                capability=self.name,
                risk_level=infer_step_risk_level(subgoal.title, navigation_plan.actions),
                expected_evidence=self.build_expected_evidence(
                    subgoal=subgoal,
                    world_model=world_model,
                    actions=navigation_plan.actions,
                ),
            )
        if direct_plan := self.web_agent.try_plan(subgoal.title):
            return StepProposal.from_plan_result(
                direct_plan,
                capability=self.name,
                risk_level=infer_step_risk_level(subgoal.title, direct_plan.actions),
                expected_evidence=self.build_expected_evidence(
                    subgoal=subgoal,
                    world_model=world_model,
                    actions=direct_plan.actions,
                ),
            )
        if follow_up_plan := self.web_agent.build_dom_follow_up_plan(subgoal.title, execution_state.memory):
            return StepProposal.from_plan_result(
                follow_up_plan,
                capability=self.name,
                risk_level=infer_step_risk_level(subgoal.title, follow_up_plan.actions),
                expected_evidence=self.build_expected_evidence(
                    subgoal=subgoal,
                    world_model=world_model,
                    actions=follow_up_plan.actions,
                ),
            )
        return None

    def plan_repair(
        self,
        *,
        subgoal: Subgoal,
        world_model: WorldModel,
        execution_state: ExecutionState,
        previous_step: StepProposal | None,
        verification: VerificationResult | None,
        config: AgentConfig,
    ) -> StepProposal | None:
        browser_snapshot = world_model.browser_snapshot or {}
        if verification is not None and verification.failure_kind == "stale_target":
            target = None
            for action in (previous_step.actions if previous_step is not None else []):
                target = action.selector or action.text or target
                if target:
                    break
            if target:
                action = Action.from_dict({"type": "browser_dom_wait", "selector": target if target.startswith(("#", ".", "[")) else None, "text": None if target.startswith(("#", ".", "[")) else target, "seconds": config.browser_dom_timeout})
                return StepProposal(
                    intent=f"Wait for the browser target to become stable again: {subgoal.title}",
                    actions=[action],
                    expected_evidence=[EvidenceRequirement(kind="browser_available", detail="A live browser DOM should be available.")],
                    progress_signals=[target],
                    repair_strategy=["re-anchor_target", "retry_with_fresh_observation"],
                    risk_level="low",
                    capability=self.name,
                    current_focus=subgoal.title,
                )
        if not browser_snapshot.get("url"):
            action = Action.from_dict({"type": "open_app_if_needed", "app": "browser"})
            return StepProposal(
                intent=f"Re-open the browser context for: {subgoal.title}",
                actions=[action],
                expected_evidence=[EvidenceRequirement(kind="active_app_is", value="browser", detail="The browser should be active.")],
                progress_signals=[subgoal.title],
                repair_strategy=["refresh_dom_context", "retry_with_fresh_observation"],
                risk_level="low",
                capability=self.name,
                current_focus=subgoal.title,
            )
        return super().plan_repair(
            subgoal=subgoal,
            world_model=world_model,
            execution_state=execution_state,
            previous_step=previous_step,
            verification=verification,
            config=config,
        )


class ClipboardCapability(CapabilityAdapter):
    name = "clipboard"

    def can_handle(self, subgoal: Subgoal, world_model: WorldModel) -> float:
        text = _normalize_text(subgoal.title)
        if any(token in text for token in ("copy", "paste", "clipboard", "复制", "粘贴", "剪贴板")):
            return 0.85
        return 0.0

    def propose_step(
        self,
        *,
        subgoal: Subgoal,
        world_model: WorldModel,
        execution_state: ExecutionState,
        config: AgentConfig,
        planner,
    ) -> StepProposal | None:
        text = _normalize_text(subgoal.title)
        actions: list[Action] = []
        if "paste" in text or "粘贴" in text:
            actions.append(Action.from_dict({"type": "clipboard_paste"}))
        elif "copy" in text or "复制" in text:
            actions.append(Action.from_dict({"type": "clipboard_copy"}))
        if not actions:
            return None
        return StepProposal(
            intent=f"Use the clipboard to progress: {subgoal.title}",
            actions=actions,
            capability=self.name,
            expected_evidence=[
                EvidenceRequirement(
                    kind="clipboard_or_input_changed",
                    detail="Clipboard or focused input state should change after the shortcut.",
                    required=False,
                )
            ],
            risk_level=infer_step_risk_level(subgoal.title, actions),
            current_focus=subgoal.title,
        )


class FileSystemCapability(CapabilityAdapter):
    name = "filesystem"

    def can_handle(self, subgoal: Subgoal, world_model: WorldModel) -> float:
        text = _normalize_text(subgoal.title)
        if any(token in text for token in ("file", "folder", "save", "open", "download", "上传", "文件", "保存", "打开")):
            return 0.45
        return 0.0


class OfficeCOMCapability(CapabilityAdapter):
    name = "office_com"

    def can_handle(self, subgoal: Subgoal, world_model: WorldModel) -> float:
        text = _normalize_text(subgoal.title)
        if any(token in text for token in ("excel", "powerpoint", "word", "spreadsheet", "slide", "ppt")):
            return 0.7
        title = _normalize_text(world_model.active_window_title)
        if any(token in title for token in ("excel", "powerpoint", "word")):
            return 0.9
        return 0.0


class WindowsUIACapability(CapabilityAdapter):
    name = "windows_uia"

    def can_handle(self, subgoal: Subgoal, world_model: WorldModel) -> float:
        if world_model.active_window_title and world_model.active_app not in {"browser"}:
            return 0.55
        return 0.15

    def extract_anchors(self, world_model: WorldModel) -> list[str]:
        anchors = super().extract_anchors(world_model)
        for item in world_model.uia_tree[:6]:
            name = str(item.get("name") or item.get("title") or "").strip()
            if name:
                anchors.append(name)
        return anchors[:8]


class GuardedShellRecipeCapability(CapabilityAdapter):
    name = "guarded_shell_recipe"

    _PYTHON_ENV_PATTERN = re.compile(
        r"\b(?:create|configure|set up|setup|prepare)\b.*\b(?:python)\b.*\b(?:env|environment|venv|virtualenv)\b",
        re.I,
    )
    _PIP_INSTALL_PATTERN = re.compile(r"\bpip\s+install\s+(?P<package>[A-Za-z0-9._\-]+)", re.I)

    def can_handle(self, subgoal: Subgoal, world_model: WorldModel) -> float:
        text = subgoal.title
        normalized = _normalize_text(text)
        if self._PYTHON_ENV_PATTERN.search(text):
            return 0.8
        if self._PIP_INSTALL_PATTERN.search(text):
            return 0.75
        if any(token in normalized for token in ("terminal", "shell", "command line", "终端", "命令行")):
            return 0.55
        return 0.0

    def propose_step(
        self,
        *,
        subgoal: Subgoal,
        world_model: WorldModel,
        execution_state: ExecutionState,
        config: AgentConfig,
        planner,
    ) -> StepProposal | None:
        text = subgoal.title.strip()
        recipe: str | None = None
        arguments: str | None = None

        package_match = self._PIP_INSTALL_PATTERN.search(text)
        if package_match:
            recipe = "pip_install"
            arguments = package_match.group("package")
        elif self._PYTHON_ENV_PATTERN.search(text):
            recipe = "python_env_bootstrap"
            arguments = text

        if not recipe:
            return None

        action = Action.from_dict(
            {
                "type": "shell_recipe_request",
                "recipe": recipe,
                "text": arguments or text,
                "risk_level": "high",
            }
        )
        return StepProposal(
            intent=f"Request a guarded shell recipe for: {subgoal.title}",
            actions=[action],
            expected_evidence=[
                EvidenceRequirement(
                    kind="file_observation",
                    detail="A file-system side effect or saved artifact should be observed after the recipe.",
                    required=False,
                )
            ],
            risk_level="high",
            capability=self.name,
            requires_approval=True,
            current_focus=subgoal.title,
            rationale="A controlled shell recipe is safer than letting the model emit arbitrary terminal commands.",
        )


class DesktopGUICapability(CapabilityAdapter):
    name = "desktop_gui"

    def can_handle(self, subgoal: Subgoal, world_model: WorldModel) -> float:
        return 0.35


@dataclass(slots=True)
class CapabilityRegistry:
    capabilities: list[CapabilityAdapter] = field(default_factory=list)

    def register(self, capability: CapabilityAdapter) -> None:
        self.capabilities.append(capability)

    def enabled(self, config: AgentConfig) -> list[CapabilityAdapter]:
        allowed = {item.strip().lower() for item in (config.enabled_capabilities or []) if str(item).strip()}
        if not allowed:
            return list(self.capabilities)
        return [capability for capability in self.capabilities if capability.name in allowed]

    def rank(
        self,
        *,
        subgoal: Subgoal,
        world_model: WorldModel,
        config: AgentConfig,
        execution_state: ExecutionState | None = None,
        driver_registry: DriverRegistry | None = None,
    ) -> list[tuple[CapabilityAdapter, float]]:
        candidates = self.enabled(config)
        driver = driver_registry.detect(world_model) if driver_registry is not None else None
        preferred = set(driver.preferred_capabilities()) if driver is not None else set()
        completion_kind = _completion_requirement_kind(subgoal)
        ranked: list[tuple[CapabilityAdapter, float]] = []
        for capability in candidates:
            score = capability.can_handle(subgoal, world_model)
            if capability.name == subgoal.capability_preference:
                score += 0.2
            if capability.name in preferred:
                score += 0.15
            if completion_kind and _capability_supports_evidence(capability.name, completion_kind):
                score += 0.12
            if _capability_prefers_structured(capability.name):
                structured_bonus = 0.1 if world_model.structured_sources else -0.05
                score += structured_bonus
            if capability.name in subgoal.failed_capabilities:
                score -= 0.25
            if execution_state is not None:
                recent_results = execution_state.capability_failures.get(_failure_key(subgoal.id, capability.name), [])[-3:]
                recent_failures = sum(1 for item in recent_results if item in {"failed", "partial_progress"})
                if recent_failures >= 2:
                    score -= 0.45
                elif recent_failures == 1:
                    score -= 0.15
                if recent_results and recent_results[-1] == "success":
                    score += 0.08
            ranked.append((capability, score))
        ranked.sort(key=lambda item: item[1], reverse=True)
        if ranked:
            return ranked
        fallback = candidates[-1] if candidates else DesktopGUICapability()
        return [(fallback, fallback.can_handle(subgoal, world_model))]

    def select(
        self,
        *,
        subgoal: Subgoal,
        world_model: WorldModel,
        config: AgentConfig,
        execution_state: ExecutionState | None = None,
        driver_registry: DriverRegistry | None = None,
    ) -> CapabilityAdapter:
        ranked = self.rank(
            subgoal=subgoal,
            world_model=world_model,
            config=config,
            execution_state=execution_state,
            driver_registry=driver_registry,
        )
        return ranked[0][0]


@dataclass(slots=True)
class CapabilityExecutor:
    config: AgentConfig
    planner: Any
    registry: CapabilityRegistry
    driver_registry: DriverRegistry | None = None

    def observe(self, world_model: WorldModel) -> list[ObservedFact]:
        facts: list[ObservedFact] = _world_model_facts(world_model)
        if self.driver_registry is not None:
            facts.extend(self.driver_registry.describe(world_model))
        for capability in self.registry.enabled(self.config):
            try:
                facts.extend(capability.observe(world_model))
            except Exception:
                continue
        return _dedupe_facts(facts)

    def choose_capability(self, *, subgoal: Subgoal, world_model: WorldModel) -> CapabilityAdapter:
        return self.registry.select(
            subgoal=subgoal,
            world_model=world_model,
            config=self.config,
            execution_state=None,
            driver_registry=self.driver_registry,
        )

    def rank_capabilities(
        self,
        *,
        subgoal: Subgoal,
        world_model: WorldModel,
        execution_state: ExecutionState,
    ) -> list[tuple[CapabilityAdapter, float]]:
        return self.registry.rank(
            subgoal=subgoal,
            world_model=world_model,
            config=self.config,
            execution_state=execution_state,
            driver_registry=self.driver_registry,
        )

    def propose_step(self, *, execution_state: ExecutionState, world_model: WorldModel) -> StepProposal:
        subgoal = execution_state.current_subgoal()
        if subgoal is None:
            return StepProposal(intent="Task already complete.", actions=[], capability="desktop_gui")

        pending_repair = execution_state.app_context.get("pending_repair")
        if isinstance(pending_repair, dict) and str(pending_repair.get("subgoal_id")) == subgoal.id:
            repair_proposal = self.propose_repair(
                execution_state=execution_state,
                world_model=world_model,
                previous_step=execution_state.last_step,
                verification=execution_state.last_verification,
            )
            if repair_proposal is not None:
                return repair_proposal

        ranked_capabilities = self.rank_capabilities(
            subgoal=subgoal,
            world_model=world_model,
            execution_state=execution_state,
        )
        selected_capability = ranked_capabilities[0][0]
        capability = selected_capability
        proposal: StepProposal | None = None
        for candidate, _score in ranked_capabilities:
            capability = candidate
            proposal = candidate.propose_step(
                subgoal=subgoal,
                world_model=world_model,
                execution_state=execution_state,
                config=self.config,
                planner=self.planner,
            )
            if proposal is not None:
                break
        if proposal is None:
            capability = selected_capability
            plan, target_scope = self._plan_with_fallback(
                subgoal=subgoal,
                world_model=world_model,
                history=execution_state.memory,
                execution_state=execution_state,
            )
            proposal = StepProposal.from_plan_result(
                plan,
                capability=capability.name,
                risk_level=infer_step_risk_level(subgoal.title, plan.actions),
                expected_evidence=capability.build_expected_evidence(
                    subgoal=subgoal,
                    world_model=world_model,
                    actions=plan.actions,
                ),
                requires_approval=False,
                target_scope=target_scope,
            )

        proposal.risk_level = _normalize_text(proposal.risk_level) or infer_step_risk_level(subgoal.title, proposal.actions)
        if not proposal.expected_evidence:
            proposal.expected_evidence = capability.build_expected_evidence(
                subgoal=subgoal,
                world_model=world_model,
                actions=proposal.actions,
            )
        driver = self.driver_registry.detect(world_model) if self.driver_registry is not None else None
        if driver is not None:
            proposal.expected_evidence = _merge_evidence_requirements(
                proposal.expected_evidence,
                driver.verification_hints(world_model),
            )
        if not proposal.progress_signals:
            proposal.progress_signals = capability.build_progress_signals(
                subgoal=subgoal,
                world_model=world_model,
                actions=proposal.actions,
            )
        if not proposal.repair_strategy:
            proposal.repair_strategy = _default_repair_strategy(subgoal=subgoal, proposal=proposal)
        if not proposal.cost_hint:
            proposal.cost_hint = _estimate_cost_hint(proposal.actions)
        proposal.requires_approval = proposal.requires_approval or approval_required_for_policy(
            self.config.approval_policy,
            proposal.risk_level,
            proposal.actions,
        )
        proposal.current_focus = proposal.current_focus or subgoal.title
        return proposal

    def propose_repair(
        self,
        *,
        execution_state: ExecutionState,
        world_model: WorldModel,
        previous_step: StepProposal | None,
        verification: VerificationResult | None,
    ) -> StepProposal | None:
        subgoal = execution_state.current_subgoal()
        if subgoal is None:
            return None
        if verification is not None and verification.failure_kind in {"requires_auth", "requires_human"}:
            return None

        ranked_capabilities = self.rank_capabilities(
            subgoal=subgoal,
            world_model=world_model,
            execution_state=execution_state,
        )
        primary = next((item for item, _score in ranked_capabilities if item.name == (previous_step.capability if previous_step else "")), None)
        if primary is None:
            primary = ranked_capabilities[0][0] if ranked_capabilities else DesktopGUICapability()

        proposal = primary.plan_repair(
            subgoal=subgoal,
            world_model=world_model,
            execution_state=execution_state,
            previous_step=previous_step,
            verification=verification,
            config=self.config,
        )
        if proposal is None and verification is not None and verification.failure_kind in {"capability_mismatch", "goal_ambiguous"}:
            for candidate, _score in ranked_capabilities:
                if previous_step is not None and candidate.name == previous_step.capability:
                    continue
                proposal = candidate.propose_step(
                    subgoal=subgoal,
                    world_model=world_model,
                    execution_state=execution_state,
                    config=self.config,
                    planner=self.planner,
                )
                if proposal is not None:
                    proposal.repair_strategy = proposal.repair_strategy or ["switch_capability", "retry_with_fresh_observation"]
                    break
        if proposal is None:
            return None
        if not proposal.expected_evidence:
            proposal.expected_evidence = primary.build_expected_evidence(
                subgoal=subgoal,
                world_model=world_model,
                actions=proposal.actions,
            )
        if not proposal.progress_signals:
            proposal.progress_signals = primary.build_progress_signals(
                subgoal=subgoal,
                world_model=world_model,
                actions=proposal.actions,
            )
        if not proposal.repair_strategy:
            proposal.repair_strategy = ["retry_with_fresh_observation"]
        proposal.cost_hint = proposal.cost_hint or _estimate_cost_hint(proposal.actions)
        return proposal

    def verify_step(
        self,
        *,
        execution_state: ExecutionState,
        step: StepProposal,
        before: WorldModel,
        after: WorldModel,
    ) -> VerificationResult:
        subgoal = execution_state.current_subgoal()
        if subgoal is None:
            return VerificationResult(success=True, status="success", evidence=[], message="No current subgoal remained.")
        capability = next(
            (item for item in self.registry.enabled(self.config) if item.name == step.capability),
            DesktopGUICapability(),
        )
        result = capability.verify_step(subgoal=subgoal, step=step, before=before, after=after)
        execution_state.evidence_ledger.append(
            {
                "subgoal_id": subgoal.id,
                "capability": step.capability,
                "status": result.status,
                "evidence": list(result.evidence),
                "message": result.message,
                "verified_at": result.verified_at,
            }
        )
        failure_history = execution_state.capability_failures.setdefault(_failure_key(subgoal.id, step.capability), [])
        failure_history.append(result.status)
        del failure_history[:-6]
        return result

    def build_pending_decision(self, *, step: StepProposal, subgoal: Subgoal) -> PendingDecision:
        return PendingDecision(
            id=f"{subgoal.id}-{int(step.timeout or 0)}-{len(step.actions)}",
            summary=step.intent,
            reason=(
                f"The next subgoal requires approval because it is classified as {step.risk_level} risk."
            ),
            risk_level=step.risk_level,
            actions=list(step.actions),
        )

    def _plan_with_fallback(
        self,
        *,
        subgoal: Subgoal,
        world_model: WorldModel,
        history: list[str],
        execution_state: ExecutionState,
    ) -> tuple[PlanResult, str]:
        last_error: PlannerError | None = None
        plan_callable = getattr(self.planner, "plan", None)
        if plan_callable is None:
            plan_callable = getattr(getattr(self.planner, "base_planner", None), "plan", None)
        if hasattr(self.planner, "plan_subgoal"):
            try:
                return self.planner.plan_subgoal(subgoal, world_model, history), "subgoal"
            except PlannerError as exc:
                last_error = exc

        if plan_callable is not None:
            try:
                return (
                    plan_callable(
                        task=subgoal.title,
                        screenshot_path=world_model.screenshot_path,
                        history=history,
                        environment=world_model.environment,
                    ),
                    "subgoal",
                )
            except PlannerError as exc:
                last_error = exc

        remaining_titles = [
            item.title
            for item in execution_state.task_graph.subgoals
            if item.status != "completed"
        ]
        if plan_callable is not None and len(remaining_titles) > 1:
            composite_task = " and then ".join(remaining_titles[:3])
            try:
                return (
                    plan_callable(
                        task=composite_task,
                        screenshot_path=world_model.screenshot_path,
                        history=history,
                        environment=world_model.environment,
                    ),
                    "composite",
                )
            except PlannerError as exc:
                last_error = exc

        overall_task = execution_state.task.strip()
        if plan_callable is not None and overall_task and overall_task != subgoal.title:
            try:
                return (
                    plan_callable(
                        task=overall_task,
                        screenshot_path=world_model.screenshot_path,
                        history=history,
                        environment=world_model.environment,
                    ),
                    "task",
                )
            except PlannerError as exc:
                last_error = exc

        if last_error is not None:
            raise last_error
        raise PlannerError("Unable to plan the current subgoal with any fallback scope.")


def build_capability_registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.register(BrowserDOMCapability())
    registry.register(WindowsUIACapability())
    registry.register(DesktopGUICapability())
    registry.register(FileSystemCapability())
    registry.register(ClipboardCapability())
    registry.register(OfficeCOMCapability())
    registry.register(GuardedShellRecipeCapability())
    return registry


def _failure_key(subgoal_id: str, capability_name: str) -> str:
    return f"{subgoal_id}:{capability_name}"


def _world_model_facts(world_model: WorldModel) -> list[ObservedFact]:
    facts: list[ObservedFact] = []
    if world_model.active_app:
        facts.append(ObservedFact(source="world_model", key="active_app", value=str(world_model.active_app)))
    if world_model.active_window_title:
        facts.append(ObservedFact(source="world_model", key="active_window", value=str(world_model.active_window_title)))
    if world_model.selection_text:
        facts.append(ObservedFact(source="world_model", key="selection_text", value=str(world_model.selection_text), confidence=0.9))
    if world_model.clipboard_text:
        facts.append(ObservedFact(source="world_model", key="clipboard_text", value=str(world_model.clipboard_text), confidence=0.9))
    return facts


def _completion_requirement(subgoal: Subgoal) -> EvidenceRequirement | None:
    payload = subgoal.completion_evidence
    if not isinstance(payload, dict) or not payload:
        return None
    return EvidenceRequirement.from_dict(payload)


def _completion_requirement_kind(subgoal: Subgoal) -> str | None:
    requirement = _completion_requirement(subgoal)
    if requirement is None:
        return None
    return requirement.kind


def _merge_evidence_requirements(
    primary: list[EvidenceRequirement],
    secondary: list[EvidenceRequirement],
) -> list[EvidenceRequirement]:
    merged = list(primary)
    seen = {(item.kind, item.value, item.selector, item.detail) for item in merged}
    for item in secondary:
        key = (item.kind, item.value, item.selector, item.detail)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _default_repair_strategy(*, subgoal: Subgoal, proposal: StepProposal) -> list[str]:
    if proposal.capability == "browser_dom":
        return ["refresh_dom_context", "re-anchor_target", "retry_with_fresh_observation"]
    if proposal.capability in {"windows_uia", "desktop_gui"}:
        return ["refocus_window", "re-anchor_target", "retry_with_fresh_observation"]
    if subgoal.goal_type == "save":
        return ["verify_target_path", "retry_with_fresh_observation"]
    return ["retry_with_fresh_observation", "switch_capability"]


def _estimate_cost_hint(actions: list[Action]) -> str:
    if len(actions) >= 4:
        return "high"
    if len(actions) >= 2:
        return "medium"
    return "low"


def _capability_supports_evidence(capability_name: str, evidence_kind: str) -> bool:
    mapping = {
        "browser_dom": {"browser_url_contains", "browser_title_contains", "browser_text_contains", "browser_available"},
        "filesystem": {"file_observation"},
        "clipboard": {"clipboard_or_input_changed"},
        "windows_uia": {"window_contains", "state_change"},
        "desktop_gui": {"window_contains", "state_change"},
        "office_com": {"fact_contains", "window_contains", "state_change"},
        "guarded_shell_recipe": {"file_observation", "state_change"},
    }
    supported = mapping.get(capability_name, set())
    return evidence_kind in supported


def _capability_prefers_structured(capability_name: str) -> bool:
    return capability_name in {"browser_dom", "windows_uia", "filesystem", "office_com", "guarded_shell_recipe"}


def _evaluate_completion_evidence(
    *,
    requirement: EvidenceRequirement,
    before: WorldModel,
    after: WorldModel,
) -> bool:
    if _evaluate_evidence(requirement, after):
        return True
    if requirement.kind in {"state_change", "clipboard_or_input_changed"}:
        return _infer_world_progress(before, after)
    if requirement.kind == "file_observation":
        return bool(after.file_observations or after.downloads)
    return False


def _detect_progress_signals(signals: list[str], *, before: WorldModel, after: WorldModel) -> bool:
    normalized_signals = [_normalize_text(item) for item in signals if _normalize_text(item)]
    haystacks = [
        _normalize_text(after.active_window_title),
        _normalize_text(after.active_app),
        _normalize_text(after.clipboard_text),
        _normalize_text((after.browser_snapshot or {}).get("url")),
        _normalize_text((after.browser_snapshot or {}).get("title")),
        _normalize_text((after.browser_snapshot or {}).get("text")),
        " ".join(_normalize_text(item) for item in after.anchor_candidates if _normalize_text(item)),
        " ".join(_normalize_text(item.value) for item in after.facts if _normalize_text(item.value)),
    ]
    if any(signal and any(signal in haystack for haystack in haystacks if haystack) for signal in normalized_signals):
        return True
    return _infer_world_progress(before, after)


def _infer_world_progress(before: WorldModel, after: WorldModel) -> bool:
    if _normalize_text(before.active_window_title) != _normalize_text(after.active_window_title):
        return True
    if _normalize_text(before.active_app) != _normalize_text(after.active_app):
        return True
    if _normalize_text(before.clipboard_text) != _normalize_text(after.clipboard_text):
        return True
    if _normalize_text(before.selection_text) != _normalize_text(after.selection_text):
        return True
    before_browser = before.browser_snapshot or {}
    after_browser = after.browser_snapshot or {}
    if _normalize_text(before_browser.get("url")) != _normalize_text(after_browser.get("url")):
        return True
    if _normalize_text(before_browser.get("text")) != _normalize_text(after_browser.get("text")):
        return True
    if tuple(_normalize_text(item) for item in before.anchor_candidates) != tuple(_normalize_text(item) for item in after.anchor_candidates):
        return True
    if len(after.facts) != len(before.facts):
        return True
    if len(after.file_observations) != len(before.file_observations):
        return True
    return False


def _evaluate_evidence(requirement: EvidenceRequirement, world_model: WorldModel) -> bool:
    kind = requirement.kind
    expected = _normalize_text(requirement.value)
    active_title = _normalize_text(world_model.active_window_title)
    active_app = _normalize_text(world_model.active_app)
    browser_snapshot = world_model.browser_snapshot or {}
    browser_url = _normalize_text(browser_snapshot.get("url"))
    browser_text = _normalize_text(browser_snapshot.get("text"))
    browser_title = _normalize_text(browser_snapshot.get("title"))

    if kind == "action_executed":
        return True
    if kind == "active_app_is":
        return bool(expected) and expected == active_app
    if kind == "window_contains":
        return bool(expected) and expected in active_title
    if kind == "browser_url_contains":
        return bool(expected) and expected in browser_url
    if kind == "browser_title_contains":
        return bool(expected) and expected in browser_title
    if kind == "browser_text_contains":
        return bool(expected) and expected in browser_text
    if kind == "browser_available":
        return bool(browser_url or browser_title or browser_text)
    if kind == "clipboard_or_input_changed":
        return bool(_normalize_text(world_model.clipboard_text) or browser_text)
    if kind == "file_observation":
        return bool(world_model.file_observations or world_model.downloads)
    if kind == "state_change":
        return False
    if kind == "fact_contains":
        for fact in world_model.facts:
            haystack = _normalize_text(f"{fact.key} {fact.value}")
            if expected and expected in haystack:
                return True
        return False
    return False


def _dedupe_facts(facts: list[ObservedFact]) -> list[ObservedFact]:
    deduped: list[ObservedFact] = []
    seen: set[tuple[str, str, str]] = set()
    for fact in facts:
        key = (fact.source, fact.key, fact.value)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(fact)
    return deduped
