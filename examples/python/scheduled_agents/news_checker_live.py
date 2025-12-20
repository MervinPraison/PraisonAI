"""
Live News Checker Agent - 24/7 Scheduled Agent

This example demonstrates a real working agent that checks AI news
every hour using the AgentScheduler with actual API calls.

Requirements:
    - OPENAI_API_KEY environment variable set
    - praisonaiagents package installed
    
Usage:
    python news_checker_live.py
"""

import os
import sys
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../..'))

from praisonaiagents import Agent
from praisonai.scheduler import AgentScheduler

# Import search_tool from root tools.py
try:
    from tools import search_tool
except ImportError:
    # Fallback: create inline search tool
    from duckduckgo_search import DDGS
    
    def search_tool(query: str) -> list:
        """Search the web using DuckDuckGo."""
        try:
            results = []
            ddgs = DDGS()
            for result in ddgs.text(keywords=query, max_results=5):
                results.append({
                    "title": result.get("title", ""),
                    "url": result.get("href", ""),
                    "snippet": result.get("body", ""),
                })
            return results
        except Exception as e:
            print(f"Search error: {e}")
            return []


def on_success(result):
    """Callback when agent execution succeeds."""
    print("\n" + "="*80)
    print(f"✅ SUCCESS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    print(result)
    print("="*80 + "\n")


def on_failure(error):
    """Callback when agent execution fails."""
    print("\n" + "="*80)
    print(f"❌ FAILURE - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    print(f"Error: {error}")
    print("="*80 + "\n")


def main():
    """Main function to run the scheduled news checker."""
    
    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY environment variable not set")
        print("Please set it with: export OPENAI_API_KEY=your_key_here")
        sys.exit(1)
    
    print("\n🤖 Starting 24/7 AI News Checker Agent")
    print("="*80)
    
    # Create the agent with web search capability
    agent = Agent(
        name="AI News Monitor",
        role="Technology News Analyst",
        goal="Monitor and summarize the latest AI and technology news",
        backstory="""You are an expert AI news analyst who stays up-to-date 
        with the latest developments in artificial intelligence, machine learning, 
        and technology. You provide concise, accurate summaries of important news.""",
        tools=[search_tool],
        verbose=True,
        self_reflect=False  # Disable reflection for faster execution
    )
    
    # Define the task
    task = """Search for the latest AI news from today. 
    Focus on major developments, breakthroughs, or announcements.
    Provide a summary of the top 3 most important news items.
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
    # For testing: use "*/2m" (every 2 minutes) instead of "hourly"
    # For production: use "hourly"
    scheduler.start(
        schedule_expr="*/2m",  # Every 2 minutes for testing
        max_retries=3,
        run_immediately=True  # Run once immediately
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
