"""
Knowledge Agent with Reranker Example
===================================

This example demonstrates how to use Mem0's built-in reranking feature
with the Knowledge Agent for improved search result relevance.
"""

import os
from praisonaiagents import Agent
from praisonaiagents.knowledge import Knowledge

def main():
    """
    Demonstrates knowledge search with and without reranking.
    """
    
    # Create sample content for knowledge base
    sample_documents = [
        "Artificial Intelligence is a field of computer science that aims to create machines that can perform tasks that typically require human intelligence.",
        "Machine Learning is a subset of AI that enables computers to learn and improve from experience without being explicitly programmed.",
        "Deep Learning is a type of machine learning that uses neural networks with multiple layers to model and understand complex patterns.",
        "Natural Language Processing (NLP) is a branch of AI that helps computers understand, interpret and manipulate human language.",
        "Computer Vision is an AI field that trains computers to interpret and understand the visual world from digital images and videos.",
        "Reinforcement Learning is a type of machine learning where an agent learns to make decisions by taking actions in an environment.",
        "Neural Networks are computing systems inspired by biological neural networks that constitute animal brains.",
        "Data Science combines domain expertise, programming skills, and knowledge of mathematics and statistics to extract insights from data."
    ]
    
    print("=== Knowledge Agent Reranker Example ===\n")
    
    # Example 1: Basic Knowledge without reranking
    print("1. Creating Knowledge base without reranking...")
    basic_config = {
        "vector_store": {
            "provider": "chroma",
            "config": {
                "collection_name": "knowledge_basic",
                "path": ".praison_basic"
            }
        },
        "reranker": {
            "enabled": True,
            "default_rerank": False  # Disabled by default
        }
    }
    
    basic_knowledge = Knowledge(config=basic_config, verbose=1)
    
    # Add documents to knowledge base
    for i, doc in enumerate(sample_documents):
        basic_knowledge.store(doc, metadata={"doc_id": f"doc_{i}", "category": "AI"})
    
    # Example 2: Knowledge with reranking enabled by default
    print("\n2. Creating Knowledge base with reranking enabled...")
    rerank_config = {
        "vector_store": {
            "provider": "chroma", 
            "config": {
                "collection_name": "knowledge_rerank",
                "path": ".praison_rerank"
            }
        },
        "reranker": {
            "enabled": True,
            "default_rerank": True  # Enabled by default
        }
    }
    
    rerank_knowledge = Knowledge(config=rerank_config, verbose=1)
    
    # Add same documents to reranking knowledge base
    for i, doc in enumerate(sample_documents):
        rerank_knowledge.store(doc, metadata={"doc_id": f"doc_{i}", "category": "AI"})
    
    print("\n=== Search Results Comparison ===\n")
    
    query = "What is machine learning and how does it work?"
    
    # Search without reranking
    print("3. Search WITHOUT reranking:")
    basic_results = basic_knowledge.search(query, rerank=False)
    print(f"Query: {query}")
    print(f"Results (limit=3):")
    for i, result in enumerate(basic_results[:3]):
        text = result.get('memory', result.get('text', str(result)))
        score = result.get('score', 'N/A')
        print(f"  {i+1}. Score: {score}")
        print(f"     Text: {text[:100]}...")
        print()
    
    # Search with reranking explicitly enabled
    print("4. Search WITH reranking:")
    rerank_results = basic_knowledge.search(query, rerank=True)
    print(f"Query: {query}")
    print(f"Results (limit=3):")
    for i, result in enumerate(rerank_results[:3]):
        text = result.get('memory', result.get('text', str(result)))
        score = result.get('score', 'N/A')
        print(f"  {i+1}. Score: {score}")
        print(f"     Text: {text[:100]}...")
        print()
    
    # Search using config default (reranking enabled)
    print("5. Search using config default (reranking enabled):")
    default_results = rerank_knowledge.search(query)  # Will use default_rerank=True
    print(f"Query: {query}")
    print(f"Results (limit=3):")
    for i, result in enumerate(default_results[:3]):
        text = result.get('memory', result.get('text', str(result)))
        score = result.get('score', 'N/A')
        print(f"  {i+1}. Score: {score}")
        print(f"     Text: {text[:100]}...")
        print()
    
    print("=== Advanced Search Options ===\n")
    
    # Example with additional Mem0 advanced retrieval options
    print("6. Search with keyword search + reranking:")
    advanced_results = basic_knowledge.search(
        query, 
        rerank=True,
        keyword_search=True,  # Enable keyword search for better recall
        filter_memories=True   # Enable filtering for better precision
    )
    print(f"Query: {query}")
    print(f"Advanced results with keyword_search=True, filter_memories=True:")
    for i, result in enumerate(advanced_results[:3]):
        text = result.get('memory', result.get('text', str(result)))
        score = result.get('score', 'N/A')
        print(f"  {i+1}. Score: {score}")
        print(f"     Text: {text[:100]}...")
        print()
    
    # Example with Agent using reranking knowledge
    print("\n=== Agent with Reranking Knowledge ===\n")
    
    agent = Agent(
        name="AI Research Assistant",
        instructions="You are an AI research assistant. Use your knowledge base to answer questions about artificial intelligence topics.",
        knowledge=sample_documents,  # Will use default knowledge config
        knowledge_config=rerank_config,  # Use reranking config
        llm="gpt-4o-mini"
    )
    
    print("7. Agent with reranking knowledge:")
    response = agent.run("Explain the difference between machine learning and deep learning, and how they relate to AI.")
    print(f"Agent response: {response}")
    
    print("\n=== Performance Notes ===")
    print("- Basic search: ~10ms latency")
    print("- Reranking: 150-200ms additional latency")
    print("- Reranking improves relevance ordering significantly")
    print("- Use rerank=True for better results when query relevance is critical")
    print("- Use keyword_search=True for better recall")
    print("- Use filter_memories=True for better precision")

if __name__ == "__main__":
    main()