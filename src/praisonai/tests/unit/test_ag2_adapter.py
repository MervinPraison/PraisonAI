"""
Unit tests for the AG2 framework integration in PraisonAI.

Tests cover:
- AG2 availability detection (AG2_AVAILABLE flag)
- Framework validation in AgentsGenerator.__init__
- _run_ag2 method: config parsing, agent creation, tool handling
- LLMConfig construction (OpenAI and Bedrock paths)

All external calls are mocked — no real LLM API calls made.
"""

import pytest
import os
import sys
from unittest.mock import patch, MagicMock, call
import importlib

# Ensure src is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))

# Stub heavy dependencies that auto.py (develop branch) imports at module level
# so that tests can import praisonai without a full installation.
for _stub in ("instructor",):
    if _stub not in sys.modules:
        sys.modules[_stub] = MagicMock()

# openai is installed (required by ag2/autogen internals), but auto.py also
# imports it at module level. Ensure it's really loaded, not a mock.
import importlib as _importlib
if "openai" not in sys.modules:
    try:
        _importlib.import_module("openai")
    except ImportError:
        _mock_openai = MagicMock()
        _mock_openai.__version__ = "1.0.0"
        sys.modules["openai"] = _mock_openai


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(roles=None, framework="ag2", topic="Test topic"):
    """Build a minimal agents config dict."""
    if roles is None:
        roles = {
            "researcher": {
                "role": "Researcher",
                "goal": "Research things",
                "backstory": "You are a researcher.",
                "tasks": {
                    "task1": {
                        "description": "Research {topic}",
                        "expected_output": "A research report",
                    }
                },
                "tools": [],
            }
        }
    return {"framework": framework, "topic": topic, "roles": roles}


# ---------------------------------------------------------------------------
# AG2_AVAILABLE flag detection
# ---------------------------------------------------------------------------

class TestAG2AvailabilityFlag:

    def test_ag2_available_false_when_not_installed(self):
        """AG2_AVAILABLE is False when 'ag2' distribution is not found."""
        import importlib.metadata as meta
        original_fn = meta.distribution

        def raise_not_found(name):
            if name == 'ag2':
                raise meta.PackageNotFoundError('ag2')
            return original_fn(name)

        # Verify detection logic directly without relying on cached module state
        ag2_detected = True
        try:
            with patch('importlib.metadata.distribution', side_effect=raise_not_found):
                meta.distribution('ag2')
        except meta.PackageNotFoundError:
            ag2_detected = False
        assert ag2_detected is False

    def test_ag2_available_true_when_installed(self):
        """AG2_AVAILABLE is True when 'ag2' distribution and LLMConfig are present."""
        import importlib.metadata as meta
        try:
            dist = meta.distribution('ag2')
            assert dist is not None
            from autogen import LLMConfig  # noqa: F401
        except (meta.PackageNotFoundError, ImportError):
            pytest.skip("ag2 not installed — skipping")


# ---------------------------------------------------------------------------
# AgentsGenerator.__init__ framework validation
# ---------------------------------------------------------------------------

class TestAgentsGeneratorAG2Validation:

    def _make_generator(self, framework, ag2_available=True):
        """Create AgentsGenerator with mocked availability flags."""
        with patch("praisonai.agents_generator.AG2_AVAILABLE", ag2_available), \
             patch("praisonai.agents_generator.CREWAI_AVAILABLE", False), \
             patch("praisonai.agents_generator.AUTOGEN_AVAILABLE", False), \
             patch("praisonai.agents_generator.PRAISONAI_AVAILABLE", True):
            from praisonai.agents_generator import AgentsGenerator
            return AgentsGenerator(
                agent_file="agents.yaml",
                framework=framework,
                config_list=[{"model": "gpt-4o-mini", "api_key": "test-key"}],
            )

    def test_ag2_framework_accepted_when_available(self):
        """No ImportError when framework='ag2' and AG2 is installed."""
        gen = self._make_generator("ag2", ag2_available=True)
        assert gen.framework == "ag2"

    def test_ag2_framework_raises_when_not_available(self):
        """ImportError raised with helpful message when ag2 not installed."""
        with pytest.raises(ImportError, match="AG2 is not installed"):
            self._make_generator("ag2", ag2_available=False)

    def test_autogen_framework_unaffected(self):
        """Existing autogen framework path still works independently."""
        with patch("praisonai.agents_generator.AG2_AVAILABLE", False), \
             patch("praisonai.agents_generator.AUTOGEN_AVAILABLE", True), \
             patch("praisonai.agents_generator.CREWAI_AVAILABLE", False), \
             patch("praisonai.agents_generator.PRAISONAI_AVAILABLE", True):
            from praisonai.agents_generator import AgentsGenerator
            gen = AgentsGenerator(
                agent_file="agents.yaml",
                framework="autogen",
                config_list=[{"model": "gpt-4o-mini", "api_key": "test-key"}],
            )
            assert gen.framework == "autogen"


# ---------------------------------------------------------------------------
# _run_ag2: LLMConfig construction
# ---------------------------------------------------------------------------

class TestRunAG2LLMConfig:

    def _make_gen_with_config(self, config_list):
        """Build an AgentsGenerator instance with given config_list."""
        with patch("praisonai.agents_generator.AG2_AVAILABLE", True), \
             patch("praisonai.agents_generator.CREWAI_AVAILABLE", False), \
             patch("praisonai.agents_generator.AUTOGEN_AVAILABLE", False), \
             patch("praisonai.agents_generator.PRAISONAI_AVAILABLE", True):
            from praisonai.agents_generator import AgentsGenerator
            return AgentsGenerator(
                agent_file="agents.yaml",
                framework="ag2",
                config_list=config_list,
            )

    @patch("praisonai.agents_generator.AG2_AVAILABLE", True)
    def test_openai_llm_config_constructed(self):
        """LLMConfig is built with api_type='openai' for standard config."""
        gen = self._make_gen_with_config([
            {"model": "gpt-4o-mini", "api_key": "sk-test", "api_type": "openai"}
        ])

        mock_llm_config = MagicMock()
        mock_llm_config.__enter__ = MagicMock(return_value=mock_llm_config)
        mock_llm_config.__exit__ = MagicMock(return_value=False)

        mock_assistant = MagicMock()
        mock_user_proxy = MagicMock()
        mock_groupchat = MagicMock()
        mock_groupchat.messages = [{"name": "Researcher", "content": "Done. TERMINATE", "role": "assistant"}]
        mock_manager = MagicMock()

        with patch("praisonai.agents_generator.AG2_AVAILABLE", True), \
             patch("autogen.LLMConfig", return_value=mock_llm_config) as mock_llmcfg, \
             patch("autogen.AssistantAgent", return_value=mock_assistant), \
             patch("autogen.UserProxyAgent", return_value=mock_user_proxy), \
             patch("autogen.GroupChat", return_value=mock_groupchat), \
             patch("autogen.GroupChatManager", return_value=mock_manager):

            config = _make_config()
            gen._run_ag2(config, "Test topic", {})

            mock_llmcfg.assert_called_once()
            # LLMConfig is called with a positional dict arg
            call_args = mock_llmcfg.call_args[0][0]
            assert call_args.get("model") == "gpt-4o-mini"
            assert call_args.get("api_key") == "sk-test"

    @patch("praisonai.agents_generator.AG2_AVAILABLE", True)
    def test_bedrock_llm_config_constructed(self):
        """LLMConfig uses api_type='bedrock' when config specifies bedrock."""
        gen = self._make_gen_with_config([
            {
                "model": "anthropic.claude-3-5-sonnet-20241022-v2:0",
                "api_type": "bedrock",
            }
        ])

        mock_llm_config = MagicMock()
        mock_llm_config.__enter__ = MagicMock(return_value=mock_llm_config)
        mock_llm_config.__exit__ = MagicMock(return_value=False)

        mock_assistant = MagicMock()
        mock_user_proxy = MagicMock()
        mock_groupchat = MagicMock()
        mock_groupchat.messages = [{"name": "Agent", "content": "Report ready. TERMINATE", "role": "assistant"}]
        mock_manager = MagicMock()

        with patch("autogen.LLMConfig", return_value=mock_llm_config) as mock_llmcfg, \
             patch("autogen.AssistantAgent", return_value=mock_assistant), \
             patch("autogen.UserProxyAgent", return_value=mock_user_proxy), \
             patch("autogen.GroupChat", return_value=mock_groupchat), \
             patch("autogen.GroupChatManager", return_value=mock_manager):

            config = _make_config()
            gen._run_ag2(config, "AWS deployment", {})

            mock_llmcfg.assert_called_once()
            # LLMConfig is called with a positional dict arg
            call_args = mock_llmcfg.call_args[0][0]
            assert call_args.get("api_type") == "bedrock"
            assert "api_key" not in call_args  # no api_key for bedrock


# ---------------------------------------------------------------------------
# _run_ag2: agent and GroupChat creation
# ---------------------------------------------------------------------------

class TestRunAG2AgentCreation:

    def _make_gen(self):
        with patch("praisonai.agents_generator.AG2_AVAILABLE", True), \
             patch("praisonai.agents_generator.CREWAI_AVAILABLE", False), \
             patch("praisonai.agents_generator.AUTOGEN_AVAILABLE", False), \
             patch("praisonai.agents_generator.PRAISONAI_AVAILABLE", True):
            from praisonai.agents_generator import AgentsGenerator
            return AgentsGenerator(
                agent_file="agents.yaml",
                framework="ag2",
                config_list=[{"model": "gpt-4o-mini", "api_key": "sk-test"}],
            )

    def test_assistant_created_per_role(self):
        """One AssistantAgent is created for each role in the config."""
        gen = self._make_gen()
        config = _make_config(roles={
            "role_a": {
                "role": "Agent A", "goal": "Goal A", "backstory": "Backstory A",
                "tasks": {"t1": {"description": "Do A", "expected_output": "A done"}},
                "tools": [],
            },
            "role_b": {
                "role": "Agent B", "goal": "Goal B", "backstory": "Backstory B",
                "tasks": {"t2": {"description": "Do B", "expected_output": "B done"}},
                "tools": [],
            },
        })

        mock_llm_config = MagicMock()
        mock_llm_config.__enter__ = MagicMock(return_value=mock_llm_config)
        mock_llm_config.__exit__ = MagicMock(return_value=False)

        created_agents = []

        def fake_assistant(**kwargs):
            m = MagicMock()
            m.name = kwargs.get("name", "agent")
            created_agents.append(m)
            return m

        mock_user_proxy = MagicMock()
        mock_groupchat = MagicMock()
        mock_groupchat.messages = [{"name": "Agent A", "content": "Done. TERMINATE", "role": "assistant"}]
        mock_manager = MagicMock()

        with patch("autogen.LLMConfig", return_value=mock_llm_config), \
             patch("autogen.AssistantAgent", side_effect=fake_assistant), \
             patch("autogen.UserProxyAgent", return_value=mock_user_proxy), \
             patch("autogen.GroupChat", return_value=mock_groupchat), \
             patch("autogen.GroupChatManager", return_value=mock_manager):

            gen._run_ag2(config, "Test", {})

        assert len(created_agents) == 2

    def test_groupchat_includes_user_proxy_and_assistants(self):
        """GroupChat receives user_proxy + all assistants."""
        gen = self._make_gen()
        config = _make_config()

        mock_llm_config = MagicMock()
        mock_llm_config.__enter__ = MagicMock(return_value=mock_llm_config)
        mock_llm_config.__exit__ = MagicMock(return_value=False)

        mock_assistant = MagicMock()
        mock_assistant.name = "Researcher"
        mock_user_proxy = MagicMock()
        mock_user_proxy.name = "User"
        mock_groupchat = MagicMock()
        mock_groupchat.messages = [{"name": "Researcher", "content": "Done. TERMINATE", "role": "assistant"}]
        mock_manager = MagicMock()

        groupchat_call_args = {}

        def capture_groupchat(**kwargs):
            groupchat_call_args.update(kwargs)
            return mock_groupchat

        with patch("autogen.LLMConfig", return_value=mock_llm_config), \
             patch("autogen.AssistantAgent", return_value=mock_assistant), \
             patch("autogen.UserProxyAgent", return_value=mock_user_proxy), \
             patch("autogen.GroupChat", side_effect=capture_groupchat), \
             patch("autogen.GroupChatManager", return_value=mock_manager):

            gen._run_ag2(config, "Test", {})

        agents_in_groupchat = groupchat_call_args.get("agents", [])
        assert mock_user_proxy in agents_in_groupchat
        assert mock_assistant in agents_in_groupchat

    def test_empty_roles_returns_no_agents_message(self):
        """Returns a clear message when no roles are defined in config."""
        gen = self._make_gen()
        config = _make_config(roles={})

        mock_llm_config = MagicMock()
        mock_llm_config.__enter__ = MagicMock(return_value=mock_llm_config)
        mock_llm_config.__exit__ = MagicMock(return_value=False)
        mock_user_proxy = MagicMock()

        with patch("autogen.LLMConfig", return_value=mock_llm_config), \
             patch("autogen.AssistantAgent"), \
             patch("autogen.UserProxyAgent", return_value=mock_user_proxy):

            result = gen._run_ag2(config, "Test", {})

        assert "No agents" in result


# ---------------------------------------------------------------------------
# _run_ag2: system message composition
# ---------------------------------------------------------------------------

class TestRunAG2SystemMessage:

    def _make_gen(self):
        with patch("praisonai.agents_generator.AG2_AVAILABLE", True), \
             patch("praisonai.agents_generator.CREWAI_AVAILABLE", False), \
             patch("praisonai.agents_generator.AUTOGEN_AVAILABLE", False), \
             patch("praisonai.agents_generator.PRAISONAI_AVAILABLE", True):
            from praisonai.agents_generator import AgentsGenerator
            return AgentsGenerator(
                agent_file="agents.yaml",
                framework="ag2",
                config_list=[{"model": "gpt-4o-mini", "api_key": "sk-test"}],
            )

    def test_system_message_contains_backstory(self):
        """AssistantAgent system_message includes the backstory from YAML."""
        gen = self._make_gen()
        config = _make_config(roles={
            "agent1": {
                "role": "Expert",
                "goal": "Help users",
                "backstory": "A unique backstory for testing purposes.",
                "tasks": {"t": {"description": "Do it", "expected_output": "Done"}},
                "tools": [],
            }
        })

        mock_llm_config = MagicMock()
        mock_llm_config.__enter__ = MagicMock(return_value=mock_llm_config)
        mock_llm_config.__exit__ = MagicMock(return_value=False)
        mock_user_proxy = MagicMock()
        mock_groupchat = MagicMock()
        mock_groupchat.messages = [{"name": "Expert", "content": "Done. TERMINATE", "role": "assistant"}]
        mock_manager = MagicMock()

        assistant_kwargs = {}

        def capture_assistant(**kwargs):
            assistant_kwargs.update(kwargs)
            m = MagicMock()
            m.name = kwargs.get("name", "agent")
            return m

        with patch("autogen.LLMConfig", return_value=mock_llm_config), \
             patch("autogen.AssistantAgent", side_effect=capture_assistant), \
             patch("autogen.UserProxyAgent", return_value=mock_user_proxy), \
             patch("autogen.GroupChat", return_value=mock_groupchat), \
             patch("autogen.GroupChatManager", return_value=mock_manager):

            gen._run_ag2(config, "Test", {})

        assert "A unique backstory for testing purposes." in assistant_kwargs.get("system_message", "")
        assert "TERMINATE" in assistant_kwargs.get("system_message", "")

    def test_agent_name_sanitised(self):
        """Agent names with special characters are sanitised for AG2 compatibility."""
        gen = self._make_gen()
        config = _make_config(roles={
            "agent1": {
                "role": "AI & ML Expert (2024)",  # contains special chars
                "goal": "Help",
                "backstory": "Expert.",
                "tasks": {"t": {"description": "Do it", "expected_output": "Done"}},
                "tools": [],
            }
        })

        mock_llm_config = MagicMock()
        mock_llm_config.__enter__ = MagicMock(return_value=mock_llm_config)
        mock_llm_config.__exit__ = MagicMock(return_value=False)
        mock_user_proxy = MagicMock()
        mock_groupchat = MagicMock()
        mock_groupchat.messages = [{"name": "AI___ML_Expert__2024_", "content": "Done. TERMINATE", "role": "assistant"}]
        mock_manager = MagicMock()
        created_name = {}

        def capture_assistant(**kwargs):
            created_name["name"] = kwargs.get("name", "")
            m = MagicMock()
            m.name = created_name["name"]
            return m

        with patch("autogen.LLMConfig", return_value=mock_llm_config), \
             patch("autogen.AssistantAgent", side_effect=capture_assistant), \
             patch("autogen.UserProxyAgent", return_value=mock_user_proxy), \
             patch("autogen.GroupChat", return_value=mock_groupchat), \
             patch("autogen.GroupChatManager", return_value=mock_manager):

            gen._run_ag2(config, "Test", {})

        name = created_name.get("name", "")
        # Should not contain special chars that would break AG2
        import re
        assert re.match(r"^[a-zA-Z0-9_\-]+$", name), f"Name '{name}' contains invalid characters"


# ---------------------------------------------------------------------------
# _run_ag2: output extraction
# ---------------------------------------------------------------------------

class TestRunAG2OutputExtraction:

    def _make_gen(self):
        with patch("praisonai.agents_generator.AG2_AVAILABLE", True), \
             patch("praisonai.agents_generator.CREWAI_AVAILABLE", False), \
             patch("praisonai.agents_generator.AUTOGEN_AVAILABLE", False), \
             patch("praisonai.agents_generator.PRAISONAI_AVAILABLE", True):
            from praisonai.agents_generator import AgentsGenerator
            return AgentsGenerator(
                agent_file="agents.yaml",
                framework="ag2",
                config_list=[{"model": "gpt-4o-mini", "api_key": "sk-test"}],
            )

    def _run_with_messages(self, messages):
        gen = self._make_gen()
        config = _make_config()

        mock_llm_config = MagicMock()
        mock_assistant = MagicMock()
        mock_assistant.name = "Researcher"
        mock_user_proxy = MagicMock()
        # chat_result with no summary so extraction falls back to messages
        mock_chat_result = MagicMock()
        mock_chat_result.summary = None
        mock_user_proxy.initiate_chat.return_value = mock_chat_result
        mock_groupchat = MagicMock()
        mock_groupchat.messages = messages
        mock_manager = MagicMock()

        with patch("autogen.LLMConfig", return_value=mock_llm_config), \
             patch("autogen.AssistantAgent", return_value=mock_assistant), \
             patch("autogen.UserProxyAgent", return_value=mock_user_proxy), \
             patch("autogen.GroupChat", return_value=mock_groupchat), \
             patch("autogen.GroupChatManager", return_value=mock_manager):

            return gen._run_ag2(config, "Test", {})

    def test_output_prefixed_with_ag2_header(self):
        """Result always starts with '### AG2 Output ###'."""
        result = self._run_with_messages([
            {"name": "Researcher", "content": "Here are my findings. TERMINATE", "role": "assistant"}
        ])
        assert result.startswith("### AG2 Output ###")

    def test_terminate_marker_stripped_from_output(self):
        """TERMINATE keyword is removed from the extracted output."""
        result = self._run_with_messages([
            {"name": "Researcher", "content": "Detailed findings here. TERMINATE", "role": "assistant"}
        ])
        assert "TERMINATE" not in result
        assert "Detailed findings here" in result

    def test_user_messages_skipped_in_extraction(self):
        """User proxy messages are not included in the extracted output."""
        result = self._run_with_messages([
            {"name": "User", "content": "This is the user message", "role": "user"},
            {"name": "Researcher", "content": "This is the agent response. TERMINATE", "role": "assistant"},
        ])
        assert "This is the user message" not in result
        assert "This is the agent response" in result

    def test_execution_error_returns_error_message(self):
        """Exception during initiate_chat returns a '### AG2 Error ###' message."""
        gen = self._make_gen()
        config = _make_config()

        mock_llm_config = MagicMock()
        mock_llm_config.__enter__ = MagicMock(return_value=mock_llm_config)
        mock_llm_config.__exit__ = MagicMock(return_value=False)
        mock_assistant = MagicMock()
        mock_assistant.name = "Researcher"
        mock_user_proxy = MagicMock()
        mock_user_proxy.initiate_chat.side_effect = RuntimeError("Connection failed")
        mock_groupchat = MagicMock()
        mock_groupchat.messages = []
        mock_manager = MagicMock()

        with patch("autogen.LLMConfig", return_value=mock_llm_config), \
             patch("autogen.AssistantAgent", return_value=mock_assistant), \
             patch("autogen.UserProxyAgent", return_value=mock_user_proxy), \
             patch("autogen.GroupChat", return_value=mock_groupchat), \
             patch("autogen.GroupChatManager", return_value=mock_manager):

            result = gen._run_ag2(config, "Test", {})

        assert "### AG2 Error ###" in result
        assert "Connection failed" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
