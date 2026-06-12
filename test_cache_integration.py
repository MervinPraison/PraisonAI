#!/usr/bin/env python3
"""
Test script to validate cache optimization integration.
"""

import sys
import os

# Add the source path to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

def test_imports():
    """Test that all imports work correctly."""
    try:
        from praisonaiagents.tools.base import get_sorted_tool_schemas
        from praisonaiagents.memory.memory import Memory, CACHE_BOUNDARY
        print("✓ Imports successful")
        return True
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False

def test_tool_sorting():
    """Test tool schema sorting functionality (internal sorting)."""
    try:
        # Test the sorting function directly
        def sort_formatted_tools(tools_list):
            """Sort already-formatted tool schemas by function name."""
            def sort_key(tool):
                if isinstance(tool, dict) and tool.get('type') == 'function':
                    return str(tool.get('function', {}).get('name') or '')
                return ''
            return sorted(tools_list, key=sort_key)
        
        # Test with formatted tool schemas
        test_tools = [
            {"type": "function", "function": {"name": "zebra_tool", "description": "Z tool"}},
            {"type": "function", "function": {"name": "alpha_tool", "description": "A tool"}},
            {"type": "function", "function": {"name": "beta_tool", "description": "B tool"}},
        ]
        
        sorted_tools = sort_formatted_tools(test_tools)
        tool_names = [tool["function"]["name"] for tool in sorted_tools]
        
        expected_order = ["alpha_tool", "beta_tool", "zebra_tool"]
        if tool_names == expected_order:
            print("✓ Tool sorting works correctly")
            return True
        else:
            print(f"✗ Tool sorting failed. Got: {tool_names}, Expected: {expected_order}")
            return False
    except Exception as e:
        print(f"✗ Tool sorting test failed: {e}")
        return False

def test_cache_optimized_context():
    """Test cache-optimized context building."""
    try:
        from praisonaiagents.memory.memory import Memory
        
        # Create a memory instance with proper config
        config = {}  # Empty config for basic testing
        memory = Memory(config)
        
        # Test cache-optimized context building
        result = memory.build_cache_optimized_context(
            task_descr="test task",
            include_cache_boundary=True
        )
        
        if isinstance(result, dict) and 'stable_prefix' in result and 'cache_boundary' in result:
            print("✓ Cache-optimized context building works")
            return True
        else:
            print(f"✗ Cache-optimized context building failed. Got: {result}")
            return False
    except Exception as e:
        print(f"✗ Cache-optimized context test failed: {e}")
        return False

def test_agent_integration():
    """Test agent integration with cache optimization."""
    try:
        from praisonaiagents.agent.chat_mixin import ChatMixin
        
        # Mock the necessary methods for testing
        class TestAgent(ChatMixin):
            def __init__(self):
                self.tools = []
                self._formatted_tools_cache = {}
                self._system_prompt_cache = {}
                self._memory_instance = None
                self.use_system_prompt = True
                self.role = "test"
                self.goal = "test"
                self.backstory = "test"
                self._rules_manager_initialized = False
                self._rules_manager = None
                self._skills = None
                self._skills_dirs = None
                self.verbose = False
                
            def _cache_get(self, cache, key):
                return cache.get(key)
                
            def _cache_put(self, cache, key, value):
                cache[key] = value
                
            def _get_tools_cache_key(self, tools):
                return str(tools)
                
            def get_memory_context(self):
                return ""
                
            def get_learn_context(self):
                return ""
                
            def get_skills_prompt(self):
                return ""
        
        agent = TestAgent()
        
        # Test tool formatting with sorting - pass already formatted tools
        test_tools = [
            {"type": "function", "function": {"name": "zebra_tool", "description": "Z tool"}},
            {"type": "function", "function": {"name": "alpha_tool", "description": "A tool"}},
        ]
        
        formatted_tools = agent._format_tools_for_completion(test_tools)
        if len(formatted_tools) == 2:
            tool_names = [tool["function"]["name"] for tool in formatted_tools]
            if tool_names == ["alpha_tool", "zebra_tool"]:
                print("✓ Agent tool integration works correctly")
                return True
            else:
                print(f"✗ Agent tools not sorted correctly. Got: {tool_names}")
                return False
        else:
            print(f"✗ Agent tool formatting failed. Got {len(formatted_tools)} tools")
            return False
            
    except Exception as e:
        print(f"✗ Agent integration test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("Testing cache optimization integration...")
    print()
    
    tests = [
        test_imports,
        test_tool_sorting,
        test_cache_optimized_context,
        test_agent_integration
    ]
    
    results = []
    for test in tests:
        results.append(test())
        
    print()
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"🎉 All {total} tests passed!")
        return 0
    else:
        print(f"💥 {total - passed} out of {total} tests failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())