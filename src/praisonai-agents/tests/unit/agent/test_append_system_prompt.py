"""Tests for the per-invocation --append-system-prompt behaviour (issue #3743).

The CLI flag exports ``PRAISONAI_APPEND_SYSTEM_PROMPT``; the core Agent reads it
when assembling the system prompt and appends the text at the END so the stable,
cacheable prefix is preserved. It is a per-invocation knob and is never written
back to any agent definition.
"""

import os
import unittest

from praisonaiagents import Agent

ENV_VAR = "PRAISONAI_APPEND_SYSTEM_PROMPT"


class TestAppendSystemPrompt(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.pop(ENV_VAR, None)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop(ENV_VAR, None)
        else:
            os.environ[ENV_VAR] = self._saved

    def test_append_system_prompt_affects_behaviour(self):
        """The env text is appended to the tail of the base system prompt."""
        os.environ[ENV_VAR] = "Always answer in French"
        agent = Agent(instructions="You are a helpful assistant")
        assert agent.system_prompt.rstrip().endswith("Always answer in French")

    def test_append_visible_in_chat_build_path(self):
        """The chat message-build path also appends the text at the end."""
        os.environ[ENV_VAR] = "Always answer in French"
        agent = Agent(instructions="You are a helpful assistant")
        built = agent._build_system_prompt()
        assert built is not None
        assert built.rstrip().endswith("Always answer in French")

    def test_noop_when_unset(self):
        """No env var means the system prompt is unchanged."""
        agent = Agent(instructions="You are a helpful assistant")
        assert "Always answer in French" not in agent.system_prompt

    def test_noop_when_blank(self):
        """Whitespace-only value is treated as unset."""
        os.environ[ENV_VAR] = "   "
        agent = Agent(instructions="You are a helpful assistant")
        assert agent.system_prompt.strip() != ""
        assert "   \n" not in agent.system_prompt.rstrip()

    def test_not_persisted_to_agent_backstory(self):
        """The append is applied to the prompt only, never to backstory."""
        os.environ[ENV_VAR] = "Always answer in French"
        agent = Agent(instructions="You are a helpful assistant")
        assert "Always answer in French" not in agent.backstory


class TestResolveAppendHelper(unittest.TestCase):
    """The CLI helper resolves literal text, @file, and the env fallback."""

    def setUp(self):
        self._saved = os.environ.pop(ENV_VAR, None)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop(ENV_VAR, None)
        else:
            os.environ[ENV_VAR] = self._saved

    def _helper(self):
        import importlib

        try:
            return importlib.import_module(
                "praisonai_code.cli.utils.append_prompt"
            )
        except ImportError:
            self.skipTest("praisonai_code wrapper not installed")

    def test_literal_text(self):
        mod = self._helper()
        assert mod.resolve_append_system_prompt("hello") == "hello"

    def test_none_returns_env_fallback(self):
        mod = self._helper()
        os.environ[ENV_VAR] = "from-env"
        assert mod.resolve_append_system_prompt(None) == "from-env"

    def test_none_without_env_is_none(self):
        mod = self._helper()
        assert mod.resolve_append_system_prompt(None) is None

    def test_at_file_form(self, ):
        mod = self._helper()
        import tempfile

        with tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8"
        ) as fh:
            fh.write("Respond concisely")
            path = fh.name
        try:
            assert mod.resolve_append_system_prompt(f"@{path}") == "Respond concisely"
        finally:
            os.unlink(path)

    def test_apply_sets_env(self):
        mod = self._helper()
        mod.apply_append_system_prompt("set-me")
        assert os.environ.get(ENV_VAR) == "set-me"


if __name__ == "__main__":
    unittest.main()
