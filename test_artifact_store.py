#!/usr/bin/env python
"""Test artifact storage functionality."""

import sys
import os
sys.path.insert(0, 'src/praisonai-agents')

from praisonaiagents import Agent
from praisonaiagents.config.feature_configs import ToolOutputConfig
from praisonaiagents.context import FileSystemArtifactStore, ArtifactMetadata
from praisonaiagents.tools import tool
import tempfile

# Create a test tool that generates large output
@tool
def generate_large_output(size: int = 20000) -> str:
    """Generate a large string for testing artifact storage."""
    return "X" * size

def test_artifact_storage():
    """Test that large tool outputs are stored as artifacts."""
    print("Testing artifact storage...")
    
    # Create agent with artifact storage enabled
    agent = Agent(
        name="TestAgent",
        instructions="You are a test agent",
        tools=[generate_large_output],
        tool_output=ToolOutputConfig(
            max_bytes=1000,  # Low limit to trigger artifact storage
            enable_artifacts=True,
            retention_days=1
        )
    )
    
    # Verify artifact store was initialized
    assert agent._artifact_store is not None
    print("✓ Artifact store initialized")
    
    # Test storing an artifact directly
    store = FileSystemArtifactStore()
    metadata = ArtifactMetadata(
        agent_id="test_agent",
        run_id="test_run",
        tool_name="test_tool",
        turn_id=1
    )
    
    large_content = "TEST" * 5000  # 20KB content
    ref = store.store(large_content, metadata)
    
    assert ref is not None
    assert ref.size_bytes == len(large_content)
    print(f"✓ Stored artifact: {ref.artifact_id}")
    
    # Test retrieval methods
    head = store.head(ref, lines=2)
    assert "TEST" in head
    print("✓ Head retrieval works")
    
    tail = store.tail(ref, lines=2)
    assert "TEST" in tail
    print("✓ Tail retrieval works")
    
    # Test grep
    matches = store.grep(ref, "TEST", context_lines=1, max_matches=5)
    assert len(matches) > 0
    print(f"✓ Grep found {len(matches)} matches")
    
    # Test chunk
    chunk = store.chunk(ref, start_line=1, end_line=3)
    assert "TEST" in chunk
    print("✓ Chunk retrieval works")
    
    # Test full load
    loaded = store.load(ref)
    assert loaded == large_content
    print("✓ Full load works")
    
    # Test cleanup
    deleted = store.delete(ref)
    assert deleted
    print("✓ Artifact deleted")
    
    print("\n✅ All artifact storage tests passed!")

if __name__ == "__main__":
    test_artifact_storage()