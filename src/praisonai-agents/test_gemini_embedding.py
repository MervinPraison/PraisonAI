#!/usr/bin/env python3
"""Test script for Gemini embedding support in PraisonAI"""

import os
import sys
import json
import logging

# Add the source directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/praisonai-agents'))

from praisonaiagents import Agent, Task, PraisonAIAgents

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_gemini_embedding():
    """Test Gemini embedding model integration"""
    
    # Test with OpenAI embedding (backward compatibility)
    print("\n" + "="*50)
    print("Testing OpenAI Embedding (Backward Compatibility)")
    print("="*50)
    
    # Create a simple agent
    agent = Agent(
        name="Test Agent",
        role="Memory Tester",
        goal="Test memory storage with embeddings",
        backstory="An agent that tests memory functionality",
        llm="gpt-5-nano"
    )
    
    # Create a task
    task = Task(
        description="Remember this fact: The capital of France is Paris. This is a test fact for memory storage.",
        expected_output="Confirmation that the fact has been stored",
        agent=agent
    )
    
    # Test with default OpenAI embeddings
    agents_openai = PraisonAIAgents(
        agents=[agent],
        tasks=[task],
        verbose=5,
        memory=True
    )
    
    print("\nRunning with default OpenAI embeddings...")
    agents_openai.start()
    
    # Test with explicit OpenAI embedding config
    print("\n" + "="*50)
    print("Testing Explicit OpenAI Embedding Configuration")
    print("="*50)
    
    agent2 = Agent(
        name="Test Agent 2",
        role="Memory Tester",
        goal="Test memory storage with explicit OpenAI embeddings",
        backstory="An agent that tests memory functionality",
        llm="gpt-5-nano"
    )
    
    task2 = Task(
        description="Remember this fact: The Eiffel Tower is 330 meters tall. This is another test fact.",
        expected_output="Confirmation that the fact has been stored",
        agent=agent2
    )
    
    agents_openai_explicit = PraisonAIAgents(
        agents=[agent2],
        tasks=[task2],
        verbose=5,
        memory=True,
        embedder={
            "provider": "openai",
            "config": {
                "model": "text-embedding-3-small"
            }
        }
    )
    
    print("\nRunning with explicit OpenAI embedding config...")
    agents_openai_explicit.start()
    
    # Test with Gemini embeddings
    print("\n" + "="*50)
    print("Testing Gemini Embedding Model")
    print("="*50)
    
    agent3 = Agent(
        name="Gemini Test Agent",
        role="Memory Tester with Gemini",
        goal="Test memory storage with Gemini embeddings",
        backstory="An agent that tests Gemini embedding functionality",
        llm="gpt-5-nano"  # Still use GPT for chat, but Gemini for embeddings
    )
    
    task3 = Task(
        description="Remember this fact: Google released Gemini in 2023. This tests Gemini embedding storage.",
        expected_output="Confirmation that the fact has been stored using Gemini embeddings",
        agent=agent3
    )
    
    # Configure with Gemini embeddings
    agents_gemini = PraisonAIAgents(
        agents=[agent3],
        tasks=[task3],
        verbose=5,
        memory=True,
        embedder={
            "provider": "gemini",
            "config": {
                "model": "text-embedding-004"  # Gemini embedding model
            }
        }
    )
    
    print("\nRunning with Gemini embeddings...")
    try:
        agents_gemini.start()
        print("\n✅ Gemini embedding test completed successfully!")
    except Exception as e:
        print(f"\n❌ Gemini embedding test failed: {e}")
        logger.error(f"Error details: {e}", exc_info=True)
    
    # Test memory search across different embedding models
    print("\n" + "="*50)
    print("Testing Memory Search")
    print("="*50)
    
    if agents_gemini.shared_memory:
        print("\nSearching for 'Gemini' in memory...")
        results = agents_gemini.shared_memory.search_long_term("Gemini", limit=5)
        print(f"Found {len(results)} results")
        for i, result in enumerate(results):
            print(f"\nResult {i+1}:")
            print(f"  Text: {result.get('text', '')[:100]}...")
            print(f"  Score: {result.get('score', 'N/A')}")

    print("\n" + "="*50)
    print("All tests completed!")
    print("="*50)

if __name__ == "__main__":
    # Check if Google API key is set
    if not os.environ.get("GOOGLE_API_KEY"):
        print("\n⚠️  Warning: GOOGLE_API_KEY not found in environment variables.")
        print("   Gemini embedding test will likely fail without it.")
        print("   Set it with: export GOOGLE_API_KEY='your-api-key'")
    
    test_gemini_embedding()