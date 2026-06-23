"""Tests for Agent integration with runtime capability system."""

from praisonaiagents.agent.agent import Agent
from praisonaiagents.config.feature_configs import RuntimeConfig


def test_agent_runtime_integration():
    """Test Agent constructor with runtime parameter."""
    agent = Agent(instructions="Test agent")
    assert agent._runtime_config is None

    agent = Agent(instructions="Test agent", runtime=True)
    assert agent._runtime_config is not None
    assert agent._runtime_config.required_capabilities is None

    agent = Agent(instructions="Test agent", runtime="native")
    assert agent._runtime_config is not None
    assert agent._runtime_config.preferred_runtime == "native"

    agent = Agent(
        instructions="Test agent",
        runtime={
            "required_capabilities": ["tool_loop", "basic_chat"],
            "preferred_runtime": "native",
        },
    )
    assert agent._runtime_config is not None
    assert "tool_loop" in agent._runtime_config.required_capabilities
    assert "basic_chat" in agent._runtime_config.required_capabilities

    config = RuntimeConfig(
        required_capabilities=["native_hooks", "streaming_deltas"],
        preferred_runtime="native",
    )
    agent = Agent(instructions="Test agent", runtime=config)
    assert agent._runtime_config is config

    config_no_validation = RuntimeConfig(
        required_capabilities=["native_hooks"],
        validate_on_creation=False,
    )
    agent = Agent(instructions="Test agent", runtime=config_no_validation)
    assert agent._runtime_config.validate_on_creation is False
