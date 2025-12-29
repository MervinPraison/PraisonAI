#!/usr/bin/env python3
"""
Recipe Scheduler Example

This example demonstrates how to schedule recipes and agents
to run periodically with retry logic and cost budgeting.

Requirements:
    pip install praisonai praisonaiagents

Usage:
    python example_scheduler.py
"""

import time
import signal
import sys


def main():
    """Run a scheduled agent."""
    
    print("=" * 60)
    print("Recipe Scheduler Example")
    print("=" * 60)
    
    from praisonaiagents import Agent
    from praisonai.scheduler import AgentScheduler
    
    # Create an agent
    agent = Agent(
        name="News Monitor",
        instructions="You are a news monitoring assistant. Provide brief updates.",
        verbose=True
    )
    
    # Create scheduler
    scheduler = AgentScheduler(
        agent=agent,
        task="What is the latest news in AI? Give a one-sentence summary.",
        timeout=60,
        max_cost=0.10  # $0.10 budget limit
    )
    
    print("\n1. Starting scheduler...")
    print("   Interval: every 30 seconds (for demo)")
    print("   Max retries: 3")
    print("   Timeout: 60s")
    print("   Budget: $0.10")
    
    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\n\n2. Stopping scheduler...")
        scheduler.stop()
        
        # Show stats
        stats = scheduler.get_stats()
        print("\n3. Final Statistics:")
        print(f"   Total Executions: {stats['total_executions']}")
        print(f"   Successful: {stats['successful_executions']}")
        print(f"   Failed: {stats['failed_executions']}")
        print(f"   Success Rate: {stats['success_rate']:.1f}%")
        
        print("\n" + "=" * 60)
        print("Example completed!")
        print("=" * 60)
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Start scheduler with short interval for demo
    scheduler.start(
        schedule_expr="*/30s",  # Every 30 seconds for demo
        max_retries=3,
        run_immediately=True
    )
    
    print("\n   Press Ctrl+C to stop...\n")
    
    # Keep running
    while scheduler.is_running:
        time.sleep(1)


if __name__ == "__main__":
    main()
