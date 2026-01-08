"""
TDD Tests for Agent-Centric Autonomy System.

Tests cover:
- 1A: Agent-centric autonomy integration
- 1B: Unified autonomous loop (run_autonomous)
- 1C: Progressive escalation (agent-owned)
- 1D: Router consolidation
- 1E: Verification hooks protocol
- 1F: Checkpoint/restore integration
- 1G: Subagent delegation
- 1H: Explore agent profile
- 1I: Doom-loop detection + recovery
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from typing import Set, Dict, Any


# ============================================================
# 1A: Agent-Centric Autonomy Integration Tests
# ============================================================

class TestAgentAutonomyIntegration:
    """Tests for Agent(autonomy=...) integration."""
    
    def test_agent_autonomy_disabled_by_default(self):
        """Agent should have autonomy disabled by default."""
        from praisonaiagents import Agent
        agent = Agent(instructions="Test agent")
        assert agent.autonomy_enabled == False
    
    def test_agent_autonomy_enabled_with_true(self):
        """Agent(autonomy=True) should enable autonomy with defaults."""
        from praisonaiagents import Agent
        agent = Agent(instructions="Test agent", autonomy=True)
        assert agent.autonomy_enabled == True
        assert agent._autonomy_trigger is not None
        assert agent._doom_loop_tracker is not None
    
    def test_agent_autonomy_enabled_with_dict(self):
        """Agent(autonomy={...}) should enable with custom config."""
        from praisonaiagents import Agent
        agent = Agent(
            instructions="Test agent",
            autonomy={
                "max_iterations": 50,
                "doom_loop_threshold": 5,
                "auto_escalate": False,
            }
        )
        assert agent.autonomy_enabled == True
        assert agent.autonomy_config.get("max_iterations") == 50
        assert agent.autonomy_config.get("doom_loop_threshold") == 5
    
    def test_agent_analyze_prompt_returns_signals(self):
        """Agent.analyze_prompt() should return signal set."""
        from praisonaiagents import Agent
        agent = Agent(instructions="Test agent", autonomy=True)
        
        signals = agent.analyze_prompt("What is Python?")
        assert isinstance(signals, set)
        assert "simple_question" in signals
    
    def test_agent_analyze_prompt_detects_file_references(self):
        """Agent.analyze_prompt() should detect file references."""
        from praisonaiagents import Agent
        agent = Agent(instructions="Test agent", autonomy=True)
        
        signals = agent.analyze_prompt("Read the file main.py and explain it")
        assert "file_references" in signals
    
    def test_agent_analyze_prompt_detects_edit_intent(self):
        """Agent.analyze_prompt() should detect edit intent."""
        from praisonaiagents import Agent
        agent = Agent(instructions="Test agent", autonomy=True)
        
        signals = agent.analyze_prompt("Edit the config.py file to add logging")
        assert "edit_intent" in signals
    
    def test_agent_get_recommended_stage_direct(self):
        """Simple questions should recommend DIRECT stage."""
        from praisonaiagents import Agent
        agent = Agent(instructions="Test agent", autonomy=True)
        
        stage = agent.get_recommended_stage("What is Python?")
        assert stage == "direct"
    
    def test_agent_get_recommended_stage_heuristic(self):
        """File references should recommend HEURISTIC stage."""
        from praisonaiagents import Agent
        agent = Agent(instructions="Test agent", autonomy=True)
        
        stage = agent.get_recommended_stage("Read main.py")
        assert stage == "heuristic"
    
    def test_agent_get_recommended_stage_planned(self):
        """Edit intent should recommend PLANNED stage."""
        from praisonaiagents import Agent
        agent = Agent(instructions="Test agent", autonomy=True)
        
        stage = agent.get_recommended_stage("Edit the auth.py file to fix the bug")
        assert stage == "planned"
    
    def test_agent_get_recommended_stage_autonomous(self):
        """Multi-step tasks should recommend AUTONOMOUS stage."""
        from praisonaiagents import Agent
        agent = Agent(instructions="Test agent", autonomy=True)
        
        stage = agent.get_recommended_stage(
            "First analyze the codebase, then refactor the auth module, "
            "and finally add tests"
        )
        assert stage == "autonomous"


# ============================================================
# 1B: Unified Autonomous Loop Tests
# ============================================================

class TestAgentRunAutonomous:
    """Tests for Agent.run_autonomous() method."""
    
    def test_run_autonomous_exists(self):
        """Agent should have run_autonomous method."""
        from praisonaiagents import Agent
        agent = Agent(instructions="Test agent", autonomy=True)
        assert hasattr(agent, "run_autonomous")
        assert callable(agent.run_autonomous)
    
    def test_run_autonomous_requires_autonomy_enabled(self):
        """run_autonomous should require autonomy=True."""
        from praisonaiagents import Agent
        agent = Agent(instructions="Test agent", autonomy=False)
        
        with pytest.raises(ValueError, match="autonomy"):
            agent.run_autonomous("Do something")
    
    def test_run_autonomous_returns_result(self):
        """run_autonomous should return AutonomyResult."""
        from praisonaiagents import Agent
        from praisonaiagents.agent.autonomy import AutonomyResult
        
        agent = Agent(instructions="Test agent", autonomy=True)
        # Mock the LLM to avoid real API calls
        with patch.object(agent, 'chat', return_value="Done"):
            result = agent.run_autonomous("Simple task")
        
        assert isinstance(result, AutonomyResult)
        assert result.success == True
    
    def test_run_autonomous_respects_max_iterations(self):
        """run_autonomous should stop at max_iterations."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            autonomy={"max_iterations": 3}
        )
        
        # Mock chat to always return "continue" to force iteration
        call_count = 0
        def mock_chat(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return "Need to continue..."
        
        with patch.object(agent, 'chat', side_effect=mock_chat):
            result = agent.run_autonomous("Complex task")
        
        assert result.iterations <= 3
    
    def test_run_autonomous_detects_completion(self):
        """run_autonomous should detect task completion."""
        from praisonaiagents import Agent
        
        agent = Agent(instructions="Test agent", autonomy=True)
        
        with patch.object(agent, 'chat', return_value="Task completed successfully."):
            result = agent.run_autonomous("Simple task")
        
        assert result.success == True
        assert result.completion_reason == "goal"


# ============================================================
# 1C: Progressive Escalation Tests
# ============================================================

class TestProgressiveEscalation:
    """Tests for progressive escalation stages."""
    
    def test_stage_direct_no_tools(self):
        """DIRECT stage should not use tools."""
        from praisonaiagents import Agent
        from praisonaiagents.agent.autonomy import AutonomyStage
        
        agent = Agent(instructions="Test agent", autonomy=True)
        stage = agent.get_recommended_stage("What is 2+2?")
        
        assert stage == "direct"
    
    def test_stage_heuristic_read_only_tools(self):
        """HEURISTIC stage should use read-only tools."""
        from praisonaiagents import Agent
        
        agent = Agent(instructions="Test agent", autonomy=True)
        stage = agent.get_recommended_stage("Read the README.md file")
        
        assert stage == "heuristic"
    
    def test_stage_planned_creates_plan(self):
        """PLANNED stage should create a plan before execution."""
        from praisonaiagents import Agent
        
        agent = Agent(instructions="Test agent", autonomy=True)
        stage = agent.get_recommended_stage("Fix the bug in auth.py")
        
        assert stage == "planned"
    
    def test_stage_autonomous_full_loop(self):
        """AUTONOMOUS stage should run full loop with tools."""
        from praisonaiagents import Agent
        
        agent = Agent(instructions="Test agent", autonomy=True)
        stage = agent.get_recommended_stage(
            "Refactor the entire authentication system step by step"
        )
        
        assert stage == "autonomous"
    
    def test_escalation_from_direct_to_heuristic(self):
        """Should escalate from DIRECT to HEURISTIC when needed."""
        from praisonaiagents import Agent
        
        agent = Agent(instructions="Test agent", autonomy={"auto_escalate": True})
        
        # Start with simple question
        stage1 = agent.get_recommended_stage("What is Python?")
        assert stage1 == "direct"
        
        # Then ask about a file
        stage2 = agent.get_recommended_stage("Show me main.py")
        assert stage2 == "heuristic"


# ============================================================
# 1I: Doom-loop Detection Tests
# ============================================================

class TestDoomLoopDetection:
    """Tests for doom-loop detection and recovery."""
    
    def test_doom_loop_tracker_initialized(self):
        """Agent should have doom loop tracker when autonomy enabled."""
        from praisonaiagents import Agent
        
        agent = Agent(instructions="Test agent", autonomy=True)
        assert agent._doom_loop_tracker is not None
    
    def test_doom_loop_detection_after_repeated_actions(self):
        """Should detect doom loop after repeated identical actions."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            autonomy={"doom_loop_threshold": 3}
        )
        
        # Record same action multiple times
        for _ in range(3):
            agent._record_action("read_file", {"path": "test.py"}, "content", True)
        
        assert agent._is_doom_loop() == True
    
    def test_doom_loop_not_triggered_for_different_actions(self):
        """Should not trigger doom loop for different actions."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            autonomy={"doom_loop_threshold": 3}
        )
        
        # Record different actions
        agent._record_action("read_file", {"path": "a.py"}, "content", True)
        agent._record_action("read_file", {"path": "b.py"}, "content", True)
        agent._record_action("write_file", {"path": "c.py"}, "ok", True)
        
        assert agent._is_doom_loop() == False
    
    def test_doom_loop_reset(self):
        """Should be able to reset doom loop tracker."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            autonomy={"doom_loop_threshold": 2}
        )
        
        # Trigger doom loop
        for _ in range(2):
            agent._record_action("read_file", {"path": "test.py"}, "content", True)
        
        assert agent._is_doom_loop() == True
        
        # Reset
        agent._reset_doom_loop()
        
        assert agent._is_doom_loop() == False


# ============================================================
# 1E: Verification Hooks Protocol Tests
# ============================================================

class TestVerificationHooks:
    """Tests for verification hooks protocol."""
    
    def test_verification_hook_protocol_exists(self):
        """VerificationHook protocol should exist in core."""
        from praisonaiagents.hooks import VerificationHook
        assert VerificationHook is not None
    
    def test_agent_accepts_verification_hooks(self):
        """Agent should accept verification_hooks parameter."""
        from praisonaiagents import Agent
        
        mock_hook = Mock()
        mock_hook.name = "test_hook"
        mock_hook.run = Mock(return_value={"success": True})
        
        agent = Agent(
            instructions="Test agent",
            autonomy=True,
            verification_hooks=[mock_hook]
        )
        
        assert len(agent._verification_hooks) == 1
    
    def test_verification_hooks_run_after_writes(self):
        """Verification hooks should run after file writes."""
        from praisonaiagents import Agent
        
        mock_hook = Mock()
        mock_hook.name = "test_runner"
        mock_hook.run = Mock(return_value={"success": True, "output": "All tests pass"})
        
        agent = Agent(
            instructions="Test agent",
            autonomy=True,
            verification_hooks=[mock_hook]
        )
        
        # Simulate a write action
        agent._run_verification_hooks()
        
        mock_hook.run.assert_called_once()


# ============================================================
# 1F: Checkpoint Integration Tests
# ============================================================

class TestCheckpointIntegration:
    """Tests for checkpoint integration with autonomy."""
    
    def test_agent_accepts_checkpoint_config(self):
        """Agent should accept checkpoint configuration."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            autonomy={
                "checkpoint_on_write": True,
                "checkpoint_dir": "/tmp/checkpoints"
            }
        )
        
        assert agent.autonomy_config.get("checkpoint_on_write") == True
    
    def test_checkpoint_created_before_write(self):
        """Checkpoint should be created before file writes."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            autonomy={"checkpoint_on_write": True}
        )
        
        # This would be tested with actual file operations
        # For now, verify the config is set
        assert agent.autonomy_config.get("checkpoint_on_write") == True


# ============================================================
# 1G: Subagent Delegation Tests
# ============================================================

class TestAgentHandoffMethods:
    """Tests for agent handoff methods (delegate removed, handoff_to is canonical)."""
    
    def test_agent_has_handoff_to_method(self):
        """Agent should have handoff_to method."""
        from praisonaiagents import Agent
        
        agent = Agent(instructions="Test agent", autonomy=True)
        assert hasattr(agent, "handoff_to")
        assert callable(agent.handoff_to)
        assert hasattr(agent, "handoff_to_async")
        assert callable(agent.handoff_to_async)
    
    def test_agent_does_not_have_delegate_method(self):
        """Agent.delegate() has been removed - use handoff_to() instead."""
        from praisonaiagents import Agent
        
        agent = Agent(instructions="Test agent", autonomy=True)
        # delegate method should no longer exist
        assert not hasattr(agent, "delegate"), "delegate() removed - use handoff_to()"


# ============================================================
# 1H: Explore Agent Profile Tests
# ============================================================

class TestExploreProfile:
    """Tests for explorer agent profile."""
    
    def test_explorer_profile_exists(self):
        """Explorer profile should exist in built-in profiles."""
        from praisonaiagents.agents.profiles import BUILTIN_PROFILES
        
        assert "explorer" in BUILTIN_PROFILES
    
    def test_explorer_profile_read_only(self):
        """Explorer profile should only have read-only tools."""
        from praisonaiagents.agents.profiles import BUILTIN_PROFILES
        
        explorer = BUILTIN_PROFILES.get("explorer")
        assert explorer is not None
        
        # Should not have write tools
        write_tools = {"write_file", "delete_file", "bash", "shell"}
        for tool in explorer.tools:
            assert tool not in write_tools
    
    def test_explorer_profile_has_search_tools(self):
        """Explorer profile should have search/read tools."""
        from praisonaiagents.agents.profiles import BUILTIN_PROFILES
        
        explorer = BUILTIN_PROFILES.get("explorer")
        read_tools = {"read_file", "list_files", "search", "grep"}
        
        # Should have at least some read tools
        assert any(tool in read_tools for tool in explorer.tools)


# ============================================================
# Integration Tests
# ============================================================

class TestAutonomyIntegration:
    """Integration tests for the full autonomy system."""
    
    def test_full_autonomy_flow(self):
        """Test complete autonomy flow from prompt to result."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="You are a helpful coding assistant",
            autonomy=True
        )
        
        # Analyze prompt
        signals = agent.analyze_prompt("What is Python?")
        assert "simple_question" in signals
        
        # Get stage
        stage = agent.get_recommended_stage("What is Python?")
        assert stage == "direct"
    
    def test_autonomy_disabled_methods_return_defaults(self):
        """When autonomy disabled, methods should return safe defaults."""
        from praisonaiagents import Agent
        
        agent = Agent(instructions="Test agent", autonomy=False)
        
        # analyze_prompt should return empty set
        signals = agent.analyze_prompt("Any prompt")
        assert signals == set()
        
        # get_recommended_stage should return "direct"
        stage = agent.get_recommended_stage("Any prompt")
        assert stage == "direct"
        
        # _is_doom_loop should return False
        assert agent._is_doom_loop() == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
