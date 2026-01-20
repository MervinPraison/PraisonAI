"""
Agent-centric Embedding Example

This example shows how to use embeddings with PraisonAI Agents.
Embeddings are used internally by Agent for:
- Knowledge retrieval (RAG)
- Memory storage and search
- Semantic similarity

You can also use the embedding API directly for custom use cases.
"""

from praisonaiagents import Agent, embedding

# =============================================================================
# Example 1: Direct Embedding API
# =============================================================================

def example_direct_embedding():
    """Use the embedding API directly."""
    
    # Single text embedding
    result = embedding("Hello, world!")
    print(f"Single embedding: {len(result.embeddings[0])} dimensions")
    
    # Batch embedding
    texts = ["AI agents are powerful", "Machine learning is fascinating"]
    result = embedding(texts, model="text-embedding-3-small")
    print(f"Batch embeddings: {len(result.embeddings)} vectors")
    
    # Custom dimensions (for models that support it)
    result = embedding("Hello", model="text-embedding-3-large", dimensions=256)
    print(f"Custom dimensions: {len(result.embeddings[0])} dimensions")
    
    return result


# =============================================================================
# Example 2: Agent with Knowledge (uses embeddings internally)
# =============================================================================

def example_agent_with_knowledge():
    """Agent with knowledge uses embeddings for RAG."""
    
    agent = Agent(
        instructions="You are a helpful assistant with knowledge about AI.",
        knowledge=["AI agents can use tools to accomplish tasks."],
        knowledge_config={
            "embedder": {
                "provider": "openai",
                "config": {"model": "text-embedding-3-small"}
            }
        }
    )
    
    # The agent uses embeddings internally for knowledge retrieval
    response = agent.chat("What can AI agents do?")
    print(f"Agent response: {response}")
    
    return agent


# =============================================================================
# Example 3: Agent with Memory (uses embeddings internally)
# =============================================================================

def example_agent_with_memory():
    """Agent with memory uses embeddings for semantic search."""
    
    agent = Agent(
        instructions="You are a helpful assistant that remembers conversations.",
        memory=True,
        memory_config={
            "embedding_model": "text-embedding-3-small"
        }
    )
    
    # The agent uses embeddings internally for memory storage/retrieval
    agent.chat("My name is Alice and I love Python programming.")
    response = agent.chat("What do I love?")
    print(f"Agent remembered: {response}")
    
    return agent


# =============================================================================
# Example 4: Custom Embedding for Similarity Search
# =============================================================================

def example_similarity_search():
    """Use embeddings for custom similarity search."""
    import math
    
    def cosine_similarity(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        return dot / (norm_a * norm_b) if norm_a and norm_b else 0
    
    # Embed documents
    documents = [
        "Python is a programming language",
        "JavaScript runs in browsers",
        "AI agents can automate tasks"
    ]
    doc_embeddings = embedding(documents)
    
    # Embed query
    query = "What language is used for web development?"
    query_embedding = embedding(query)
    
    # Find most similar document
    similarities = [
        cosine_similarity(query_embedding.embeddings[0], doc_emb)
        for doc_emb in doc_embeddings.embeddings
    ]
    
    best_idx = similarities.index(max(similarities))
    print(f"Most similar document: {documents[best_idx]}")
    print(f"Similarity score: {similarities[best_idx]:.4f}")
    
    return similarities


if __name__ == "__main__":
    print("=" * 60)
    print("Example 1: Direct Embedding API")
    print("=" * 60)
    example_direct_embedding()
    
    print("\n" + "=" * 60)
    print("Example 4: Custom Similarity Search")
    print("=" * 60)
    example_similarity_search()
    
    # Uncomment to run agent examples (requires API key)
    # print("\n" + "=" * 60)
    # print("Example 2: Agent with Knowledge")
    # print("=" * 60)
    # example_agent_with_knowledge()
    
    # print("\n" + "=" * 60)
    # print("Example 3: Agent with Memory")
    # print("=" * 60)
    # example_agent_with_memory()
