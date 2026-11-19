"""Opt-in real local-model checks for structured generation.

Set PRAISONAI_AUTO_TEST_URL to an OpenAI-compatible local endpoint and
PRAISONAI_AUTO_TEST_MODEL to its installed model, then run with network/local
services explicitly enabled. No model is downloaded or server started here.
"""

import os
from pathlib import Path

import pytest
import yaml


@pytest.mark.integration
@pytest.mark.local_service
@pytest.mark.skipif(
    not os.environ.get("PRAISONAI_AUTO_TEST_URL")
    or not os.environ.get("PRAISONAI_AUTO_TEST_MODEL"),
    reason="explicit local-model URL and model are required",
)
def test_real_local_agent_and_structured_generators(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from praisonai.auto import AutoGenerator, WorkflowAutoGenerator
    from praisonaiagents import Agent

    url = os.environ["PRAISONAI_AUTO_TEST_URL"]
    model = os.environ["PRAISONAI_AUTO_TEST_MODEL"]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_BASE_URL", url)
    monkeypatch.setenv("OPENAI_API_KEY", "local-test")
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    monkeypatch.setenv("PRAISONAI_TELEMETRY_DISABLED", "true")
    agent = Agent(
        name="schema-check",
        instructions="Answer in one short sentence.",
        model=model,
        base_url=url,
        api_key="local-test",
        memory=False,
        reflection=False,
    )
    result = agent.start("Say hello in one sentence.")
    print("Real Agent.start output:", result)
    assert isinstance(result, str) and result.strip()

    config = [{"model": model, "base_url": url, "api_key": "local-test"}]
    for generator, target, key in [
        (
            AutoGenerator(
                topic="Create one greeting agent. No tools.",
                agent_file=str(tmp_path / "agents.yaml"),
                framework="praisonai",
                config_list=config,
            ),
            tmp_path / "agents.yaml",
            "roles",
        ),
        (
            WorkflowAutoGenerator(
                topic="Create one agent with id greeter and one sequential step using greeter. No tools.",
                workflow_file=str(tmp_path / "workflow.yaml"),
                framework="praisonai",
                config_list=config,
            ),
            tmp_path / "workflow.yaml",
            "agents",
        ),
    ]:
        try:
            generator.generate()
            print(target.read_text())
            data = yaml.safe_load(target.read_text())
            assert isinstance(data[key], dict) and data[key]
            if key == "agents":
                assert data["steps"]
        finally:
            generator.close()
