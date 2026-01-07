"""
Reranking: Improving Retrieval Precision

This example demonstrates reranking - a second-pass scoring mechanism
that improves the quality of retrieved documents.

RAG Concept: Initial retrieval (first stage) prioritizes recall - finding
all potentially relevant documents. Reranking (second stage) prioritizes
precision - ordering results by true relevance to the query.
"""

from praisonaiagents import Agent

# Sample knowledge base: Research paper abstracts
RESEARCH_PAPERS = [
    {
        "id": "paper_001",
        "content": """
        Title: Attention Mechanisms in Neural Machine Translation
        
        Abstract: This paper introduces a novel attention mechanism for sequence-to-sequence
        models in machine translation. Unlike previous approaches that use a fixed-length
        context vector, our method allows the model to automatically search for parts of
        the source sentence relevant to predicting the target word. Experiments on
        English-to-French translation show significant improvements over baseline systems.
        """
    },
    {
        "id": "paper_002",
        "content": """
        Title: Deep Residual Learning for Image Recognition
        
        Abstract: We present a residual learning framework to ease the training of very deep
        neural networks. By reformulating layers as learning residual functions with
        reference to layer inputs, we show that these networks are easier to optimize
        and can gain accuracy from considerably increased depth. Our 152-layer residual
        network achieves state-of-the-art results on ImageNet classification.
        """
    },
    {
        "id": "paper_003",
        "content": """
        Title: BERT: Pre-training of Deep Bidirectional Transformers
        
        Abstract: We introduce BERT, a new language representation model designed to
        pre-train deep bidirectional representations from unlabeled text. Unlike previous
        models, BERT is designed to jointly condition on both left and right context.
        The pre-trained BERT model can be fine-tuned with just one additional output
        layer for a wide range of NLP tasks.
        """
    },
    {
        "id": "paper_004",
        "content": """
        Title: Generative Adversarial Networks
        
        Abstract: We propose a new framework for estimating generative models via an
        adversarial process. We simultaneously train two models: a generative model G
        that captures the data distribution, and a discriminative model D that estimates
        the probability that a sample came from the training data rather than G.
        This framework can generate realistic images from random noise.
        """
    },
    {
        "id": "paper_005",
        "content": """
        Title: Transformer Architecture for Language Understanding
        
        Abstract: We propose the Transformer, a model architecture eschewing recurrence
        and instead relying entirely on an attention mechanism to draw global dependencies
        between input and output. The Transformer allows for significantly more
        parallelization and achieves new state of the art in translation quality.
        """
    },
    {
        "id": "paper_006",
        "content": """
        Title: Word Embeddings and Semantic Similarity
        
        Abstract: This paper explores methods for learning distributed representations
        of words that capture semantic relationships. We show that word vectors trained
        on large corpora encode meaningful syntactic and semantic regularities. These
        representations enable analogical reasoning: king - man + woman = queen.
        """
    }
]


def explain_reranking():
    """Explain the reranking concept."""
    
    print("=" * 60)
    print("RERANKING EXPLAINED")
    print("=" * 60)
    
    print("""
    🔄 Two-Stage Retrieval Pipeline:
    
    Stage 1: Initial Retrieval (Bi-encoder)
    ├── Fast approximate matching
    ├── Retrieves top-K candidates (e.g., 20-100)
    ├── Uses pre-computed embeddings
    └── Optimizes for RECALL (find all relevant docs)
    
    Stage 2: Reranking (Cross-encoder)
    ├── Slower but more accurate scoring
    ├── Reorders the top-K candidates
    ├── Computes query-document interaction
    └── Optimizes for PRECISION (best docs first)
    
    Why Reranking Matters:
    - Bi-encoders encode query and docs separately (fast but approximate)
    - Cross-encoders process query+doc together (slow but accurate)
    - Reranking gives you the best of both worlds
    """)


def rag_with_reranking():
    """Demonstrate RAG with reranking enabled."""
    
    # Build context from research papers
    context = "\n\n".join([f"[{p['id']}]\n{p['content']}" for p in RESEARCH_PAPERS])
    
    # Create agent with context
    agent = Agent(
        name="Research Assistant",
        instructions=f"""You are a research paper expert.
        Answer questions about machine learning research.
        Reference specific papers when relevant.
        Be precise about technical details.
        
        RESEARCH PAPERS:
        {context}""",
        verbose=False
    )
    
    queries = [
        "Which paper introduced the attention mechanism for translation?",
        "Tell me about pre-training language models",
        "What architecture avoids recurrence entirely?"
    ]
    
    print("\n" + "=" * 60)
    print("RAG WITH RERANKING")
    print("=" * 60)
    
    for query in queries:
        print(f"\n📝 Query: {query}")
        response = agent.chat(query)
        print(f"💡 Answer: {response[:300]}..." if len(str(response)) > 300 else f"💡 Answer: {response}")
        print("-" * 40)


def compare_with_without_reranking():
    """Compare retrieval quality with and without reranking."""
    
    print("\n" + "=" * 60)
    print("RERANKING IMPACT COMPARISON")
    print("=" * 60)
    
    # Build context
    context = "\n\n".join([f"[{p['id']}]\n{p['content']}" for p in RESEARCH_PAPERS])
    
    query = "How do transformers handle long-range dependencies?"
    
    # Agent with context
    agent = Agent(
        name="Research Agent",
        instructions=f"""Answer based on the research papers provided.
        
        RESEARCH PAPERS:
        {context}""",
        verbose=False
    )
    
    print(f"\n📝 Query: {query}")
    
    print("\n🔍 RAG Response:")
    response = agent.chat(query)
    print(f"   {response[:250]}...")
    
    print("\n💡 Note: Reranking uses cross-encoders to improve precision after initial retrieval.")


def reranking_configuration():
    """Show reranking configuration options."""
    
    print("\n" + "=" * 60)
    print("RERANKING CONFIGURATION")
    print("=" * 60)
    
    print("""
    Configuration options for reranking in PraisonAI:
    
    ```python
    agent = Agent(
        name="My Agent",
        knowledge=documents,
        knowledge_config={
            # Enable reranking
            "rerank": True,
            
            # Number of candidates for initial retrieval
            "top_k": 10,
            
            # Number of results after reranking
            "rerank_top_k": 3,
            
            # Reranker model (optional)
            "rerank_model": "cross-encoder/ms-marco-MiniLM-L-6-v2"
        }
    )
    ```
    
    Performance Considerations:
    ┌─────────────────┬──────────────┬─────────────┐
    │ Configuration   │ Latency      │ Quality     │
    ├─────────────────┼──────────────┼─────────────┤
    │ No reranking    │ ~50ms        │ Good        │
    │ Light reranker  │ ~100ms       │ Better      │
    │ Heavy reranker  │ ~200ms       │ Best        │
    └─────────────────┴──────────────┴─────────────┘
    
    Tip: Use reranking for precision-critical applications
    where quality matters more than latency.
    """)


def main():
    """Run all reranking examples."""
    print("\n🚀 PraisonAI Reranking Examples\n")
    
    # Example 1: Explain reranking
    explain_reranking()
    
    # Example 2: RAG with reranking
    rag_with_reranking()
    
    # Example 3: Compare with/without reranking
    compare_with_without_reranking()
    
    # Example 4: Configuration options
    reranking_configuration()
    
    print("\n✅ Reranking examples completed!")


if __name__ == "__main__":
    main()
