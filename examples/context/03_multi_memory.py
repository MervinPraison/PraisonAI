"""
Multi-Memory Aggregation Example

Demonstrates concurrent fetching from multiple context sources.
Inspired by CrewAI's ContextualMemory pattern.
"""

import asyncio
from praisonaiagents.context import ContextAggregator, create_aggregator_from_config

# Example 1: Basic aggregator with mock sources
def mock_memory_search(query: str) -> str:
    """Mock memory search - returns recent conversation context."""
    return f"[Memory] User previously asked about: {query}. They prefer Python."

def mock_knowledge_search(query: str) -> str:
    """Mock knowledge search - returns facts from knowledge base."""
    return f"[Knowledge] Relevant facts: Python is a high-level programming language."

def mock_rag_retrieve(query: str) -> str:
    """Mock RAG retrieval - returns document chunks."""
    return f"[RAG] Retrieved: Documentation about {query} from the codebase."

# Create aggregator
aggregator = ContextAggregator(
    max_tokens=4000,
    separator="\n\n---\n\n",
    include_source_labels=True
)

# Register sources with priorities (lower = higher priority)
aggregator.register_source("memory", mock_memory_search, priority=10)
aggregator.register_source("knowledge", mock_knowledge_search, priority=20)
aggregator.register_source("rag", mock_rag_retrieve, priority=30)

async def demo_async():
    """Demo async aggregation."""
    print("=== Async Aggregation ===")
    result = await aggregator.aggregate("Python web development")
    print(f"Sources used: {result.sources_used}")
    print(f"Tokens used: {result.tokens_used}")
    print(f"Fetch times: {result.fetch_times}")
    print()
    print("Context:")
    print(result.context)
    return result

def demo_sync():
    """Demo sync aggregation."""
    print("=== Sync Aggregation ===")
    result = aggregator.aggregate_sync("Flask API development")
    print(f"Sources used: {result.sources_used}")
    print(f"Tokens used: {result.tokens_used}")
    print()
    print("Context:")
    print(result.context)
    return result

if __name__ == "__main__":
    print("=== Multi-Memory Aggregation Example ===")
    print()
    
    # Show registered sources
    print(f"Registered sources: {aggregator.sources}")
    print()
    
    # Demo sync aggregation
    demo_sync()
    print()
    
    # Demo async aggregation
    asyncio.run(demo_async())
    print()
    
    # Demo selective sources
    print("=== Selective Sources ===")
    result = aggregator.aggregate_sync(
        "Find database info",
        sources=["memory", "knowledge"]  # Only use these
    )
    print(f"Sources used: {result.sources_used}")
