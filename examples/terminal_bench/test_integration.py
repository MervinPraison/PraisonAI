"""
Tests for the PraisonAI Terminal-Bench 2.1 (Harbor) integration.

Run from the repo root with PYTHONPATH set so the package import path resolves:
    PYTHONPATH=. python -m pytest examples/terminal_bench/test_integration.py -v

Tests that require Harbor are honestly skipped only when Harbor is not installed
(checked via importlib.util.find_spec). pytest-asyncio must be installed for the
async tests.
"""

import importlib.util
import shlex
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

HARBOR_AVAILABLE = importlib.util.find_spec("harbor") is not None

pytestmark = pytest.mark.skipif(
    not HARBOR_AVAILABLE, reason="Harbor not installed"
)


class TestPraisonAICodeAgent:
    """The headline `praisonai code` adapter."""

    def test_metadata(self):
        from examples.terminal_bench.praisonai_code_agent import PraisonAICodeAgent

        agent = PraisonAICodeAgent(model_name="openai/gpt-4o-mini", logs_dir="/tmp")
        assert agent.name() == "praisonai-code"
        assert agent.get_version_command() == "praisonai --version"

    @pytest.mark.asyncio
    async def test_code_agent_command_shape(self, tmp_path):
        """run() must issue the exact headless `praisonai code` command."""
        from examples.terminal_bench.praisonai_code_agent import PraisonAICodeAgent

        agent = PraisonAICodeAgent(
            model_name="openai/gpt-4o-mini", logs_dir=str(tmp_path)
        )
        env = Mock()
        env.exec = AsyncMock(
            return_value=SimpleNamespace(stdout="", stderr="", return_code=0)
        )
        context = SimpleNamespace(metadata=None)

        instruction = "fix the failing test"
        await agent.run(instruction, env, context)

        env.exec.assert_awaited()
        command = env.exec.await_args.kwargs.get("command", "")
        assert command.startswith(f"praisonai code {shlex.quote(instruction)}")
        assert "--dangerously-skip-approval" in command
        assert "--model openai/gpt-4o-mini" in command


class TestPraisonAIExternalAgent:
    """The external (SDK-level) adapter."""

    def test_metadata(self, tmp_path):
        from examples.terminal_bench.praisonai_external_agent import (
            PraisonAIExternalAgent,
        )

        agent = PraisonAIExternalAgent(logs_dir=str(tmp_path))
        assert agent.name() == "praisonai"
        version = agent.version()
        assert version is None or isinstance(version, str)

    def test_context_population_uses_cost_summary(self, tmp_path):
        from examples.terminal_bench.praisonai_external_agent import (
            PraisonAIExternalAgent,
        )

        agent_impl = PraisonAIExternalAgent(logs_dir=str(tmp_path))

        # cost_summary is a dict property on the real Agent, not a callable.
        mock_agent = Mock()
        mock_agent.name = "test-agent"
        mock_agent.llm = "gpt-4o-mini"
        mock_agent.cost_summary = {"tokens_in": 100, "tokens_out": 50, "cost": 0.01}

        context = SimpleNamespace(
            n_input_tokens=None, n_output_tokens=None, cost_usd=None, metadata=None
        )
        agent_impl._populate_context(mock_agent, context, "done")

        assert context.n_input_tokens == 100
        assert context.n_output_tokens == 50
        assert context.cost_usd == 0.01
        assert context.metadata["framework"] == "praisonai"


class TestPraisonAIInstalledAgent:
    """The installed adapter."""

    def test_metadata_and_flags(self):
        from examples.terminal_bench.praisonai_installed_agent import (
            PraisonAIInstalledAgent,
        )

        agent = PraisonAIInstalledAgent(logs_dir="/tmp")
        assert agent.name() == "praisonai"
        # CliFlag is keyed by `kwarg` in the real Harbor dataclass.
        assert all(getattr(f, "kwarg", None) for f in agent.CLI_FLAGS)

    def test_runner_script_uses_cost_summary(self):
        from examples.terminal_bench.praisonai_installed_agent import (
            PraisonAIInstalledAgent,
        )

        agent = PraisonAIInstalledAgent(logs_dir="/tmp")
        script = agent._build_runner_script()
        assert "cost_summary" in script
        assert "_usage" not in script
        assert "execute_command" in script
