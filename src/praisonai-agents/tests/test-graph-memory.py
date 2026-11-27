#!/usr/bin/env python3
"""
Test script for graph memory functionality
"""

import pytest

from praisonaiagents.memory import Memory
from praisonaiagents.knowledge import Knowledge


@pytest.mark.live
def test_memory_graph_config():
    """Test memory with graph configuration"""
    print("Testing Memory with graph configuration...")
    
    # Configuration with graph store
    config = {
        "provider": "mem0",
        "config": {
            "graph_store": {
                "provider": "memgraph",
                "config": {
                    "url": "bolt://localhost:7687",
                    "username": "memgraph",
                    "password": ""
                }
            },
            "vector_store": {
                "provider": "chroma",
                "config": {"path": ".test_graph_memory"}
            }
        }
    }
    
    memory = Memory(config=config, verbose=1)
    print(f"✅ Memory initialized. Graph enabled: {getattr(memory, 'graph_enabled', False)}")

    # Test basic memory operations
    memory.store_short_term("Alice loves hiking", {"category": "preference"})
    memory.store_short_term("Alice's friend John also loves hiking", {"category": "social"})

    results = memory.search_short_term("hiking", limit=2)
    print(f"✅ Short-term search returned {len(results)} results")
    assert isinstance(results, list)

@pytest.mark.live
def test_knowledge_graph_config():
    """Test Knowledge with graph configuration"""
    print("\nTesting Knowledge with graph configuration...")
    
    config = {
        "vector_store": {
            "provider": "chroma",
            "config": {
                "collection_name": "test_graph_knowledge",
                "path": ".test_graph_knowledge"
            }
        },
        "graph_store": {
            "provider": "memgraph",
            "config": {
                "url": "bolt://localhost:7687",
                "username": "memgraph",
                "password": ""
            }
        }
    }
    
    knowledge = Knowledge(config=config, verbose=0)
    final_config = knowledge.config
    assert "graph_store" in final_config, "Graph store configuration missing"

@pytest.mark.live
def test_backward_compatibility():
    """Test that existing configurations still work"""
    print("\nTesting backward compatibility...")
    
    # Old-style configuration without graph
    old_config = {
        "provider": "mem0",
        "config": {
            "vector_store": {
                "provider": "chroma",
                "config": {"path": ".test_backward_compat"}
            }
        }
    }
    
    memory = Memory(config=old_config, verbose=0)
    assert memory is not None
    print("✅ Backward compatibility maintained")
    print(f"   Graph enabled: {getattr(memory, 'graph_enabled', False)}")

if __name__ == "__main__":
    print("🧪 Graph Memory Integration Tests")
    print("=" * 50)
    
    tests = [
        test_memory_graph_config,
        test_knowledge_graph_config,
        test_backward_compatibility
    ]
    
    passed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"⚠️  {test.__name__} failed (expected if dependencies missing): {e}")
    
    print(f"\n📊 Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("🎉 All tests passed!")
    else:
        print("⚠️  Some tests failed. This is expected if graph dependencies are not installed.")
    
    print("\n💡 To enable full graph memory functionality:")
    print("   pip install \"mem0ai[graph]\"")
    print("   docker run -p 7687:7687 memgraph/memgraph-mage:latest")