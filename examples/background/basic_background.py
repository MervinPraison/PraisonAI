#!/usr/bin/env python3
"""
Basic Background Tasks Example for PraisonAI Agents.

This example demonstrates how to use the background task system to:
1. Run tasks asynchronously
2. Track task progress
3. Cancel running tasks
4. Handle task completion

Usage:
    python basic_background.py
"""

import asyncio
import time

from praisonaiagents.background import BackgroundRunner, BackgroundConfig, TaskStatus


async def main():
    print("=" * 60)
    print("Background Tasks Demo")
    print("=" * 60)
    
    # Create a background runner with config
    config = BackgroundConfig(max_concurrent_tasks=3)
    runner = BackgroundRunner(config=config)
    
    # Define some example tasks
    def slow_task(duration: float, name: str) -> str:
        """A slow task that simulates work."""
        print(f"  🔄 Task '{name}' starting (will take {duration}s)")
        time.sleep(duration)
        return f"Task '{name}' completed after {duration}s"
    
    async def async_task(duration: float, name: str) -> str:
        """An async task that simulates work."""
        print(f"  🔄 Async task '{name}' starting (will take {duration}s)")
        await asyncio.sleep(duration)
        return f"Async task '{name}' completed after {duration}s"
    
    # Submit tasks
    print("\n--- Submitting Tasks ---")
    
    task1 = await runner.submit(slow_task, args=(1.0, "quick-job"), name="task1")
    print(f"✅ Submitted task 1: {task1.id[:8]}")
    
    task2 = await runner.submit(slow_task, args=(2.0, "medium-job"), name="task2")
    print(f"✅ Submitted task 2: {task2.id[:8]}")
    
    task3 = await runner.submit(async_task, args=(1.5, "async-job"), name="task3")
    print(f"✅ Submitted async task 3: {task3.id[:8]}")
    
    # List all tasks
    print("\n--- Task Status ---")
    for task in runner.tasks:
        print(f"  [{task.id[:8]}] {task.status.value}")
    
    # Wait for task 1 to complete
    print("\n--- Waiting for Task 1 ---")
    await task1.wait(timeout=5.0)
    print(f"✅ Task 1 result: {task1.result}")
    
    # Check status of all tasks
    print("\n--- Updated Task Status ---")
    for task in [task1, task2, task3]:
        status = "✅" if task.status == TaskStatus.COMPLETED else "🔄"
        print(f"  {status} [{task.id[:8]}] {task.status.value}")
    
    # Wait for all remaining tasks
    print("\n--- Waiting for All Tasks ---")
    await task2.wait(timeout=10.0)
    await task3.wait(timeout=10.0)
    
    # Final status
    print("\n--- Final Results ---")
    for task in [task1, task2, task3]:
        if task.result:
            print(f"  ✅ {task.result}")
    
    # Cleanup
    runner.clear_completed()
    print("\n✅ Cleared completed tasks")
    
    print("\n" + "=" * 60)
    print("Demo Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
