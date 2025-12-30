#!/usr/bin/env python3
"""
MCP Tasks API Example

Demonstrates the Tasks API per MCP 2025-11-25 specification.
Tasks are durable state machines for tracking long-running operations.

Usage:
    python mcp_tasks_example.py
"""

import asyncio
from praisonai.mcp_server.tasks import (
    TaskManager,
    TaskStatus,
)


async def simulate_long_operation(method: str, params: dict) -> str:
    """Simulate a long-running operation."""
    print(f"  Executing: {method} with {params}")
    await asyncio.sleep(1)  # Simulate work
    return f"Result for {method}: Success!"


async def main():
    print("=" * 60)
    print("MCP Tasks API Example (2025-11-25 Specification)")
    print("=" * 60)
    
    # Create task manager with executor
    manager = TaskManager(executor=simulate_long_operation)
    
    # 1. Create a task
    print("\n1. Creating a task...")
    task = await manager.create_task(
        method="tools/call",
        params={"name": "search", "arguments": {"query": "AI news"}},
        metadata={"user": "demo"},
        execute=True,  # Start execution immediately
    )
    print(f"   Task created: {task.id}")
    print(f"   Status: {task.status.value}")
    print(f"   Created at: {task.created_at}")
    
    # 2. Get task status (poll)
    print("\n2. Polling task status...")
    for i in range(3):
        await asyncio.sleep(0.5)
        current = manager.get_task(task.id)
        if current:
            print(f"   Poll {i+1}: status={current.status.value}")
            if current.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                break
    
    # 3. Get final result
    print("\n3. Getting task result...")
    final = manager.get_task(task.id)
    if final:
        print(f"   Final status: {final.status.value}")
        print(f"   Result: {final.result}")
        
        # Show MCP-compliant response format
        print("\n   MCP Response Format:")
        task_dict = final.to_dict()
        for key, value in task_dict.items():
            print(f"     {key}: {value}")
    
    # 4. Create another task and cancel it
    print("\n4. Creating and cancelling a task...")
    task2 = await manager.create_task(
        method="tools/call",
        params={"name": "slow_operation"},
        execute=False,  # Don't execute yet
    )
    print(f"   Task created: {task2.id}")
    
    cancelled = await manager.cancel_task(task2.id)
    if cancelled:
        print(f"   Task cancelled: {cancelled.status.value}")
        print(f"   Status message: {cancelled.status_message}")
    
    # 5. List all tasks
    print("\n5. Listing all tasks...")
    tasks = manager.list_tasks()
    for t in tasks:
        print(f"   - {t.id}: {t.status.value}")
    
    print("\n" + "=" * 60)
    print("Tasks API Example Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
