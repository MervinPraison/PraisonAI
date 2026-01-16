"""
RAG Evaluation Example

This example demonstrates how to evaluate RAG quality by testing
agent responses against expected answers.

Usage:
    python rag_evaluation.py
"""

from praisonaiagents import Agent


# Sample knowledge for evaluation
SAMPLE_KNOWLEDGE = """
Product Overview:
CloudManager Pro is an enterprise cloud management platform.
Its main purpose is to help organizations monitor, optimize, and secure their multi-cloud infrastructure.

Key Features:
- Real-time monitoring across AWS, Azure, and GCP
- Cost optimization with automated recommendations
- Security compliance checking
- Automated scaling and resource management

Getting Started:
1. Sign up at cloudmanager.example.com
2. Connect your cloud accounts
3. Configure monitoring dashboards
4. Set up alerts and policies
"""


def create_test_queries():
    """Create sample test queries for evaluation."""
    return [
        {
            "query": "What is the main purpose of CloudManager Pro?",
            "expected_contains": ["monitor", "cloud", "infrastructure"],
        },
        {
            "query": "What are the key features?",
            "expected_contains": ["monitoring", "cost", "security"],
        },
        {
            "query": "How do I get started?",
            "expected_contains": ["sign up", "connect", "configure"],
        },
    ]


def evaluate_rag_agent(agent: Agent, test_queries: list) -> dict:
    """
    Evaluate RAG agent performance on test queries.
    
    Returns metrics including answer relevance accuracy.
    """
    results = {
        "total": len(test_queries),
        "passed": 0,
        "details": [],
    }
    
    for test in test_queries:
        query = test["query"]
        expected_terms = test.get("expected_contains", [])
        
        # Get agent response
        response = agent.chat(query)
        response_lower = response.lower()
        
        # Check if response contains expected terms
        terms_found = sum(1 for term in expected_terms if term.lower() in response_lower)
        pass_rate = terms_found / len(expected_terms) if expected_terms else 1.0
        passed = pass_rate >= 0.5  # At least 50% of terms found
        
        if passed:
            results["passed"] += 1
        
        results["details"].append({
            "query": query,
            "passed": passed,
            "terms_found": terms_found,
            "total_terms": len(expected_terms),
            "pass_rate": pass_rate,
            "answer_preview": response[:150],
        })
    
    results["accuracy"] = results["passed"] / results["total"]
    return results


def print_results(results: dict):
    """Print evaluation results in a formatted way."""
    print("\n" + "=" * 60)
    print("RAG Evaluation Results")
    print("=" * 60)
    
    print(f"\nTotal Queries: {results['total']}")
    print(f"Passed: {results['passed']}/{results['total']}")
    print(f"Accuracy: {results['accuracy']:.1%}")
    
    print("\n" + "-" * 60)
    print("Detailed Results:")
    print("-" * 60)
    
    for i, detail in enumerate(results["details"], 1):
        status = "✅ PASS" if detail["passed"] else "❌ FAIL"
        print(f"\n[{i}] {status}: {detail['query']}")
        print(f"    Terms Found: {detail['terms_found']}/{detail['total_terms']}")
        print(f"    Answer: {detail['answer_preview']}...")


def main():
    print("=" * 60)
    print("RAG Evaluation Example")
    print("=" * 60)
    
    # Create agent with knowledge
    agent = Agent(
        name="Product Expert",
        instructions=f"""You are a product expert who answers questions accurately.
        Use only the following knowledge to answer questions.
        
        KNOWLEDGE:
        {SAMPLE_KNOWLEDGE}""",
        output="silent"
    )
    
    # Get test queries
    test_queries = create_test_queries()
    
    # Run evaluation
    print(f"\nEvaluating {len(test_queries)} queries...")
    results = evaluate_rag_agent(agent, test_queries)
    
    # Print results
    print_results(results)
    
    # Return status
    if results["accuracy"] < 0.8:
        print("\n⚠️ WARNING: Accuracy below 80% threshold!")
        return 1
    
    print("\n✅ Evaluation PASSED!")
    return 0


if __name__ == "__main__":
    exit(main())
