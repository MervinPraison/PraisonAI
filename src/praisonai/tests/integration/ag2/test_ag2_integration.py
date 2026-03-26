"""
AG2 Mock Integration Tests — verifies PraisonAI correctly orchestrates AG2 agents.

Uses mocked AG2 responses — no real LLM API calls are made.
Fast: all tests should complete in < 1s each.

Run:
    pytest tests/integration/ag2/test_ag2_integration.py -v
"""

import pytest
import os
import sys
from unittest.mock import patch, MagicMock

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


@pytest.fixture
def multi_agent_yaml():
    return """
framework: ag2
topic: Explain why open-source AI matters
roles:
  researcher:
    role: "Research Analyst"
    goal: "Research and gather key facts"
    backstory: "Expert in technology research and trend analysis."
    tasks:
      research:
        description: "Research why open-source AI matters"
        expected_output: "Key facts and data points"
  writer:
    role: "Technical Writer"
    goal: "Write clear technical content"
    backstory: "Professional technical writer with 10 years experience."
    tasks:
      write:
        description: "Write a clear explanation of why open-source AI matters"
        expected_output: "A 200-word explanation"
"""


@pytest.fixture
def mock_ag2_classes():
    """Mock all AG2 classes used in _run_ag2."""
    mock_llm_config = MagicMock()
    mock_llm_config.__enter__ = MagicMock(return_value=mock_llm_config)
    mock_llm_config.__exit__ = MagicMock(return_value=False)

    mock_assistant = MagicMock()
    mock_assistant.name = "test_agent"

    mock_user_proxy = MagicMock()
    mock_user_proxy.name = "User"

    mock_groupchat = MagicMock()
    mock_groupchat.messages = [
        {
            "name": "test_agent",
            "role": "assistant",
            "content": "Task completed successfully. TERMINATE",
        }
    ]

    mock_manager = MagicMock()

    return {
        "llm_config": mock_llm_config,
        "assistant": mock_assistant,
        "user_proxy": mock_user_proxy,
        "groupchat": mock_groupchat,
        "manager": mock_manager,
    }


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
# Single-agent flow (mocked)
# ---------------------------------------------------------------------------

class TestAG2SingleAgentFlow:

    @pytest.mark.integration
    def test_single_agent_yaml_initialises_praisonai(self, single_agent_yaml, mock_ag2_classes):
        """PraisonAI initialises correctly with framework='ag2' from YAML."""
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(single_agent_yaml)
            yaml_path = f.name

        try:
            with patch("praisonai.agents_generator.AG2_AVAILABLE", True), \
                 patch("praisonai.agents_generator.PRAISONAI_AVAILABLE", True):
                try:
                    from praisonai import PraisonAI
                    ai = PraisonAI(agent_file=yaml_path, framework="ag2")
                    assert ai.framework == "ag2"
                except ImportError as e:
                    pytest.skip(f"PraisonAI not available: {e}")
        finally:
            os.unlink(yaml_path)

    @pytest.mark.integration
    def test_single_agent_run_returns_ag2_output(self, mock_ag2_classes):
        """_run_ag2 executes single-agent flow and returns '### AG2 Output ###'."""
        config = {
            "framework": "ag2",
            "topic": "Write a poem",
            "roles": {
                "poet": {
                    "role": "Creative Poet",
                    "goal": "Write poems",
                    "backstory": "A creative poet.",
                    "tasks": {
                        "task1": {
                            "description": "Write a poem about Python",
                            "expected_output": "A short poem",
                        }
                    },
                    "tools": [],
                }
            },
        }

        m = mock_ag2_classes
        with patch("praisonai.agents_generator.AG2_AVAILABLE", True), \
             patch("praisonai.agents_generator.CREWAI_AVAILABLE", False), \
             patch("praisonai.agents_generator.AUTOGEN_AVAILABLE", False), \
             patch("praisonai.agents_generator.PRAISONAI_AVAILABLE", True):
            try:
                from praisonai.agents_generator import AgentsGenerator
            except ImportError as e:
                pytest.skip(f"AgentsGenerator not available: {e}")

            gen = AgentsGenerator(
                agent_file="agents.yaml",
                framework="ag2",
                config_list=[{"model": "gpt-4o-mini", "api_key": "sk-test"}],
            )

            with patch("autogen.LLMConfig", return_value=m["llm_config"]), \
                 patch("autogen.AssistantAgent", return_value=m["assistant"]), \
                 patch("autogen.UserProxyAgent", return_value=m["user_proxy"]), \
                 patch("autogen.GroupChat", return_value=m["groupchat"]), \
                 patch("autogen.GroupChatManager", return_value=m["manager"]):

                result = gen._run_ag2(config, "Write a poem", {})

        assert "### AG2 Output ###" in result
        assert "Task completed successfully" in result

    @pytest.mark.integration
    def test_single_agent_calls_initiate_chat(self, mock_ag2_classes):
        """user_proxy.initiate_chat is called with the manager and initial message."""
        config = {
            "framework": "ag2",
            "topic": "Test topic",
            "roles": {
                "agent": {
                    "role": "Agent",
                    "goal": "Help",
                    "backstory": "Helpful agent.",
                    "tasks": {
                        "t": {"description": "Do the task", "expected_output": "Done"}
                    },
                    "tools": [],
                }
            },
        }

        m = mock_ag2_classes
        with patch("praisonai.agents_generator.AG2_AVAILABLE", True), \
             patch("praisonai.agents_generator.CREWAI_AVAILABLE", False), \
             patch("praisonai.agents_generator.AUTOGEN_AVAILABLE", False), \
             patch("praisonai.agents_generator.PRAISONAI_AVAILABLE", True):
            try:
                from praisonai.agents_generator import AgentsGenerator
            except ImportError as e:
                pytest.skip(f"AgentsGenerator not available: {e}")

            gen = AgentsGenerator(
                agent_file="agents.yaml",
                framework="ag2",
                config_list=[{"model": "gpt-4o-mini", "api_key": "sk-test"}],
            )

            with patch("autogen.LLMConfig", return_value=m["llm_config"]), \
                 patch("autogen.AssistantAgent", return_value=m["assistant"]), \
                 patch("autogen.UserProxyAgent", return_value=m["user_proxy"]), \
                 patch("autogen.GroupChat", return_value=m["groupchat"]), \
                 patch("autogen.GroupChatManager", return_value=m["manager"]):

                gen._run_ag2(config, "Test topic", {})

        m["user_proxy"].initiate_chat.assert_called_once()
        call_args = m["user_proxy"].initiate_chat.call_args
        # First positional arg should be the manager
        assert call_args[0][0] is m["manager"]
        # message kwarg should be non-empty (task description or topic)
        message = call_args[1].get("message", "")
        assert message != ""


# ---------------------------------------------------------------------------
# Multi-agent GroupChat flow (mocked)
# ---------------------------------------------------------------------------

class TestAG2MultiAgentGroupChatFlow:

    @pytest.mark.integration
    def test_multi_agent_creates_correct_number_of_assistants(self, multi_agent_yaml, mock_ag2_classes):
        """Two roles in YAML → two AssistantAgents created."""
        config = {
            "framework": "ag2",
            "topic": "Explain open-source AI",
            "roles": {
                "researcher": {
                    "role": "Research Analyst", "goal": "Research", "backstory": "Analyst.",
                    "tasks": {"r": {"description": "Research it", "expected_output": "Facts"}},
                    "tools": [],
                },
                "writer": {
                    "role": "Technical Writer", "goal": "Write", "backstory": "Writer.",
                    "tasks": {"w": {"description": "Write it", "expected_output": "Article"}},
                    "tools": [],
                },
            },
        }

        m = mock_ag2_classes
        assistant_call_count = [0]

        def count_assistant(**kwargs):
            assistant_call_count[0] += 1
            a = MagicMock()
            a.name = kwargs.get("name", f"agent_{assistant_call_count[0]}")
            return a

        with patch("praisonai.agents_generator.AG2_AVAILABLE", True), \
             patch("praisonai.agents_generator.CREWAI_AVAILABLE", False), \
             patch("praisonai.agents_generator.AUTOGEN_AVAILABLE", False), \
             patch("praisonai.agents_generator.PRAISONAI_AVAILABLE", True):
            try:
                from praisonai.agents_generator import AgentsGenerator
            except ImportError as e:
                pytest.skip(f"AgentsGenerator not available: {e}")

            gen = AgentsGenerator(
                agent_file="agents.yaml",
                framework="ag2",
                config_list=[{"model": "gpt-4o-mini", "api_key": "sk-test"}],
            )

            with patch("autogen.LLMConfig", return_value=m["llm_config"]), \
                 patch("autogen.AssistantAgent", side_effect=count_assistant), \
                 patch("autogen.UserProxyAgent", return_value=m["user_proxy"]), \
                 patch("autogen.GroupChat", return_value=m["groupchat"]), \
                 patch("autogen.GroupChatManager", return_value=m["manager"]):

                gen._run_ag2(config, "Explain open-source AI", {})

        assert assistant_call_count[0] == 2

    @pytest.mark.integration
    def test_multi_agent_groupchat_max_round_set(self, mock_ag2_classes):
        """GroupChat is created with max_round parameter."""
        config = {
            "framework": "ag2",
            "topic": "Test",
            "roles": {
                "a": {
                    "role": "Agent", "goal": "Help", "backstory": "Helper.",
                    "tasks": {"t": {"description": "Do", "expected_output": "Done"}},
                    "tools": [],
                }
            },
        }

        m = mock_ag2_classes
        groupchat_kwargs = {}

        def capture_groupchat(**kwargs):
            groupchat_kwargs.update(kwargs)
            return m["groupchat"]

        with patch("praisonai.agents_generator.AG2_AVAILABLE", True), \
             patch("praisonai.agents_generator.CREWAI_AVAILABLE", False), \
             patch("praisonai.agents_generator.AUTOGEN_AVAILABLE", False), \
             patch("praisonai.agents_generator.PRAISONAI_AVAILABLE", True):
            try:
                from praisonai.agents_generator import AgentsGenerator
            except ImportError as e:
                pytest.skip(f"AgentsGenerator not available: {e}")

            gen = AgentsGenerator(
                agent_file="agents.yaml",
                framework="ag2",
                config_list=[{"model": "gpt-4o-mini", "api_key": "sk-test"}],
            )

            with patch("autogen.LLMConfig", return_value=m["llm_config"]), \
                 patch("autogen.AssistantAgent", return_value=m["assistant"]), \
                 patch("autogen.UserProxyAgent", return_value=m["user_proxy"]), \
                 patch("autogen.GroupChat", side_effect=capture_groupchat), \
                 patch("autogen.GroupChatManager", return_value=m["manager"]):

                gen._run_ag2(config, "Test", {})

        assert "max_round" in groupchat_kwargs
        assert groupchat_kwargs["max_round"] > 0


# ---------------------------------------------------------------------------
# Backward-compatibility: existing autogen/crewai paths unaffected
# ---------------------------------------------------------------------------

class TestAG2BackwardCompatibility:

    @pytest.mark.integration
    def test_autogen_framework_still_works(self):
        """framework='autogen' dispatches to _run_autogen, not _run_ag2."""
        import yaml

        with patch("praisonai.agents_generator.AUTOGEN_AVAILABLE", True), \
             patch("praisonai.agents_generator.AG2_AVAILABLE", False), \
             patch("praisonai.agents_generator.CREWAI_AVAILABLE", False), \
             patch("praisonai.agents_generator.PRAISONAI_AVAILABLE", True):
            try:
                from praisonai.agents_generator import AgentsGenerator
            except ImportError as e:
                pytest.skip(f"AgentsGenerator not available: {e}")

            gen = AgentsGenerator(
                agent_file="agents.yaml",
                framework="autogen",
                config_list=[{"model": "gpt-4o-mini", "api_key": "sk-test"}],
            )
            assert gen.framework == "autogen"

            gen.agent_yaml = yaml.dump({
                "framework": "autogen",
                "topic": "Test",
                "roles": {
                    "agent": {
                        "role": "Agent", "goal": "Help", "backstory": "Helper.",
                        "tasks": {"t": {"description": "Do", "expected_output": "Done"}},
                        "tools": [],
                    }
                },
            })

            # Verify _run_ag2 is NOT called when framework='autogen'
            with patch.object(gen, "_run_ag2") as mock_run_ag2, \
                 patch.object(gen, "_run_autogen", return_value="autogen result") as mock_run_autogen:
                gen.generate_crew_and_kickoff()

        mock_run_ag2.assert_not_called()
        mock_run_autogen.assert_called_once()

    @pytest.mark.integration
    def test_ag2_framework_dispatches_to_run_ag2(self, mock_ag2_classes):
        """framework='ag2' dispatches to _run_ag2 and NOT to _run_autogen."""
        import yaml

        m = mock_ag2_classes
        with patch("praisonai.agents_generator.AG2_AVAILABLE", True), \
             patch("praisonai.agents_generator.CREWAI_AVAILABLE", False), \
             patch("praisonai.agents_generator.AUTOGEN_AVAILABLE", False), \
             patch("praisonai.agents_generator.PRAISONAI_AVAILABLE", True):
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

            with patch.object(gen, "_run_autogen") as mock_autogen, \
                 patch("autogen.LLMConfig", return_value=m["llm_config"]), \
                 patch("autogen.AssistantAgent", return_value=m["assistant"]), \
                 patch("autogen.UserProxyAgent", return_value=m["user_proxy"]), \
                 patch("autogen.GroupChat", return_value=m["groupchat"]), \
                 patch("autogen.GroupChatManager", return_value=m["manager"]):

                result = gen.generate_crew_and_kickoff()

        mock_autogen.assert_not_called()
        assert "### AG2 Output ###" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
