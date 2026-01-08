#!/usr/bin/env python3
"""
Basic Checkpoints Example for PraisonAI Agents.

This example demonstrates how to use the shadow git checkpointing system with Agent:
1. Create an Agent with checkpoint support
2. Save checkpoints before making changes
3. List available checkpoints
4. Restore to a previous checkpoint

Usage:
    python basic_checkpoints.py
"""

import asyncio
import tempfile
from pathlib import Path

from praisonaiagents import Agent
from praisonaiagents.checkpoints import CheckpointService


async def main():
    # Create a temporary workspace for demonstration
    with tempfile.TemporaryDirectory() as workspace:
        print("=" * 60)
        print("Agent-Centric Checkpointing Demo")
        print("=" * 60)
        print(f"\nWorkspace: {workspace}")
        
        # Create some initial files
        test_file = Path(workspace) / "example.py"
        test_file.write_text("# Initial content\nprint('Hello, World!')\n")
        print(f"\n✅ Created initial file: {test_file.name}")
        
        # Create checkpoint service
        checkpoints = CheckpointService(workspace_dir=workspace)
        
        # Create an Agent with checkpoint support
        agent = Agent(
            name="RefactorBot",
            instructions="You are a code refactoring assistant.",
            checkpoints=checkpoints
        )
        
        print("\n--- Agent with Checkpoint Support Created ---")
        print(f"Agent: {agent.name}")
        print(f"Checkpoints enabled: {agent.checkpoints is not None}")
        
        try:
            # Initialize the shadow git repository
            print("\n--- Initializing Checkpoint Service ---")
            await agent.checkpoints.initialize()
            print("✅ Shadow git repository initialized")
            
            # Save first checkpoint
            print("\n--- Saving Checkpoint 1: Initial State ---")
            result1 = await agent.checkpoints.save("Initial state")
            print(f"✅ Checkpoint saved: {result1.checkpoint.id[:8]}")
            print(f"   Message: {result1.checkpoint.message}")
            
            # Make some changes (simulating agent modifications)
            print("\n--- Simulating Agent Changes ---")
            test_file.write_text("# Refactored content\nprint('Hello, PraisonAI!')\nprint('Checkpoints are awesome!')\n")
            print("✅ Modified example.py")
            
            # Create a new file
            new_file = Path(workspace) / "utils.py"
            new_file.write_text("def helper():\n    return 'I help!'\n")
            print("✅ Created utils.py")
            
            # Save second checkpoint
            print("\n--- Saving Checkpoint 2: After Refactoring ---")
            result2 = await agent.checkpoints.save("Added features")
            print(f"✅ Checkpoint saved: {result2.checkpoint.id[:8]}")
            
            # List all checkpoints
            print("\n--- Listing All Checkpoints ---")
            checkpoints_list = await agent.checkpoints.list_checkpoints()
            for i, cp in enumerate(checkpoints_list, 1):
                print(f"  {i}. [{cp.id[:8]}] {cp.message}")
            
            # Show diff
            print("\n--- Current Diff ---")
            diff = await agent.checkpoints.diff()
            if diff.files:
                for f in diff.files:
                    print(f"  {f.status}: {f.path}")
            else:
                print("  No uncommitted changes")
            
            # Make more changes
            test_file.write_text("# Bad changes\nprint('This will be reverted')\n")
            print("\n✅ Made problematic changes to example.py")
            
            # Restore to checkpoint 2
            print(f"\n--- Restoring to Checkpoint: {result2.checkpoint.id[:8]} ---")
            await agent.checkpoints.restore(result2.checkpoint.id)
            print("✅ Restored successfully!")
            
            # Verify restoration
            content = test_file.read_text()
            print(f"\n--- Verified Content After Restore ---")
            print(content)
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            raise
        
        print("\n" + "=" * 60)
        print("Demo Complete!")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
