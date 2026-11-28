"""
AG2 integration tests.

framework='ag2' is not supported: the AG2 adapter is an unimplemented stub
and the AG2 run path was removed (#6661). This module pins the rejection
behaviour (a clear error naming the supported frameworks, never an
instruction to `pip install praisonai-frameworks[ag2]`) and the remaining
AG2 distribution-detection checks. No real LLM API calls are made.

Run:
    pytest tests/integration/ag2/test_ag2_integration.py -v
"""

import pytest
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../"))

# Stub heavy dependencies that auto.py (develop branch) imports at module level
# so that tests can import praisonai without a full installation.
for _stub in ("instructor",):
    if _stub not in sys.modules:
        sys.modules[_stub] = MagicMock()

import importlib as _importlib
if "openai" not in sys.modules:
    try:
        _importlib.import_module("openai")
    except ImportError:
        _mock_openai = MagicMock()
        _mock_openai.__version__ = "1.0.0"
        sys.modules["openai"] = _mock_openai


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def single_agent_yaml():
    return """
framework: ag2
topic: Write a short poem about Python
roles:
  poet:
    role: "Creative Poet"
    goal: "Write elegant and concise poems"
    backstory: "You are a creative poet who loves Python and technology."
    tasks:
      write_poem:
        description: "Write a short 4-line poem about Python programming"
        expected_output: "A 4-line poem about Python"
"""


# ---------------------------------------------------------------------------
# AG2 import detection
# ---------------------------------------------------------------------------

class TestAG2Import:

    @pytest.mark.integration
    def test_ag2_distribution_available(self):
        """ag2 PyPI distribution should be findable when installed.

        Note: ag2 installs under the 'autogen' namespace — 'import ag2' does NOT work.
        Detection uses importlib.metadata to check the 'ag2' distribution name.
        """
        import importlib.metadata
        try:
            dist = importlib.metadata.distribution('ag2')
            assert dist.metadata['Name'] == 'ag2'
        except importlib.metadata.PackageNotFoundError:
            pytest.skip("ag2 not installed — skipping AG2 integration tests")

    @pytest.mark.integration
    def test_autogen_namespace_importable_with_ag2(self):
        """When ag2 is installed, autogen namespace classes are importable."""
        try:
            from autogen import AssistantAgent, UserProxyAgent, GroupChat, LLMConfig
            assert AssistantAgent is not None
            assert UserProxyAgent is not None
            assert GroupChat is not None
            assert LLMConfig is not None
        except ImportError:
            pytest.skip("ag2 not installed — autogen namespace not available")


# ---------------------------------------------------------------------------
# framework='ag2' is rejected (removed, not implemented) — see #6661
# ---------------------------------------------------------------------------
# The AG2 adapter is an unimplemented stub (implemented = False) here and in
# praisonai-frameworks, and AgentsGenerator._run_ag2 was removed, so 'ag2' is
# no longer an accepted framework value. These tests pin the replacement
# behaviour: a clear error naming the supported frameworks, never an
# instruction to `pip install praisonai-frameworks[ag2]`.


# These tests are fully offline: they assert the rejection before any LLM
# call, so they opt out of the file's provider/network auto-marking.
@pytest.mark.offline
class TestAG2FrameworkRemoved:

    @pytest.mark.integration
    def test_single_agent_yaml_rejected_with_clear_error(self, single_agent_yaml, capsys):
        """PraisonAI(framework='ag2') fails fast naming the supported frameworks."""
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(single_agent_yaml)
            yaml_path = f.name

        try:
            try:
                from praisonai import PraisonAI
            except ImportError as e:
                pytest.skip(f"PraisonAI not available: {e}")

            with pytest.raises(SystemExit):
                PraisonAI(agent_file=yaml_path, framework="ag2")
        finally:
            os.unlink(yaml_path)

        out = capsys.readouterr().out
        assert "not supported" in out
        assert "Supported frameworks" in out
        assert "praisonai-frameworks[ag2]" not in out

    @pytest.mark.integration
    def test_ag2_run_rejected_with_clear_error(self):
        """AgentsGenerator with framework='ag2' fails at run prep, not at run time."""
        import yaml

        try:
            from praisonai.agents_generator import AgentsGenerator
        except ImportError as e:
            pytest.skip(f"AgentsGenerator not available: {e}")

        gen = AgentsGenerator(
            agent_file="agents.yaml",
            framework="ag2",
            config_list=[{"model": "gpt-4o-mini", "api_key": "sk-test"}],
        )
        gen.agent_yaml = yaml.dump({
            "framework": "ag2",
            "topic": "Test",
            "roles": {
                "agent": {
                    "role": "Agent", "goal": "Help", "backstory": "Helper.",
                    "tasks": {"t": {"description": "Do", "expected_output": "Done"}},
                    "tools": [],
                }
            },
        })

        with pytest.raises(ValueError, match="not supported") as exc_info:
            gen.generate_crew_and_kickoff()
        assert "Supported frameworks" in str(exc_info.value)
        assert "praisonai-frameworks[ag2]" not in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
