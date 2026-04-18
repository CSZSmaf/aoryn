from __future__ import annotations

import base64
import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from desktop_agent.actions import ActionValidationError, PlanResult
from desktop_agent.config import AgentConfig
from desktop_agent.prompts import SYSTEM_PROMPT
from desktop_agent.web_agent import WebAgent, WebCommand
from desktop_agent.workflow import Subgoal, TaskGraph, WorldModel
from desktop_agent.windows_env import DesktopEnvironment


class PlannerError(RuntimeError):
    """Raised when planner cannot generate a valid plan."""


class StructuredOutputUnsupportedError(RuntimeError):
    """Raised when the upstream model rejects structured output settings."""


class BasePlanner(ABC):
    @abstractmethod
    def plan(
        self,
        task: str,
        screenshot_path: Path | None,
        history: list[str],
        environment: DesktopEnvironment | None = None,
    ) -> PlanResult:
        raise NotImplementedError


class RulePlanner(BasePlanner):
    """Deterministic planner for common demo tasks."""

    _NOTEPAD_PATTERN = re.compile(
        r"^(?:\u6253\u5f00|open)\s*(?:\u4e00\u4e2a\s*|an?\s*)?(?:\u8bb0\u4e8b\u672c|notepad)\s*"
        r"(?:(?:\u5e76|\u7136\u540e)|and)?\s*(?:\u8f93\u5165|type)\s*(?P<text>.+)$",
        re.I,
    )
    _CALCULATOR_PATTERN = re.compile(
        r"^(?:\u6253\u5f00|open)\s*(?:\u4e00\u4e2a\s*|an?\s*)?(?:\u8ba1\u7b97\u5668|calculator|calc)\s*$",
        re.I,
    )
    _CALCULATOR_EXPRESSION_PATTERNS = (
        re.compile(
            r"^(?:\u6253\u5f00|open)\s*(?:\u4e00\u4e2a\s*|an?\s*)?(?:\u8ba1\u7b97\u5668|calculator|calc)\s*"
            r"(?:(?:\u5e76|\u7136\u540e)|and)?\s*(?:\u8ba1\u7b97|calculate|compute|evaluate)\s*(?P<expr>.+)$",
            re.I,
        ),
        re.compile(
            r"^(?:\u7528|\u4f7f\u7528|with|use)\s*(?:\u8ba1\u7b97\u5668|calculator|calc)\s*"
            r"(?:\u8ba1\u7b97|calculate|compute|evaluate)\s*(?P<expr>.+)$",
            re.I,
        ),
        re.compile(
            r"^(?:calculate|compute|evaluate)\s*(?P<expr>.+?)\s*(?:with|using)\s*(?:calculator|calc)\s*$",
            re.I,
        ),
    )
    _EXPLORER_PATTERN = re.compile(
        r"^(?:\u6253\u5f00|open)\s*(?:\u4e00\u4e2a\s*|an?\s*)?"
        r"(?:\u8d44\u6e90\u7ba1\u7406\u5668|\u6587\u4ef6\u8d44\u6e90\u7ba1\u7406\u5668|explorer)\s*$",
        re.I,
    )
    _WAIT_PATTERN = re.compile(
        r"^(?:\u7b49\u5f85|wait)\s*(?P<seconds>[0-9]+(?:\.[0-9]+)?)\s*(?:\u79d2|seconds?|s)?\s*$",
        re.I,
    )
    _TYPE_PATTERN = re.compile(r"^(?:\u8f93\u5165|\u952e\u5165|type)\s*(?P<text>.+)$", re.I)

    def __init__(self) -> None:
        self.web_agent = WebAgent()

    def plan(
        self,
        task: str,
        screenshot_path: Path | None,
        history: list[str],
        environment: DesktopEnvironment | None = None,
    ) -> PlanResult:
        stripped = task.strip()

        if match := self._NOTEPAD_PATTERN.match(stripped):
            return _build_result(
                "Rule task: open Notepad and type text.",
                [
                    {"type": "open_app_if_needed", "app": "notepad"},
                    {"type": "wait", "seconds": 1.0},
                    {"type": "type", "text": _clean_tail_text(match.group("text"))},
                ],
            )

        if self._CALCULATOR_PATTERN.match(stripped):
            return _build_result(
                "Rule task: open Calculator.",
                [
                    {"type": "open_app_if_needed", "app": "calculator"},
                    {"type": "wait", "seconds": 0.8},
                ],
            )

        if calculator_plan := self._build_calculator_expression_result(stripped):
            return calculator_plan

        if self._EXPLORER_PATTERN.match(stripped):
            return _build_result(
                "Rule task: open Explorer.",
                [
                    {"type": "open_app_if_needed", "app": "explorer"},
                    {"type": "wait", "seconds": 0.8},
                ],
            )

        if web_plan := self.web_agent.try_plan(stripped):
            return web_plan

        if match := self._WAIT_PATTERN.match(stripped):
            return _build_result(
                "Rule task: wait.",
                [{"type": "wait", "seconds": float(match.group("seconds"))}],
            )

        if match := self._TYPE_PATTERN.match(stripped):
            return _build_result(
                "Rule task: type into the current focused window.",
                [{"type": "type", "text": _clean_tail_text(match.group("text"))}],
            )

        raise PlannerError("RulePlanner does not support this task.")

    def _build_calculator_expression_result(self, task: str) -> PlanResult | None:
        for pattern in self._CALCULATOR_EXPRESSION_PATTERNS:
            match = pattern.match(task)
            if not match:
                continue
            expression = _normalize_calculator_expression(match.group("expr"))
            if not expression:
                raise PlannerError("Calculator task did not contain a safe arithmetic expression.")
            return _build_result(
                f"Rule task: calculate {expression} in Calculator.",
                [
                    {"type": "open_app_if_needed", "app": "calculator"},
                    {"type": "wait", "seconds": 0.8},
                    {"type": "type", "text": expression},
                    {"type": "press", "key": "enter"},
                ],
            )
        return None


class VLMPlanner(BasePlanner):
    """Planner backed by an OpenAI-compatible VLM endpoint such as LM Studio."""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.web_agent = WebAgent(request_timeout=min(float(config.model_request_timeout), 3.0))

    def plan(
        self,
        task: str,
        screenshot_path: Path | None,
        history: list[str],
        environment: DesktopEnvironment | None = None,
    ) -> PlanResult:
        browser_command = self.web_agent.parse(task)
        if _should_use_browser_shortcut(task, history, browser_command):
            if web_plan := self.web_agent.try_plan(task):
                return web_plan

        requests = _import_requests()
        if screenshot_path is None or not screenshot_path.exists():
            raise PlannerError("VLMPlanner requires a screenshot.")

        api_base = _normalize_api_base_url(self.config.model_base_url)
        model_name = self._resolve_model_name(requests, api_base)
        image_b64 = base64.b64encode(screenshot_path.read_bytes()).decode("utf-8")
        browser_command = self.web_agent.parse(task)
        history_text = _format_history_for_prompt(history)
        browser_context = self.web_agent.build_task_context(task)
        decomposition_text = _build_task_decomposition(task, history, browser_command)
        environment_context = _build_environment_context(environment)

        response_format_mode = _normalize_structured_output_mode(self.config.model_structured_output)
        payload = _build_vlm_payload(
            model_name=model_name,
            task=task,
            history_text=history_text,
            decomposition_text=decomposition_text,
            image_b64=image_b64,
            browser_context=browser_context,
            environment_context=environment_context,
            response_format_mode=response_format_mode,
        )

        try:
            content = self._request_plan_text(
                requests=requests,
                api_base=api_base,
                payload=payload,
                response_format_mode=response_format_mode,
            )
        except StructuredOutputUnsupportedError:
            fallback_payload = _build_vlm_payload(
                model_name=model_name,
                task=task,
                history_text=history_text,
                decomposition_text=decomposition_text,
                image_b64=image_b64,
                browser_context=browser_context,
                environment_context=environment_context,
                response_format_mode="off",
            )
            content = self._request_plan_text(
                requests=requests,
                api_base=api_base,
                payload=fallback_payload,
                response_format_mode="off",
            )

        try:
            plan_payload = _extract_json(content)
            return PlanResult.from_payload(plan_payload, raw_response=content)
        except (ActionValidationError, json.JSONDecodeError) as exc:
            raise PlannerError(
                "The VLM response could not be parsed into a valid action plan. "
                "Please confirm you loaded a vision-capable chat model in LM Studio."
            ) from exc

    def _resolve_model_name(self, requests_module, api_base: str) -> str:
        configured_model = (self.config.model_name or "").strip()
        if not _needs_model_discovery(configured_model) and not self.config.model_auto_discover:
            return configured_model

        available_models = self._fetch_models(requests_module, api_base)
        return _pick_model_name(configured_model, available_models)

    def _fetch_models(self, requests_module, api_base: str) -> list[dict]:
        models_url = f"{api_base}/models"
        headers = _build_request_headers(self.config.model_api_key)
        try:
            response = requests_module.get(
                models_url,
                headers=headers,
                timeout=self.config.model_request_timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests_module.RequestException as exc:
            raise PlannerError(_build_connection_hint(api_base, exc)) from exc
        except ValueError as exc:
            raise PlannerError("LM Studio returned an invalid /models response.") from exc

        data = payload.get("data")
        if not isinstance(data, list) or not data:
            raise PlannerError(
                "LM Studio responded successfully, but no models were available at /v1/models. "
                "Load a model and start the local server first."
            )
        return data

    def _request_plan_text(
        self,
        *,
        requests,
        api_base: str,
        payload: dict,
        response_format_mode: str,
    ) -> str:
        url = f"{api_base}/chat/completions"
        headers = _build_request_headers(self.config.model_api_key)
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.config.model_request_timeout,
            )
        except requests.RequestException as exc:
            raise PlannerError(_build_connection_hint(api_base, exc)) from exc

        if response.status_code >= 400:
            body_text = response.text.strip()
            if response_format_mode != "off" and _looks_like_structured_output_rejection(body_text):
                raise StructuredOutputUnsupportedError(body_text)
            raise PlannerError(
                f"LM Studio request failed with HTTP {response.status_code}. "
                f"Response: {body_text or '<empty>'}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise PlannerError("LM Studio returned invalid JSON for chat/completions.") from exc

        return _extract_message_content(data)


class AutoPlanner(BasePlanner):
    """Try rule planner first, then fall back to the VLM planner."""

    def __init__(self, config: AgentConfig):
        self.rule = RulePlanner()
        self.vlm = VLMPlanner(config)

    def plan(
        self,
        task: str,
        screenshot_path: Path | None,
        history: list[str],
        environment: DesktopEnvironment | None = None,
    ) -> PlanResult:
        browser_command = self.rule.web_agent.parse(task)
        planner_order = (
            (self.vlm, self.rule)
            if _task_requires_vlm_reasoning(task, history, browser_command)
            else (self.rule, self.vlm)
        )
        last_error: Exception | None = None
        for planner in planner_order:
            try:
                return planner.plan(task, screenshot_path, history, environment)
            except PlannerError as exc:
                last_error = exc
                continue
        raise PlannerError(str(last_error) if last_error is not None else "Unable to plan the task.")


class TaskGraphPlanner:
    """Split a broad task into generic, verifiable subgoals."""

    def __init__(self, config: AgentConfig | None = None) -> None:
        self.config = config or AgentConfig()
        self.web_agent = WebAgent()

    def plan(self, task: str, *, history: list[str] | None = None, world_model: WorldModel | None = None) -> TaskGraph:
        browser_command = self.web_agent.parse(task)
        raw_subgoals = _extract_task_sub_goals(task, browser_command)
        if not raw_subgoals:
            raw_subgoals = [task.strip()]

        subgoals: list[Subgoal] = []
        for index, item in enumerate(raw_subgoals, start=1):
            title = item.strip()
            if not title:
                continue
            subgoals.append(
                Subgoal(
                    id=f"subgoal_{index:02d}",
                    title=title,
                    success_condition=_build_subgoal_success_condition(title, world_model=world_model),
                    capability_preference=_infer_capability_preference(title, world_model=world_model),
                    risk_level=_infer_subgoal_risk(title),
                    retry_budget=max(1, int(self.config.max_subgoal_retries or 1)),
                )
            )

        if not subgoals:
            subgoals.append(
                Subgoal(
                    id="subgoal_01",
                    title=task.strip() or "Complete the task.",
                    success_condition="Confirm that the requested task is completed.",
                    retry_budget=max(1, int(self.config.max_subgoal_retries or 1)),
                )
            )

        success_criteria = [item.success_condition for item in subgoals]
        constraints = [
            "Use guarded actions only.",
            "Switch capability when verification repeatedly fails.",
        ]
        risk_points = [item.title for item in subgoals if item.risk_level in {"high", "critical"}]
        return TaskGraph(
            task=task.strip(),
            subgoals=subgoals,
            success_criteria=success_criteria,
            constraints=constraints,
            risk_points=risk_points,
        )


class SubgoalPlanner:
    """Plan low-level guarded actions for a single current subgoal."""

    def __init__(self, config: AgentConfig, *, base_planner: BasePlanner | None = None):
        self.config = config
        self.base_planner = base_planner or build_planner(config)

    def plan_subgoal(self, subgoal: Subgoal, world_model: WorldModel, history: list[str]) -> PlanResult:
        return self.base_planner.plan(
            task=subgoal.title,
            screenshot_path=world_model.screenshot_path,
            history=history,
            environment=world_model.environment,
        )


def build_planner(config: AgentConfig) -> BasePlanner:
    mode = config.planner_mode.lower().strip()
    if mode == "rule":
        return RulePlanner()
    if mode == "vlm":
        return VLMPlanner(config)
    return AutoPlanner(config)


def _build_result(
    summary: str,
    actions: list[dict],
    done: bool = True,
    *,
    current_focus: str | None = None,
    reasoning: str | None = None,
    remaining_steps: list[str] | None = None,
) -> PlanResult:
    return PlanResult.from_payload(
        {
            "status_summary": summary,
            "done": done,
            "actions": actions,
            "current_focus": current_focus,
            "reasoning": reasoning,
            "remaining_steps": remaining_steps or [],
        }
    )


def _clean_tail_text(text: str) -> str:
    return text.strip().strip("\"' ")


def _normalize_calculator_expression(text: str) -> str | None:
    normalized = _clean_tail_text(text)
    replacements = (
        ("（", "("),
        ("）", ")"),
        ("×", "*"),
        ("x", "*"),
        ("X", "*"),
        ("÷", "/"),
        ("\u4e58\u4ee5", "*"),
        ("\u4e58", "*"),
        ("\u52a0", "+"),
        ("\u51cf\u53bb", "-"),
        ("\u51cf", "-"),
        ("\u9664\u4ee5", "/"),
        ("\u9664", "/"),
        ("\u7b49\u4e8e\u591a\u5c11", ""),
        ("\u7b49\u4e8e", ""),
        ("\u591a\u5c11", ""),
        ("=", ""),
        ("?", ""),
        ("\uff1f", ""),
        ("\u3002", ""),
    )
    for source, target in replacements:
        normalized = normalized.replace(source, target)
    normalized = re.sub(r"\s+", "", normalized)
    if not normalized:
        return None
    if not re.fullmatch(r"[0-9+\-*/().]+", normalized):
        return None
    if not re.search(r"[+\-*/]", normalized):
        return None
    return normalized


def _format_history_for_prompt(history: list[str]) -> str:
    if not history:
        return "Round 0:\n  No prior execution history."

    recent_history = history[-4:]
    start_index = len(history) - len(recent_history) + 1
    blocks: list[str] = []
    for round_index, entry in enumerate(recent_history, start=start_index):
        lines = [line.strip() for line in str(entry).splitlines() if line.strip()]
        if not lines:
            blocks.append(f"Round {round_index}:\n  <empty>")
            continue
        indented = "\n  ".join(lines)
        blocks.append(f"Round {round_index}:\n  {indented}")
    return "\n".join(blocks)


def _build_task_decomposition(
    task: str,
    history: list[str],
    browser_command: WebCommand | None,
) -> str:
    sub_goals = _extract_task_sub_goals(task, browser_command)
    if not sub_goals:
        return "No explicit sub-goal split was detected. Focus on the next visible prerequisite."

    lines = [
        f"Overall goal: {task.strip()}",
        "Candidate sub-goals:",
    ]
    for index, sub_goal in enumerate(sub_goals, start=1):
        lines.append(f"{index}. {sub_goal}")
    if history:
        lines.append(
            "Planning policy: use the execution memory and screenshot to continue from the first unmet sub-goal instead of restarting."
        )
    else:
        lines.append("Planning policy: start from the first prerequisite sub-goal and keep later work in remaining_steps.")
    return "\n".join(lines)


def _extract_task_sub_goals(task: str, browser_command: WebCommand | None) -> list[str]:
    if browser_command is not None:
        initial_step = _describe_browser_initial_step(browser_command)
        browser_steps = [initial_step] if initial_step else []
        browser_steps.extend(step for step in browser_command.follow_up_steps if step)
        return browser_steps[:6]

    normalized = task.strip()
    if not normalized:
        return []

    separator = " ||| "
    split_patterns = (
        re.compile(r"\s*(?:,|;|->|=>)\s+(?=(?:open|launch|visit|go to|search|click|type|press|scroll|wait|select|choose|filter|sort|fill|submit|download|upload|find|check|compare)\b)", re.I),
        re.compile(r"\s+(?:and then|then|after that|next|finally)\s+", re.I),
        re.compile(r"\s+and\s+(?=(?:open|launch|visit|go|search|click|type|press|scroll|wait|select|choose|filter|sort|fill|submit|download|upload|find|check|compare)\b)", re.I),
        re.compile(r"\s*(?:然后|接着|之后|再|最后)\s*"),
        re.compile(r"\s*(?:并且|并)\s*(?=(?:打开|启动|访问|搜索|点击|输入|按|滚动|等待|选择|筛选|排序|填写|提交|下载|上传|查找|检查|比较))"),
    )
    for pattern in split_patterns:
        normalized = pattern.sub(separator, normalized)

    parts = [_clean_sub_goal_part(part) for part in normalized.split(separator)]
    unique_parts: list[str] = []
    for part in parts:
        if part and part not in unique_parts:
            unique_parts.append(part)
    return unique_parts[:6]


def _task_requires_vlm_reasoning(
    task: str,
    history: list[str],
    browser_command: WebCommand | None,
) -> bool:
    if history:
        return True
    if browser_command is not None and browser_command.follow_up_steps:
        return True
    lowered = task.strip().lower()
    if not lowered:
        return False
    app_markers = 0
    for marker in ("browser", "edge", "chrome", "firefox", "notepad", "calculator", "calc", "explorer", "file explorer"):
        if marker in lowered:
            app_markers += 1
    if app_markers >= 2:
        return True
    sub_goals = _extract_task_sub_goals(task, browser_command)
    if len(sub_goals) >= 3:
        return True
    if len(sub_goals) >= 2 and any(
        keyword in lowered
        for keyword in (
            "switch",
            "focus",
            "window",
            "minimize",
            "close",
            "copy",
            "paste",
            "record",
            "整理",
            "切换",
            "窗口",
            "最小化",
            "关闭",
        )
    ):
        return True
    return False


def _should_use_browser_shortcut(
    task: str,
    history: list[str],
    browser_command: WebCommand | None,
) -> bool:
    if history or browser_command is None:
        return False
    if browser_command.follow_up_steps:
        return False
    return not _task_requires_vlm_reasoning(task, history, browser_command)


def _describe_browser_initial_step(command: WebCommand) -> str | None:
    if command.intent == "launch":
        return "open the browser"
    if command.intent == "open_url" and command.target:
        return f"open {command.target}"
    if command.intent == "search" and command.target:
        return f"search for {command.target}"
    if command.intent == "shopping_search" and command.shopping_query:
        return f"open shopping results for {command.shopping_query}"
    return command.follow_up or command.target


def _clean_sub_goal_part(text: str) -> str:
    cleaned = text.strip().strip("\"' ")
    cleaned = cleaned.strip(",;:，；。")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _build_subgoal_success_condition(title: str, *, world_model: WorldModel | None = None) -> str:
    normalized = title.strip()
    lowered = normalized.lower()
    if any(token in lowered for token in ("open ", "launch ", "visit ", "打开", "启动", "访问")):
        return f"Verify that the requested destination or application is open: {normalized}"
    if any(token in lowered for token in ("search", "find", "lookup", "搜索", "查找", "检索")):
        return f"Verify that visible results or page content correspond to: {normalized}"
    if any(token in lowered for token in ("type", "fill", "enter", "输入", "填写")):
        return f"Verify that the requested content was entered for: {normalized}"
    if any(token in lowered for token in ("click", "select", "choose", "点击", "选择")):
        return f"Verify that the requested control changed state after: {normalized}"
    if world_model is not None and world_model.active_window_title:
        return f"Verify that progress is visible in {world_model.active_window_title} after: {normalized}"
    return f"Verify that the subgoal is completed: {normalized}"


def _infer_capability_preference(title: str, *, world_model: WorldModel | None = None) -> str | None:
    lowered = title.strip().lower()
    if any(token in lowered for token in ("browser", "website", "web", "search", "visit", "网页", "网站", "搜索", "访问")):
        return "browser_dom"
    if any(token in lowered for token in ("copy", "paste", "clipboard", "复制", "粘贴")):
        return "clipboard"
    if any(token in lowered for token in ("excel", "powerpoint", "word", "spreadsheet", "slide", "ppt")):
        return "office_com"
    if any(token in lowered for token in ("terminal", "shell", "python env", "venv", "命令行", "终端")):
        return "guarded_shell_recipe"
    if world_model is not None and world_model.active_app == "browser":
        return "browser_dom"
    return None


def _infer_subgoal_risk(title: str) -> str:
    lowered = title.strip().lower()
    if any(
        token in lowered
        for token in (
            "login",
            "sign in",
            "password",
            "cart",
            "checkout",
            "pay",
            "submit",
            "send",
            "delete",
            "remove",
            "install",
            "登录",
            "密码",
            "购物车",
            "下单",
            "支付",
            "提交",
            "发送",
            "删除",
            "安装",
        )
    ):
        return "high"
    if any(token in lowered for token in ("save", "download", "bookmark", "保存", "下载", "收藏")):
        return "medium"
    return "low"


def _import_requests():
    try:
        import requests
    except ModuleNotFoundError as exc:
        raise PlannerError(
            "VLMPlanner requires the requests package. "
            "Run `python -m pip install requests` or install from requirements.txt."
        ) from exc
    return requests


def _normalize_api_base_url(base_url: str) -> str:
    raw = (base_url or "").strip()
    if not raw:
        raw = "http://127.0.0.1:1234/v1"
    if "://" not in raw:
        raw = f"http://{raw}"

    parsed = urlsplit(raw)
    path = parsed.path.rstrip("/")

    if path.endswith("/chat/completions"):
        path = path[: -len("/chat/completions")]
    elif path.endswith("/models"):
        path = path[: -len("/models")]

    if not path:
        path = "/v1"
    elif path != "/v1" and not path.endswith("/v1"):
        path = f"{path}/v1"

    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _needs_model_discovery(model_name: str | None) -> bool:
    return not (model_name or "").strip() or (model_name or "").strip().lower() in {"auto", "first"}


def _pick_model_name(configured_model: str | None, available_models: list[dict]) -> str:
    available_ids = [str(item.get("id", "")).strip() for item in available_models if str(item.get("id", "")).strip()]
    if not available_ids:
        raise PlannerError("No model identifiers were returned by /v1/models.")

    configured = (configured_model or "").strip()
    if _needs_model_discovery(configured):
        return available_ids[0]

    if configured in available_ids:
        return configured

    raise PlannerError(
        f"The configured model `{configured}` was not returned by /v1/models. "
        f"Available models: {', '.join(available_ids[:8])}"
    )


def _normalize_structured_output_mode(mode: str | None) -> str:
    normalized = (mode or "auto").strip().lower()
    if normalized in {"off", "none", "false"}:
        return "off"
    if normalized == "json_object":
        return "json_object"
    if normalized in {"auto", "json_schema"}:
        return "json_schema"
    return "off"


def _build_vlm_payload(
    *,
    model_name: str,
    task: str,
    history_text: str,
    decomposition_text: str,
    image_b64: str,
    browser_context: str | None,
    environment_context: str | None,
    response_format_mode: str,
) -> dict:
    user_text = (
        f"Task: {task}\n"
        f"Recent execution memory:\n{history_text}\n"
        f"Task decomposition hints:\n{decomposition_text}\n"
        + (f"Browser context:\n{browser_context}\n" if browser_context else "")
        + (f"Desktop environment:\n{environment_context}\n" if environment_context else "")
        + "Use the screenshot and execution memory to choose the next unmet sub-goal.\n"
        + "Keep actions focused on the current sub-goal, explain it with current_focus/reasoning when helpful, "
        + "and place unfinished future work in remaining_steps.\n"
        + "Return the next action plan as JSON."
    )
    payload = {
        "model": model_name,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_b64}",
                        },
                    },
                ],
            },
        ],
    }
    response_format = _build_response_format(response_format_mode)
    if response_format is not None:
        payload["response_format"] = response_format
    return payload


def _build_response_format(mode: str) -> dict | None:
    if mode == "off":
        return None
    if mode == "json_object":
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "desktop_agent_plan",
            "schema": _planner_json_schema(),
        },
    }


def _planner_json_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "status_summary": {"type": "string"},
            "done": {"type": "boolean"},
            "current_focus": {"type": "string"},
            "reasoning": {"type": "string"},
            "remaining_steps": {
                "type": "array",
                "items": {"type": "string"},
            },
            "actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "app": {"type": "string"},
                        "keys": {"type": "array", "items": {"type": "string"}},
                        "key": {"type": "string"},
                        "text": {"type": "string"},
                        "selector": {"type": "string"},
                        "title": {"type": "string"},
                        "x": {"type": "integer"},
                        "y": {"type": "integer"},
                        "width": {"type": "integer"},
                        "height": {"type": "integer"},
                        "relative_x": {"type": "number"},
                        "relative_y": {"type": "number"},
                        "button": {"type": "string"},
                        "clicks": {"type": "integer"},
                        "seconds": {"type": "number"},
                        "amount": {"type": "integer"},
                    },
                    "required": ["type"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["status_summary", "done", "actions"],
        "additionalProperties": False,
    }


def _build_request_headers(api_key: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _build_connection_hint(api_base: str, exc: Exception) -> str:
    return (
        f"Could not connect to the OpenAI-compatible server at {api_base}. "
        "If you are using LM Studio, start the local server first and make sure the base URL "
        "matches the server port. Original error: "
        f"{exc}"
    )


def _build_environment_context(environment: DesktopEnvironment | None) -> str | None:
    if environment is None:
        return None

    lines = [f"Platform: {environment.platform}"]
    lines.append(
        "Virtual desktop bounds: "
        f"{environment.virtual_bounds.left},{environment.virtual_bounds.top} "
        f"to {environment.virtual_bounds.right},{environment.virtual_bounds.bottom}"
    )
    if environment.current_monitor is not None:
        monitor = environment.current_monitor
        lines.append(
            f"Current monitor: {monitor.device_name} "
            f"work area {monitor.work_area.left},{monitor.work_area.top} "
            f"{monitor.work_area.width}x{monitor.work_area.height}"
        )
    if environment.taskbar is not None:
        lines.append(
            f"Taskbar: position={environment.taskbar.position or 'unknown'}, "
            f"auto_hide={'yes' if environment.taskbar.auto_hide else 'no'}, "
            f"occupies_work_area={'yes' if environment.taskbar.occupies_work_area else 'no'}"
        )
    lines.append(f"DPI scale: {environment.dpi_scale}")
    if environment.foreground_window is not None:
        foreground = environment.foreground_window
        title = foreground.title or "<untitled>"
        rect = foreground.rect
        rect_text = (
            f"{rect.left},{rect.top} {rect.width}x{rect.height}"
            if rect is not None
            else "unknown"
        )
        lines.append(
            f"Foreground window: {title}; minimized={'yes' if foreground.is_minimized else 'no'}; "
            f"maximized={'yes' if foreground.is_maximized else 'no'}; rect={rect_text}"
        )
    if environment.visible_windows:
        window_titles = [item.title for item in environment.visible_windows if item.title][:8]
        if window_titles:
            lines.append("Visible windows: " + ", ".join(window_titles))
    lines.append(
        "Planning policy: prefer reusing or focusing an existing target window, minimize unrelated windows before closing them, "
        "dismiss only obvious blockers, avoid assuming the taskbar or viewport consumes the full screenshot height, "
        "and prefer relative_click inside a known target window over fragile full-screen absolute click coordinates."
    )
    return "\n".join(lines)


def _looks_like_structured_output_rejection(body_text: str) -> bool:
    lowered = body_text.lower()
    phrases = (
        "response_format",
        "json_schema",
        "json_object",
        "structured output",
        "unsupported",
        "schema",
    )
    return any(phrase in lowered for phrase in phrases)


def _extract_message_content(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise PlannerError("Planner response contains no choices.")
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "\n".join(parts)
    raise PlannerError("Unsupported message content format.")


def _extract_json(text: str) -> dict:
    stripped = text.strip()
    if not stripped:
        raise PlannerError("Empty planner response.")
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", stripped, flags=re.S)
    if fenced:
        return json.loads(fenced.group(1))
    brace = _find_braced_object(stripped)
    if brace:
        return json.loads(brace)
    raise PlannerError("Unable to parse planner JSON output.")


def _find_braced_object(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]
