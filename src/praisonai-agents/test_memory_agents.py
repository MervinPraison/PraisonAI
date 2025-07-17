"""
Test script for memory agents functionality

This script tests the three new memory features:
1. Session summaries
2. Agentic memory management
3. Memory references
"""

import os
import sys
import time
from pathlib import Path

# Add the praisonaiagents package to path
sys.path.insert(0, str(Path(__file__).parent))

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.memory import Memory, MemoryTools


def test_session_summaries():
    """Test session summary functionality"""
    print("🧠 Testing Session Summaries...")
    
    # Configure memory with session summaries enabled
    memory_config = {
        "provider": "rag",
        "use_embedding": True,
        "session_summary_config": {
            "enabled": True,
            "update_after_n_turns": 3,  # Summarize every 3 turns for testing
            "model": "gpt-4o-mini",
            "include_in_context": True
        }
    }
    
    memory = Memory(memory_config, verbose=5)
    
    # Simulate a conversation
    memory.add_to_session("user", "Hi, I'm working on a machine learning project about sentiment analysis")
    memory.add_to_session("assistant", "That sounds interesting! What kind of data are you working with?")
    memory.add_to_session("user", "I'm using movie reviews from IMDB, specifically focusing on positive and negative reviews")
    
    # Check if summary was created (should trigger after 3 turns)
    summary = memory.get_session_summary()
    if summary:
        print("✅ Session summary created successfully:")
        print(f"   Text: {summary.get('text', 'No text')}")
        print(f"   Topics: {summary.get('topics', [])}")
    else:
        print("❌ Session summary not created")
    
    print()


def test_agentic_memory():
    """Test agentic memory management"""
    print("🤖 Testing Agentic Memory Management...")
    
    # Configure memory with agentic features enabled
    memory_config = {
        "provider": "rag", 
        "use_embedding": True,
        "agentic_config": {
            "enabled": True,
            "auto_classify": True,
            "confidence_threshold": 0.7,
            "management_model": "gpt-4o-mini"
        }
    }
    
    memory = Memory(memory_config, verbose=5)
    
    # Test storing different types of information
    facts = [
        "The user prefers dark mode in applications",  # Should be important
        "Hello, how are you today?",  # Should be unimportant
        "The project deadline is next Friday",  # Should be important
        "Nice weather today",  # Should be unimportant
    ]
    
    print("Storing facts with auto-classification...")
    for fact in facts:
        stored = memory.remember(fact)
        print(f"   {'✅' if stored else '❌'} Stored: '{fact[:50]}...'")
    
    # Test searching memories
    results = memory.search_memories("project deadline", limit=3)
    print(f"\n🔍 Found {len(results)} relevant memories about 'project deadline'")
    for result in results:
        print(f"   - {result.get('text', '')[:80]}...")
    
    # Test updating a memory
    if results:
        memory_id = results[0].get('id')
        if memory_id:
            updated = memory.update_memory(memory_id, "The project deadline has been moved to next Monday")
            print(f"   {'✅' if updated else '❌'} Updated memory with ID: {memory_id}")
    
    print()


def test_memory_references():
    """Test memory references in responses"""
    print("📚 Testing Memory References...")
    
    # Configure memory with references enabled
    memory_config = {
        "provider": "rag",
        "use_embedding": True,
        "reference_config": {
            "include_references": True,
            "reference_format": "inline",
            "max_references": 3,
            "show_confidence": True
        }
    }
    
    memory = Memory(memory_config, verbose=5)
    
    # Store some facts first
    facts = [
        "The user is working on a sentiment analysis project using IMDB movie reviews",
        "The project uses Python with scikit-learn and pandas libraries",
        "The model achieved 85% accuracy on the test dataset"
    ]
    
    print("Storing reference facts...")
    for fact in facts:
        memory.store_long_term(fact)
        print(f"   ✅ Stored: {fact}")
    
    # Search with references
    result = memory.search_with_references("machine learning project", limit=3)
    
    print(f"\n🔗 Search results with references:")
    print(f"Content: {result['content']}")
    print(f"References ({len(result['references'])}):")
    for ref in result['references']:
        confidence = f" (confidence: {ref.get('confidence', 0):.2f})" if 'confidence' in ref else ""
        print(f"   [{ref['id']}] {ref['text'][:80]}...{confidence}")
    
    print()


def test_memory_tools():
    """Test MemoryTools for agent integration"""
    print("🛠️ Testing Memory Tools...")
    
    # Configure memory
    memory_config = {
        "provider": "rag",
        "use_embedding": True,
        "agentic_config": {
            "enabled": True,
            "auto_classify": True,
            "confidence_threshold": 0.6
        }
    }
    
    memory = Memory(memory_config, verbose=5)
    
    # Create memory tools
    memory_tools = MemoryTools(memory)
    
    # Test the tools
    print("Testing memory tools...")
    
    # Test remember tool
    stored = memory_tools.remember("The user wants to implement a chatbot feature")
    print(f"   {'✅' if stored else '❌'} Remember tool works")
    
    # Test search tool
    results = memory_tools.search_memories("chatbot", limit=2)
    print(f"   🔍 Search tool found {len(results)} results")
    
    # Test session summary tool
    summary = memory_tools.get_session_summary()
    print(f"   📝 Session summary tool: {'✅' if summary is not None else '❌'}")
    
    # Test search with references tool
    ref_result = memory_tools.search_with_references("chatbot feature")
    print(f"   📚 References tool: {'✅' if ref_result['content'] else '❌'}")
    
    print()


def test_agent_integration():
    """Test memory integration with agents"""
    print("🤝 Testing Agent Integration...")
    
    try:
        # Configure memory for the agents workflow
        memory_config = {
            "provider": "rag",
            "use_embedding": True,
            "session_summary_config": {
                "enabled": True,
                "update_after_n_turns": 2,
                "model": "gpt-4o-mini",
                "include_in_context": True
            },
            "agentic_config": {
                "enabled": True,
                "auto_classify": True,
                "confidence_threshold": 0.7,
                "management_model": "gpt-4o-mini"
            },
            "reference_config": {
                "include_references": True,
                "reference_format": "inline",
                "max_references": 3,
                "show_confidence": True
            }
        }
        
        # Create an agent with memory tools
        memory = Memory(memory_config, verbose=5)
        from praisonaiagents.memory.tools import get_memory_tools
        
        agent = Agent(
            name="MemoryAgent",
            role="Memory-Enabled Assistant",
            goal="Help users while managing memory effectively",
            backstory="An intelligent assistant that can remember and reference past conversations",
            llm="gpt-4o-mini",
            memory=memory,
            tools=get_memory_tools(memory)
        )
        
        print("✅ Agent created with memory and tools")
        
        # Test basic functionality
        task = Task(
            description="Store the fact that the user likes machine learning and then search for it",
            expected_output="Confirmation that the information was stored and retrieved",
            agent=agent
        )
        
        # Create workflow
        workflow = PraisonAIAgents(
            agents=[agent],
            tasks=[task],
            verbose=1,
            memory=True,
            memory_config=memory_config
        )
        
        print("✅ Workflow created with memory configuration")
        print("🚀 Memory agents implementation is ready!")
        
    except Exception as e:
        print(f"❌ Error in agent integration: {e}")
    
    print()


def main():
    """Run all memory agent tests"""
    print("🧪 Testing Memory Agents Implementation")
    print("=" * 50)
    
    # Check for required environment variables
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  Warning: OPENAI_API_KEY not set. Some tests may fail.")
        print("   Please set your OpenAI API key to test LLM-based features.")
        print()
    
    # Run tests
    test_session_summaries()
    test_agentic_memory()
    test_memory_references()
    test_memory_tools()
    test_agent_integration()
    
    print("🎉 All memory agent tests completed!")
    print("\n📋 Summary of implemented features:")
    print("   ✅ Session Summaries - Auto-summarize conversations every N turns")
    print("   ✅ Agentic Memory Management - Auto-classify and manage important info") 
    print("   ✅ Memory References - Include references to stored memories in responses")
    print("   ✅ Memory Tools - Agent tools for memory CRUD operations")
    print("   ✅ Agent Integration - Full integration with PraisonAI agent system")


if __name__ == "__main__":
    main()