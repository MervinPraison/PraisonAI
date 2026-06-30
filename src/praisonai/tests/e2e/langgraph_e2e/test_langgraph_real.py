"""
LangGraph Real End-to-End Test

WARNING: Live tests make real API calls and may incur costs.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))


def _write_yaml(content: str) -> str:
    handle = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    handle.write(content)
    handle.close()
    return handle.name


@pytest.mark.real
class TestLangGraphReal:
    """Real LangGraph tests with actual API calls."""

    def test_langgraph_simple_setup(self):
        try:
            from praisonai import PraisonAI
        except ImportError as exc:
            pytest.skip(f"PraisonAI not available: {exc}")

        yaml_content = """
framework: langgraph
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
            praisonai = PraisonAI(agent_file=test_file, framework="langgraph")
            assert praisonai is not None
            assert praisonai.framework == "langgraph"
        finally:
            if os.path.exists(test_file):
                os.unlink(test_file)

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
    def test_langgraph_environment_check(self):
        pytest.importorskip("langgraph")
        pytest.importorskip("praisonai_frameworks")

    @pytest.mark.skipif(
        not os.getenv("PRAISONAI_LIVE_TESTS"),
        reason="Set PRAISONAI_LIVE_TESTS=1 to run real API calls",
    )
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
    def test_langgraph_full_execution_single_task(self):
        try:
            from praisonai import PraisonAI
        except ImportError as exc:
            pytest.skip(f"PraisonAI not available: {exc}")

        pytest.importorskip("langgraph")
        pytest.importorskip("praisonai_frameworks")

        yaml_content = """
framework: langgraph
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
            praisonai = PraisonAI(agent_file=test_file, framework="langgraph")
            result = praisonai.run()
            text = str(result)
            assert text.strip()
            assert "6" in text
            assert "LangGraph Output" in text or "langgraph" in text.lower()
        finally:
            if os.path.exists(test_file):
                os.unlink(test_file)

    @pytest.mark.skipif(
        not os.getenv("PRAISONAI_LIVE_TESTS"),
        reason="Set PRAISONAI_LIVE_TESTS=1 to run real API calls",
    )
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
    def test_langgraph_full_execution_sequential_context(self):
        try:
            from praisonai import PraisonAI
        except ImportError as exc:
            pytest.skip(f"PraisonAI not available: {exc}")

        pytest.importorskip("langgraph")
        pytest.importorskip("praisonai_frameworks")

        yaml_content = """
framework: langgraph
topic: Planet facts
roles:
  researcher:
    role: Research_Analyst
    goal: Gather concise facts
    backstory: Expert researcher
    tasks:
      research:
        description: Name one planet in our solar system. Reply with only the planet name.
        expected_output: A planet name
      summarise:
        description: Write one short sentence describing that planet.
        expected_output: One sentence
        context:
          - research
"""
        test_file = _write_yaml(yaml_content)
        try:
            praisonai = PraisonAI(agent_file=test_file, framework="langgraph")
            result = praisonai.run()
            text = str(result)
            assert text.strip()
            assert len(text.split()) >= 3
        finally:
            if os.path.exists(test_file):
                os.unlink(test_file)

    @pytest.mark.skipif(
        not os.getenv("PRAISONAI_LIVE_TESTS"),
        reason="Set PRAISONAI_LIVE_TESTS=1 to run real API calls",
    )
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
    def test_langgraph_adapter_direct_run(self):
        pytest.importorskip("langgraph")
        from praisonai_frameworks.langgraph.adapter import LangGraphAdapter

        config = {
            "framework": "langgraph",
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
        result = LangGraphAdapter().run(config, llm_config, "Quick test", tools_dict={})
        assert "### LangGraph Output ###" in result
        assert "OK" in result.upper()
