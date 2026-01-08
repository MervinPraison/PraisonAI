#!/usr/bin/env python3
"""
Basic Background Tasks Example for PraisonAI Agents.

This example demonstrates how to use the background task system with Agent:
1. Create an Agent with background task support
2. Run agent tasks asynchronously
3. Track task progress
4. Handle task completion

Usage:
    python basic_background.py
"""

import asyncio
from praisonaiagents import Agent
from praisonaiagents.background import BackgroundRunner, BackgroundConfig, TaskStatus


async def main():
    print("=" * 60)
    print("Agent-Centric Background Tasks Demo")
    print("=" * 60)
    
    # Create a background runner with config (used standalone, not passed to Agent)
    runner = BackgroundRunner(config=BackgroundConfig(max_concurrent_tasks=3))
    
    # Create an Agent
    agent = Agent(
        name="AsyncAssistant",
        instructions="You are a helpful research assistant.",
    )
    
    print("\n--- Agent with Background Support Created ---")
    print(f"Agent: {agent.name}")
    print(f"Background runner: {runner is not None}")
    
    # Define some example tasks
    async def research_task(topic: str) -> str:
        """Simulate a research task."""
        print(f"  🔄 Researching '{topic}'...")
        await asyncio.sleep(1.5)
        return f"Research on '{topic}' completed with 5 key findings"
    
    async def analysis_task(data: str) -> str:
        """Simulate an analysis task."""
        print(f"  🔄 Analyzing data...")
        await asyncio.sleep(1.0)
        return f"Analysis complete: {data}"
    
    # Submit tasks via background runner
    print("\n--- Submitting Background Tasks ---")
    
    task1 = await runner.submit(
        research_task, 
        args=("AI trends 2025",), 
        name="research_ai"
    )
    print(f"✅ Submitted research task: {task1.id[:8]}")
    
    task2 = await runner.submit(
        analysis_task, 
        args=("market data",), 
        name="analyze_market"
    )
    print(f"✅ Submitted analysis task: {task2.id[:8]}")
    
    # List all tasks
    print("\n--- Task Status ---")
    for task in runner.tasks:
        print(f"  [{task.id[:8]}] {task.status.value}")
    
    # Wait for tasks to complete
    print("\n--- Waiting for Tasks ---")
    await task1.wait(timeout=10.0)
    await task2.wait(timeout=10.0)
    
    # Final results
    print("\n--- Results ---")
    for task in [task1, task2]:
        status = "✅" if task.status == TaskStatus.COMPLETED else "❌"
        print(f"  {status} {task.result}")
    
    # Cleanup
    runner.clear_completed()
    print("\n✅ Cleared completed tasks")
    
    print("\n" + "=" * 60)
    print("Demo Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
