#!/usr/bin/env python3
"""
Test script for context assembly cache optimization (Issue #1808).

This test verifies that:
1. Memory search results are sorted deterministically
2. Tool schemas are sorted by function name
3. Cache boundary markers are properly included
4. Multiple runs produce identical context strings for caching
"""

import sys
import os

# Add the praisonai-agents package to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

def test_memory_stable_sorting():
    """Test that memory context is assembled deterministically."""
    print("Testing memory stable sorting...")
    
    from praisonaiagents.memory.memory import Memory
    
    # Create test data that simulates memory search results
    test_results = [
        {"text": "First memory", "timestamp": 1000, "id": "1"},
        {"text": "Second memory", "timestamp": 2000, "id": "2"},  
        {"text": "Third memory", "timestamp": 1500, "id": "3"}
    ]
    
    # Create a memory instance and stub the search methods to return controlled data
    memory = Memory(config={})
    
    # Mock the search methods to return our test data
    original_search_short = memory.search_short_term
    original_search_long = memory.search_long_term
    original_search_entity = memory.search_entity
    original_search_user = memory.search_user_memory
    
    try:
        memory.search_short_term = lambda q, limit=3: test_results.copy()
        memory.search_long_term = lambda q, limit=3: []
        memory.search_entity = lambda q, limit=3: []
        memory.search_user_memory = lambda user_id, q, limit=3: []
        
        # Test multiple runs produce identical context strings
        context1 = memory.build_context_for_task("test task", include_in_output=True)
        context2 = memory.build_context_for_task("test task", include_in_output=True)
        
        assert context1 == context2, "Memory context should be deterministic"
        
        # Verify the order is correct in the actual context (newest first)
        lines = context1.split('\n')
        second_idx = next((i for i, line in enumerate(lines) if "Second memory" in line), -1)
        third_idx = next((i for i, line in enumerate(lines) if "Third memory" in line), -1) 
        first_idx = next((i for i, line in enumerate(lines) if "First memory" in line), -1)
        
        assert second_idx < third_idx < first_idx, "Memory should be ordered newest first"
        print("✓ Memory context is deterministic and correctly ordered")
        
    finally:
        # Restore original methods
        memory.search_short_term = original_search_short
        memory.search_long_term = original_search_long
        memory.search_entity = original_search_entity
        memory.search_user_memory = original_search_user
    
    # Test cache boundary constants are available
    from praisonaiagents.memory.memory import CACHE_BOUNDARY
    assert CACHE_BOUNDARY is not None, "CACHE_BOUNDARY should be defined"
    print("✓ Cache boundary constants are available")

def test_tool_schema_sorting():
    """Test that tool schemas are sorted deterministically."""
    print("Testing tool schema sorting...")
    
    from praisonaiagents.tools.base import get_sorted_tool_schemas
    from praisonaiagents.tools.decorator import tool
    
    # Create test tools with different names
    @tool
    def zebra_tool():
        """A tool starting with Z."""
        return "zebra"
    
    @tool  
    def apple_tool():
        """A tool starting with A."""
        return "apple"
        
    @tool
    def middle_tool():
        """A tool in the middle."""
        return "middle"
    
    tools = [zebra_tool, apple_tool, middle_tool]
    
    # Get sorted schemas multiple times
    schemas1 = get_sorted_tool_schemas(tools)
    schemas2 = get_sorted_tool_schemas(tools)
    
    # Results should be identical
    assert schemas1 == schemas2, "Tool schemas should be deterministic"
    
    # Check they are sorted by name
    names = [schema["function"]["name"] for schema in schemas1]
    expected_names = ["apple_tool", "middle_tool", "zebra_tool"]
    assert names == expected_names, f"Tools should be sorted alphabetically, got {names}"
    print("✓ Tool schemas are sorted deterministically")

def test_cache_boundary_markers():
    """Test that cache boundary markers work correctly."""
    print("Testing cache boundary markers...")
    
    from praisonaiagents.memory.memory import Memory, CACHE_BOUNDARY
    
    # Test that the boundary constant is properly defined
    assert "CACHE_BOUNDARY" in CACHE_BOUNDARY
    assert len(CACHE_BOUNDARY) > 0
    print("✓ Cache boundary constant is defined")
    
    # Test the cache-optimized context method actually works
    memory = Memory(config={})
    
    # Mock search methods to return empty results for simpler test
    memory.search_short_term = lambda q, limit=3: []
    memory.search_long_term = lambda q, limit=3: []
    memory.search_entity = lambda q, limit=3: []
    memory.search_user_memory = lambda user_id, q, limit=3: []
    
    # Test with cache boundary enabled
    result = memory.build_cache_optimized_context("test task", include_cache_boundary=True, include_in_output=True)
    assert "stable_prefix" in result, "Result should have stable_prefix"
    assert "cache_boundary" in result, "Result should have cache_boundary"
    assert result["cache_boundary"] == CACHE_BOUNDARY, "Cache boundary should match constant"
    
    # Test with cache boundary disabled
    result2 = memory.build_cache_optimized_context("test task", include_cache_boundary=False, include_in_output=True)
    assert result2["cache_boundary"] == "", "Cache boundary should be empty when disabled"
    
    print("✓ Cache optimization method works correctly")

if __name__ == "__main__":
    try:
        test_memory_stable_sorting()
        test_tool_schema_sorting()
        test_cache_boundary_markers()
        print("\n🎉 All tests passed! Context assembly cache optimization is working correctly.")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)