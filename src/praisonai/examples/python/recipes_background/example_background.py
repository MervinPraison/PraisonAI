#!/usr/bin/env python3
"""
Recipe Background Tasks Example

This example demonstrates how to run recipes as background tasks
with progress tracking and result retrieval.

Requirements:
    pip install praisonai

Usage:
    python example_background.py
"""

import asyncio


async def main():
    """Run a recipe as a background task."""
    
    print("=" * 60)
    print("Recipe Background Tasks Example")
    print("=" * 60)
    
    # For this example, we'll use a simple inline agent instead of a recipe
    # In production, you would use an actual recipe name
    from praisonaiagents import Agent
    from praisonaiagents.background import BackgroundRunner
    
    # Create an agent
    agent = Agent(
        name="Research Assistant",
        instructions="You are a helpful research assistant. Provide concise answers.",
        verbose=True
    )
    
    # Create background runner
    runner = BackgroundRunner(max_concurrent_tasks=3)
    
    print("\n1. Submitting task to background...")
    
    # Submit task
    task = await runner.submit(
        lambda: agent.start("What are the top 3 benefits of AI in healthcare?"),
        name="healthcare-research",
        timeout=120,
    )
    
    print(f"   Task ID: {task.id}")
    print(f"   Status: {task.status.value}")
    
    print("\n2. Waiting for completion...")
    
    # Wait for result
    result = await runner.wait_for_task(task.id, timeout=120)
    
    print("\n3. Task completed!")
    print(f"   Status: {task.status.value}")
    print(f"   Result preview: {str(result)[:200]}...")
    
    # List all tasks
    print("\n4. Listing all tasks:")
    tasks = runner.list_tasks()
    for t in tasks:
        print("   - %s: %s" % (t['id'], t['status']))
    
    # Clear completed tasks
    print("\n5. Clearing completed tasks...")
    runner.clear_completed()
    
    print("\n" + "=" * 60)
    print("Example completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
