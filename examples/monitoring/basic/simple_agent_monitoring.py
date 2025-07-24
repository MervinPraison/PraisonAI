#!/usr/bin/env python3
"""
Basic Agent Performance Monitoring Example

This example demonstrates the simplest way to monitor agent performance
including token usage and timing metrics without modifying existing code.
"""

import sys
import os
import time
from datetime import datetime

# Add the praisonai-agents module to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src', 'praisonai-agents'))

from praisonaiagents.agent import Agent
from praisonaiagents.telemetry.metrics import MetricsCollector

def main():
    """Demonstrate basic agent performance monitoring."""
    
    print("🚀 Basic Agent Performance Monitoring Example")
    print("=" * 50)
    
    # Create an agent with metrics tracking enabled
    agent = Agent(
        name="DataAnalyst",
        role="Data Analyst",
        goal="Analyze data and provide insights",
        backstory="You are an experienced data analyst who excels at finding patterns in data.",
        track_metrics=True  # Enable metrics tracking
    )
    
    print(f"✅ Agent created: {agent.name}")
    print(f"📊 Metrics tracking: {agent.track_metrics}")
    print(f"🗂️  Metrics collector: {type(agent.metrics_collector).__name__}")
    print()
    
    # Example tasks to monitor
    tasks = [
        "What are the key benefits of data visualization?",
        "Explain the difference between correlation and causation.",
        "How would you approach analyzing customer churn data?"
    ]
    
    print("🔍 Running monitored tasks...")
    print("-" * 30)
    
    # Execute tasks and monitor performance
    for i, task in enumerate(tasks, 1):
        print(f"\nTask {i}: {task[:50]}...")
        
        # Record start time
        start_time = time.time()
        
        # Execute the task (simulated - in real usage you'd call agent.chat())
        # For demo purposes, we'll simulate a response
        print("📝 Processing task... (simulated)")
        time.sleep(0.5)  # Simulate processing time
        
        # Get last metrics (would be populated after real agent.chat() call)
        if hasattr(agent, 'last_metrics') and agent.last_metrics:
            tokens = agent.last_metrics.get('tokens')
            performance = agent.last_metrics.get('performance')
            
            if tokens:
                print(f"🪙  Tokens - Input: {tokens.input_tokens}, Output: {tokens.output_tokens}, Total: {tokens.total_tokens}")
            
            if performance:
                print(f"⏱️  Performance - TTFT: {performance.time_to_first_token:.3f}s, Total: {performance.total_time:.3f}s")
                print(f"🚀 Speed: {performance.tokens_per_second:.1f} tokens/sec")
        else:
            # Simulate metrics for demo
            elapsed = time.time() - start_time
            print(f"⏱️  Elapsed time: {elapsed:.3f}s")
            print(f"📝 Task completed (simulated)")
    
    print("\n" + "=" * 50)
    
    # Display session-level metrics
    if agent.metrics_collector:
        session_metrics = agent.metrics_collector.get_session_metrics()
        
        print("📋 Session Summary:")
        print(f"🆔 Session ID: {session_metrics['session_id']}")
        print(f"⏰ Duration: {session_metrics['duration_seconds']:.1f} seconds")
        print(f"🪙  Total Tokens: {session_metrics['total_tokens']['total_tokens']}")
        
        # Display agent-specific metrics
        if session_metrics['by_agent']:
            print("\n📊 By Agent:")
            for agent_name, metrics in session_metrics['by_agent'].items():
                print(f"  {agent_name}:")
                print(f"    Input tokens: {metrics['input_tokens']}")
                print(f"    Output tokens: {metrics['output_tokens']}")
                print(f"    Total tokens: {metrics['total_tokens']}")
        
        # Display performance metrics
        if session_metrics['performance']:
            print("\n⚡ Performance Summary:")
            for agent_name, perf in session_metrics['performance'].items():
                print(f"  {agent_name}:")
                print(f"    Avg TTFT: {perf['average_ttft']:.3f}s")
                print(f"    Avg Total Time: {perf['average_total_time']:.3f}s")
                print(f"    Avg Speed: {perf['average_tokens_per_second']:.1f} tokens/sec")
                print(f"    Requests: {perf['request_count']}")
    
    print("\n✅ Basic monitoring example complete!")
    print("\n💡 Key Takeaways:")
    print("• Set track_metrics=True to enable monitoring")
    print("• MetricsCollector is auto-created when needed")
    print("• Access last execution metrics via agent.last_metrics")
    print("• Get session summary via metrics_collector.get_session_metrics()")

if __name__ == "__main__":
    main()