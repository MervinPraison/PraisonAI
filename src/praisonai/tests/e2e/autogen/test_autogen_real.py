"""AutoGen real E2E via praisonai-frameworks entry point."""

from __future__ import annotations

import os
import tempfile

import pytest

pytestmark = pytest.mark.real


@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY required")
def test_autogen_environment_check():
    import autogen

    assert autogen is not None


def test_autogen_simple_setup():
    from praisonai import PraisonAI

    yaml_content = """
framework: autogen
topic: Simple Math Question
roles:
  helper:
    role: Helper
    goal: Help solve basic math problems
    backstory: I am a helpful math teacher
    tasks:
      answer:
        description: What is 2 + 2? Provide just the number.
        expected_output: The answer to 2 + 2
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        test_file = f.name

    try:
        praison = PraisonAI(agent_file=test_file, framework="autogen")
        assert praison.framework == "autogen"
    finally:
        os.unlink(test_file)


@pytest.mark.skipif(not os.getenv("PRAISONAI_RUN_FULL_TESTS"), reason="Set PRAISONAI_RUN_FULL_TESTS=true")
def test_autogen_full_execution():
    from praisonai import run
    from praisonai.framework_adapters.registry import get_default_registry

    adapter = get_default_registry().create("autogen")
    resolved = adapter.resolve()
    assert type(resolved).__module__.startswith("praisonai_frameworks")

    yaml_content = """
framework: autogen
topic: Quick Test
roles:
  helper:
    role: Helper
    goal: Answer very briefly
    backstory: I give one-word answers
    tasks:
      answer:
        description: What is 1+1? Answer with just the number, nothing else.
        expected_output: Just the number
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        test_file = f.name

    try:
        result = run(test_file, framework="autogen")
        assert result is not None
        assert "2" in str(result)
    finally:
        os.unlink(test_file)
