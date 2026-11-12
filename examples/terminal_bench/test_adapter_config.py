"""Static regression checks for the in-tree Harbor adapter configuration."""

from pathlib import Path

import yaml


EXAMPLES = Path(__file__).parent


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


def test_smoke_yaml_uses_terminal_bench_21_registry_ids():
    job = yaml.safe_load(
        (EXAMPLES / "job_code_smoke.yaml").read_text(encoding="utf-8")
    )
    names = job["datasets"][0]["task_names"]

    assert names
    assert all(name.startswith("terminal-bench/") for name in names)
    assert names == [
        "terminal-bench/build-pmars",
        "terminal-bench/bn-fit-modify",
        "terminal-bench/break-filter-js-from-html",
    ]


def test_example_job_yamls_use_harbor_022_dataset_id():
    for name in ("job.yaml", "job_test_5.yaml", "job_test_5_wrapper.yaml"):
        job = yaml.safe_load((EXAMPLES / name).read_text(encoding="utf-8"))
        dataset = job["datasets"][0]

        assert dataset["name"] == "terminal-bench/terminal-bench-2-1", name
        assert "version" not in dataset, name
        assert all(
            task.startswith("terminal-bench/")
            for task in dataset.get("task_names", [])
        ), name
