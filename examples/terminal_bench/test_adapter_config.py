"""Static regression checks for the in-tree Harbor adapter configuration."""

from pathlib import Path

import pytest
import yaml

EXAMPLES = Path(__file__).parent

TB21_DATASET = "terminal-bench/terminal-bench-2-1"
SMOKE_TASKS = [
    "terminal-bench/build-pmars",
    "terminal-bench/bn-fit-modify",
    "terminal-bench/break-filter-js-from-html",
]

HARBOR_JOB_FILES_WITH_SMOKE_TASKS = (
    "job_code_smoke.yaml",
    "job_test_5.yaml",
    "job_test_5_wrapper.yaml",
)


def _load_job(filename: str) -> dict:
    return yaml.safe_load((EXAMPLES / filename).read_text(encoding="utf-8"))


def _assert_tb21_dataset(dataset: dict, *, expect_tasks: bool) -> None:
    assert dataset["name"] == TB21_DATASET
    assert "version" not in dataset
    if expect_tasks:
        names = dataset["task_names"]
        assert names == SMOKE_TASKS
        assert all(name.startswith("terminal-bench/") for name in names)
    else:
        assert "task_names" not in dataset


def test_external_adapter_sets_coding_execution_budget():
    source = (EXAMPLES / "praisonai_external_agent.py").read_text(encoding="utf-8")

    assert "ExecutionConfig" in source
    assert "max_tool_calls_per_turn=80" in source
    assert "max_iter=40" in source
    assert "max_steps=80" in source


def test_external_adapter_does_not_guess_completion_from_pytest_text():
    source = (EXAMPLES / "praisonai_external_agent.py").read_text(encoding="utf-8")

    assert '"1 passed"' not in source
    assert '"test passed"' not in source


 main
