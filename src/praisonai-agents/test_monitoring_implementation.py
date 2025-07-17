#!/usr/bin/env python3
"""
Test script for the new monitoring implementation.

This script tests the key features from issue #970:
- TokenMetrics with granular token tracking
- PerformanceMetrics with TTFT
- MetricsCollector for session-level aggregation
- Agent integration with track_metrics parameter
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

def test_token_metrics():
    """Test TokenMetrics functionality."""
    print("Testing TokenMetrics...")
    
    from praisonaiagents.metrics import TokenMetrics
    from praisonaiagents.llm.openai_client import CompletionUsage, CompletionTokensDetails, PromptTokensDetails
    
    # Test creating TokenMetrics from scratch
    metrics1 = TokenMetrics(
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        reasoning_tokens=10,
        cached_tokens=20
    )
    
    # Test aggregation
    metrics2 = TokenMetrics(
        input_tokens=200,
        output_tokens=75,
        total_tokens=275,
        reasoning_tokens=15,
        cached_tokens=5
    )
    
    total = metrics1 + metrics2
    assert total.input_tokens == 300
    assert total.output_tokens == 125
    assert total.total_tokens == 425
    assert total.reasoning_tokens == 25
    assert total.cached_tokens == 25
    
    # Test conversion from CompletionUsage
    usage = CompletionUsage(
        completion_tokens=50,
        prompt_tokens=100,
        total_tokens=150,
        completion_tokens_details=CompletionTokensDetails(reasoning_tokens=10),
        prompt_tokens_details=PromptTokensDetails(cached_tokens=20)
    )
    
    converted = TokenMetrics.from_completion_usage(usage, "gpt-4o")
    assert converted.input_tokens == 100
    assert converted.output_tokens == 50
    assert converted.reasoning_tokens == 10
    assert converted.cached_tokens == 20
    assert converted.model == "gpt-4o"
    
    print("✅ TokenMetrics tests passed")


def test_performance_metrics():
    """Test PerformanceMetrics functionality."""
    print("Testing PerformanceMetrics...")
    
    from praisonaiagents.metrics import PerformanceMetrics, create_performance_metrics
    import time
    
    # Test manual tracking
    metrics = PerformanceMetrics(model="gpt-4o", streaming=True)
    
    start = time.time()
    metrics.start_tracking()
    
    # Simulate first token after 100ms
    time.sleep(0.1)
    metrics.mark_first_token()
    
    # Simulate total completion after 200ms more
    time.sleep(0.2)
    metrics.end_tracking(token_count=50)
    
    assert metrics.time_to_first_token is not None
    assert 0.08 < metrics.time_to_first_token < 0.15  # Allow some tolerance
    assert 0.28 < metrics.total_time < 0.35
    assert metrics.tokens_per_second is not None
    assert metrics.tokens_per_second > 0
    
    # Test utility function
    now = time.time()
    util_metrics = create_performance_metrics(
        start_time=now - 0.5,
        first_token_time=now - 0.4,
        end_time=now,
        token_count=100,
        model="claude-3-sonnet",
        streaming=False
    )
    
    assert abs(util_metrics.time_to_first_token - 0.1) < 0.01
    assert abs(util_metrics.total_time - 0.5) < 0.01
    assert abs(util_metrics.tokens_per_second - 200) < 10
    
    print("✅ PerformanceMetrics tests passed")


def test_metrics_collector():
    """Test MetricsCollector functionality."""
    print("Testing MetricsCollector...")
    
    from praisonaiagents.metrics import MetricsCollector, TokenMetrics, PerformanceMetrics
    
    collector = MetricsCollector("test_session")
    
    # Add some metrics
    token_metrics1 = TokenMetrics(
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        model="gpt-4o"
    )
    perf_metrics1 = PerformanceMetrics(
        total_time=1.5,
        time_to_first_token=0.2,
        tokens_per_second=33.3,
        model="gpt-4o"
    )
    
    collector.track_request(token_metrics1, perf_metrics1, "agent1")
    
    # Add more metrics
    token_metrics2 = TokenMetrics(
        input_tokens=200,
        output_tokens=75,
        total_tokens=275,
        model="claude-3-sonnet"
    )
    perf_metrics2 = PerformanceMetrics(
        total_time=2.0,
        time_to_first_token=0.3,
        tokens_per_second=37.5,
        model="claude-3-sonnet"
    )
    
    collector.track_request(token_metrics2, perf_metrics2, "agent2")
    
    # Check session metrics
    session = collector.get_session_metrics()
    assert session.total_requests == 2
    assert session.total_tokens.total_tokens == 425
    assert abs(session.total_time - 3.5) < 0.01
    assert abs(session.average_response_time - 1.75) < 0.01
    
    # Check per-agent breakdown
    assert "agent1" in session.by_agent
    assert "agent2" in session.by_agent
    assert session.by_agent["agent1"].total_tokens == 150
    assert session.by_agent["agent2"].total_tokens == 275
    
    # Check per-model breakdown
    assert "gpt-4o" in session.by_model
    assert "claude-3-sonnet" in session.by_model
    
    print("✅ MetricsCollector tests passed")


def test_agent_integration():
    """Test Agent class integration with metrics."""
    print("Testing Agent integration...")
    
    # This test will be minimal since we don't want to make actual LLM calls
    from praisonaiagents.agent.agent import Agent
    from praisonaiagents.metrics import MetricsCollector
    
    # Test agent creation with metrics enabled
    collector = MetricsCollector("agent_test_session")
    agent = Agent(
        name="TestAgent",
        instructions="You are a test agent",
        track_metrics=True,
        metrics_collector=collector
    )
    
    assert agent.track_metrics == True
    assert agent.metrics_collector == collector
    assert agent.last_metrics is None
    
    # Test agent creation with auto-collector
    agent2 = Agent(
        name="TestAgent2",
        instructions="You are another test agent",
        track_metrics=True
    )
    
    assert agent2.track_metrics == True
    assert agent2.metrics_collector is not None
    assert isinstance(agent2.metrics_collector, MetricsCollector)
    
    # Test agent without metrics (default)
    agent3 = Agent(
        name="TestAgent3",
        instructions="You are a regular agent"
    )
    
    assert agent3.track_metrics == False
    assert agent3.metrics_collector is None
    
    print("✅ Agent integration tests passed")


def test_telemetry_integration():
    """Test enhanced telemetry integration."""
    print("Testing telemetry integration...")
    
    try:
        from praisonaiagents.telemetry import MinimalTelemetry
        from praisonaiagents.metrics import TokenMetrics, PerformanceMetrics
        
        # Create telemetry instance (disabled for testing)
        telemetry = MinimalTelemetry(enabled=False)
        
        # Test token tracking
        token_metrics = TokenMetrics(
            input_tokens=100,
            output_tokens=50,
            reasoning_tokens=10,
            model="gpt-4o"
        )
        
        # This should not crash even with disabled telemetry
        telemetry.track_tokens(token_metrics)
        
        # Test performance tracking
        perf_metrics = PerformanceMetrics(
            total_time=1.5,
            time_to_first_token=0.2,
            model="gpt-4o"
        )
        
        telemetry.track_performance(perf_metrics)
        
        print("✅ Telemetry integration tests passed")
        
    except ImportError:
        print("⚠️  Telemetry not available, skipping telemetry tests")


def test_backwards_compatibility():
    """Test that existing functionality still works."""
    print("Testing backwards compatibility...")
    
    # Test that Agent can be created without new parameters
    from praisonaiagents.agent.agent import Agent
    
    agent = Agent(
        name="BackwardsCompatAgent",
        role="Assistant",
        goal="Test backwards compatibility"
    )
    
    # Should have default values for new parameters
    assert agent.track_metrics == False
    assert agent.metrics_collector is None
    assert agent.last_metrics is None
    
    # Test that all existing parameters still work
    agent2 = Agent(
        name="FullySpecifiedAgent",
        role="Specialist",
        goal="Do specialized work",
        backstory="I am a specialist",
        llm="gpt-4o",
        verbose=True,
        max_iter=10,
        stream=True
    )
    
    assert agent2.name == "FullySpecifiedAgent"
    assert agent2.role == "Specialist"
    assert agent2.verbose == True
    assert agent2.max_iter == 10
    assert agent2.stream == True
    
    print("✅ Backwards compatibility tests passed")


def main():
    """Run all tests."""
    print("🚀 Running monitoring implementation tests...\n")
    
    try:
        test_token_metrics()
        test_performance_metrics()
        test_metrics_collector()
        test_agent_integration()
        test_telemetry_integration()
        test_backwards_compatibility()
        
        print("\n🎉 All tests passed! The monitoring implementation is working correctly.")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()