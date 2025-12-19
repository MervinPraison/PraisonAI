"""
End-to-End Tests for CLI Features with Real API Keys.

These tests require actual API keys to be set in environment variables:
- OPENAI_API_KEY
- ANTHROPIC_API_KEY (optional)
- GEMINI_API_KEY (optional)

Run with: pytest tests/e2e/test_cli_features_e2e.py -v --tb=short
"""

import pytest
import os
import time
from unittest.mock import patch

# Skip all tests if no API key is available
pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)


class TestSlashCommandsE2E:
    """End-to-end tests for slash commands."""
    
    def test_slash_command_handler_initialization(self):
        """Test that slash command handler initializes correctly."""
        from praisonai.cli.features import SlashCommandHandler
        
        handler = SlashCommandHandler(verbose=True)
        assert handler.registry is not None
        assert len(handler.registry.get_all()) > 0
    
    def test_help_command_execution(self):
        """Test /help command execution."""
        from praisonai.cli.features import SlashCommandHandler
        
        handler = SlashCommandHandler()
        
        with patch('rich.console.Console.print'):
            result = handler.execute("/help")
        
        assert result is not None
        assert result["type"] == "help"
    
    def test_cost_command_with_context(self):
        """Test /cost command with session context."""
        from praisonai.cli.features.slash_commands import (
            SlashCommandHandler,
            CommandContext
        )
        
        handler = SlashCommandHandler()
        ctx = CommandContext(
            total_tokens=5000,
            total_cost=0.015,
            prompt_count=10,
            session_start_time=time.time() - 300
        )
        handler.set_context(ctx)
        
        with patch('rich.console.Console.print'):
            result = handler.execute("/cost")
        
        assert result["type"] == "stats"
        assert result["tokens"] == 5000
        assert result["cost"] == 0.015
    
    def test_command_completions(self):
        """Test command auto-completion."""
        from praisonai.cli.features import SlashCommandHandler
        
        handler = SlashCommandHandler()
        
        completions = handler.get_completions("/he")
        assert "/help" in completions
        
        completions = handler.get_completions("/mo")
        assert "/model" in completions


class TestAutonomyModeE2E:
    """End-to-end tests for autonomy modes."""
    
    def test_autonomy_mode_initialization(self):
        """Test autonomy mode handler initialization."""
        from praisonai.cli.features import AutonomyModeHandler
        
        handler = AutonomyModeHandler(verbose=True)
        manager = handler.initialize(mode="suggest")
        
        assert manager is not None
        assert handler.get_mode() == "suggest"
    
    def test_mode_transitions(self):
        """Test transitioning between autonomy modes."""
        from praisonai.cli.features import AutonomyModeHandler
        
        handler = AutonomyModeHandler()
        handler.initialize(mode="suggest")
        
        # Test all mode transitions
        for mode in ["suggest", "auto_edit", "full_auto"]:
            handler.set_mode(mode)
            assert handler.get_mode() == mode
    
    def test_approval_flow_suggest_mode(self):
        """Test approval flow in suggest mode."""
        from praisonai.cli.features.autonomy_mode import (
            AutonomyModeHandler,
            ActionRequest,
            ActionType,
            ApprovalResult
        )
        
        # Mock approval callback
        def mock_approval(action):
            return ApprovalResult(approved=True)
        
        handler = AutonomyModeHandler()
        handler.initialize(mode="suggest", approval_callback=mock_approval)
        
        # File read should be auto-approved
        read_action = ActionRequest(ActionType.FILE_READ, "Read file")
        result = handler.request_approval(read_action)
        assert result.approved is True
        
        # File write should require approval (via callback)
        write_action = ActionRequest(ActionType.FILE_WRITE, "Write file")
        result = handler.request_approval(write_action)
        assert result.approved is True
    
    def test_full_auto_mode(self):
        """Test full auto mode approves everything."""
        from praisonai.cli.features.autonomy_mode import (
            AutonomyModeHandler,
            ActionRequest,
            ActionType
        )
        
        handler = AutonomyModeHandler()
        handler.initialize(mode="full_auto")
        
        # All actions should be auto-approved
        actions = [
            ActionRequest(ActionType.FILE_WRITE, "Write"),
            ActionRequest(ActionType.SHELL_COMMAND, "Command"),
            ActionRequest(ActionType.FILE_DELETE, "Delete"),
        ]
        
        for action in actions:
            result = handler.request_approval(action)
            assert result.approved is True


class TestCostTrackerE2E:
    """End-to-end tests for cost tracking."""
    
    def test_cost_tracker_initialization(self):
        """Test cost tracker initialization."""
        from praisonai.cli.features import CostTrackerHandler
        
        handler = CostTrackerHandler(verbose=True)
        tracker = handler.initialize(session_id="e2e-test")
        
        assert tracker is not None
        assert tracker.session_id == "e2e-test"
    
    def test_track_multiple_requests(self):
        """Test tracking multiple requests."""
        from praisonai.cli.features import CostTrackerHandler
        
        handler = CostTrackerHandler()
        handler.initialize()
        
        # Track several requests
        models = ["gpt-4o", "gpt-4o-mini", "gpt-4o"]
        for i, model in enumerate(models):
            handler.track_request(
                model=model,
                input_tokens=1000 * (i + 1),
                output_tokens=500 * (i + 1)
            )
        
        assert handler.get_tokens() == 9000  # (1500 + 3000 + 4500)
        assert handler.get_cost() > 0
    
    def test_cost_calculation_accuracy(self):
        """Test cost calculation is accurate."""
        from praisonai.cli.features.cost_tracker import CostTracker
        
        tracker = CostTracker()
        
        # gpt-4o: $2.50/1M input, $10.00/1M output
        stats = tracker.track_request(
            model="gpt-4o",
            input_tokens=100_000,
            output_tokens=50_000
        )
        
        # Expected: (100K/1M * 2.50) + (50K/1M * 10.00) = 0.25 + 0.50 = 0.75
        assert abs(stats.cost - 0.75) < 0.01
    
    def test_session_export(self):
        """Test session data export."""
        from praisonai.cli.features.cost_tracker import CostTracker
        import json
        
        tracker = CostTracker(session_id="export-test")
        tracker.track_request("gpt-4o", 1000, 500)
        tracker.track_request("gpt-4o-mini", 2000, 1000)
        
        json_str = tracker.export_json()
        data = json.loads(json_str)
        
        assert data["session"]["session_id"] == "export-test"
        assert len(data["requests"]) == 2


class TestIntegratedFeaturesE2E:
    """End-to-end tests for integrated features."""
    
    def test_all_features_together(self):
        """Test all features working together."""
        from praisonai.cli.features import (
            SlashCommandHandler,
            AutonomyModeHandler,
            CostTrackerHandler
        )
        from praisonai.cli.features.slash_commands import CommandContext
        from praisonai.cli.features.autonomy_mode import (
            ActionRequest,
            ActionType,
        )
        
        # Initialize all handlers
        slash_handler = SlashCommandHandler()
        autonomy_handler = AutonomyModeHandler()
        cost_handler = CostTrackerHandler()
        
        # Set up autonomy mode
        autonomy_handler.initialize(mode="auto_edit")
        
        # Initialize cost tracking
        cost_handler.initialize(session_id="integrated-test")
        
        # Track some requests
        cost_handler.track_request("gpt-4o", 1000, 500)
        cost_handler.track_request("gpt-4o", 2000, 1000)
        
        # Set up slash command context with cost data
        ctx = CommandContext(
            total_tokens=cost_handler.get_tokens(),
            total_cost=cost_handler.get_cost(),
            prompt_count=2
        )
        slash_handler.set_context(ctx)
        
        # Execute cost command
        with patch('rich.console.Console.print'):
            result = slash_handler.execute("/cost")
        
        assert result["tokens"] == 4500
        assert result["cost"] > 0
        
        # Test autonomy mode
        write_action = ActionRequest(ActionType.FILE_WRITE, "Write file")
        approval = autonomy_handler.request_approval(write_action)
        assert approval.approved is True  # Auto-approved in auto_edit mode


class TestRealAPIIntegration:
    """Tests that use real API calls."""
    
    @pytest.mark.skipif(
        not os.environ.get("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY required for this test"
    )
    def test_cost_tracking_with_real_agent(self):
        """Test cost tracking with a real agent call."""
        from praisonai.cli.features import CostTrackerHandler
        
        handler = CostTrackerHandler()
        handler.initialize()
        
        # Simulate what would happen after an agent call
        # In real usage, this would be called after agent.start()
        handler.track_request(
            model="gpt-4o-mini",
            input_tokens=150,
            output_tokens=50,
            duration_ms=500.0
        )
        
        summary = handler.get_summary()
        
        assert summary["total_requests"] == 1
        assert summary["total_tokens"] == 200
        assert summary["total_cost"] > 0
        
        # Print summary for verification
        print("\nCost tracking test:")
        print(f"  Tokens: {summary['total_tokens']}")
        print(f"  Cost: ${summary['total_cost']:.6f}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
