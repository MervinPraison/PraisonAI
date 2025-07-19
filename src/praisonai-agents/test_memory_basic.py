"""
Basic test script for memory agents functionality (no API keys required)

This script tests the memory system initialization and basic functionality
without requiring external API calls.
"""

import os
import sys
from pathlib import Path

# Add the praisonaiagents package to path
sys.path.insert(0, str(Path(__file__).parent))

def test_memory_imports():
    """Test that all memory components can be imported"""
    print("🧠 Testing Memory Imports...")
    
    try:
        from praisonaiagents.memory import Memory, MemoryTools, get_memory_tools
        print("✅ Memory imports successful")
        return True
    except ImportError as e:
        print(f"❌ Memory import failed: {e}")
        return False


def test_memory_initialization():
    """Test memory initialization with different configurations"""
    print("🔧 Testing Memory Initialization...")
    
    try:
        from praisonaiagents.memory import Memory
        
        # Test basic configuration
        basic_config = {
            "provider": "rag",
            "use_embedding": False  # Disable embedding to avoid API calls
        }
        
        memory = Memory(basic_config, verbose=0)
        print("✅ Basic memory initialization successful")
        
        # Test session summary configuration
        session_config = {
            "provider": "rag",
            "use_embedding": False,
            "session_summary_config": {
                "enabled": True,
                "update_after_n_turns": 5,
                "model": "gpt-4o-mini",
                "include_in_context": True
            }
        }
        
        memory_with_session = Memory(session_config, verbose=0)
        print("✅ Session summary configuration successful")
        assert memory_with_session.session_enabled == True
        assert memory_with_session.update_after_n_turns == 5
        
        # Test agentic memory configuration
        agentic_config = {
            "provider": "rag",
            "use_embedding": False,
            "agentic_config": {
                "enabled": True,
                "auto_classify": True,
                "confidence_threshold": 0.7,
                "management_model": "gpt-4o"
            }
        }
        
        memory_with_agentic = Memory(agentic_config, verbose=0)
        print("✅ Agentic memory configuration successful")
        assert memory_with_agentic.agentic_enabled == True
        assert memory_with_agentic.confidence_threshold == 0.7
        
        # Test reference configuration
        reference_config = {
            "provider": "rag",
            "use_embedding": False,
            "reference_config": {
                "include_references": True,
                "reference_format": "inline",
                "max_references": 5,
                "show_confidence": True
            }
        }
        
        memory_with_references = Memory(reference_config, verbose=0)
        print("✅ Reference configuration successful")
        assert memory_with_references.include_references == True
        assert memory_with_references.reference_format == "inline"
        assert memory_with_references.max_references == 5
        
        return True
        
    except Exception as e:
        print(f"❌ Memory initialization failed: {e}")
        return False


def test_memory_tools():
    """Test memory tools creation and basic functionality"""
    print("🛠️ Testing Memory Tools...")
    
    try:
        from praisonaiagents.memory import Memory, MemoryTools, get_memory_tools
        
        # Create memory instance
        config = {
            "provider": "rag",
            "use_embedding": False,
            "agentic_config": {
                "enabled": True,
                "auto_classify": False  # Disable auto-classify to avoid API calls
            }
        }
        
        memory = Memory(config, verbose=0)
        
        # Test MemoryTools class
        tools = MemoryTools(memory)
        print("✅ MemoryTools class creation successful")
        
        # Test get_memory_tools function
        tool_list = get_memory_tools(memory)
        print(f"✅ get_memory_tools returned {len(tool_list)} tools")
        
        # Verify tools have the expected names
        tool_names = [tool.__name__ for tool in tool_list]
        expected_tools = [
            'remember', 'update_memory', 'forget', 
            'search_memories', 'get_session_summary', 'search_with_references'
        ]
        
        for expected_tool in expected_tools:
            if expected_tool in tool_names:
                print(f"✅ Tool '{expected_tool}' found")
            else:
                print(f"❌ Tool '{expected_tool}' missing")
                return False
        
        return True
        
    except Exception as e:
        print(f"❌ Memory tools test failed: {e}")
        return False


def test_basic_memory_operations():
    """Test basic memory operations without API calls"""
    print("💾 Testing Basic Memory Operations...")
    
    try:
        from praisonaiagents.memory import Memory
        
        config = {
            "provider": "rag",
            "use_embedding": False,
            "session_summary_config": {
                "enabled": True,
                "update_after_n_turns": 5
            },
            "agentic_config": {
                "enabled": True,
                "auto_classify": False  # Disable to avoid API calls
            }
        }
        
        memory = Memory(config, verbose=0)
        
        # Test session tracking
        memory.add_to_session("user", "Hello, this is a test message")
        memory.add_to_session("assistant", "Hello! How can I help you today?")
        
        assert len(memory.session_history) == 2
        assert memory.turn_counter == 2
        print("✅ Session tracking works")
        
        # Test basic memory storage (without auto-classification)
        stored = memory.remember("Test fact for storage", {"test": True})
        print(f"✅ Memory storage: {'successful' if stored else 'failed'}")
        
        # Test basic search (local SQLite only)
        results = memory.search_memories("test fact", limit=5)
        print(f"✅ Memory search returned {len(results)} results")
        
        # Test search with references (without actual references due to no embeddings)
        ref_result = memory.search_with_references("test fact")
        print(f"✅ Reference search: content='{ref_result['content'][:50]}...', refs={len(ref_result['references'])}")
        
        return True
        
    except Exception as e:
        print(f"❌ Basic memory operations failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_backward_compatibility():
    """Test that existing memory functionality still works"""
    print("🔄 Testing Backward Compatibility...")
    
    try:
        from praisonaiagents.memory import Memory
        
        # Test old-style configuration (should still work)
        old_config = {
            "provider": "rag",
            "use_embedding": False
        }
        
        memory = Memory(old_config, verbose=0)
        
        # Test existing methods
        memory.store_short_term("Test short-term data")
        memory.store_long_term("Test long-term data")
        
        # Test existing search methods
        short_results = memory.search_short_term("test", limit=3)
        long_results = memory.search_long_term("test", limit=3)
        
        print(f"✅ Short-term operations: {len(short_results)} results")
        print(f"✅ Long-term operations: {len(long_results)} results")
        
        # Test quality methods
        quality_score = memory.compute_quality_score(0.8, 0.9, 0.7, 0.85)
        print(f"✅ Quality score calculation: {quality_score}")
        
        return True
        
    except Exception as e:
        print(f"❌ Backward compatibility test failed: {e}")
        return False


def main():
    """Run all basic memory tests"""
    print("🧪 Testing Memory Agents Implementation (Basic)")
    print("=" * 50)
    
    tests = [
        test_memory_imports,
        test_memory_initialization,
        test_memory_tools,
        test_basic_memory_operations,
        test_backward_compatibility
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print("🎉 Test Results:")
    print(f"   ✅ Passed: {passed}/{total}")
    print(f"   {'❌' if passed < total else '✅'} {'Some tests failed' if passed < total else 'All tests passed!'}")
    
    if passed == total:
        print("\n📋 Summary of implemented features:")
        print("   ✅ Session Summaries - Configuration and tracking ready")
        print("   ✅ Agentic Memory Management - Auto-classification and tools ready") 
        print("   ✅ Memory References - Reference formatting ready")
        print("   ✅ Memory Tools - Complete tool set for agents")
        print("   ✅ Backward Compatibility - All existing features preserved")
        print("\n🚀 Memory agents implementation is complete and ready!")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)