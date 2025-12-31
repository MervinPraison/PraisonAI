"""
Queue Management Example for PraisonAI.

This example demonstrates how to use the queue system programmatically.
"""

import asyncio
from praisonai.cli.features.queue import (
    QueueManager,
    QueueConfig,
    QueuedRun,
    RunState,
    RunPriority,
)


async def main():
    """Demonstrate queue management."""
    
    print("PraisonAI Queue Management Example")
    print("=" * 50)
    
    # Create queue configuration
    config = QueueConfig(
        max_concurrent_global=2,
        max_concurrent_per_agent=1,
        max_queue_size=10,
        enable_persistence=False,  # Use in-memory for demo
    )
    
    # Track outputs
    outputs = {}
    
    async def on_output(run_id: str, chunk: str):
        if run_id not in outputs:
            outputs[run_id] = ""
        outputs[run_id] += chunk
        print(f"  [{run_id[:8]}] {chunk}", end="", flush=True)
    
    async def on_complete(run_id: str, run: QueuedRun):
        print(f"\n  [{run_id[:8]}] Completed: {run.state.value}")
    
    async def on_error(run_id: str, error: Exception):
        print(f"\n  [{run_id[:8]}] Error: {error}")
    
    # Create queue manager
    manager = QueueManager(
        config=config,
        on_output=on_output,
        on_complete=on_complete,
        on_error=on_error,
    )
    
    # Start the manager
    await manager.start(recover=False)
    print("Queue manager started")
    
    # Submit some runs with different priorities
    print("\nSubmitting runs...")
    
    run1 = await manager.submit(
        input_content="Low priority task",
        agent_name="Agent1",
        priority=RunPriority.LOW,
    )
    print(f"  Submitted run1: {run1} (LOW priority)")
    
    run2 = await manager.submit(
        input_content="High priority task",
        agent_name="Agent2",
        priority=RunPriority.HIGH,
    )
    print(f"  Submitted run2: {run2} (HIGH priority)")
    
    run3 = await manager.submit(
        input_content="Normal priority task",
        agent_name="Agent1",
        priority=RunPriority.NORMAL,
    )
    print(f"  Submitted run3: {run3} (NORMAL priority)")
    
    # Check queue status
    print(f"\nQueue status:")
    print(f"  Queued: {manager.queued_count}")
    print(f"  Running: {manager.running_count}")
    
    # List runs
    runs = manager.list_runs()
    print(f"\nAll runs ({len(runs)}):")
    for run in runs:
        print(f"  {run.run_id[:8]}: {run.agent_name} - {run.state.value} ({run.priority.name})")
    
    # Wait a bit for processing
    print("\nWaiting for processing...")
    await asyncio.sleep(2)
    
    # Cancel a run
    if runs:
        cancel_id = runs[-1].run_id
        print(f"\nCancelling run: {cancel_id[:8]}")
        await manager.cancel(cancel_id)
    
    # Get stats
    stats = manager.get_stats()
    print(f"\nQueue statistics:")
    print(f"  Total runs: {stats.total_runs}")
    print(f"  Queued: {stats.queued_count}")
    print(f"  Running: {stats.running_count}")
    print(f"  Succeeded: {stats.succeeded_count}")
    print(f"  Failed: {stats.failed_count}")
    print(f"  Cancelled: {stats.cancelled_count}")
    
    # Stop the manager
    await manager.stop()
    print("\nQueue manager stopped")
    
    print("\n" + "=" * 50)
    print("Example complete!")


if __name__ == "__main__":
    asyncio.run(main())
