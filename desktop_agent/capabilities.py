from __future__ import annotations

from dataclasses import dataclass, field
import re
import time
from typing import Any
from urllib.parse import urlparse

from desktop_agent.actions import Action, PlanResult
from desktop_agent.composer import DocumentArtifact, DocumentComposer
from desktop_agent.config import AgentConfig
from desktop_agent.drivers import DriverRegistry
from desktop_agent.planner import PlannerError
from desktop_agent.surfaces import TargetAnchor, choose_surface_kind
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
    "登陆",
    "验证码",
    "密码",
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
    "隐私",
    "终端",
    "命令",
    "命令行",
    "注册表",
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

_CRITICAL_RISK_TERMS = (
    "run as administrator",
    "administrator privilege",
    "administrator privileges",
    "admin privilege",
    "admin privileges",
    "elevated privilege",
    "elevated privileges",
    "uac",
    "sudo",
    "root privilege",
    "root privileges",
    "system32",
    "\u4ee5\u7ba1\u7406\u5458\u8eab\u4efd",
    "\u7ba1\u7406\u5458\u6743\u9650",
    "\u7cfb\u7edf\u6743\u9650",
    "\u63d0\u6743",
)

_RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _normalize_text(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _extract_domain(target: str) -> str:
    parsed = urlparse(target if "://" in target else f"https://{target}")
    return str(parsed.netloc or parsed.path).strip().lower()


def infer_step_risk_level(text: str, actions: list[Action]) -> str:
    haystacks = [_normalize_text(text)]
    for action in actions:
        haystacks.extend(_action_risk_fragments(action))
    joined = " ".join(item for item in haystacks if item)
    declared_action_risk = _max_risk_level(*(action.risk_level for action in actions))
    if any(term in joined for term in _CRITICAL_RISK_TERMS):
        return _max_risk_level(declared_action_risk, "critical")
    if any(term in joined for term in _HIGH_RISK_TERMS):
        return _max_risk_level(declared_action_risk, "high")
    if any(term in joined for term in _MEDIUM_RISK_TERMS):
        return _max_risk_level(declared_action_risk, "medium")
    if any(action.type == "shell_recipe_request" for action in actions):
        return _max_risk_level(declared_action_risk, "high")
    return declared_action_risk or "low"


def _action_risk_fragments(action: Action) -> list[str]:
    fragments = [
        action.type,
        action.app,
        action.text,
        action.selector,
        action.title,
        action.key,
        action.recipe,
        action.target_scope,
    ]
    if action.keys:
        fragments.append(" ".join(action.keys))
    return [_normalize_text(fragment) for fragment in fragments if fragment]


def _max_risk_level(*levels: str | None) -> str:
    highest = "low"
    for level in levels:
        normalized = _normalize_text(level)
        if normalized in _RISK_ORDER and _RISK_ORDER[normalized] > _RISK_ORDER[highest]:
            highest = normalized
    return highest


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
                    "selector": requirement.selector,
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
                    "selector": completion_requirement.selector,
                    "required": True,
                    "satisfied": completion_satisfied,
                    "scope": "subgoal_completion",
                }
            )

        if all_required_satisfied and completion_satisfied:
            if completion_requirement is None and not any(
                item.get("required", True) and item.get("satisfied") for item in evidence_results
            ):
                progress_detected = any_satisfied or _detect_progress_signals(
                    step.progress_signals,
                    before=before,
                    after=after,
                )
                if progress_detected:
                    return VerificationResult(
                        success=False,
                        status="partial_progress",
                        evidence=evidence_results,
                        failure_kind="verification_failed",
                        message=(
                            f"Observed progress for {subgoal.title}, but no required evidence "
                            "proved the subgoal is complete."
                        ),
                    )
                return VerificationResult(
                    success=False,
                    status="failed",
                    evidence=evidence_results,
                    failure_kind="verification_failed",
                    message=f"No required evidence was available to verify completion for {subgoal.title}.",
                )
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
                failure_kind="verification_failed",
                message=f"Observed partial progress for {subgoal.title}, but completion evidence is still missing.",
            )

        return VerificationResult(
            success=False,
            status="failed",
            evidence=evidence_results,
            failure_kind=_classify_verification_failure(evidence_results),
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
        desktop_app_target = any(
            token in text
            for token in (
                "calculator",
                "calc",
                "notepad",
                "explorer",
                "paint",
                "settings",
                "excel",
                "powerpoint",
                "word",
                "vscode",
            )
        )
        web_intent = any(token in text for token in ("browser", "website", "web", "search", "visit"))
        if desktop_app_target and not web_intent:
            return 0.0
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
        research_step = self._maybe_research_extraction(
            subgoal=subgoal,
            world_model=world_model,
            execution_state=execution_state,
            config=config,
        )
        if research_step is not None:
            return research_step
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

    def _maybe_research_extraction(
        self,
        *,
        subgoal: Subgoal,
        world_model: WorldModel,
        execution_state: ExecutionState,
        config: AgentConfig,
    ) -> StepProposal | None:
        """When a research/gather subgoal feeds a downstream synthesis or authoring
        step, search and then *read the results page content* into research notes,
        instead of stopping at the search results page. Plain search tasks (no
        downstream consumer) keep the simple one-step behaviour."""

        if not getattr(config, "research_extract_enabled", True):
            return None
        if not _research_feeds_downstream_synthesis(execution_state, subgoal):
            return None
        browser = world_model.browser_snapshot or {}
        context = execution_state.app_context
        extracted_key = f"research_extracted:{subgoal.id}"
        query = _research_query(subgoal.title)

        if not query:
            return None
        if not _browser_snapshot_matches_query(browser, query):
            # Search first, but defer completion so the page can be read afterwards.
            # A browser can already have an unrelated page open; do not treat that
            # stale content as research for this subgoal.
            subgoal.completion_evidence = None
            return StepProposal(
                intent=f"Search the web to research: {query}",
                actions=[Action.from_dict({"type": "browser_search", "text": query})],
                capability=self.name,
                expected_evidence=[
                    EvidenceRequirement(kind="browser_available", detail="Search results should be visible.")
                ],
                progress_signals=[query, subgoal.title],
                risk_level="low",
                current_focus=f"search {query}",
                completes_subgoal=False,
            )

        if not context.get(extracted_key):
            context[extracted_key] = True
            subgoal.completion_evidence = {
                "kind": "action_executed",
                "detail": f"Web research material gathered for: {subgoal.title}",
            }
            return StepProposal(
                intent="Read the search results to gather research material.",
                actions=[Action.from_dict({"type": "browser_dom_extract", "selector": "body"})],
                capability=self.name,
                expected_evidence=[
                    EvidenceRequirement(kind="browser_available", detail="A live page should remain available.")
                ],
                progress_signals=[subgoal.title],
                risk_level="low",
                current_focus="gather research content",
                completes_subgoal=True,
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


class DocumentAuthoringCapability(CapabilityAdapter):
    """Synthesize gathered research into a structured document and author it.

    This is the "think + write" capability: it opens the target editor, asks the
    composer (the model) to turn accumulated research notes plus the task goal
    into a long-form document, then writes that document into the editor with a
    single ``insert_text`` action.
    """

    name = "document_authoring"

    _AUTHOR_VERBS = (
        "write",
        "compose",
        "draft",
        "summarize",
        "summarise",
        "撰写",
        "起草",
        "整理到",
        "整理成",
        "整理为",
        "写入",
        "写到",
        "写进",
        "写出",
        "记录到",
        "记录在",
        "总结",
        "生成文档",
        "生成报告",
    )
    _EDITOR_APPS = ("word", "记事本", "notepad", "wps", "文档", "docx")

    def can_handle(self, subgoal: Subgoal, world_model: WorldModel) -> float:
        lowered = _normalize_text(f"{subgoal.title} {subgoal.goal or ''}")
        # Require an explicit author verb (write / compose / 整理 / 总结 ...). Merely
        # naming an editor ("open notepad", "type X") or a document noun is not enough,
        # otherwise plain typing or navigation steps get hijacked.
        if not lowered or not any(token in lowered for token in self._AUTHOR_VERBS):
            return 0.0
        active_editor = self._active_editor(world_model)
        return min(0.96, 0.9 + (0.05 if active_editor else 0.0))

    def propose_step(
        self,
        *,
        subgoal: Subgoal,
        world_model: WorldModel,
        execution_state: ExecutionState,
        config: AgentConfig,
        planner,
    ) -> StepProposal | None:
        # Only act when this is genuinely an authoring subgoal; otherwise defer so
        # the fallback planner keeps ownership of unrelated steps.
        if self.can_handle(subgoal, world_model) < 0.5:
            return None
        target_app = self._target_app(subgoal, config)
        if not _document_app_is_active(world_model, target_app):
            # Opening the editor must not complete the subgoal: clear the (loosely
            # inferred) completion evidence so this round only proves the editor is
            # focused, and the document still has to be written afterwards.
            subgoal.completion_evidence = None
            action = Action.from_dict({"type": "open_app_if_needed", "app": target_app})
            return StepProposal(
                intent=f"Open {target_app} before writing the document for: {subgoal.title}",
                actions=[action],
                capability=self.name,
                expected_evidence=[
                    EvidenceRequirement(
                        kind="active_app_is",
                        value=target_app,
                        detail=f"{target_app} should become active before the document is written.",
                    )
                ],
                progress_signals=[target_app, subgoal.title],
                risk_level="low",
                current_focus=f"open {target_app}",
                rationale="The target editor must be focused before the synthesized document can be written.",
            )

        artifact = self._ensure_artifact(subgoal=subgoal, execution_state=execution_state, config=config)
        body = artifact.to_plain_text()
        max_len = max(1, int(config.max_document_length))
        if len(body) > max_len:
            body = body[:max_len].rstrip()
        action = Action.from_dict({"type": "insert_text", "text": body})
        # Writing the composed document into the focused editor is the completion
        # signal. The agent cannot read the document back out of the editor, so
        # completion is proven by the write action executing into the active editor.
        subgoal.completion_evidence = {
            "kind": "action_executed",
            "detail": f"The composed document was written into {target_app} for: {subgoal.title}",
        }
        return StepProposal(
            intent=(
                f"Write the composed document ({artifact.source}, {len(artifact.sections)} sections) "
                f"into {target_app}."
            ),
            actions=[action],
            capability=self.name,
            expected_evidence=[
                EvidenceRequirement(
                    kind="active_app_is",
                    value=target_app,
                    detail=f"{target_app} stays active while the document is written.",
                ),
                EvidenceRequirement(
                    kind="state_change",
                    detail="The composed document text should appear in the editor.",
                    required=False,
                ),
            ],
            progress_signals=[artifact.title, target_app],
            risk_level="low",
            current_focus=f"write document into {target_app}",
            completes_subgoal=True,
            rationale=f"Authoring the synthesized document ({artifact.source}) completes the writing subgoal.",
        )

    def build_expected_evidence(
        self,
        *,
        subgoal: Subgoal,
        world_model: WorldModel,
        actions: list[Action],
    ) -> list[EvidenceRequirement]:
        evidence = super().build_expected_evidence(subgoal=subgoal, world_model=world_model, actions=actions)
        if any(action.type == "insert_text" for action in actions):
            evidence.append(
                EvidenceRequirement(
                    kind="state_change",
                    detail="The composed document text should appear in the editor.",
                    required=False,
                )
            )
        return evidence

    def _ensure_artifact(
        self,
        *,
        subgoal: Subgoal,
        execution_state: ExecutionState,
        config: AgentConfig,
    ) -> DocumentArtifact:
        workspace = execution_state.workspace
        for item in workspace.artifacts:
            if (
                isinstance(item, dict)
                and item.get("kind") == "composed_document"
                and item.get("subgoal_id") == subgoal.id
                and isinstance(item.get("document"), dict)
            ):
                return DocumentArtifact.from_dict(item["document"])

        goal = (execution_state.task or "").strip() or subgoal.title
        # Feed the composer real research material (web/selection notes), not the
        # workspace's internal orchestration breadcrumbs.
        research_notes = [
            note
            for note in workspace.notes
            if isinstance(note, str) and note.startswith(("[extract]", "[web]", "[selection]"))
        ]
        if not research_notes:
            research_notes = [
                note
                for note in workspace.notes
                if isinstance(note, str) and not note.startswith("[composed]") and "proposed:" not in note
            ]
        composer = DocumentComposer(config)
        artifact = composer.compose(
            goal=goal,
            notes=research_notes,
            history=list(execution_state.memory),
            doc_type=self._doc_type(subgoal),
        )
        workspace.artifacts.append(
            {
                "kind": "composed_document",
                "subgoal_id": subgoal.id,
                "title": artifact.title,
                "source": artifact.source,
                "document": artifact.to_dict(),
                "created_at": time.time(),
            }
        )
        del workspace.artifacts[:-16]
        if config.task_workspace_enabled:
            workspace.add_note(
                f"[composed] {artifact.title} ({artifact.source}, {len(artifact.sections)} sections)"
            )
        return artifact

    def _target_app(self, subgoal: Subgoal, config: AgentConfig) -> str:
        lowered = _normalize_text(f"{subgoal.title} {subgoal.goal or ''}")
        if any(token in lowered for token in ("notepad", "记事本")):
            return "notepad"
        if "wps" in lowered:
            return "wps"
        if any(token in lowered for token in ("word", "文档", "docx", "report", "报告", "document")):
            return "word"
        return (config.document_default_app or "word").strip() or "word"

    def _doc_type(self, subgoal: Subgoal) -> str | None:
        lowered = _normalize_text(f"{subgoal.title} {subgoal.goal or ''}")
        for token, label in (
            ("itinerary", "travel itinerary"),
            ("攻略", "travel itinerary"),
            ("旅游", "travel itinerary"),
            ("report", "report"),
            ("报告", "report"),
            ("plan", "plan"),
            ("计划", "plan"),
            ("方案", "plan"),
            ("summary", "summary"),
            ("总结", "summary"),
        ):
            if token in lowered:
                return label
        return None

    def _active_editor(self, world_model: WorldModel) -> bool:
        active_app = _normalize_text(world_model.active_app)
        if active_app in {"word", "notepad", "wps", "wordpad"}:
            return True
        active_title = _normalize_text(world_model.active_window_title)
        return any(token in active_title for token in self._EDITOR_APPS)


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
        intent_preferred = _intent_preferred_capabilities(execution_state)
        completion_kind = _completion_requirement_kind(subgoal)
        ranked: list[tuple[CapabilityAdapter, float]] = []
        for capability in candidates:
            score = capability.can_handle(subgoal, world_model)
            if capability.name in intent_preferred:
                score += max(0.0, 0.18 - (0.03 * intent_preferred.index(capability.name)))
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
                    score -= 0.7
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


def _capability_for_proposal(
    *,
    proposal: StepProposal,
    ranked_capabilities: list[tuple[CapabilityAdapter, float]],
    fallback: CapabilityAdapter | None = None,
) -> CapabilityAdapter:
    capability_name = _normalize_text(proposal.capability)
    if capability_name:
        match = next((candidate for candidate, _score in ranked_capabilities if candidate.name == capability_name), None)
        if match is not None:
            return match
    if fallback is not None:
        return fallback
    return ranked_capabilities[0][0] if ranked_capabilities else DesktopGUICapability()


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

    def choose_capability(
        self,
        *,
        subgoal: Subgoal,
        world_model: WorldModel,
        execution_state: ExecutionState | None = None,
    ) -> CapabilityAdapter:
        return self.registry.select(
            subgoal=subgoal,
            world_model=world_model,
            config=self.config,
            execution_state=execution_state,
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
        execution_state.app_context["capability_ranking"] = _summarize_capability_ranking(ranked_capabilities)
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

        return self._finalize_step_proposal(
            proposal=proposal,
            subgoal=subgoal,
            world_model=world_model,
            execution_state=execution_state,
            ranked_capabilities=ranked_capabilities,
            capability=capability,
        )

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
        if proposal is None and verification is not None and verification.failure_kind in {
            "capability_mismatch",
            "goal_ambiguous",
            "verification_failed",
            "stale_target",
            "missing_data",
        }:
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
        proposal_capability = _capability_for_proposal(
            proposal=proposal,
            ranked_capabilities=ranked_capabilities,
            fallback=primary,
        )
        return self._finalize_step_proposal(
            proposal=proposal,
            subgoal=subgoal,
            world_model=world_model,
            execution_state=execution_state,
            ranked_capabilities=ranked_capabilities,
            capability=proposal_capability,
        )

    def _finalize_step_proposal(
        self,
        *,
        proposal: StepProposal,
        subgoal: Subgoal,
        world_model: WorldModel,
        execution_state: ExecutionState,
        ranked_capabilities: list[tuple[CapabilityAdapter, float]],
        capability: CapabilityAdapter,
    ) -> StepProposal:
        inferred_risk = infer_step_risk_level(
            f"{subgoal.title} {subgoal.goal or ''} {proposal.intent}",
            proposal.actions,
        )
        proposal.risk_level = _max_risk_level(proposal.risk_level, inferred_risk)
        if not proposal.rationale:
            proposal.rationale = _build_capability_choice_rationale(
                selected=capability.name,
                ranked=ranked_capabilities,
                subgoal=subgoal,
                execution_state=execution_state,
            )
        if not proposal.fallbacks:
            proposal.fallbacks = [
                candidate.name
                for candidate, _score in ranked_capabilities
                if candidate.name != capability.name
            ][:3]
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
        proposal.surface_kind = choose_surface_kind(
            config=self.config,
            active_app=world_model.active_app,
            browser_snapshot=world_model.browser_snapshot,
            goal_type=subgoal.goal_type,
            subgoal_text=subgoal.title,
        )
        proposal.primary_anchor = proposal.primary_anchor or _build_primary_anchor(
            proposal=proposal,
            world_model=world_model,
        )
        if not proposal.fallback_anchors:
            proposal.fallback_anchors = _build_fallback_anchors(
                proposal=proposal,
                world_model=world_model,
            )
        proposal.current_focus = proposal.current_focus or subgoal.title
        execution_state.current_surface_kind = proposal.surface_kind
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
        requires_user_presence = _step_requires_user_presence(step)
        return PendingDecision(
            id=f"{subgoal.id}-{int(step.timeout or 0)}-{len(step.actions)}",
            summary=step.intent,
            reason=_step_approval_reason(step),
            risk_level=step.risk_level,
            decision_type="step_approval",
            actions=list(step.actions),
            approval_policy=self.config.approval_policy,
            requires_user_presence=requires_user_presence,
            operator_hint=_operator_presence_hint() if requires_user_presence else None,
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
    registry.register(DocumentAuthoringCapability())
    registry.register(GuardedShellRecipeCapability())
    return registry


def _research_feeds_downstream_synthesis(execution_state: ExecutionState, subgoal: Subgoal) -> bool:
    """True when a later, still-pending subgoal will consume the gathered research
    (a synthesis/authoring step), so it is worth reading page content, not just
    opening the results."""

    for item in execution_state.task_graph.subgoals:
        if item.id == subgoal.id or item.status == "completed":
            continue
        if _normalize_text(item.capability_preference) in {"document_authoring", "office_com"}:
            return True
        title = _normalize_text(f"{item.title} {item.goal or ''}")
        if item.goal_type in {"fill", "transform", "extract"} and any(
            marker in title for marker in ("撰写", "总结", "summary", "报告", "report", "compose", "write")
        ):
            return True
    return False


def _research_query(title: str) -> str:
    cleaned = _normalize_text(title)
    match = re.match(
        r"^(?:搜索|搜一下|查找|查询|调研|了解|research|search(?:\s+for)?|look\s+up|find(?:\s+out)?|gather|investigate)"
        r"\s*[:：]?\s*(?P<query>.+)$",
        cleaned,
        re.I,
    )
    query = match.group("query") if match else cleaned
    query = re.sub(r"(?:的)?(?:相关)?(?:资料|信息|内容)$", "", query).strip()
    return query or cleaned


def _document_app_is_active(world_model: WorldModel, app: str) -> bool:
    aliases = _app_aliases(_normalize_text(app))
    if not aliases:
        return False
    active_app = _normalize_text(world_model.active_app)
    if active_app in aliases:
        return True
    active_title = _normalize_text(world_model.active_window_title)
    if any(alias in active_title for alias in aliases):
        return True
    return False


def _browser_snapshot_matches_query(browser: dict[str, Any], query: str) -> bool:
    text = _normalize_text(
        " ".join(
            str(browser.get(key) or "")
            for key in ("url", "title", "text", "extracted_text")
        )
    )
    if not text:
        return False
    query_text = _normalize_text(query)
    if query_text and query_text in text:
        return True
    tokens = [
        token
        for token in re.findall(r"[0-9a-zA-Z]+|[\u4e00-\u9fff]+", query_text)
        if len(token) >= 2
    ]
    if not tokens:
        return False
    required = 1 if len(tokens) <= 2 else 2
    return sum(1 for token in tokens if token in text) >= required


def _failure_key(subgoal_id: str, capability_name: str) -> str:
    return f"{subgoal_id}:{capability_name}"


def _intent_preferred_capabilities(execution_state: ExecutionState | None) -> list[str]:
    if execution_state is None:
        return []
    intent = execution_state.task_graph.intent if isinstance(execution_state.task_graph.intent, dict) else {}
    values = intent.get("preferred_capabilities") if isinstance(intent, dict) else None
    if not isinstance(values, list):
        return []
    preferred: list[str] = []
    for item in values:
        name = str(item or "").strip()
        if name and name not in preferred:
            preferred.append(name)
    return preferred


def _summarize_capability_ranking(ranked: list[tuple[CapabilityAdapter, float]]) -> list[dict[str, Any]]:
    return [
        {"name": capability.name, "score": round(float(score), 3)}
        for capability, score in ranked[:5]
    ]


def _build_capability_choice_rationale(
    *,
    selected: str,
    ranked: list[tuple[CapabilityAdapter, float]],
    subgoal: Subgoal,
    execution_state: ExecutionState,
) -> str:
    intent_caps = _intent_preferred_capabilities(execution_state)
    score = next((score for capability, score in ranked if capability.name == selected), 0.0)
    reasons: list[str] = [f"Selected {selected} for {subgoal.goal_type} subgoal with score {score:.2f}."]
    if selected == subgoal.capability_preference:
        reasons.append("It matches the subgoal capability preference.")
    if selected in intent_caps:
        reasons.append("It matches the task intent preference.")
    recent_results = execution_state.capability_failures.get(_failure_key(subgoal.id, selected), [])
    if recent_results:
        reasons.append(f"Recent verification history: {', '.join(recent_results[-3:])}.")
    return " ".join(reasons)


def _world_model_facts(world_model: WorldModel) -> list[ObservedFact]:
    facts: list[ObservedFact] = []
    if world_model.active_app:
        facts.append(ObservedFact(source="world_model", key="active_app", value=str(world_model.active_app)))
    if world_model.active_window_title:
        facts.append(ObservedFact(source="world_model", key="active_window", value=str(world_model.active_window_title)))
    if world_model.surface_kind:
        facts.append(ObservedFact(source="world_model", key="surface_kind", value=str(world_model.surface_kind)))
    for source in world_model.fact_sources[:6]:
        if source:
            facts.append(ObservedFact(source="world_model", key="fact_source", value=str(source), confidence=0.7))
    if world_model.state_delta:
        facts.append(
            ObservedFact(
                source="world_model",
                key="state_delta",
                value=", ".join(str(key) for key in world_model.state_delta.keys())[:240],
                confidence=0.75,
            )
        )
    if isinstance(world_model.browser_observation, dict):
        runtime = str(world_model.browser_observation.get("runtime") or "").strip()
        if runtime:
            facts.append(ObservedFact(source="world_model", key="browser_runtime", value=runtime))
    if world_model.selection_text:
        facts.append(ObservedFact(source="world_model", key="selection_text", value=str(world_model.selection_text), confidence=0.9))
    if world_model.clipboard_text:
        facts.append(ObservedFact(source="world_model", key="clipboard_text", value=str(world_model.clipboard_text), confidence=0.9))
    return facts


def _build_primary_anchor(*, proposal: StepProposal, world_model: WorldModel) -> TargetAnchor | None:
    for action in proposal.actions:
        if action.selector:
            return TargetAnchor(kind="selector", value=action.selector, detail=action.type)
        if action.title:
            return TargetAnchor(kind="window", value=action.title, detail=action.type)
        if action.text and action.type not in {"type", "press"}:
            return TargetAnchor(kind="text", value=action.text[:240], detail=action.type, confidence=0.8)
    if world_model.active_window_title:
        return TargetAnchor(
            kind="window",
            value=str(world_model.active_window_title),
            detail="active_window",
            confidence=0.6,
        )
    browser_snapshot = world_model.browser_snapshot or {}
    if browser_snapshot.get("url"):
        return TargetAnchor(
            kind="url",
            value=str(browser_snapshot["url"]),
            detail="browser_url",
            confidence=0.7,
        )
    return None


def _build_fallback_anchors(*, proposal: StepProposal, world_model: WorldModel) -> list[TargetAnchor]:
    anchors: list[TargetAnchor] = []
    if world_model.active_window_title:
        anchors.append(
            TargetAnchor(
                kind="window",
                value=str(world_model.active_window_title),
                detail="active_window",
                confidence=0.5,
            )
        )
    browser_snapshot = world_model.browser_snapshot or {}
    for key in ("title", "url"):
        value = str(browser_snapshot.get(key) or "").strip()
        if value:
            anchors.append(
                TargetAnchor(
                    kind=key,
                    value=value[:240],
                    detail=f"browser_{key}",
                    confidence=0.5,
                )
            )
    for candidate in world_model.anchor_candidates[:4]:
        anchors.append(
            TargetAnchor(
                kind="text",
                value=str(candidate)[:240],
                detail="anchor_candidate",
                confidence=0.45,
            )
        )
    deduped: list[TargetAnchor] = []
    seen: set[tuple[str, str]] = set()
    for item in anchors:
        key = (item.kind, item.value)
        if not item.value or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:6]


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


def _classify_verification_failure(evidence_results: list[dict[str, Any]]) -> str:
    unsatisfied = [
        item
        for item in evidence_results
        if isinstance(item, dict) and item.get("required", True) and not item.get("satisfied")
    ]
    if any(str(item.get("kind") or "") == "browser_available" for item in unsatisfied):
        return "stale_target"
    if any(str(item.get("kind") or "") in {"browser_text_contains", "fact_contains", "file_observation"} for item in unsatisfied):
        return "missing_data"
    if any(str(item.get("scope") or "") == "subgoal_completion" for item in unsatisfied):
        return "verification_failed"
    if any(str(item.get("selector") or "").strip() for item in unsatisfied):
        return "stale_target"
    return "capability_mismatch"


def _default_repair_strategy(*, subgoal: Subgoal, proposal: StepProposal) -> list[str]:
    if proposal.capability == "browser_dom":
        return ["refresh_dom_context", "re-anchor_target", "retry_with_fresh_observation"]
    if proposal.capability in {"windows_uia", "desktop_gui"}:
        return ["refocus_window", "re-anchor_target", "retry_with_fresh_observation"]
    if subgoal.goal_type == "save":
        return ["verify_target_path", "retry_with_fresh_observation"]
    return ["retry_with_fresh_observation", "switch_capability"]


def _step_requires_user_presence(step: StepProposal) -> bool:
    if _normalize_text(step.risk_level) == "critical":
        return True
    haystack = " ".join(
        [item for item in [_normalize_text(step.intent)] if item]
        + [item for action in step.actions for item in _action_risk_fragments(action)]
    )
    return any(term in haystack for term in _CRITICAL_RISK_TERMS)


def _step_approval_reason(step: StepProposal) -> str:
    if _step_requires_user_presence(step):
        return (
            f"The next subgoal is classified as {step.risk_level} risk and may require an operator "
            "at the screen for an administrator, UAC, or privileged-system prompt."
        )
    return f"The next subgoal requires approval because it is classified as {step.risk_level} risk."


def _operator_presence_hint() -> str:
    return (
        "Keep a person at the screen before approving; the action may open an administrator, "
        "UAC, or other privileged-system confirmation that automation cannot safely complete alone."
    )


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
        "document_authoring": {"state_change", "window_contains", "clipboard_or_input_changed", "fact_contains"},
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
    expected_app = _normalize_open_app_request(expected)
    active_title = _normalize_text(world_model.active_window_title)
    active_app = _normalize_text(world_model.active_app)
    browser_snapshot = world_model.browser_snapshot or {}
    browser_url = _normalize_text(browser_snapshot.get("url"))
    browser_text = _normalize_text(browser_snapshot.get("text"))
    browser_title = _normalize_text(browser_snapshot.get("title"))

    if kind == "action_executed":
        return True
    if kind == "active_app_is":
        aliases = _app_aliases(expected_app or expected)
        if not aliases:
            return False
        if active_app in aliases:
            return True
        if any(alias in active_title for alias in aliases):
            return True
        for item in world_model.visible_windows:
            title = _normalize_text(item.get("title"))
            process_name = _normalize_text(item.get("process_name"))
            if any(alias in title or alias in process_name for alias in aliases):
                return True
        return False
    if kind == "window_contains":
        if bool(expected) and expected in active_title:
            return True
        aliases = _app_aliases(expected_app)
        if not aliases:
            return False
        if active_app in aliases or any(alias in active_title for alias in aliases):
            return True
        for item in world_model.visible_windows:
            title = _normalize_text(item.get("title"))
            process_name = _normalize_text(item.get("process_name"))
            if any(alias in title or alias in process_name for alias in aliases):
                return True
        return False
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


def _app_aliases(expected: str) -> set[str]:
    mapping = {
        "calculator": {"calculator", "calc", "计算器", "calc.exe"},
        "notepad": {"notepad", "记事本", "notepad.exe"},
        "explorer": {"explorer", "file explorer", "资源管理器", "explorer.exe"},
        "browser": {"browser", "edge", "chrome", "firefox", "浏览器", "msedge.exe", "chrome.exe", "firefox.exe"},
        "微信": {"微信", "wechat", "weixin", "wechat.exe", "weixin.exe"},
        "pycharm": {"pycharm", "pycharm64.exe", "jetbrains pycharm"},
        "todesk": {"todesk", "todesk.exe"},
        "excel": {"excel", "excel.exe"},
        "word": {"word", "winword", "winword.exe"},
        "powerpoint": {"powerpoint", "ppt", "powerpnt", "powerpnt.exe"},
        "vscode": {"vscode", "visual studio code", "cursor", "code.exe", "cursor.exe"},
        "paint": {"paint", "mspaint", "mspaint.exe", "画图"},
        "settings": {"settings", "systemsettings", "systemsettings.exe", "设置"},
        "wechat": {"wechat", "weixin", "wechat.exe", "weixin.exe", "微信"},
        "dingtalk": {"dingtalk", "dingtalk.exe", "钉钉"},
        "wps": {"wps", "wps office", "wps.exe"},
    }
    if expected in mapping:
        return set(mapping[expected])
    return {expected} if expected else set()


def _normalize_open_app_request(expected: str) -> str:
    cleaned = _normalize_text(expected)
    for prefix in ("打开", "open "):
        if cleaned.startswith(prefix):
            return cleaned[len(prefix):].strip()
    return cleaned


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
