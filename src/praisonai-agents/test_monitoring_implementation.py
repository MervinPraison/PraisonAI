#!/usr/bin/env python3
"""
Test script for the comprehensive monitoring system implementation.

Tests all the features requested in issue #970:
1. TokenMetrics - Granular token tracking
2. PerformanceMetrics - TTFT and response time tracking  
3. MetricsCollector - Session-level aggregation
4. Agent integration - metrics tracking parameters
5. Enhanced telemetry - token and performance tracking
"""

import os
import time
import tempfile
import json
from pathlib import Path

# Set environment variable to disable telemetry for testing
os.environ['PRAISONAI_TELEMETRY_DISABLED'] = 'true'

# Import the classes to test
from praisonaiagents.telemetry.metrics import TokenMetrics, PerformanceMetrics, MetricsCollector
from praisonaiagents.telemetry import get_telemetry
from praisonaiagents.agent import Agent

# Mock CompletionUsage for testing
class MockCompletionUsage:
    def __init__(self):
        self.prompt_tokens = 100
        self.completion_tokens = 50
        self.total_tokens = 150
        self.prompt_tokens_details = MockPromptTokensDetails()
        self.completion_tokens_details = MockCompletionTokensDetails()

class MockPromptTokensDetails:
    def __init__(self):
        self.audio_tokens = 10
        self.cached_tokens = 20

class MockCompletionTokensDetails:
    def __init__(self):
        self.audio_tokens = 5
        self.reasoning_tokens = 15

def test_token_metrics():
    """Test TokenMetrics functionality."""
    print("🧪 Testing TokenMetrics...")
    
    # Test basic creation
    metrics1 = TokenMetrics(input_tokens=100, output_tokens=50, audio_tokens=10)
    metrics1.update_totals()
    assert metrics1.total_tokens == 150, f"Expected 150, got {metrics1.total_tokens}"
    
    # Test aggregation
    metrics2 = TokenMetrics(input_tokens=200, output_tokens=75, cached_tokens=30)
    combined = metrics1 + metrics2
    assert combined.input_tokens == 300, f"Expected 300, got {combined.input_tokens}"
    assert combined.output_tokens == 125, f"Expected 125, got {combined.output_tokens}"
    assert combined.cached_tokens == 30, f"Expected 30, got {combined.cached_tokens}"
    
    # Test from_completion_usage
    mock_usage = MockCompletionUsage()
    metrics3 = TokenMetrics.from_completion_usage(mock_usage)
    assert metrics3.input_tokens == 100, f"Expected 100, got {metrics3.input_tokens}"
    assert metrics3.output_tokens == 50, f"Expected 50, got {metrics3.output_tokens}"
    assert metrics3.cached_tokens == 20, f"Expected 20, got {metrics3.cached_tokens}"
    assert metrics3.reasoning_tokens == 15, f"Expected 15, got {metrics3.reasoning_tokens}"
    assert metrics3.audio_tokens == 15, f"Expected 15, got {metrics3.audio_tokens}"  # 10 + 5
    
    print("✅ TokenMetrics tests passed!")

def test_performance_metrics():
    """Test PerformanceMetrics functionality."""
    print("🧪 Testing PerformanceMetrics...")
    
    perf = PerformanceMetrics()
    
    # Test timing
    perf.start_timing()
    time.sleep(0.1)  # Simulate some processing
    perf.mark_first_token()
    time.sleep(0.05)  # Simulate additional processing
    perf.end_timing(100)  # 100 tokens generated
    
    assert perf.time_to_first_token > 0.09, f"TTFT too low: {perf.time_to_first_token}"
    assert perf.total_time > 0.14, f"Total time too low: {perf.total_time}"
    assert perf.tokens_per_second > 0, f"TPS should be > 0: {perf.tokens_per_second}"
    
    print(f"✅ PerformanceMetrics tests passed! TTFT: {perf.time_to_first_token:.3f}s, TPS: {perf.tokens_per_second:.1f}")

def test_metrics_collector():
    """Test MetricsCollector functionality."""
    print("🧪 Testing MetricsCollector...")
    
    collector = MetricsCollector()
    
    # Add metrics for different agents
    metrics1 = TokenMetrics(input_tokens=100, output_tokens=50, total_tokens=150)
    perf1 = PerformanceMetrics()
    perf1.time_to_first_token = 0.5
    perf1.total_time = 2.0
    perf1.tokens_per_second = 25.0
    
    collector.add_agent_metrics("Agent1", metrics1, perf1, "gpt-4o")
    
    # Add more metrics for same agent
    metrics2 = TokenMetrics(input_tokens=200, output_tokens=100, total_tokens=300)
    collector.add_agent_metrics("Agent1", metrics2, model_name="gpt-4o")
    
    # Add metrics for different agent
    metrics3 = TokenMetrics(input_tokens=50, output_tokens=25, total_tokens=75)
    collector.add_agent_metrics("Agent2", metrics3, model_name="claude-3")
    
    # Test session metrics
    session_metrics = collector.get_session_metrics()
    
    assert "Agent1" in session_metrics["by_agent"], "Agent1 not found in session metrics"
    assert "Agent2" in session_metrics["by_agent"], "Agent2 not found in session metrics"
    assert session_metrics["by_agent"]["Agent1"]["input_tokens"] == 300, "Agent1 input tokens incorrect"
    assert session_metrics["total_tokens"]["total_tokens"] == 525, "Total tokens incorrect"
    
    # Test export functionality
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_path = f.name
    
    try:
        collector.export_metrics(temp_path)
        
        # Verify exported data
        with open(temp_path, 'r') as f:
            exported_data = json.load(f)
        
        assert "session_id" in exported_data, "Session ID not in exported data"
        assert "by_agent" in exported_data, "by_agent not in exported data"
        assert exported_data["total_tokens"]["total_tokens"] == 525, "Exported total tokens incorrect"
        
    finally:
        os.unlink(temp_path)
    
    print("✅ MetricsCollector tests passed!")

def test_agent_integration():
    """Test Agent integration with metrics tracking."""
    print("🧪 Testing Agent metrics integration...")
    
    # Test Agent creation with metrics tracking
    collector = MetricsCollector()
    agent = Agent(
        name="TestAgent",
        instructions="You are a test agent",
        track_metrics=True,
        metrics_collector=collector
    )
    
    assert agent.track_metrics == True, "track_metrics not set correctly"
    assert agent.metrics_collector == collector, "metrics_collector not set correctly"
    assert hasattr(agent, 'last_metrics'), "last_metrics attribute missing"
    
    # Test Agent with auto-created collector
    agent2 = Agent(
        name="TestAgent2", 
        instructions="You are another test agent",
        track_metrics=True
    )
    
    assert agent2.track_metrics == True, "track_metrics not set correctly"
    assert agent2.metrics_collector is not None, "MetricsCollector not auto-created"
    
    # Test Agent without metrics tracking (default)
    agent3 = Agent(name="TestAgent3", instructions="You are a normal agent")
    assert agent3.track_metrics == False, "track_metrics should default to False"
    
    print("✅ Agent integration tests passed!")

def test_enhanced_telemetry():
    """Test enhanced telemetry functionality."""
    print("🧪 Testing enhanced telemetry...")
    
    # Get telemetry instance
    telemetry = get_telemetry()
    
    # Test token tracking
    token_metrics = TokenMetrics(
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        cached_tokens=20,
        reasoning_tokens=10,
        audio_tokens=5
    )
    
    # This should not raise any exceptions
    telemetry.track_tokens(token_metrics)
    
    # Test performance tracking
    perf_metrics = PerformanceMetrics()
    perf_metrics.time_to_first_token = 0.5
    perf_metrics.total_time = 2.0
    perf_metrics.tokens_per_second = 25.0
    
    # This should not raise any exceptions
    telemetry.track_performance(perf_metrics)
    
    print("✅ Enhanced telemetry tests passed!")

def test_backward_compatibility():
    """Test that existing functionality still works."""
    print("🧪 Testing backward compatibility...")
    
    # Test Agent creation without metrics (should work as before)
    agent = Agent(name="CompatibilityAgent", instructions="Test compatibility")
    
    assert hasattr(agent, 'name'), "Basic agent attributes missing"
    assert agent.name == "CompatibilityAgent", "Agent name not set correctly"
    assert agent.track_metrics == False, "Default metrics tracking should be False"
    
    # Test telemetry basic functions still work
    telemetry = get_telemetry()
    telemetry.track_agent_execution("test_agent", success=True)
    telemetry.track_task_completion("test_task", success=True)
    telemetry.track_tool_usage("test_tool", success=True)
    telemetry.track_error("test_error")
    telemetry.track_feature_usage("test_feature")
    
    print("✅ Backward compatibility tests passed!")

def main():
    """Run all tests."""
    print("🚀 Starting comprehensive monitoring system tests...")
    print("=" * 60)
    
    try:
        test_token_metrics()
        test_performance_metrics()
        test_metrics_collector()
        test_agent_integration()
        test_enhanced_telemetry()
        test_backward_compatibility()
        
        print("=" * 60)
        print("🎉 All tests passed! Monitoring system implementation is working correctly.")
        print()
        print("📊 Features implemented:")
        print("  ✅ TokenMetrics - Granular token tracking with aggregation")
        print("  ✅ PerformanceMetrics - TTFT and response time measurement")
        print("  ✅ MetricsCollector - Session-level aggregation and export")
        print("  ✅ Agent Integration - Optional track_metrics and metrics_collector")
        print("  ✅ Enhanced Telemetry - Token and performance tracking methods")
        print("  ✅ Backward Compatibility - All existing functionality preserved")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        raise

if __name__ == "__main__":
    main()