"""
Tests for Cost Tracking System.

Test-Driven Development approach for cost and token tracking.
"""

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timedelta
import json

from praisonai.cli.features.cost_tracker import (
    ModelPricing,
    TokenUsage,
    RequestStats,
    SessionStats,
    CostTracker,
    CostTrackerHandler,
    get_pricing,
    DEFAULT_PRICING,
)


# ============================================================================
# ModelPricing Tests
# ============================================================================

class TestModelPricing:
    """Tests for ModelPricing dataclass."""
    
    def test_create_pricing(self):
        """Test creating model pricing."""
        pricing = ModelPricing(
            model_name="gpt-4o",
            input_price_per_1m=2.50,
            output_price_per_1m=10.00
        )
        assert pricing.model_name == "gpt-4o"
        assert pricing.input_price_per_1m == 2.50
        assert pricing.output_price_per_1m == 10.00
        assert pricing.context_window == 128000
    
    def test_calculate_cost(self):
        """Test cost calculation."""
        pricing = ModelPricing(
            model_name="test",
            input_price_per_1m=1.00,
            output_price_per_1m=2.00
        )
        
        # 1000 input tokens, 500 output tokens
        cost = pricing.calculate_cost(1000, 500)
        
        # Expected: (1000/1M * 1.00) + (500/1M * 2.00) = 0.001 + 0.001 = 0.002
        assert cost == pytest.approx(0.002, rel=1e-6)
    
    def test_calculate_cost_large_tokens(self):
        """Test cost calculation with large token counts."""
        pricing = ModelPricing(
            model_name="test",
            input_price_per_1m=2.50,
            output_price_per_1m=10.00
        )
        
        # 100K input, 50K output
        cost = pricing.calculate_cost(100_000, 50_000)
        
        # Expected: (100K/1M * 2.50) + (50K/1M * 10.00) = 0.25 + 0.50 = 0.75
        assert cost == pytest.approx(0.75, rel=1e-6)


# ============================================================================
# get_pricing Tests
# ============================================================================

class TestGetPricing:
    """Tests for get_pricing function."""
    
    def test_get_exact_match(self):
        """Test getting pricing with exact model name."""
        pricing = get_pricing("gpt-4o")
        assert pricing.model_name == "gpt-4o"
    
    def test_get_partial_match(self):
        """Test getting pricing with partial model name."""
        pricing = get_pricing("gpt-4o-2024-08-06")
        assert "gpt-4o" in pricing.model_name.lower() or pricing == DEFAULT_PRICING["default"]
    
    def test_get_unknown_model(self):
        """Test getting pricing for unknown model returns default."""
        pricing = get_pricing("unknown-model-xyz")
        assert pricing == DEFAULT_PRICING["default"]
    
    def test_default_pricing_exists(self):
        """Test that default pricing models exist."""
        assert "gpt-4o" in DEFAULT_PRICING
        assert "gpt-4o-mini" in DEFAULT_PRICING
        assert "claude-3-5-sonnet" in DEFAULT_PRICING
        assert "gemini-2.0-flash" in DEFAULT_PRICING
        assert "default" in DEFAULT_PRICING


# ============================================================================
# TokenUsage Tests
# ============================================================================

class TestTokenUsage:
    """Tests for TokenUsage dataclass."""
    
    def test_create_usage(self):
        """Test creating token usage."""
        usage = TokenUsage(
            input_tokens=100,
            output_tokens=50
        )
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.total_tokens == 150
        assert usage.cached_tokens == 0
    
    def test_usage_with_cached(self):
        """Test usage with cached tokens."""
        usage = TokenUsage(
            input_tokens=100,
            output_tokens=50,
            cached_tokens=30
        )
        assert usage.cached_tokens == 30
    
    def test_total_tokens_auto_calculated(self):
        """Test total tokens is auto-calculated."""
        usage = TokenUsage(input_tokens=200, output_tokens=100)
        assert usage.total_tokens == 300
    
    def test_total_tokens_explicit(self):
        """Test explicit total tokens is preserved."""
        usage = TokenUsage(
            input_tokens=100,
            output_tokens=50,
            total_tokens=200  # Explicit value
        )
        assert usage.total_tokens == 200


# ============================================================================
# RequestStats Tests
# ============================================================================

class TestRequestStats:
    """Tests for RequestStats dataclass."""
    
    def test_create_request_stats(self):
        """Test creating request stats."""
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        stats = RequestStats(
            timestamp=datetime.now(),
            model="gpt-4o",
            usage=usage,
            cost=0.001
        )
        assert stats.model == "gpt-4o"
        assert stats.usage.total_tokens == 150
        assert stats.cost == 0.001
    
    def test_to_dict(self):
        """Test converting to dictionary."""
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        stats = RequestStats(
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            model="gpt-4o",
            usage=usage,
            cost=0.001,
            duration_ms=500.0
        )
        
        data = stats.to_dict()
        
        assert data["model"] == "gpt-4o"
        assert data["input_tokens"] == 100
        assert data["output_tokens"] == 50
        assert data["cost"] == 0.001
        assert data["duration_ms"] == 500.0
        assert "timestamp" in data


# ============================================================================
# SessionStats Tests
# ============================================================================

class TestSessionStats:
    """Tests for SessionStats dataclass."""
    
    def test_create_session_stats(self):
        """Test creating session stats."""
        stats = SessionStats(
            session_id="test-123",
            start_time=datetime.now()
        )
        assert stats.session_id == "test-123"
        assert stats.total_requests == 0
        assert stats.total_cost == 0.0
    
    def test_add_request(self):
        """Test adding request to session."""
        session = SessionStats(
            session_id="test",
            start_time=datetime.now()
        )
        
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        request = RequestStats(
            timestamp=datetime.now(),
            model="gpt-4o",
            usage=usage,
            cost=0.001
        )
        
        session.add_request(request)
        
        assert session.total_requests == 1
        assert session.total_input_tokens == 100
        assert session.total_output_tokens == 50
        assert session.total_tokens == 150
        assert session.total_cost == 0.001
        assert "gpt-4o" in session.models_used
    
    def test_add_multiple_requests(self):
        """Test adding multiple requests."""
        session = SessionStats(
            session_id="test",
            start_time=datetime.now()
        )
        
        for i in range(3):
            usage = TokenUsage(input_tokens=100, output_tokens=50)
            request = RequestStats(
                timestamp=datetime.now(),
                model="gpt-4o",
                usage=usage,
                cost=0.001
            )
            session.add_request(request)
        
        assert session.total_requests == 3
        assert session.total_tokens == 450
        assert session.total_cost == pytest.approx(0.003)
    
    def test_avg_tokens_per_request(self):
        """Test average tokens per request."""
        session = SessionStats(
            session_id="test",
            start_time=datetime.now()
        )
        
        for tokens in [100, 200, 300]:
            usage = TokenUsage(input_tokens=tokens, output_tokens=0)
            request = RequestStats(
                timestamp=datetime.now(),
                model="gpt-4o",
                usage=usage,
                cost=0.0
            )
            session.add_request(request)
        
        assert session.avg_tokens_per_request == 200.0
    
    def test_avg_cost_per_request(self):
        """Test average cost per request."""
        session = SessionStats(
            session_id="test",
            start_time=datetime.now()
        )
        
        for cost in [0.001, 0.002, 0.003]:
            usage = TokenUsage(input_tokens=100, output_tokens=50)
            request = RequestStats(
                timestamp=datetime.now(),
                model="gpt-4o",
                usage=usage,
                cost=cost
            )
            session.add_request(request)
        
        assert session.avg_cost_per_request == pytest.approx(0.002)
    
    def test_duration_seconds(self):
        """Test session duration calculation."""
        start = datetime.now() - timedelta(seconds=60)
        session = SessionStats(
            session_id="test",
            start_time=start
        )
        
        assert session.duration_seconds >= 60
    
    def test_to_dict(self):
        """Test converting to dictionary."""
        session = SessionStats(
            session_id="test-123",
            start_time=datetime(2024, 1, 1, 12, 0, 0)
        )
        
        data = session.to_dict()
        
        assert data["session_id"] == "test-123"
        assert data["total_requests"] == 0
        assert "start_time" in data


# ============================================================================
# CostTracker Tests
# ============================================================================

class TestCostTracker:
    """Tests for CostTracker."""
    
    def test_create_tracker(self):
        """Test creating cost tracker."""
        tracker = CostTracker()
        
        assert tracker.session_id is not None
        assert len(tracker.session_id) == 8
        assert tracker.session_stats is not None
    
    def test_create_tracker_with_session_id(self):
        """Test creating tracker with custom session ID."""
        tracker = CostTracker(session_id="custom-id")
        
        assert tracker.session_id == "custom-id"
    
    def test_track_request(self):
        """Test tracking a request."""
        tracker = CostTracker()
        
        stats = tracker.track_request(
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500
        )
        
        assert stats is not None
        assert stats.model == "gpt-4o"
        assert stats.usage.input_tokens == 1000
        assert stats.usage.output_tokens == 500
        assert stats.cost > 0
    
    def test_track_multiple_requests(self):
        """Test tracking multiple requests."""
        tracker = CostTracker()
        
        tracker.track_request("gpt-4o", 1000, 500)
        tracker.track_request("gpt-4o-mini", 2000, 1000)
        tracker.track_request("gpt-4o", 500, 250)
        
        assert tracker.get_request_count() == 3
        assert tracker.get_total_tokens() == 5250
        assert tracker.get_total_cost() > 0
    
    def test_track_with_cached_tokens(self):
        """Test tracking with cached tokens."""
        tracker = CostTracker()
        
        stats = tracker.track_request(
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            cached_tokens=200
        )
        
        assert stats.usage.cached_tokens == 200
        assert tracker.session_stats.total_cached_tokens == 200
    
    def test_track_with_duration(self):
        """Test tracking with duration."""
        tracker = CostTracker()
        
        stats = tracker.track_request(
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            duration_ms=1500.0
        )
        
        assert stats.duration_ms == 1500.0
    
    def test_get_current_stats(self):
        """Test getting current stats."""
        tracker = CostTracker()
        tracker.track_request("gpt-4o", 1000, 500)
        
        stats = tracker.get_current_stats()
        
        assert stats.total_requests == 1
        assert stats.total_tokens == 1500
    
    def test_format_summary(self):
        """Test formatting summary."""
        tracker = CostTracker(session_id="test-123")
        tracker.track_request("gpt-4o", 1000, 500)
        
        summary = tracker.format_summary()
        
        assert "test-123" in summary
        assert "Tokens:" in summary
        assert "Cost:" in summary
    
    def test_export_json(self):
        """Test exporting to JSON."""
        tracker = CostTracker(session_id="test-123")
        tracker.track_request("gpt-4o", 1000, 500)
        
        json_str = tracker.export_json()
        data = json.loads(json_str)
        
        assert "session" in data
        assert "requests" in data
        assert data["session"]["session_id"] == "test-123"
        assert len(data["requests"]) == 1
    
    def test_end_session(self):
        """Test ending session."""
        tracker = CostTracker()
        tracker.track_request("gpt-4o", 1000, 500)
        
        stats = tracker.end_session()
        
        assert stats.end_time is not None
    
    def test_models_used_tracking(self):
        """Test tracking of models used."""
        tracker = CostTracker()
        
        tracker.track_request("gpt-4o", 1000, 500)
        tracker.track_request("gpt-4o", 1000, 500)
        tracker.track_request("gpt-4o-mini", 1000, 500)
        
        stats = tracker.get_current_stats()
        
        assert stats.models_used["gpt-4o"] == 2
        assert stats.models_used["gpt-4o-mini"] == 1


# ============================================================================
# CostTracker Response Tracking Tests
# ============================================================================

class TestCostTrackerResponseTracking:
    """Tests for tracking from LLM responses."""
    
    def test_track_from_openai_response(self):
        """Test tracking from OpenAI-style response."""
        tracker = CostTracker()
        
        # Mock OpenAI response
        mock_response = MagicMock()
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.cached_tokens = 0
        
        stats = tracker.track_from_response("gpt-4o", mock_response)
        
        assert stats is not None
        assert stats.usage.input_tokens == 100
        assert stats.usage.output_tokens == 50
    
    def test_track_from_dict_response(self):
        """Test tracking from dict response."""
        tracker = CostTracker()
        
        response = {
            "usage": {
                "prompt_tokens": 200,
                "completion_tokens": 100
            }
        }
        
        stats = tracker.track_from_response("gpt-4o", response)
        
        assert stats is not None
        assert stats.usage.input_tokens == 200
        assert stats.usage.output_tokens == 100
    
    def test_track_from_invalid_response(self):
        """Test tracking from invalid response returns None."""
        tracker = CostTracker()
        
        stats = tracker.track_from_response("gpt-4o", "invalid response")
        
        assert stats is None


# ============================================================================
# CostTrackerHandler Tests
# ============================================================================

class TestCostTrackerHandler:
    """Tests for CostTrackerHandler."""
    
    def test_handler_creation(self):
        """Test handler creation."""
        handler = CostTrackerHandler()
        assert handler.feature_name == "cost_tracker"
    
    def test_initialize(self):
        """Test initializing tracker."""
        handler = CostTrackerHandler()
        tracker = handler.initialize()
        
        assert tracker is not None
        assert handler.get_tracker() is tracker
    
    def test_initialize_with_session_id(self):
        """Test initializing with session ID."""
        handler = CostTrackerHandler()
        tracker = handler.initialize(session_id="custom-123")
        
        assert tracker.session_id == "custom-123"
    
    def test_track_request(self):
        """Test tracking request through handler."""
        handler = CostTrackerHandler()
        
        stats = handler.track_request(
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500
        )
        
        assert stats is not None
        assert handler.get_cost() > 0
        assert handler.get_tokens() == 1500
    
    def test_get_summary(self):
        """Test getting summary."""
        handler = CostTrackerHandler()
        handler.track_request("gpt-4o", 1000, 500)
        
        summary = handler.get_summary()
        
        assert "total_requests" in summary
        assert summary["total_requests"] == 1
    
    def test_get_cost_before_init(self):
        """Test getting cost before initialization."""
        handler = CostTrackerHandler()
        
        assert handler.get_cost() == 0.0
    
    def test_get_tokens_before_init(self):
        """Test getting tokens before initialization."""
        handler = CostTrackerHandler()
        
        assert handler.get_tokens() == 0


# ============================================================================
# Integration Tests
# ============================================================================

class TestCostTrackerIntegration:
    """Integration tests for cost tracking."""
    
    def test_full_session_workflow(self):
        """Test full session workflow."""
        handler = CostTrackerHandler(verbose=False)
        handler.initialize(session_id="integration-test")
        
        # Simulate multiple requests
        models = ["gpt-4o", "gpt-4o-mini", "gpt-4o"]
        for i, model in enumerate(models):
            handler.track_request(
                model=model,
                input_tokens=1000 * (i + 1),
                output_tokens=500 * (i + 1),
                duration_ms=100.0 * (i + 1)
            )
        
        # Verify totals
        summary = handler.get_summary()
        
        assert summary["total_requests"] == 3
        assert summary["total_input_tokens"] == 6000  # 1000 + 2000 + 3000
        assert summary["total_output_tokens"] == 3000  # 500 + 1000 + 1500
        assert summary["total_tokens"] == 9000
        assert handler.get_cost() > 0
    
    def test_cost_calculation_accuracy(self):
        """Test cost calculation accuracy."""
        tracker = CostTracker()
        
        # Use known pricing
        # gpt-4o: $2.50/1M input, $10.00/1M output
        stats = tracker.track_request(
            model="gpt-4o",
            input_tokens=1_000_000,  # 1M tokens
            output_tokens=1_000_000   # 1M tokens
        )
        
        # Expected: $2.50 + $10.00 = $12.50
        assert stats.cost == pytest.approx(12.50, rel=0.01)
    
    def test_session_persistence(self):
        """Test session data can be exported and contains all info."""
        tracker = CostTracker(session_id="persist-test")
        
        tracker.track_request("gpt-4o", 1000, 500)
        tracker.track_request("gpt-4o-mini", 2000, 1000)
        
        json_str = tracker.export_json()
        data = json.loads(json_str)
        
        # Verify structure
        assert data["session"]["session_id"] == "persist-test"
        assert len(data["requests"]) == 2
        assert data["session"]["total_requests"] == 2
        
        # Verify request details preserved
        assert data["requests"][0]["model"] == "gpt-4o"
        assert data["requests"][1]["model"] == "gpt-4o-mini"
