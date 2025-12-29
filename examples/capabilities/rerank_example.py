"""
Rerank Capabilities Example

Demonstrates document reranking using PraisonAI capabilities.
"""

from praisonai.capabilities import rerank

print("=== Document Reranking ===")
try:
    documents = [
        "Python is a programming language",
        "Machine learning uses algorithms",
        "Python is great for data science",
        "JavaScript runs in browsers"
    ]
    
    results = rerank(
        query="Python programming",
        documents=documents,
        model="cohere/rerank-english-v3.0"
    )
    
    print(f"Query: 'Python programming'")
    print(f"Reranked results:")
    for r in results:
        print(f"  Score {r.get('relevance_score', 0):.4f}: {r.get('document', {}).get('text', '')[:50]}")
except Exception as e:
    print(f"Note: Reranking requires Cohere API key")
    print(f"Error: {e}")

print("\nSee CLI: praisonai rerank <query> --documents 'doc1' 'doc2'")
