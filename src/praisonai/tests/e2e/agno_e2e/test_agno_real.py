"""
Agno Real End-to-End Test

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
class TestAgnoReal:
    """Real Agno tests with actual API calls."""

    def test_agno_simple_setup(self):
        pytest.importorskip("agno")
        pytest.importorskip("praisonai_frameworks")
        try:
            from praisonai import PraisonAI
        except ImportError as exc:
            pytest.skip(f"PraisonAI not available: {exc}")

        yaml_content = """
framework: agno
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
            praisonai = PraisonAI(agent_file=test_file, framework="agno")
            assert praisonai is not None
            assert praisonai.framework == "agno"
        finally:
            if os.path.exists(test_file):
                os.unlink(test_file)

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
    def test_agno_environment_check(self):
        pytest.importorskip("agno")
        pytest.importorskip("praisonai_frameworks")
        from praisonai_frameworks._availability import is_available
        from praisonai_frameworks.agno.adapter import AgnoAdapter

        assert is_available("agno") is True
        assert AgnoAdapter().is_available() is True

    @pytest.mark.skipif(
        not os.getenv("PRAISONAI_LIVE_TESTS"),
        reason="Set PRAISONAI_LIVE_TESTS=1 to run real API calls",
    )
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
    def test_agno_full_execution_single_task(self):
        try:
            from praisonai import PraisonAI
        except ImportError as exc:
            pytest.skip(f"PraisonAI not available: {exc}")

        pytest.importorskip("agno")
        pytest.importorskip("praisonai_frameworks")

        yaml_content = """
framework: agno
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
            praisonai = PraisonAI(agent_file=test_file, framework="agno")
            result = praisonai.run()
            text = str(result)
            assert text.strip()
            assert "6" in text
            assert "Agno Output" in text or "agno" in text.lower()
        finally:
            if os.path.exists(test_file):
                os.unlink(test_file)

    @pytest.mark.skipif(
        not os.getenv("PRAISONAI_LIVE_TESTS"),
        reason="Set PRAISONAI_LIVE_TESTS=1 to run real API calls",
    )
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
    def test_agno_adapter_direct_run(self):
        pytest.importorskip("agno")
        pytest.importorskip("praisonai_frameworks")
        from praisonai_frameworks.agno.adapter import AgnoAdapter

        config = {
            "framework": "agno",
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
        result = AgnoAdapter().run(config, llm_config, "Quick test", tools_dict={})
        assert "### Agno Output ###" in result
        assert "OK" in result.upper()

    @pytest.mark.skipif(
        not os.getenv("PRAISONAI_LIVE_TESTS"),
        reason="Set PRAISONAI_LIVE_TESTS=1 to run real API calls",
    )
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
    def test_agno_full_execution_sequential_context(self):
        try:
            from praisonai import PraisonAI
        except ImportError as exc:
            pytest.skip(f"PraisonAI not available: {exc}")

        pytest.importorskip("agno")
        pytest.importorskip("praisonai_frameworks")

        yaml_content = """
framework: agno
topic: numbers
roles:
  writer:
    role: Writer
    goal: Write numbers only
    backstory: Concise writer
    tasks:
      draft:
        description: Reply with only the number 3.
        expected_output: "3"
      polish:
        description: Add 3 to the previous result. Reply with only the number.
        expected_output: "6"
        context:
          - draft
"""
        test_file = _write_yaml(yaml_content)
        try:
            praisonai = PraisonAI(agent_file=test_file, framework="agno")
            result = praisonai.run()
            text = str(result)
            assert "6" in text
            assert "Agno Output" in text
        finally:
            if os.path.exists(test_file):
                os.unlink(test_file)
