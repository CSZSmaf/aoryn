from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from desktop_agent.logic_benchmark import run_logic_benchmark


DEFAULT_BENCHMARK_PATH = (
    PROJECT_ROOT / "desktop_agent" / "tests" / "fixtures" / "logic_benchmark.yaml"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the deterministic planner logic benchmark.")
    parser.add_argument(
        "benchmark",
        nargs="?",
        default=str(DEFAULT_BENCHMARK_PATH),
        help="Path to a benchmark YAML file.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    result = run_logic_benchmark(args.benchmark)
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(
            "Logic benchmark: "
            f"{result.passed_cases}/{result.total_cases} cases, "
            f"{result.passed_checks}/{result.total_checks} checks, "
            f"score {result.score:.1%}"
        )
        for case in result.cases:
            status = "PASS" if case.passed else "FAIL"
            print(f"{status} {case.name}: {case.passed_checks}/{case.total_checks}")
            for failure in case.failures:
                print(f"  - {failure}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
