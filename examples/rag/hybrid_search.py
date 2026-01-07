"""
Hybrid Search: Combining Dense and Sparse Retrieval

This example demonstrates hybrid retrieval that combines semantic (dense)
search with keyword (sparse) search for improved accuracy.

RAG Concept: Dense embeddings capture meaning but may miss exact matches.
Sparse/keyword search finds exact terms but lacks semantic understanding.
Hybrid search combines both for best results.
"""

from praisonaiagents import Agent

# Sample knowledge base: Technical troubleshooting guides
TROUBLESHOOTING_GUIDES = [
    {
        "id": "error_001",
        "content": """
        Error Code: ERR_CONNECTION_REFUSED
        
        This error occurs when the client cannot establish a connection to the server.
        
        Common Causes:
        - Server is not running or has crashed
        - Firewall blocking the connection port
        - Incorrect host or port configuration
        - Network connectivity issues
        
        Resolution Steps:
        1. Verify the server process is running: `systemctl status myservice`
        2. Check firewall rules: `sudo ufw status`
        3. Test port connectivity: `telnet hostname 8080`
        4. Review server logs for startup errors
        """
    },
    {
        "id": "error_002",
        "content": """
        Error Code: ERR_OUT_OF_MEMORY
        
        This error indicates the application has exhausted available memory.
        
        Common Causes:
        - Memory leak in application code
        - Insufficient heap size configuration
        - Too many concurrent connections
        - Large data processing without streaming
        
        Resolution Steps:
        1. Increase heap size: `-Xmx4g` for Java applications
        2. Enable memory profiling to identify leaks
        3. Implement pagination for large datasets
        4. Add memory limits to container configurations
        """
    },
    {
        "id": "error_003",
        "content": """
        Error Code: ERR_SSL_CERTIFICATE_EXPIRED
        
        This error means the SSL/TLS certificate has passed its validity date.
        
        Common Causes:
        - Certificate not renewed before expiration
        - Automatic renewal process failed
        - Wrong certificate installed
        
        Resolution Steps:
        1. Check certificate expiry: `openssl x509 -enddate -noout -in cert.pem`
        2. Renew certificate with your CA or Let's Encrypt
        3. Update certificate files on the server
        4. Restart the web server to load new certificate
        """
    },
    {
        "id": "error_004",
        "content": """
        Error Code: ERR_DATABASE_DEADLOCK
        
        A deadlock occurs when two transactions block each other indefinitely.
        
        Common Causes:
        - Transactions acquiring locks in different orders
        - Long-running transactions holding locks
        - Missing indexes causing table scans with locks
        
        Resolution Steps:
        1. Review transaction isolation levels
        2. Ensure consistent lock ordering across queries
        3. Add appropriate indexes to reduce lock duration
        4. Implement retry logic for deadlock exceptions
        """
    },
    {
        "id": "error_005",
        "content": """
        Error Code: ERR_RATE_LIMIT_EXCEEDED
        
        The API has rejected requests due to exceeding the rate limit.
        
        Common Causes:
        - Too many requests in a short time window
        - Missing request throttling in client code
        - Retry loops without backoff
        
        Resolution Steps:
        1. Implement exponential backoff for retries
        2. Cache responses to reduce API calls
        3. Use bulk endpoints where available
        4. Request rate limit increase if needed
        """
    }
]


def demonstrate_search_types():
    """Show the difference between semantic and keyword search concepts."""
    
    print("=" * 60)
    print("SEARCH TYPES COMPARISON")
    print("=" * 60)
    
    print("""
    📊 DENSE (Semantic) Search:
       - Uses vector embeddings to capture meaning
       - "memory issues" matches "out of memory" and "RAM exhausted"
       - Good for natural language queries
       - May miss exact technical terms
    
    📊 SPARSE (Keyword) Search:
       - Uses term frequency and exact matching
       - "ERR_SSL_CERTIFICATE_EXPIRED" matches exactly
       - Good for error codes, IDs, technical terms
       - Misses synonyms and paraphrases
    
    📊 HYBRID Search:
       - Combines both approaches
       - Weighted scoring: (α × dense_score) + ((1-α) × sparse_score)
       - Best of both worlds for technical documentation
    """)


def hybrid_rag_example():
    """Demonstrate hybrid retrieval with an agent."""
    
    # Build context from troubleshooting guides
    context = "\n\n".join([f"[{g['id']}]\n{g['content']}" for g in TROUBLESHOOTING_GUIDES])
    
    # Create agent with context in instructions
    agent = Agent(
        name="Tech Support",
        instructions=f"""You are a technical support specialist.
        Help users troubleshoot errors using the knowledge base.
        Always mention the specific error code when relevant.
        Provide step-by-step resolution guidance.
        
        TROUBLESHOOTING KNOWLEDGE BASE:
        {context}""",
        verbose=False
    )
    
    # Test with different query types
    queries = [
        # Semantic query (natural language)
        "My application is running out of memory, what should I do?",
        
        # Exact match query (error code)
        "ERR_SSL_CERTIFICATE_EXPIRED",
        
        # Mixed query
        "Getting connection refused error when connecting to port 8080",
        
        # Conceptual query
        "How do I handle API throttling?"
    ]
    
    print("\n" + "=" * 60)
    print("HYBRID RAG IN ACTION")
    print("=" * 60)
    
    for query in queries:
        print(f"\n📝 Query: {query}")
        response = agent.chat(query)
        print(f"💡 Answer: {response[:300]}..." if len(str(response)) > 300 else f"💡 Answer: {response}")
        print("-" * 40)


def compare_retrieval_modes():
    """Compare results with different retrieval configurations."""
    
    print("\n" + "=" * 60)
    print("RETRIEVAL MODE COMPARISON")
    print("=" * 60)
    
    # Build context
    context = "\n\n".join([f"[{g['id']}]\n{g['content']}" for g in TROUBLESHOOTING_GUIDES])
    
    query = "database transaction blocking issue"
    
    # Agent with context
    agent = Agent(
        name="Search Agent",
        instructions=f"""Answer based on the knowledge provided.
        
        KNOWLEDGE BASE:
        {context}""",
        verbose=False
    )
    
    print(f"\n📝 Query: {query}")
    
    print("\n🔍 RAG Response:")
    response = agent.chat(query)
    print(f"   {response[:200]}...")
    
    print("\n💡 Note: Hybrid search combines semantic + keyword matching for best results.")


def hybrid_search_tuning():
    """Explain hybrid search tuning parameters."""
    
    print("\n" + "=" * 60)
    print("HYBRID SEARCH TUNING")
    print("=" * 60)
    
    print("""
    Key parameters for hybrid search optimization:
    
    1. **Alpha (α) Weight** - Balance between dense and sparse
       - α = 1.0: Pure semantic search
       - α = 0.5: Equal weight (good default)
       - α = 0.0: Pure keyword search
    
    2. **Top-K Retrieval** - Number of candidates
       - Higher K: More context, slower, may dilute relevance
       - Lower K: Faster, focused, may miss relevant docs
       - Typical range: 3-10 for RAG
    
    3. **Reranking** - Second-pass scoring
       - Cross-encoder reranking improves precision
       - Adds latency but improves quality
    
    Example configuration:
    ```python
    knowledge_config = {
        "hybrid": True,
        "hybrid_alpha": 0.6,  # Favor semantic
        "top_k": 5,
        "rerank": True
    }
    ```
    """)


def main():
    """Run all hybrid search examples."""
    print("\n🚀 PraisonAI Hybrid Search Examples\n")
    
    # Example 1: Explain search types
    demonstrate_search_types()
    
    # Example 2: Hybrid RAG in action
    hybrid_rag_example()
    
    # Example 3: Compare retrieval modes
    compare_retrieval_modes()
    
    # Example 4: Tuning guidance
    hybrid_search_tuning()
    
    print("\n✅ Hybrid search examples completed!")


if __name__ == "__main__":
    main()
