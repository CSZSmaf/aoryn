from pathlib import Path

from desktop_agent.logic_benchmark import run_logic_benchmark


FIXTURE = Path(__file__).parent / "fixtures" / "logic_benchmark.yaml"


def test_logic_benchmark_fixture_passes():
    result = run_logic_benchmark(FIXTURE)

    assert result.passed is True
    assert result.score == 1.0
    assert result.passed_cases == result.total_cases
    assert result.total_cases >= 5


def test_logic_benchmark_reports_failed_expectations(tmp_path):
    benchmark = tmp_path / "bad_benchmark.yaml"
    benchmark.write_text(
        "\n".join(
            [
                "cases:",
                "  - name: wrong_expectation",
                "    task: open notepad",
                "    expected_subgoals:",
                "      - open calculator",
                "    expected_action_types:",
                "      - [browser_open]",
            ]
        ),
        encoding="utf-8",
    )

    result = run_logic_benchmark(benchmark)

    assert result.passed is False
    assert result.score < 1.0
    assert result.cases[0].failures
