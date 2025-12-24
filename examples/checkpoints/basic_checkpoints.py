#!/usr/bin/env python3
"""
Basic Checkpoints Example for PraisonAI Agents.

This example demonstrates how to use the shadow git checkpointing system to:
1. Save checkpoints before making changes
2. List available checkpoints
3. View diffs between checkpoints
4. Restore to a previous checkpoint

Usage:
    python basic_checkpoints.py
"""

import asyncio
import tempfile
from pathlib import Path

from praisonaiagents.checkpoints import CheckpointService


async def main():
    # Create a temporary workspace for demonstration
    with tempfile.TemporaryDirectory() as workspace:
        print("=" * 60)
        print("Shadow Git Checkpointing Demo")
        print("=" * 60)
        print(f"\nWorkspace: {workspace}")
        
        # Create some initial files
        test_file = Path(workspace) / "example.py"
        test_file.write_text("# Initial content\nprint('Hello, World!')\n")
        print(f"\n✅ Created initial file: {test_file.name}")
        
        # Initialize the checkpoint service
        service = CheckpointService(workspace_dir=workspace)
        
        try:
            # Initialize the shadow git repository
            print("\n--- Initializing Checkpoint Service ---")
            await service.initialize()
            print("✅ Shadow git repository initialized")
            
            # Save first checkpoint
            print("\n--- Saving Checkpoint 1: Initial State ---")
            result1 = await service.save("Initial state")
            print(f"✅ Checkpoint saved: {result1.checkpoint.id[:8]}")
            print(f"   Message: {result1.checkpoint.message}")
            
            # Make some changes
            print("\n--- Making Changes ---")
            test_file.write_text("# Modified content\nprint('Hello, PraisonAI!')\nprint('Checkpoints are awesome!')\n")
            print("✅ Modified example.py")
            
            # Create a new file
            new_file = Path(workspace) / "utils.py"
            new_file.write_text("def helper():\n    return 'I help!'\n")
            print("✅ Created utils.py")
            
            # Save second checkpoint
            print("\n--- Saving Checkpoint 2: After Changes ---")
            result2 = await service.save("Added features")
            print(f"✅ Checkpoint saved: {result2.checkpoint.id[:8]}")
            
            # List all checkpoints
            print("\n--- Listing All Checkpoints ---")
            checkpoints = await service.list_checkpoints()
            for i, cp in enumerate(checkpoints, 1):
                print(f"  {i}. [{cp.id[:8]}] {cp.message} ({cp.timestamp})")
            
            # Show diff
            print("\n--- Current Diff (uncommitted changes) ---")
            diff = await service.diff()
            if diff.files:
                for f in diff.files:
                    print(f"  {f.status}: {f.path}")
            else:
                print("  No uncommitted changes")
            
            # Make more changes to show diff
            test_file.write_text("# Even more changes\nprint('This will be reverted')\n")
            print("\n✅ Made more changes to example.py")
            
            diff = await service.diff()
            print("\n--- New Diff ---")
            if diff.files:
                for f in diff.files:
                    print(f"  {f.status}: {f.path}")
            
            # Restore to checkpoint 2
            print(f"\n--- Restoring to Checkpoint: {result2.checkpoint.id[:8]} ---")
            await service.restore(result2.checkpoint.id)
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
