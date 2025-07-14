#!/usr/bin/env python3
"""
Example: Using Gemini Embedding Models with PraisonAI Memory

This example demonstrates how to configure PraisonAI to use Google's Gemini
embedding models for memory storage and retrieval, as requested in issue #870.

Supported Gemini embedding models:
- gemini-embedding-exp-03-07 (experimental)
- text-embedding-004 (stable)

Prerequisites:
1. Install praisonaiagents with memory support:
   pip install "praisonaiagents[memory]"

2. Set your Google API key:
   export GOOGLE_API_KEY='your-api-key'

3. Ensure litellm is installed (comes with praisonaiagents)
"""

import os
from praisonaiagents import Agent, Task, PraisonAIAgents

def main():
    """Demonstrate Gemini embedding usage"""
    
    # Verify Google API key
    if not os.environ.get("GOOGLE_API_KEY"):
        print("Error: GOOGLE_API_KEY environment variable not set")
        print("Please set it with: export GOOGLE_API_KEY='your-api-key'")
        return
    
    print("=== Gemini Embedding Example ===\n")
    
    # Create agents for different tasks
    researcher = Agent(
        name="Research Agent",
        role="Information Researcher",
        goal="Research and store important information about topics",
        backstory="Expert at analyzing and documenting information with semantic understanding",
        llm="gpt-4o-mini"  # Using GPT for chat, Gemini for embeddings
    )
    
    retriever = Agent(
        name="Retrieval Agent",
        role="Information Retriever",
        goal="Retrieve relevant information from memory using semantic search",
        backstory="Specialist in finding and presenting stored information",
        llm="gpt-4o-mini"
    )
    
    # Task 1: Store information with semantic meaning
    store_task = Task(
        description="""
        Research and store the following information:
        1. Gemini is Google's family of multimodal AI models
        2. Gemini models support text, image, video, and audio understanding
        3. The embedding models provide semantic representations of text
        4. Gemini Ultra is the largest and most capable model
        5. Gemini was announced in December 2023
        
        Store each fact with its semantic meaning preserved.
        """,
        expected_output="Confirmation that all facts have been stored in memory",
        agent=researcher
    )
    
    # Task 2: Semantic retrieval test
    retrieve_task = Task(
        description="""
        Using semantic search, find information about:
        1. Google's AI capabilities
        2. Multimodal understanding features
        3. When was Google's latest AI announced
        
        Note: Use semantic similarity, not exact keyword matching.
        """,
        expected_output="Retrieved information based on semantic meaning",
        agent=retriever
    )
    
    # Configure with Gemini embeddings
    # Option 1: Using stable text-embedding-004
    agents = PraisonAIAgents(
        agents=[researcher, retriever],
        tasks=[store_task, retrieve_task],
        verbose=True,
        memory=True,
        embedder={
            "provider": "gemini",
            "config": {
                "model": "text-embedding-004",
                # Optional: specify task type for better results
                # "task_type": "RETRIEVAL_DOCUMENT"  
            }
        }
    )
    
    # Alternative: Using experimental model with advanced features
    # agents = PraisonAIAgents(
    #     agents=[researcher, retriever],
    #     tasks=[store_task, retrieve_task],
    #     verbose=True,
    #     memory=True,
    #     embedder={
    #         "provider": "gemini",
    #         "config": {
    #             "model": "gemini-embedding-exp-03-07",
    #             # Task types: SEMANTIC_SIMILARITY, CLASSIFICATION, CLUSTERING,
    #             #            RETRIEVAL_DOCUMENT, RETRIEVAL_QUERY, QUESTION_ANSWERING,
    #             #            FACT_VERIFICATION
    #             "task_type": "RETRIEVAL_DOCUMENT"
    #         }
    #     }
    # )
    
    # Execute the workflow
    print("Starting agents with Gemini embeddings...\n")
    result = agents.start()
    
    # Demonstrate direct memory access with Gemini embeddings
    print("\n=== Direct Memory Search Example ===\n")
    
    if agents.shared_memory:
        # Search queries that test semantic understanding
        queries = [
            "What are Google's latest AI innovations?",
            "Explain multimodal AI capabilities",
            "Large language model features"
        ]
        
        for query in queries:
            print(f"\nSearching for: '{query}'")
            results = agents.shared_memory.search_long_term(query, limit=3)
            
            if results:
                print(f"Found {len(results)} semantically similar results:")
                for i, result in enumerate(results, 1):
                    print(f"\n{i}. Relevance Score: {result.get('score', 0):.3f}")
                    print(f"   Content: {result.get('text', '')[:150]}...")
            else:
                print("No results found")
    
    print("\n=== Example Complete ===")
    print("\nKey Points:")
    print("1. Gemini embeddings provide semantic understanding of text")
    print("2. Results are based on meaning, not just keyword matching")
    print("3. Different task types can optimize embedding quality")
    print("4. Compatible with LiteLLM for easy integration")

if __name__ == "__main__":
    main()