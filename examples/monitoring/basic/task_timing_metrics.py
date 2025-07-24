#!/usr/bin/env python3
"""
Task Performance Timing and Metrics Example

This example shows how to monitor individual task performance,
measure execution times, and track detailed metrics for specific operations.
"""

import sys
import os
import time
from datetime import datetime

# Add the praisonai-agents module to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src', 'praisonai-agents'))

from praisonaiagents.agent import Agent
from praisonaiagents.telemetry.metrics import TokenMetrics, PerformanceMetrics, MetricsCollector

class TaskTimer:
    """Helper class to time task execution and collect metrics."""
    
    def __init__(self, task_name: str):
        self.task_name = task_name
        self.start_time = None
        self.end_time = None
        self.performance_metrics = PerformanceMetrics()
    
    def __enter__(self):
        """Context manager entry - start timing."""
        self.start_time = time.time()
        self.performance_metrics.start_timing()
        print(f"⏱️  Starting task: {self.task_name}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - end timing."""
        self.end_time = time.time()
        elapsed = self.end_time - self.start_time
        
        # Simulate token count for demo (in real usage, this comes from agent response)
        simulated_tokens = 50
        self.performance_metrics.end_timing(simulated_tokens)
        
        print(f"✅ Task completed: {self.task_name}")
        print(f"   Duration: {elapsed:.3f}s")
        print(f"   Estimated speed: {simulated_tokens/elapsed:.1f} tokens/sec")
        return False  # Don't suppress exceptions

def demonstrate_manual_metrics():
    """Demonstrate manual performance metrics creation and tracking."""
    
    print("🔧 Manual Performance Metrics Creation")
    print("-" * 40)
    
    # Create performance metrics manually
    perf_metrics = PerformanceMetrics()
    
    # Start timing
    perf_metrics.start_timing()
    print("⏱️  Started timing...")
    
    # Simulate some work
    time.sleep(0.2)
    
    # Mark first token (simulated)
    perf_metrics.mark_first_token()
    print("🎯 First token received (simulated)")
    
    # Continue work
    time.sleep(0.3)
    
    # End timing with token count
    token_count = 75
    perf_metrics.end_timing(token_count)
    
    print(f"✅ Timing complete:")
    print(f"   Time to First Token: {perf_metrics.time_to_first_token:.3f}s")
    print(f"   Total Time: {perf_metrics.total_time:.3f}s")  
    print(f"   Tokens per Second: {perf_metrics.tokens_per_second:.1f}")
    
    return perf_metrics

def demonstrate_token_metrics():
    """Demonstrate token metrics creation and aggregation."""
    
    print("\n💰 Token Metrics Demonstration")
    print("-" * 40)
    
    # Create individual token metrics
    task1_tokens = TokenMetrics(
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        cached_tokens=20,
        reasoning_tokens=10
    )
    
    task2_tokens = TokenMetrics(
        input_tokens=80,
        output_tokens=60,
        total_tokens=140,
        cached_tokens=15,
        reasoning_tokens=5
    )
    
    print("Task 1 Tokens:")
    print(f"  Input: {task1_tokens.input_tokens}, Output: {task1_tokens.output_tokens}")
    print(f"  Cached: {task1_tokens.cached_tokens}, Reasoning: {task1_tokens.reasoning_tokens}")
    
    print("Task 2 Tokens:")
    print(f"  Input: {task2_tokens.input_tokens}, Output: {task2_tokens.output_tokens}")
    print(f"  Cached: {task2_tokens.cached_tokens}, Reasoning: {task2_tokens.reasoning_tokens}")
    
    # Aggregate tokens
    total_tokens = task1_tokens + task2_tokens
    print("\nAggregated Tokens:")
    print(f"  Total Input: {total_tokens.input_tokens}")
    print(f"  Total Output: {total_tokens.output_tokens}")
    print(f"  Total Cached: {total_tokens.cached_tokens}")
    print(f"  Total Reasoning: {total_tokens.reasoning_tokens}")
    print(f"  Grand Total: {total_tokens.total_tokens}")
    
    return [task1_tokens, task2_tokens, total_tokens]

def main():
    """Main demonstration function."""
    
    print("🎯 Task Timing and Metrics Example")
    print("=" * 50)
    
    # Create agent with metrics tracking
    agent = Agent(
        name="TaskMonitor",
        role="Performance Monitor",
        goal="Monitor and analyze task performance",
        backstory="You specialize in performance analysis and optimization.",
        track_metrics=True
    )
    
    # Demonstrate different monitoring approaches
    tasks = [
        "Analyze quarterly sales data",
        "Generate marketing report", 
        "Review customer feedback"
    ]
    
    print("📋 Monitoring Task Execution")
    print("-" * 30)
    
    # Method 1: Using context manager for timing
    for i, task in enumerate(tasks, 1):
        with TaskTimer(f"Task {i}: {task}") as timer:
            # Simulate task execution
            time.sleep(0.1 + i * 0.1)  # Variable execution time
            
            # In real usage, you would call:
            # response = agent.chat(task)
            # metrics = agent.last_metrics
    
    print("\n" + "=" * 50)
    
    # Method 2: Manual metrics creation
    manual_metrics = demonstrate_manual_metrics()
    
    # Method 3: Token metrics demonstration
    token_metrics_list = demonstrate_token_metrics()
    
    # Method 4: Using MetricsCollector for aggregation
    print("\n📊 MetricsCollector Aggregation")
    print("-" * 40)
    
    collector = MetricsCollector()
    
    # Add metrics to collector
    for i, tokens in enumerate(token_metrics_list[:-1], 1):  # Exclude the aggregated one
        collector.add_agent_metrics(
            agent_name=f"Agent_{i}",
            token_metrics=tokens,
            performance_metrics=manual_metrics if i == 1 else None,
            model_name=f"gpt-4o-{i}"
        )
    
    # Get session metrics
    session_data = collector.get_session_metrics()
    
    print("Session Summary:")
    print(f"  Duration: {session_data['duration_seconds']:.1f}s")
    print(f"  Total Tokens: {session_data['total_tokens']['total_tokens']}")
    
    print("\nBy Agent:")
    for agent_name, metrics in session_data['by_agent'].items():
        print(f"  {agent_name}: {metrics['total_tokens']} total tokens")
    
    print("\nBy Model:")
    for model_name, metrics in session_data['by_model'].items():
        print(f"  {model_name}: {metrics['total_tokens']} total tokens")
    
    # Export metrics (optional)
    export_file = "/tmp/task_metrics_example.json"
    try:
        collector.export_metrics(export_file)
        print(f"\n💾 Metrics exported to: {export_file}")
    except Exception as e:
        print(f"\n⚠️  Export failed: {e}")
    
    print("\n✅ Task timing and metrics example complete!")
    print("\n💡 Key Monitoring Techniques:")
    print("• Use context managers for automatic timing")
    print("• Create PerformanceMetrics manually for custom timing")
    print("• Aggregate TokenMetrics using + operator")
    print("• Use MetricsCollector for session-level aggregation")
    print("• Export metrics to files for analysis")

if __name__ == "__main__":
    main()