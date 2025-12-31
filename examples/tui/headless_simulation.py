"""
Headless TUI Simulation Example for PraisonAI.

This example demonstrates how to run TUI simulations without
launching the interactive UI - useful for testing and CI.
"""

import asyncio
from praisonai.cli.features.tui import (
    TuiOrchestrator,
    SimulationRunner,
    MockProvider,
)
from praisonai.cli.features.tui.orchestrator import OutputMode
from praisonai.cli.features.queue import QueueConfig


async def run_simulation():
    """Run a headless simulation."""
    
    # Create orchestrator with mock provider (no real API calls)
    config = QueueConfig(enable_persistence=False)
    orchestrator = TuiOrchestrator(
        queue_config=config,
        output_mode=OutputMode.PRETTY,
        debug=True,
    )
    
    # Create simulation runner
    runner = SimulationRunner(orchestrator, assert_mode=True)
    
    # Define simulation script
    script = {
        "session_id": "sim-example",
        "model": "gpt-4o-mini",
        "steps": [
            # Navigate to different screens
            {"action": "navigate", "args": {"screen": "main"}},
            {"action": "focus", "args": {"widget": "composer"}},
            
            # Change model
            {
                "action": "model",
                "args": {"model": "gpt-4"},
                "expected": {"model": "gpt-4"}
            },
            
            # Navigate to queue screen
            {"action": "navigate", "args": {"screen": "queue"}},
            
            # Take a snapshot
            {"action": "snapshot"},
            
            # Navigate back
            {"action": "navigate", "args": {"screen": "main"}},
            
            # Small delay
            {"action": "sleep", "args": {"seconds": 0.5}},
        ]
    }
    
    # Run the simulation
    print("Running headless TUI simulation...")
    print("=" * 50)
    
    success = await runner.run_script(script)
    
    # Print results
    print("=" * 50)
    summary = runner.get_summary()
    
    print(f"\nSimulation {'PASSED' if success else 'FAILED'}")
    print(f"  Assertions passed: {summary['assertions_passed']}")
    print(f"  Assertions failed: {summary['assertions_failed']}")
    
    if summary['errors']:
        print("\nErrors:")
        for error in summary['errors']:
            print(f"  - {error}")
    
    return success


async def run_with_events():
    """Run simulation and capture all events."""
    
    config = QueueConfig(enable_persistence=False)
    orchestrator = TuiOrchestrator(
        queue_config=config,
        output_mode=OutputMode.SILENT,
    )
    
    # Capture events
    events = []
    orchestrator.add_event_callback(lambda e: events.append(e))
    
    await orchestrator.start(session_id="event-capture")
    
    # Perform some actions
    orchestrator.set_model("gpt-4")
    orchestrator.navigate_screen("queue")
    orchestrator.set_focus("queue-panel")
    orchestrator.navigate_screen("main")
    
    await orchestrator.stop()
    
    # Print captured events
    print("\nCaptured Events:")
    print("-" * 40)
    for event in events:
        print(f"  {event.event_type.value}")
    
    return events


def main():
    """Main entry point."""
    print("PraisonAI TUI Headless Simulation Example")
    print("=" * 50)
    
    # Run simulation
    success = asyncio.run(run_simulation())
    
    # Run event capture
    print("\n" + "=" * 50)
    events = asyncio.run(run_with_events())
    
    print(f"\nTotal events captured: {len(events)}")
    
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
