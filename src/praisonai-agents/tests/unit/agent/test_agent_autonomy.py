"""
Tests for Agent-centric autonomy features.

These tests verify that escalation, doom loop detection, and observability
are properly integrated into the Agent class as agent-centric capabilities.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass
from typing import Optional


class TestAgentAutonomyConfig:
    """Test Agent autonomy configuration."""
    
    def test_agent_accepts_autonomy_parameter(self):
        """Agent should accept autonomy parameter."""
        from praisonaiagents import Agent
        
        # Should not raise
        agent = Agent(
            instructions="Test agent",
            autonomy=True,
            output="silent"
        )
        assert agent.autonomy_enabled == True
    
    def test_agent_autonomy_default_false(self):
        """Agent autonomy should default to False for backward compatibility."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            output="silent"
        )
        assert agent.autonomy_enabled == False
    
    def test_agent_autonomy_with_config_dict(self):
        """Agent should accept autonomy as a config dict."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            autonomy={
                "max_iterations": 10,
                "doom_loop_threshold": 3,
                "auto_escalate": True
            },
            output="silent"
        )
        assert agent.autonomy_enabled == True
        assert agent.autonomy_config.get("max_iterations") == 10
    
    def test_agent_autonomy_false_disables(self):
        """Agent autonomy=False should disable autonomy features."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            autonomy=False,
            output="silent"
        )
        assert agent.autonomy_enabled == False


class TestAgentAutonomyConfig:
    """Test AutonomyConfig dataclass."""
    
    def test_autonomy_config_creation(self):
        """AutonomyConfig should be creatable with defaults."""
        from praisonaiagents.agent.autonomy import AutonomyConfig
        
        config = AutonomyConfig()
        assert config.enabled == True
        assert config.max_iterations == 20
        assert config.doom_loop_threshold == 3
        assert config.auto_escalate == True
    
    def test_autonomy_config_custom_values(self):
        """AutonomyConfig should accept custom values."""
        from praisonaiagents.agent.autonomy import AutonomyConfig
        
        config = AutonomyConfig(
            enabled=True,
            max_iterations=50,
            doom_loop_threshold=5,
            auto_escalate=False
        )
        assert config.max_iterations == 50
        assert config.doom_loop_threshold == 5
        assert config.auto_escalate == False


class TestAgentSignalDetection:
    """Test Agent signal detection for autonomy."""
    
    def test_agent_analyze_simple_prompt(self):
        """Agent should detect simple prompts."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            autonomy=True,
            output="silent"
        )
        
        signals = agent.analyze_prompt("What is Python?")
        assert "simple_question" in signals
    
    def test_agent_analyze_complex_prompt(self):
        """Agent should detect complex prompts."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            autonomy=True,
            output="silent"
        )
        
        signals = agent.analyze_prompt("Refactor the authentication module and add comprehensive tests")
        assert "refactor_intent" in signals or "edit_intent" in signals
    
    def test_agent_analyze_file_references(self):
        """Agent should detect file references."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            autonomy=True,
            output="silent"
        )
        
        signals = agent.analyze_prompt("Read the file src/main.py and explain it")
        assert "file_references" in signals


class TestAgentDoomLoopDetection:
    """Test Agent doom loop detection."""
    
    def test_agent_detects_doom_loop(self):
        """Agent should detect doom loops when autonomy enabled."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            autonomy=True,
            output="silent"
        )
        
        # Simulate repeated identical actions
        for _ in range(4):
            agent._record_action("read_file", {"path": "test.py"}, "content", True)
        
        assert agent._is_doom_loop() == True
    
    def test_agent_no_doom_loop_without_autonomy(self):
        """Agent should not track doom loops when autonomy disabled."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            autonomy=False,
            output="silent"
        )
        
        # Should not have doom loop tracking
        assert not hasattr(agent, '_doom_loop_detector') or agent._doom_loop_detector is None


class TestAgentAutonomyStages:
    """Test Agent autonomy stage recommendations."""
    
    def test_agent_recommends_direct_stage(self):
        """Agent should recommend DIRECT stage for simple questions."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            autonomy=True,
            output="silent"
        )
        
        stage = agent.get_recommended_stage("What is 2+2?")
        assert stage == "direct"
    
    def test_agent_recommends_autonomous_stage(self):
        """Agent should recommend AUTONOMOUS stage for complex tasks."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            autonomy=True,
            output="silent"
        )
        
        stage = agent.get_recommended_stage(
            "First analyze the codebase, then refactor the auth module, "
            "add tests, and finally update the documentation"
        )
        assert stage in ["planned", "autonomous"]


class TestAgentAutonomyIntegration:
    """Test Agent autonomy integration with chat/run."""
    
    def test_agent_chat_uses_autonomy_when_enabled(self):
        """Agent.chat should use autonomy features when enabled."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="You are a helpful assistant. Be brief.",
            autonomy=True,
            output="silent"
        )
        
        # The agent should have autonomy internals initialized
        assert agent.autonomy_enabled == True
        assert hasattr(agent, '_autonomy_trigger')
    
    def test_agent_chat_skips_autonomy_when_disabled(self):
        """Agent.chat should skip autonomy when disabled."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="You are a helpful assistant.",
            autonomy=False,
            output="silent"
        )
        
        assert agent.autonomy_enabled == False
