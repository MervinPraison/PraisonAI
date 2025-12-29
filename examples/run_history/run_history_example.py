#!/usr/bin/env python3
"""
PraisonAI Run History Example

This example demonstrates how to:
1. Store recipe run results in history
2. List and query run history
3. Export runs for replay/debugging

Prerequisites:
- pip install praisonai

Usage:
    python run_history_example.py
"""

import tempfile
from pathlib import Path


def main():
    """Main example function."""
    print("=" * 60)
    print("PraisonAI Run History Example")
    print("=" * 60)
    
    # Use a temporary directory for the example
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # Create history storage in temp directory
        history_path = tmp_path / "runs"
        
        print("\n1. Creating run history storage...")
        from praisonai.recipe.history import RunHistory
        from praisonai.recipe.models import RecipeResult, RecipeStatus
        
        history = RunHistory(history_path)
        print(f"   Storage created at: {history_path}")
        
        # Create sample run results
        print("\n2. Storing sample run results...")
        
        # Run 1: Successful run
        result1 = RecipeResult(
            run_id="run-abc123",
            recipe="support-reply",
            version="1.0.0",
            status=RecipeStatus.SUCCESS,
            output={"reply": "Thank you for contacting us..."},
            metrics={"duration_sec": 2.5, "tokens": 150},
            trace={"session_id": "session-001", "trace_id": "trace-xyz"},
        )
        
        history.store(
            result=result1,
            input_data={"ticket_id": "T-123", "message": "I need help"},
        )
        print(f"   Stored: {result1.run_id} (success)")
        
        # Run 2: Failed run
        result2 = RecipeResult(
            run_id="run-def456",
            recipe="code-review",
            version="2.0.0",
            status=RecipeStatus.FAILED,
            error="Timeout exceeded",
            metrics={"duration_sec": 30.0},
            trace={"session_id": "session-002"},
        )
        
        history.store(
            result=result2,
            input_data={"code": "def hello(): pass"},
        )
        print(f"   Stored: {result2.run_id} (failed)")
        
        # Run 3: Another successful run
        result3 = RecipeResult(
            run_id="run-ghi789",
            recipe="support-reply",
            version="1.0.0",
            status=RecipeStatus.SUCCESS,
            output={"reply": "Your issue has been resolved..."},
            metrics={"duration_sec": 1.8},
            trace={"session_id": "session-001"},
        )
        
        history.store(
            result=result3,
            input_data={"ticket_id": "T-456"},
        )
        print(f"   Stored: {result3.run_id} (success)")
        
        # List all runs
        print("\n3. Listing all runs...")
        runs = history.list_runs()
        for run in runs:
            status_icon = "✓" if run["status"] == "success" else "✗"
            print(f"   {status_icon} {run['run_id']} - {run['recipe']} ({run['status']})")
        
        # Filter by recipe
        print("\n4. Filtering runs by recipe 'support-reply'...")
        filtered = history.list_runs(recipe="support-reply")
        print(f"   Found {len(filtered)} run(s)")
        
        # Filter by session
        print("\n5. Filtering runs by session 'session-001'...")
        filtered = history.list_runs(session_id="session-001")
        print(f"   Found {len(filtered)} run(s)")
        
        # Get specific run details
        print("\n6. Getting details for run-abc123...")
        run_data = history.get("run-abc123")
        print(f"   Recipe: {run_data['recipe']}")
        print(f"   Status: {run_data['status']}")
        print(f"   Input: {run_data.get('input', {})}")
        print(f"   Output: {run_data.get('output', {})}")
        
        # Export a run
        print("\n7. Exporting run-abc123...")
        export_path = history.export("run-abc123", tmp_path / "export.json")
        print(f"   Exported to: {export_path}")
        
        # Show export contents
        import json
        with open(export_path) as f:
            export_data = json.load(f)
        print(f"   Format: {export_data['format']}")
        print(f"   Exported at: {export_data['exported_at']}")
        
        # Get storage stats
        print("\n8. Getting storage statistics...")
        stats = history.get_stats()
        print(f"   Total runs: {stats['total_runs']}")
        print(f"   Storage size: {stats['total_size_bytes']} bytes")
        
        # Cleanup old runs
        print("\n9. Running cleanup...")
        deleted = history.cleanup(retention_days=0)  # Delete all for demo
        print(f"   Deleted {deleted} run(s)")
        
        print("\n" + "=" * 60)
        print("Example completed successfully!")
        print("=" * 60)


if __name__ == "__main__":
    main()
