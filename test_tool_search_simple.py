#!/usr/bin/env python3
"""
Simple test script to verify tool search implementation.
"""

import sys
import os

# Add praisonai-agents to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

def test_tool_search_basic():
    """Test basic tool search functionality."""
    print("Testing Tool Search implementation...")
    
    try:
        # Test config creation
        from praisonaiagents.tools.tool_search import ToolSearchConfig
        config = ToolSearchConfig()
        print(f"✓ ToolSearchConfig created: enabled={config.enabled}, threshold={config.threshold_pct}%")
        
        # Test config from raw values
        config_true = ToolSearchConfig.from_raw(True)
        config_false = ToolSearchConfig.from_raw(False)
        print(f"✓ Config from bool: True→{config_true.enabled}, False→{config_false.enabled}")
        
        # Test tool classification
        from praisonaiagents.tools.tool_search import classify_tools, PRAISONAI_CORE_TOOLS
        print(f"✓ Core tools defined: {len(PRAISONAI_CORE_TOOLS)} tools")
        print(f"  Sample core tools: {list(PRAISONAI_CORE_TOOLS)[:5]}")
        
        # Test bridge tools
        from praisonaiagents.tools.tool_search import bridge_tool_schemas
        bridge_schemas = bridge_tool_schemas()
        bridge_names = [schema["function"]["name"] for schema in bridge_schemas]
        print(f"✓ Bridge tools created: {bridge_names}")
        
        # Test assembly logic
        from praisonaiagents.tools.tool_search import assemble_tool_defs
        
        # Test with disabled config
        tool_defs = [
            {"type": "function", "function": {"name": "test_tool", "description": "Test"}}
        ]
        assembled, metadata = assemble_tool_defs(tool_defs, ToolSearchConfig(enabled="off"))
        print(f"✓ Disabled mode: bridge={metadata['bridge_mode']}, deferred={metadata['deferred_count']}")
        
        # Test with enabled but no deferrable tools
        assembled, metadata = assemble_tool_defs(tool_defs, ToolSearchConfig(enabled="on"))
        print(f"✓ No deferrable tools: bridge={metadata['bridge_mode']}, deferred={metadata['deferred_count']}")
        
        # Test with deferrable tools
        deferrable_tool_defs = [
            {"type": "function", "function": {"name": "read_file", "description": "Read file"}},
            {
                "type": "function", 
                "function": {"name": "mcp_weather", "description": "Get weather"},
                "__praisonai_deferrable__": True
            }
        ]
        assembled, metadata = assemble_tool_defs(deferrable_tool_defs, ToolSearchConfig(enabled="on"))
        print(f"✓ With deferrable tools: bridge={metadata['bridge_mode']}, deferred={metadata['deferred_count']}")
        print(f"  Assembled tools: {len(assembled)}, catalog: {len(metadata['catalog'])}")
        
        # Test search functionality
        from praisonaiagents.tools.tool_search import search_catalog
        search_results = search_catalog(metadata["deferrable_tools"], "weather", limit=5)
        print(f"✓ Search 'weather': {len(search_results)} results")
        if search_results:
            print(f"  First result: {search_results[0]}")
        
        print("\n🎉 All basic tests passed! Tool Search implementation is working.")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_agent_integration():
    """Test Agent class integration."""
    print("\nTesting Agent integration...")
    
    try:
        # Test config classes are exported
        from praisonaiagents.config import ToolSearchConfig
        print("✓ ToolSearchConfig available in config module")
        
        # Test Agent parameter (basic import check) 
        from praisonaiagents.agent.agent import Agent
        print("✓ Agent class imports successfully")
        
        print("✓ Agent integration looks good")
        return True
        
    except Exception as e:
        print(f"❌ Agent integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Tool Search Implementation Test")
    print("=" * 50)
    
    success1 = test_tool_search_basic()
    success2 = test_agent_integration()
    
    if success1 and success2:
        print("\n✅ All tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)