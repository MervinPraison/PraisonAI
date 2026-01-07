"""
RAG Evaluation Example

This example demonstrates how to evaluate RAG retrieval quality
using golden queries and expected answers.

Usage:
    python rag_evaluation.py

Requirements:
    pip install praisonaiagents[knowledge]
"""

import json
from pathlib import Path
from praisonaiagents import Knowledge
from praisonaiagents.rag import RAG, RAGConfig


def create_test_queries():
    """Create sample test queries for evaluation."""
    return [
        {
            "query": "What is the main purpose of the system?",
            "expected_doc": "overview.pdf",
            "expected_answer_contains": "purpose",
        },
        {
            "query": "What are the key features?",
            "expected_doc": "features.pdf",
            "expected_answer_contains": "feature",
        },
        {
            "query": "How do I get started?",
            "expected_doc": "quickstart.pdf",
            "expected_answer_contains": "start",
        },
    ]


def evaluate_rag(rag: RAG, test_queries: list) -> dict:
    """
    Evaluate RAG performance on test queries.
    
    Returns metrics including:
    - Document retrieval accuracy
    - Answer relevance
    - Average retrieval score
    """
    results = {
        "total": len(test_queries),
        "doc_hits": 0,
        "answer_hits": 0,
        "avg_score": 0.0,
        "details": [],
    }
    
    total_score = 0.0
    
    for test in test_queries:
        query = test["query"]
        expected_doc = test.get("expected_doc", "")
        expected_contains = test.get("expected_answer_contains", "")
        
        # Run RAG query
        result = rag.query(query)
        
        # Check if expected document is in citations
        doc_found = any(
            expected_doc in c.source for c in result.citations
        ) if expected_doc else True
        
        # Check if answer contains expected text
        answer_ok = (
            expected_contains.lower() in result.answer.lower()
        ) if expected_contains else True
        
        # Get average citation score
        avg_citation_score = (
            sum(c.score for c in result.citations) / len(result.citations)
            if result.citations else 0.0
        )
        
        if doc_found:
            results["doc_hits"] += 1
        if answer_ok:
            results["answer_hits"] += 1
        total_score += avg_citation_score
        
        results["details"].append({
            "query": query,
            "doc_found": doc_found,
            "answer_ok": answer_ok,
            "citation_score": avg_citation_score,
            "answer_preview": result.answer[:200],
        })
    
    results["avg_score"] = total_score / len(test_queries) if test_queries else 0.0
    results["doc_accuracy"] = results["doc_hits"] / results["total"]
    results["answer_accuracy"] = results["answer_hits"] / results["total"]
    
    return results


def print_results(results: dict):
    """Print evaluation results in a formatted way."""
    print("\n" + "=" * 60)
    print("RAG Evaluation Results")
    print("=" * 60)
    
    print(f"\nTotal Queries: {results['total']}")
    print(f"Document Retrieval Accuracy: {results['doc_accuracy']:.1%}")
    print(f"Answer Relevance Accuracy: {results['answer_accuracy']:.1%}")
    print(f"Average Citation Score: {results['avg_score']:.3f}")
    
    print("\n" + "-" * 60)
    print("Detailed Results:")
    print("-" * 60)
    
    for i, detail in enumerate(results["details"], 1):
        status = "PASS" if detail["doc_found"] and detail["answer_ok"] else "FAIL"
        print(f"\n[{i}] {status}: {detail['query']}")
        print(f"    Doc Found: {detail['doc_found']}")
        print(f"    Answer OK: {detail['answer_ok']}")
        print(f"    Score: {detail['citation_score']:.3f}")


def main():
    print("=" * 60)
    print("RAG Evaluation Example")
    print("=" * 60)
    
    # Create knowledge base
    knowledge = Knowledge()
    knowledge.add("documents/")  # Add your documents
    
    # Configure RAG
    config = RAGConfig(
        top_k=5,
        min_score=0.3,
        include_citations=True,
    )
    
    rag = RAG(knowledge=knowledge, config=config)
    
    # Get test queries
    test_queries = create_test_queries()
    
    # Run evaluation
    print(f"\nEvaluating {len(test_queries)} queries...")
    results = evaluate_rag(rag, test_queries)
    
    # Print results
    print_results(results)
    
    # Save results to file
    output_path = Path("evaluation_results.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {output_path}")
    
    # Return exit code based on results
    if results["doc_accuracy"] < 0.8 or results["answer_accuracy"] < 0.8:
        print("\nWARNING: Evaluation metrics below threshold!")
        return 1
    
    print("\nEvaluation PASSED!")
    return 0


if __name__ == "__main__":
    exit(main())
