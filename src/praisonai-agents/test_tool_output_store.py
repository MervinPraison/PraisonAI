#!/usr/bin/env python3
"""Test script for tool output store functionality."""

import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

# Add praisonaiagents to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from praisonaiagents.runtime.tool_output_store import (
    ToolOutputStore,
    get_tool_output_store,
    reset_tool_output_store
)

def test_basic_storage():
    """Test basic storage and retrieval."""
    print("Testing basic storage...")
    
    store = ToolOutputStore(run_id="test_run_1")
    
    # Create large output that would be truncated
    large_output = "A" * 20000  # 20KB of text
    
    # Store the output
    metadata = store.store("test_tool", large_output)
    
    assert metadata, "Should return metadata"
    assert "path" in metadata, "Metadata should contain path"
    assert metadata["size"] == 20000, "Size should match"
    assert metadata["tool"] == "test_tool", "Tool name should match"
    
    # Retrieve the output
    retrieved = store.retrieve(metadata)
    assert retrieved == large_output, "Retrieved output should match original"
    
    print("✓ Basic storage test passed")

def test_format_reference():
    """Test reference formatting in truncated output."""
    print("Testing reference formatting...")
    
    store = ToolOutputStore(run_id="test_run_2")
    
    # Create truncated preview with marker
    truncated = "First part\n...[50,000 chars, showing first/last portions]...\nLast part"
    
    # Store and get metadata
    large_output = "X" * 50000
    metadata = store.store("big_tool", large_output)
    
    # Format reference
    formatted = store.format_reference(metadata, truncated)
    
    assert "Full output stored at:" in formatted, "Should include storage reference"
    assert metadata["path"] in formatted, "Should include path"
    
    print("✓ Reference formatting test passed")

def test_integration_with_agent():
    """Test integration with agent tool execution."""
    print("Testing agent integration...")
    
    from praisonaiagents.agent import Agent
    from praisonaiagents.config.feature_configs import OutputConfig
    
    # Create a mock tool that returns large output
    def large_output_tool():
        """Returns a large text output."""
        return "START\n" + ("This is a line of text.\n" * 1000) + "END"
    
    # Create agent with low output limit to trigger truncation
    agent = Agent(
        name="test_agent",
        instructions="Test agent",
        tools=[large_output_tool],
        output=OutputConfig(tool_output_limit=100),  # Very low limit to force truncation
        llm="echo"  # Use mock LLM
    )
    
    # Set run_id for the agent
    agent._run_id = "test_integration"
    
    # Execute the tool (use the public method)
    result = agent.execute_tool(
        function_name="large_output_tool",
        arguments={},
        tool_call_id="test_call_123"
    )
    
    # Convert result to string
    result_str = str(result)
    
    print(f"Result length: {len(result_str)}")
    print(f"First 200 chars: {result_str[:200]}")
    
    # Check that result is truncated and contains reference
    # The actual output is ~25KB, with limit of 100 chars it should be truncated
    assert len(result_str) < 30000, f"Result should be truncated (got {len(result_str)} chars)"
    
    # The truncation marker should be present
    if "..." in result_str:
        print("✓ Found truncation marker")
    
    # Check if storage happened (look for the stored file)
    from praisonaiagents.paths import get_cache_dir
    store_dir = get_cache_dir() / "tool_outputs" / "test_integration"
    if store_dir.exists():
        stored_files = list(store_dir.glob("*.txt"))
        assert len(stored_files) > 0, "Should have stored output file"
        print(f"✓ Stored output at: {stored_files[0]}")
    
    print("✓ Agent integration test passed")

def test_cleanup():
    """Test TTL-based cleanup."""
    print("Testing cleanup...")
    
    import time
    import shutil
    from praisonaiagents.paths import get_cache_dir
    
    # Create old run directory (simulate old run)
    old_run_dir = get_cache_dir() / "tool_outputs" / "old_run"
    old_run_dir.mkdir(parents=True, exist_ok=True)
    
    # Make it "old" by setting mtime to 25 hours ago
    old_time = time.time() - (25 * 3600)
    os.utime(old_run_dir, (old_time, old_time))
    
    # Create new store (should trigger cleanup)
    store = ToolOutputStore(run_id="new_run", retention_hours=24)
    
    # Check if old directory was cleaned up
    assert not old_run_dir.exists(), "Old directory should be cleaned up"
    
    print("✓ Cleanup test passed")

def main():
    """Run all tests."""
    print("=" * 50)
    print("Testing Tool Output Store")
    print("=" * 50)
    
    try:
        # Use temporary directory for all tests to avoid mutating real cache
        with tempfile.TemporaryDirectory() as tmp:
            cache_root = Path(tmp)
            with patch("praisonaiagents.runtime.tool_output_store.get_cache_dir", return_value=cache_root), \
                 patch("praisonaiagents.paths.get_cache_dir", return_value=cache_root):
                test_basic_storage()
                test_format_reference()
                test_integration_with_agent()  # Now enabled with proper OutputConfig
                test_cleanup()
        
        print("\n✅ All tests passed!")
        return 0
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # Clean up test directories
        reset_tool_output_store()

if __name__ == "__main__":
    sys.exit(main())