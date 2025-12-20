"""
24/7 News Checker Agent Example

This example demonstrates how to create a continuously running agent
that checks for AI news every hour and prints the results.

Usage:
    python news_checker_agent.py
    
The agent will:
1. Run immediately on start
2. Check for latest AI news every 1 hour
3. Print results to console
4. Continue running until stopped (Ctrl+C)
"""

import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from praisonaiagents import Agent
from praisonai.agent_scheduler import AgentScheduler
from tools import search_tool


def on_success(result):
    """Callback function called when agent execution succeeds."""
    print("\n" + "="*80)
    print(f"✅ SUCCESS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    print(result)
    print("="*80 + "\n")


def on_failure(error):
    """Callback function called when agent execution fails."""
    print("\n" + "="*80)
    print(f"❌ FAILURE - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    print(f"Error: {error}")
    print("="*80 + "\n")


def main():
    """Main function to set up and run the scheduled news checker agent."""
    
    print("\n🤖 Starting 24/7 News Checker Agent")
    print("="*80)
    
    # Create the agent with web search capability
    agent = Agent(
        name="NewsChecker",
        role="AI News Monitor",
        goal="Monitor and summarize the latest AI and technology news",
        backstory="""You are an expert AI news analyst who stays up-to-date 
        with the latest developments in artificial intelligence, machine learning, 
        and technology. You provide concise, accurate summaries of important news.""",
        tools=[search_tool],
        verbose=True
    )
    
    # Define the task
    task = """Search for the latest AI news from today. 
    Focus on major developments, breakthroughs, or announcements.
    Provide a summary of the top 3-5 most important news items.
    Include the source and key details for each item."""
    
    # Create scheduler with callbacks
    scheduler = AgentScheduler(
        agent=agent,
        task=task,
        on_success=on_success,
        on_failure=on_failure
    )
    
    print(f"Agent: {agent.name}")
    print(f"Task: {task}")
    print(f"Schedule: Every 1 hour")
    print("="*80)
    print("\n⏰ Starting scheduler... (Press Ctrl+C to stop)\n")
    
    # Start the scheduler
    # - "hourly" or "*/1h" = every 1 hour
    # - run_immediately=True = run once before starting the schedule
    scheduler.start(
        schedule_expr="hourly",  # Run every hour
        max_retries=3,           # Retry up to 3 times on failure
        run_immediately=True     # Run immediately on start
    )
    
    try:
        # Keep the main thread alive
        while scheduler.is_running:
            import time
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\n🛑 Stopping scheduler...")
        scheduler.stop()
        
        # Print final statistics
        stats = scheduler.get_stats()
        print("\n📊 Final Statistics:")
        print(f"  Total Executions: {stats['total_executions']}")
        print(f"  Successful: {stats['successful_executions']}")
        print(f"  Failed: {stats['failed_executions']}")
        print(f"  Success Rate: {stats['success_rate']:.1f}%")
        print("\n✅ Agent stopped successfully\n")


if __name__ == "__main__":
    main()
