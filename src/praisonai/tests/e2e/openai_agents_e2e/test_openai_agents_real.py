"""
OpenAI Agents Real End-to-End Test

WARNING: Live tests make real API calls and may incur costs.
"""

from __future__ import annotations

import os
import tempfile

import pytest


def _write_yaml(content: str) -> str:
    handle = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    handle.write(content)
    handle.close()
    return handle.name


@pytest.mark.real
class TestOpenAIAgentsReal:
    """Real OpenAI Agents tests with actual API calls."""

    def test_openai_agents_simple_setup(self):
        pytest.importorskip("agents")
        pytest.importorskip("praisonai_frameworks")
        try:
            from praisonai import PraisonAI
        except ImportError as exc:
            pytest.skip(f"PraisonAI not available: {exc}")

        yaml_content = """
framework: openai_agents
topic: Simple Question Answer
roles:
  researcher:
    role: Helper
    goal: Answer simple questions accurately
    backstory: I am a helpful assistant
    tasks:
      answer:
        description: What is the capital of France? Reply with just the city name.
        expected_output: Paris
"""
        test_file = _write_yaml(yaml_content)
        try:
            praisonai = PraisonAI(agent_file=test_file, framework="openai_agents")
            assert praisonai is not None
            assert praisonai.framework == "openai_agents"
        finally:
            if os.path.exists(test_file):
                os.unlink(test_file)

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
    def test_openai_agents_environment_check(self):
        pytest.importorskip("agents")
        pytest.importorskip("praisonai_frameworks")

    @pytest.mark.skipif(
        not os.getenv("PRAISONAI_LIVE_TESTS"),
        reason="Set PRAISONAI_LIVE_TESTS=1 to run real API calls",
    )
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
    def test_openai_agents_full_execution_single_task(self):
        try:
            from praisonai import PraisonAI
        except ImportError as exc:
            pytest.skip(f"PraisonAI not available: {exc}")

        pytest.importorskip("agents")
        pytest.importorskip("praisonai_frameworks")

        yaml_content = """
framework: openai_agents
topic: Quick Math Test
roles:
  helper:
    role: Calculator
    goal: Do simple math quickly
    backstory: I give brief numeric answers
    tasks:
      math:
        description: Calculate 3+3. Answer with just the number, nothing else.
        expected_output: "6"
"""
        test_file = _write_yaml(yaml_content)
        try:
            praisonai = PraisonAI(agent_file=test_file, framework="openai_agents")
            result = praisonai.run()
            text = str(result)
            assert text.strip()
            assert "6" in text
            assert "OpenAI Agents Output" in text or "openai_agents" in text.lower()
        finally:
            if os.path.exists(test_file):
                os.unlink(test_file)

    @pytest.mark.skipif(
        not os.getenv("PRAISONAI_LIVE_TESTS"),
        reason="Set PRAISONAI_LIVE_TESTS=1 to run real API calls",
    )
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
    def test_openai_agents_adapter_direct_run(self):
        pytest.importorskip("agents")
        pytest.importorskip("praisonai_frameworks")
        from praisonai_frameworks.openai_agents.adapter import OpenAIAgentsAdapter

        config = {
            "framework": "openai_agents",
            "topic": "Quick test",
            "roles": {
                "helper": {
                    "role": "Assistant",
                    "goal": "Answer briefly",
                    "backstory": "Helpful assistant",
                    "tasks": {
                        "answer": {
                            "description": "Reply with exactly the word OK.",
                            "expected_output": "OK",
                        }
                    },
                }
            },
        }
        llm_config = [{"model": "gpt-4o-mini", "api_key": os.environ["OPENAI_API_KEY"]}]
        result = OpenAIAgentsAdapter().run(config, llm_config, "Quick test", tools_dict={})
        assert "### OpenAI Agents Output ###" in result
        assert "OK" in result.upper()
