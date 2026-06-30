"""
Google ADK Real End-to-End Test

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


def _google_key() -> str | None:
    return os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")


@pytest.mark.real
class TestGoogleAdkReal:
    """Real Google ADK tests with actual API calls."""

    def test_google_adk_simple_setup(self):
        pytest.importorskip("google.adk")
        pytest.importorskip("praisonai_frameworks")
        try:
            from praisonai import PraisonAI
        except ImportError as exc:
            pytest.skip(f"PraisonAI not available: {exc}")

        yaml_content = """
framework: google_adk
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
            praisonai = PraisonAI(agent_file=test_file, framework="google_adk")
            assert praisonai is not None
            assert praisonai.framework == "google_adk"
        finally:
            if os.path.exists(test_file):
                os.unlink(test_file)

    @pytest.mark.skipif(not _google_key(), reason="GOOGLE_API_KEY or GEMINI_API_KEY not set")
    def test_google_adk_environment_check(self):
        pytest.importorskip("google.adk")
        pytest.importorskip("praisonai_frameworks")
        from praisonai_frameworks._availability import is_available
        from praisonai_frameworks.google_adk.adapter import GoogleAdkAdapter

        assert is_available("google_adk") is True
        assert GoogleAdkAdapter().is_available() is True

    @pytest.mark.skipif(
        not os.getenv("PRAISONAI_LIVE_TESTS"),
        reason="Set PRAISONAI_LIVE_TESTS=1 to run real API calls",
    )
    @pytest.mark.skipif(not _google_key(), reason="GOOGLE_API_KEY or GEMINI_API_KEY not set")
    def test_google_adk_full_execution_single_task(self):
        try:
            from praisonai import PraisonAI
        except ImportError as exc:
            pytest.skip(f"PraisonAI not available: {exc}")

        pytest.importorskip("google.adk")
        pytest.importorskip("praisonai_frameworks")

        yaml_content = """
framework: google_adk
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
            praisonai = PraisonAI(agent_file=test_file, framework="google_adk")
            result = praisonai.run()
            text = str(result)
            assert text.strip()
            assert "6" in text
            assert "Google ADK Output" in text
        finally:
            if os.path.exists(test_file):
                os.unlink(test_file)

    @pytest.mark.skipif(
        not os.getenv("PRAISONAI_LIVE_TESTS"),
        reason="Set PRAISONAI_LIVE_TESTS=1 to run real API calls",
    )
    @pytest.mark.skipif(not _google_key(), reason="GOOGLE_API_KEY or GEMINI_API_KEY not set")
    def test_google_adk_adapter_direct_run(self):
        pytest.importorskip("google.adk")
        pytest.importorskip("praisonai_frameworks")
        from praisonai_frameworks.google_adk.adapter import GoogleAdkAdapter

        config = {
            "framework": "google_adk",
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
        llm_config = [{"model": "gemini-2.5-flash", "api_key": _google_key()}]
        result = GoogleAdkAdapter().run(config, llm_config, "Quick test", tools_dict={})
        assert "### Google ADK Output ###" in result
        assert "OK" in result.upper()

    @pytest.mark.skipif(
        not os.getenv("PRAISONAI_LIVE_TESTS"),
        reason="Set PRAISONAI_LIVE_TESTS=1 to run real API calls",
    )
    @pytest.mark.skipif(not _google_key(), reason="GOOGLE_API_KEY or GEMINI_API_KEY not set")
    def test_google_adk_full_execution_sequential_context(self):
        try:
            from praisonai import PraisonAI
        except ImportError as exc:
            pytest.skip(f"PraisonAI not available: {exc}")

        pytest.importorskip("google.adk")
        pytest.importorskip("praisonai_frameworks")

        yaml_content = """
framework: google_adk
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
            praisonai = PraisonAI(agent_file=test_file, framework="google_adk")
            result = praisonai.run()
            text = str(result)
            assert "6" in text
            assert "Google ADK Output" in text
        finally:
            if os.path.exists(test_file):
                os.unlink(test_file)

    @pytest.mark.skipif(
        not os.getenv("PRAISONAI_LIVE_TESTS"),
        reason="Set PRAISONAI_LIVE_TESTS=1 to run real API calls",
    )
    @pytest.mark.skipif(not _google_key(), reason="GOOGLE_API_KEY or GEMINI_API_KEY not set")
    def test_google_adk_full_execution_handoff_yaml(self):
        try:
            from praisonai import PraisonAI
        except ImportError as exc:
            pytest.skip(f"PraisonAI not available: {exc}")

        pytest.importorskip("google.adk")
        pytest.importorskip("praisonai_frameworks")

        yaml_content = """
framework: google_adk
topic: greeting
roles:
  triage:
    role: Triage Agent
    goal: Route English requests to English Agent
    backstory: Delegate English to the English Agent.
    handoff:
      to:
        - English Agent
    tasks:
      route:
        description: User says hello in English. Delegate appropriately.
        expected_output: A friendly English reply
  english:
    role: English Agent
    goal: Reply in English only
    backstory: English specialist.
"""
        test_file = _write_yaml(yaml_content)
        try:
            praisonai = PraisonAI(agent_file=test_file, framework="google_adk")
            result = praisonai.run()
            assert str(result).strip()
        finally:
            if os.path.exists(test_file):
                os.unlink(test_file)
