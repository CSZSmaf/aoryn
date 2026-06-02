from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from desktop_agent.config import AgentConfig
from desktop_agent.planner import PlannerError, RulePlanner, TaskGraphPlanner


@dataclass(slots=True)
class LogicBenchmarkCaseResult:
    name: str
    task: str
    passed_checks: int = 0
    total_checks: int = 0
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures


@dataclass(slots=True)
class LogicBenchmarkResult:
    cases: list[LogicBenchmarkCaseResult]

    @property
    def passed_checks(self) -> int:
        return sum(case.passed_checks for case in self.cases)

    @property
    def total_checks(self) -> int:
        return sum(case.total_checks for case in self.cases)

    @property
    def passed_cases(self) -> int:
        return sum(1 for case in self.cases if case.passed)

    @property
    def total_cases(self) -> int:
        return len(self.cases)

    @property
    def score(self) -> float:
        if self.total_checks <= 0:
            return 1.0
        return self.passed_checks / self.total_checks

    @property
    def passed(self) -> bool:
        return all(case.passed for case in self.cases)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "passed_checks": self.passed_checks,
            "total_checks": self.total_checks,
            "passed_cases": self.passed_cases,
            "total_cases": self.total_cases,
            "cases": [
                {
                    "name": case.name,
                    "task": case.task,
                    "passed": case.passed,
                    "passed_checks": case.passed_checks,
                    "total_checks": case.total_checks,
                    "failures": list(case.failures),
                }
                for case in self.cases
            ],
        }


def run_logic_benchmark(path: str | Path, *, config: AgentConfig | None = None) -> LogicBenchmarkResult:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    raw_cases = payload.get("cases") or []
    if not isinstance(raw_cases, list):
        raise ValueError("Benchmark file must contain a list under 'cases'.")

    benchmark_config = config or AgentConfig(complex_task_planning="heuristic")
    graph_planner = TaskGraphPlanner(benchmark_config)
    rule_planner = RulePlanner()
    results = [
        _run_case(raw_case, graph_planner=graph_planner, rule_planner=rule_planner)
        for raw_case in raw_cases
        if isinstance(raw_case, dict)
    ]
    return LogicBenchmarkResult(cases=results)


def _run_case(
    raw_case: dict[str, Any],
    *,
    graph_planner: TaskGraphPlanner,
    rule_planner: RulePlanner,
) -> LogicBenchmarkCaseResult:
    name = str(raw_case.get("name") or "unnamed").strip() or "unnamed"
    task = str(raw_case.get("task") or "").strip()
    result = LogicBenchmarkCaseResult(name=name, task=task)
    if not task:
        _record_failure(result, "case task is empty")
        return result

    graph = graph_planner.plan(task)
    subgoal_titles = [subgoal.title for subgoal in graph.subgoals]
    expected_subgoals = [str(item) for item in raw_case.get("expected_subgoals") or []]
    if expected_subgoals:
        _record_check(
            result,
            subgoal_titles == expected_subgoals,
            f"expected subgoals {expected_subgoals}, got {subgoal_titles}",
        )

    expected_action_types = raw_case.get("expected_action_types") or []
    expected_action_fields = raw_case.get("expected_action_fields") or []
    for index, expected_types in enumerate(expected_action_types):
        title = subgoal_titles[index] if index < len(subgoal_titles) else None
        if title is None:
            _record_failure(result, f"missing subgoal {index + 1} for expected actions {expected_types}")
            continue
        try:
            plan = rule_planner.plan(title, screenshot_path=None, history=[])
        except PlannerError as exc:
            _record_failure(result, f"subgoal {index + 1} '{title}' did not plan: {exc}")
            continue

        actual_types = [action.type for action in plan.actions]
        expected_types_list = [str(item) for item in expected_types]
        _record_check(
            result,
            actual_types == expected_types_list,
            f"subgoal {index + 1} '{title}' expected action types {expected_types_list}, got {actual_types}",
        )

        field_checks = expected_action_fields[index] if index < len(expected_action_fields) else []
        if not isinstance(field_checks, list):
            continue
        for action_index, expected_fields in enumerate(field_checks):
            if not isinstance(expected_fields, dict) or not expected_fields:
                continue
            if action_index >= len(plan.actions):
                _record_failure(result, f"subgoal {index + 1} missing action {action_index + 1} for field checks")
                continue
            actual = plan.actions[action_index].to_dict()
            for field_name, expected_value in expected_fields.items():
                _record_check(
                    result,
                    actual.get(field_name) == expected_value,
                    (
                        f"subgoal {index + 1} action {action_index + 1} expected "
                        f"{field_name}={expected_value!r}, got {actual.get(field_name)!r}"
                    ),
                )

    return result


def _record_check(result: LogicBenchmarkCaseResult, passed: bool, failure: str) -> None:
    result.total_checks += 1
    if passed:
        result.passed_checks += 1
    else:
        result.failures.append(failure)


def _record_failure(result: LogicBenchmarkCaseResult, failure: str) -> None:
    _record_check(result, False, failure)
