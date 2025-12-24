"""
Unit tests for the Thinking module.

Tests cover:
- ThinkingBudget creation and levels
- ThinkingConfig settings
- ThinkingUsage tracking
- ThinkingTracker aggregation
"""

import pytest

from praisonaiagents.thinking.budget import ThinkingBudget, BudgetLevel, BUDGET_TOKENS
from praisonaiagents.thinking.config import ThinkingConfig
from praisonaiagents.thinking.tracker import ThinkingUsage, ThinkingTracker


# =============================================================================
# ThinkingBudget Tests
# =============================================================================

class TestThinkingBudget:
    """Tests for ThinkingBudget class."""
    
    def test_budget_creation(self):
        """Test creating a budget."""
        budget = ThinkingBudget(max_tokens=10000)
        assert budget.max_tokens == 10000
        assert budget.adaptive
    
    def test_budget_from_level(self):
        """Test creating budget from level."""
        budget = ThinkingBudget.from_level(BudgetLevel.HIGH)
        assert budget.max_tokens == BUDGET_TOKENS[BudgetLevel.HIGH]
        assert budget.level == BudgetLevel.HIGH
    
    def test_budget_minimal(self):
        """Test minimal budget."""
        budget = ThinkingBudget.minimal()
        assert budget.max_tokens == 2000
    
    def test_budget_low(self):
        """Test low budget."""
        budget = ThinkingBudget.low()
        assert budget.max_tokens == 4000
    
    def test_budget_medium(self):
        """Test medium budget."""
        budget = ThinkingBudget.medium()
        assert budget.max_tokens == 8000
    
    def test_budget_high(self):
        """Test high budget."""
        budget = ThinkingBudget.high()
        assert budget.max_tokens == 16000
    
    def test_budget_maximum(self):
        """Test maximum budget."""
        budget = ThinkingBudget.maximum()
        assert budget.max_tokens == 32000
    
    def test_budget_complexity_scaling(self):
        """Test complexity-based token scaling."""
        budget = ThinkingBudget(
            max_tokens=10000,
            min_tokens=2000,
            adaptive=True
        )
        
        # Low complexity
        tokens_low = budget.get_tokens_for_complexity(0.0)
        assert tokens_low == 2000
        
        # High complexity
        tokens_high = budget.get_tokens_for_complexity(1.0)
        assert tokens_high == 10000
        
        # Medium complexity
        tokens_mid = budget.get_tokens_for_complexity(0.5)
        assert 2000 < tokens_mid < 10000
    
    def test_budget_non_adaptive(self):
        """Test non-adaptive budget."""
        budget = ThinkingBudget(
            max_tokens=10000,
            adaptive=False
        )
        
        # Should always return max_tokens
        assert budget.get_tokens_for_complexity(0.0) == 10000
        assert budget.get_tokens_for_complexity(1.0) == 10000
    
    def test_budget_to_dict(self):
        """Test budget serialization."""
        budget = ThinkingBudget(
            max_tokens=8000,
            max_time_seconds=60.0,
            adaptive=True
        )
        data = budget.to_dict()
        
        assert data["max_tokens"] == 8000
        assert data["max_time_seconds"] == 60.0
        assert data["adaptive"]
    
    def test_budget_from_dict(self):
        """Test budget deserialization."""
        data = {
            "max_tokens": 16000,
            "max_time_seconds": 120.0,
            "adaptive": False,
            "level": "high"
        }
        
        budget = ThinkingBudget.from_dict(data)
        
        assert budget.max_tokens == 16000
        assert budget.max_time_seconds == 120.0
        assert not budget.adaptive
        assert budget.level == BudgetLevel.HIGH


# =============================================================================
# ThinkingConfig Tests
# =============================================================================

class TestThinkingConfig:
    """Tests for ThinkingConfig class."""
    
    def test_config_defaults(self):
        """Test default configuration."""
        config = ThinkingConfig()
        
        assert config.enabled
        assert config.default_budget_tokens == 8000
        assert config.max_budget_tokens == 32000
        assert config.adaptive
    
    def test_config_custom(self):
        """Test custom configuration."""
        config = ThinkingConfig(
            enabled=False,
            default_budget_tokens=4000,
            adaptive=False
        )
        
        assert not config.enabled
        assert config.default_budget_tokens == 4000
        assert not config.adaptive


# =============================================================================
# ThinkingUsage Tests
# =============================================================================

class TestThinkingUsage:
    """Tests for ThinkingUsage class."""
    
    def test_usage_creation(self):
        """Test creating usage."""
        usage = ThinkingUsage(
            budget_tokens=8000,
            tokens_used=4000
        )
        
        assert usage.budget_tokens == 8000
        assert usage.tokens_used == 4000
    
    def test_usage_tokens_remaining(self):
        """Test tokens remaining calculation."""
        usage = ThinkingUsage(
            budget_tokens=8000,
            tokens_used=3000
        )
        
        assert usage.tokens_remaining == 5000
    
    def test_usage_tokens_remaining_over_budget(self):
        """Test tokens remaining when over budget."""
        usage = ThinkingUsage(
            budget_tokens=8000,
            tokens_used=10000
        )
        
        assert usage.tokens_remaining == 0
    
    def test_usage_time_remaining(self):
        """Test time remaining calculation."""
        usage = ThinkingUsage(
            budget_time=60.0,
            time_seconds=20.0
        )
        
        assert usage.time_remaining == 40.0
    
    def test_usage_time_remaining_no_budget(self):
        """Test time remaining with no budget."""
        usage = ThinkingUsage()
        
        assert usage.time_remaining is None
    
    def test_usage_token_utilization(self):
        """Test token utilization calculation."""
        usage = ThinkingUsage(
            budget_tokens=8000,
            tokens_used=4000
        )
        
        assert usage.token_utilization == 0.5
    
    def test_usage_is_over_budget(self):
        """Test over budget detection."""
        usage = ThinkingUsage(
            budget_tokens=8000,
            tokens_used=10000
        )
        
        assert usage.is_over_budget
    
    def test_usage_is_not_over_budget(self):
        """Test not over budget."""
        usage = ThinkingUsage(
            budget_tokens=8000,
            tokens_used=4000
        )
        
        assert not usage.is_over_budget
    
    def test_usage_is_over_time(self):
        """Test over time detection."""
        usage = ThinkingUsage(
            budget_time=60.0,
            time_seconds=90.0
        )
        
        assert usage.is_over_time
    
    def test_usage_to_dict(self):
        """Test usage serialization."""
        usage = ThinkingUsage(
            budget_tokens=8000,
            tokens_used=4000,
            time_seconds=30.0
        )
        data = usage.to_dict()
        
        assert data["budget_tokens"] == 8000
        assert data["tokens_used"] == 4000
        assert data["token_utilization"] == 0.5


# =============================================================================
# ThinkingTracker Tests
# =============================================================================

class TestThinkingTracker:
    """Tests for ThinkingTracker class."""
    
    @pytest.fixture
    def tracker(self):
        """Create a test tracker."""
        return ThinkingTracker()
    
    def test_tracker_creation(self, tracker):
        """Test creating a tracker."""
        assert tracker.session_count == 0
        assert tracker.total_tokens_used == 0
    
    def test_tracker_start_session(self, tracker):
        """Test starting a session."""
        usage = tracker.start_session(
            budget_tokens=8000,
            complexity=0.7
        )
        
        assert usage.budget_tokens == 8000
        assert usage.complexity == 0.7
        assert tracker.session_count == 1
    
    def test_tracker_end_session(self, tracker):
        """Test ending a session."""
        usage = tracker.start_session(budget_tokens=8000)
        tracker.end_session(usage, tokens_used=5000, time_seconds=30.0)
        
        assert usage.tokens_used == 5000
        assert usage.time_seconds == 30.0
        assert tracker.total_tokens_used == 5000
        assert tracker.total_time_seconds == 30.0
    
    def test_tracker_multiple_sessions(self, tracker):
        """Test multiple sessions."""
        usage1 = tracker.start_session(budget_tokens=8000)
        tracker.end_session(usage1, tokens_used=4000, time_seconds=20.0)
        
        usage2 = tracker.start_session(budget_tokens=8000)
        tracker.end_session(usage2, tokens_used=6000, time_seconds=40.0)
        
        assert tracker.session_count == 2
        assert tracker.total_tokens_used == 10000
        assert tracker.total_time_seconds == 60.0
    
    def test_tracker_average_tokens(self, tracker):
        """Test average tokens calculation."""
        usage1 = tracker.start_session(budget_tokens=8000)
        tracker.end_session(usage1, tokens_used=4000, time_seconds=20.0)
        
        usage2 = tracker.start_session(budget_tokens=8000)
        tracker.end_session(usage2, tokens_used=6000, time_seconds=40.0)
        
        assert tracker.average_tokens_per_session == 5000
    
    def test_tracker_average_time(self, tracker):
        """Test average time calculation."""
        usage1 = tracker.start_session(budget_tokens=8000)
        tracker.end_session(usage1, tokens_used=4000, time_seconds=20.0)
        
        usage2 = tracker.start_session(budget_tokens=8000)
        tracker.end_session(usage2, tokens_used=6000, time_seconds=40.0)
        
        assert tracker.average_time_per_session == 30.0
    
    def test_tracker_over_budget_count(self, tracker):
        """Test over budget counting."""
        usage1 = tracker.start_session(budget_tokens=8000)
        tracker.end_session(usage1, tokens_used=4000, time_seconds=20.0)
        
        usage2 = tracker.start_session(budget_tokens=8000)
        tracker.end_session(usage2, tokens_used=10000, time_seconds=40.0)
        
        assert tracker.over_budget_count == 1
    
    def test_tracker_get_summary(self, tracker):
        """Test summary generation."""
        usage = tracker.start_session(budget_tokens=8000)
        tracker.end_session(usage, tokens_used=4000, time_seconds=20.0)
        
        summary = tracker.get_summary()
        
        assert summary["session_count"] == 1
        assert summary["total_tokens_used"] == 4000
        assert "average_utilization" in summary
    
    def test_tracker_clear(self, tracker):
        """Test clearing tracker."""
        usage = tracker.start_session(budget_tokens=8000)
        tracker.end_session(usage, tokens_used=4000, time_seconds=20.0)
        
        tracker.clear()
        
        assert tracker.session_count == 0
        assert tracker.total_tokens_used == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
