from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from desktop_agent.runtime_paths import default_cache_root
from desktop_agent.workflow import ExecutionState, TaskGraph


@dataclass(slots=True)
class TaskRecipe:
    key: str
    task_type: str
    goal_types: list[str] = field(default_factory=list)
    capability_sequence: list[str] = field(default_factory=list)
    specialist_sequence: list[str] = field(default_factory=list)
    verified_evidence_kinds: list[str] = field(default_factory=list)
    summary: str | None = None
    uses: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TaskRecipe":
        return cls(
            key=str(payload.get("key", "")).strip(),
            task_type=str(payload.get("task_type", "general")).strip() or "general",
            goal_types=[str(item).strip() for item in payload.get("goal_types", []) or [] if str(item).strip()],
            capability_sequence=[
                str(item).strip()
                for item in payload.get("capability_sequence", []) or []
                if str(item).strip()
            ],
            specialist_sequence=[
                str(item).strip()
                for item in payload.get("specialist_sequence", []) or []
                if str(item).strip()
            ],
            verified_evidence_kinds=[
                str(item).strip()
                for item in payload.get("verified_evidence_kinds", []) or []
                if str(item).strip()
            ],
            summary=_optional_str(payload.get("summary")),
            uses=max(1, int(payload.get("uses", 1) or 1)),
            created_at=float(payload.get("created_at", time.time()) or time.time()),
            updated_at=float(payload.get("updated_at", time.time()) or time.time()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "task_type": self.task_type,
            "goal_types": list(self.goal_types),
            "capability_sequence": list(self.capability_sequence),
            "specialist_sequence": list(self.specialist_sequence),
            "verified_evidence_kinds": list(self.verified_evidence_kinds),
            "summary": self.summary,
            "uses": self.uses,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class TaskRecipeMemory:
    def __init__(self, path: Path | None = None, *, max_recipes: int = 60) -> None:
        self.path = path or default_recipe_memory_path()
        self.max_recipes = max(1, int(max_recipes))

    def load(self) -> list[TaskRecipe]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []
        items = payload.get("recipes") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return []
        recipes = [TaskRecipe.from_dict(item) for item in items if isinstance(item, dict)]
        return [item for item in recipes if item.key]

    def match(self, task_graph: TaskGraph, *, limit: int = 3) -> list[TaskRecipe]:
        target_key = _recipe_key_for_graph(task_graph)
        if not target_key:
            return []
        target_intent = _task_type_for_graph(task_graph)
        target_goal_types = _goal_types_for_graph(task_graph)
        matches: list[tuple[int, TaskRecipe]] = []
        for recipe in self.load():
            score = 0
            if recipe.key == target_key:
                score += 6
            if recipe.task_type == target_intent:
                score += 3
            common_prefix = _common_prefix_length(recipe.goal_types, target_goal_types)
            score += common_prefix
            if score > 0:
                matches.append((score + recipe.uses, recipe))
        matches.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
        return [recipe for _score, recipe in matches[: max(1, int(limit))]]

    def apply_hints(self, task_graph: TaskGraph) -> list[dict[str, Any]]:
        matched = self.match(task_graph)
        if not matched:
            return []
        best = matched[0]
        for subgoal, capability in zip(task_graph.subgoals, best.capability_sequence):
            if capability and not subgoal.capability_preference:
                subgoal.capability_preference = capability
        payloads = [item.to_dict() for item in matched]
        task_graph.recipes = payloads
        return payloads

    def record_success(self, execution_state: ExecutionState) -> TaskRecipe | None:
        if not execution_state.completed:
            return None
        recipe = build_recipe_from_state(execution_state)
        if recipe is None:
            return None
        recipes = self.load()
        now = time.time()
        replaced = False
        for index, existing in enumerate(recipes):
            if existing.key != recipe.key:
                continue
            recipe.created_at = existing.created_at
            recipe.uses = existing.uses + 1
            recipe.updated_at = now
            recipes[index] = recipe
            replaced = True
            break
        if not replaced:
            recipe.updated_at = now
            recipes.append(recipe)
        recipes.sort(key=lambda item: (item.uses, item.updated_at), reverse=True)
        self._save(recipes[: self.max_recipes])
        return recipe

    def _save(self, recipes: list[TaskRecipe]) -> None:
        payload = {"recipes": [item.to_dict() for item in recipes]}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def default_recipe_memory_path() -> Path:
    return default_cache_root() / "task-recipes.json"


def build_recipe_from_state(execution_state: ExecutionState) -> TaskRecipe | None:
    task_graph = execution_state.task_graph
    key = _recipe_key_for_graph(task_graph)
    if not key:
        return None
    capability_sequence = _successful_capability_sequence(execution_state)
    if not capability_sequence:
        capability_sequence = [
            subgoal.capability_preference or "desktop_gui"
            for subgoal in task_graph.subgoals
            if subgoal.status == "completed"
        ]
    return TaskRecipe(
        key=key,
        task_type=_task_type_for_graph(task_graph),
        goal_types=_goal_types_for_graph(task_graph),
        capability_sequence=capability_sequence[: len(task_graph.subgoals)],
        specialist_sequence=_successful_specialist_sequence(execution_state)[: len(task_graph.subgoals)],
        verified_evidence_kinds=_verified_evidence_kinds(execution_state),
        summary=_sanitize_recipe_summary(task_graph.completion_summary),
    )


def _recipe_key_for_graph(task_graph: TaskGraph) -> str:
    task_type = _task_type_for_graph(task_graph)
    goal_types = _goal_types_for_graph(task_graph)
    if not task_type or not goal_types:
        return ""
    return f"{task_type}:{' > '.join(goal_types[:6])}"


def _task_type_for_graph(task_graph: TaskGraph) -> str:
    intent = task_graph.intent if isinstance(task_graph.intent, dict) else {}
    return str(intent.get("task_type") or "general").strip() or "general"


def _goal_types_for_graph(task_graph: TaskGraph) -> list[str]:
    return [str(item.goal_type or "handoff").strip() or "handoff" for item in task_graph.subgoals]


def _successful_capability_sequence(execution_state: ExecutionState) -> list[str]:
    sequence: list[str] = []
    seen_by_subgoal: set[str] = set()
    for item in execution_state.evidence_ledger:
        if not isinstance(item, dict) or item.get("status") != "success":
            continue
        subgoal_id = str(item.get("subgoal_id") or "").strip()
        capability = str(item.get("capability") or "").strip()
        if not subgoal_id or not capability or subgoal_id in seen_by_subgoal:
            continue
        seen_by_subgoal.add(subgoal_id)
        sequence.append(capability)
    return sequence


def _successful_specialist_sequence(execution_state: ExecutionState) -> list[str]:
    sequence: list[str] = []
    seen_by_subgoal: set[str] = set()
    workspace = execution_state.workspace
    for item in workspace.evidence:
        if not isinstance(item, dict) or item.get("status") != "success":
            continue
        subgoal_id = str(item.get("subgoal_id") or "").strip()
        specialist = str(item.get("specialist") or "").strip()
        if not subgoal_id or not specialist or subgoal_id in seen_by_subgoal:
            continue
        seen_by_subgoal.add(subgoal_id)
        sequence.append(specialist)
    return sequence


def _verified_evidence_kinds(execution_state: ExecutionState) -> list[str]:
    kinds: list[str] = []
    for item in execution_state.evidence_ledger:
        if not isinstance(item, dict) or item.get("status") != "success":
            continue
        for evidence in item.get("evidence", []) or []:
            if not isinstance(evidence, dict):
                continue
            kind = str(evidence.get("kind") or evidence.get("scope") or "").strip()
            if kind and kind not in kinds:
                kinds.append(kind)
    return kinds[:12]


def _sanitize_recipe_summary(value: str | None) -> str | None:
    text = _optional_str(value)
    if text is None:
        return None
    text = re.sub(r"https?://\S+", "<url>", text)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "<email>", text)
    text = re.sub(r"\b[A-Za-z0-9_-]{24,}\b", "<token>", text)
    return text[:240]


def _common_prefix_length(left: list[str], right: list[str]) -> int:
    count = 0
    for left_item, right_item in zip(left, right):
        if left_item != right_item:
            break
        count += 1
    return count


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
