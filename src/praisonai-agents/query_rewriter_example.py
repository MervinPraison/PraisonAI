"""
Query Rewriter Agent Example

Demonstrates various query rewriting strategies for improving RAG retrieval.
"""

from dotenv import load_dotenv
load_dotenv()

from praisonaiagents import QueryRewriterAgent, RewriteStrategy

def main():
    # Initialize the agent
    agent = QueryRewriterAgent(
        model="gpt-4o-mini",
        verbose=True
    )
    
    print("=" * 60)
    print("Query Rewriter Agent Examples")
    print("=" * 60)
    
    # 1. Basic Rewriting - Short keyword queries
    print("\n1. BASIC REWRITING (Short Queries)")
    print("-" * 40)
    
    short_queries = [
        "AI trends",
        "python performance",
        "RAG best practices"
    ]
    
    for query in short_queries:
        result = agent.rewrite(query, strategy=RewriteStrategy.BASIC)
        print(f"Original: {query}")
        print(f"Rewritten: {result.primary_query}")
        print()
    
    # 2. HyDE - Hypothetical Document Embeddings
    print("\n2. HYDE (Hypothetical Document)")
    print("-" * 40)
    
    query = "What is quantum computing?"
    result = agent.rewrite(query, strategy=RewriteStrategy.HYDE)
    print(f"Original: {query}")
    print("Hypothetical Document (truncated):")
    print(f"{result.hypothetical_document[:300]}...")
    print()
    
    # 3. Step-Back - Higher-level concept questions
    print("\n3. STEP-BACK (Broader Context)")
    print("-" * 40)
    
    query = "What is the difference between GPT-4 and Claude 3?"
    result = agent.rewrite(query, strategy=RewriteStrategy.STEP_BACK)
    print(f"Original: {query}")
    print(f"Rewritten: {result.primary_query}")
    print(f"Step-back Question: {result.step_back_question}")
    print()
    
    # 4. Sub-Queries - Decompose complex questions
    print("\n4. SUB-QUERIES (Decomposition)")
    print("-" * 40)
    
    query = "How do I set up a RAG pipeline with vector search and what are the best embedding models to use?"
    result = agent.rewrite(query, strategy=RewriteStrategy.SUB_QUERIES)
    print(f"Original: {query}")
    print("Sub-queries:")
    for i, sq in enumerate(result.sub_queries, 1):
        print(f"  {i}. {sq}")
    print()
    
    # 5. Multi-Query - Multiple paraphrased versions
    print("\n5. MULTI-QUERY (Ensemble Retrieval)")
    print("-" * 40)
    
    query = "How to improve LLM response quality?"
    result = agent.rewrite(query, strategy=RewriteStrategy.MULTI_QUERY, num_queries=3)
    print(f"Original: {query}")
    print("Alternative queries:")
    for i, q in enumerate(result.rewritten_queries, 1):
        print(f"  {i}. {q}")
    print()
    
    # 6. Contextual - Using conversation history
    print("\n6. CONTEXTUAL (With Chat History)")
    print("-" * 40)
    
    chat_history = [
        {"role": "user", "content": "Tell me about Python programming"},
        {"role": "assistant", "content": "Python is a high-level programming language known for its simplicity and readability..."},
        {"role": "user", "content": "What frameworks are popular?"},
        {"role": "assistant", "content": "Popular Python frameworks include Django for web development, FastAPI for APIs, and PyTorch for ML..."}
    ]
    
    query = "What about its performance compared to others?"
    result = agent.rewrite(query, strategy=RewriteStrategy.CONTEXTUAL, chat_history=chat_history)
    print(f"Original: {query}")
    print(f"Standalone: {result.primary_query}")
    print()
    
    # 7. AUTO - Automatic strategy detection
    print("\n7. AUTO (Automatic Strategy Detection)")
    print("-" * 40)
    
    test_queries = [
        ("ML", None),  # Short query -> BASIC
        ("What about the cost?", chat_history),  # Follow-up -> CONTEXTUAL
        ("Compare transformers vs RNNs and explain their use cases", None),  # Complex -> SUB_QUERIES
    ]
    
    for query, history in test_queries:
        result = agent.rewrite(query, strategy=RewriteStrategy.AUTO, chat_history=history)
        print(f"Query: {query}")
        print(f"Detected Strategy: {result.strategy_used.value}")
        print(f"Result: {result.primary_query}")
        print()
    
    # 8. Custom Abbreviations
    print("\n8. CUSTOM ABBREVIATIONS")
    print("-" * 40)
    
    agent.add_abbreviations({
        "K8s": "Kubernetes",
        "TF": "TensorFlow",
        "PT": "PyTorch"
    })
    
    query = "K8s deployment for TF models"
    result = agent.rewrite(query, strategy=RewriteStrategy.BASIC)
    print(f"Original: {query}")
    print(f"Rewritten: {result.primary_query}")
    print()
    
    print("=" * 60)
    print("Examples Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
