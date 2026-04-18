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

    def can_handle(self, subgoal: Subgoal, world_model: WorldModel) -> float:
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
        return None

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
        if not evidence and actions:
            evidence.append(EvidenceRequirement(kind="action_executed", detail="The guarded action should execute without errors."))
        return evidence

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
            if requirement.required and not satisfied:
                all_required_satisfied = False

        if all_required_satisfied:
            return VerificationResult(success=True, evidence=evidence_results, message="Evidence requirements were satisfied.")

        return VerificationResult(
            success=False,
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
        return facts

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
            expected_evidence=[EvidenceRequirement(kind="action_executed", detail="The clipboard shortcut should execute.")],
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
            expected_evidence=[EvidenceRequirement(kind="action_executed", detail="The shell recipe should complete successfully.")],
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

    def select(
        self,
        *,
        subgoal: Subgoal,
        world_model: WorldModel,
        config: AgentConfig,
        driver_registry: DriverRegistry | None = None,
    ) -> CapabilityAdapter:
        candidates = self.enabled(config)
        driver = driver_registry.detect(world_model) if driver_registry is not None else None
        preferred = set(driver.preferred_capabilities()) if driver is not None else set()
        best_score = -1.0
        best = candidates[-1] if candidates else DesktopGUICapability()
        for capability in candidates:
            if capability.name in subgoal.failed_capabilities:
                continue
            score = capability.can_handle(subgoal, world_model)
            if capability.name == subgoal.capability_preference:
                score += 0.2
            if capability.name in preferred:
                score += 0.15
            if score > best_score:
                best_score = score
                best = capability
        return best


@dataclass(slots=True)
class CapabilityExecutor:
    config: AgentConfig
    planner: Any
    registry: CapabilityRegistry
    driver_registry: DriverRegistry | None = None

    def observe(self, world_model: WorldModel) -> list[ObservedFact]:
        facts: list[ObservedFact] = []
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
            driver_registry=self.driver_registry,
        )

    def propose_step(self, *, execution_state: ExecutionState, world_model: WorldModel) -> StepProposal:
        subgoal = execution_state.current_subgoal()
        if subgoal is None:
            return StepProposal(intent="Task already complete.", actions=[], capability="desktop_gui")

        capability = self.choose_capability(subgoal=subgoal, world_model=world_model)
        proposal = capability.propose_step(
            subgoal=subgoal,
            world_model=world_model,
            execution_state=execution_state,
            config=self.config,
            planner=self.planner,
        )
        if proposal is None:
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
        proposal.requires_approval = proposal.requires_approval or approval_required_for_policy(
            self.config.approval_policy,
            proposal.risk_level,
            proposal.actions,
        )
        proposal.current_focus = proposal.current_focus or subgoal.title
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
            return VerificationResult(success=True, evidence=[], message="No current subgoal remained.")
        capability = next(
            (item for item in self.registry.enabled(self.config) if item.name == step.capability),
            DesktopGUICapability(),
        )
        result = capability.verify_step(subgoal=subgoal, step=step, before=before, after=after)
        if result.success:
            return result
        if not step.expected_evidence and step.actions:
            return VerificationResult(
                success=True,
                evidence=result.evidence,
                message="The step executed without a stronger verification signal.",
            )
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
