"""
Basic RAG: Retrieve and Generate

This example demonstrates the fundamental RAG pattern in PraisonAI:
1. Provide context to an agent
2. Agent uses context to answer questions accurately
3. Generate grounded answers using the provided context

RAG Concept: The core retrieve-then-generate pattern that grounds LLM responses
in factual content, reducing hallucinations.
"""

from praisonaiagents import Agent

# Sample knowledge base: Technology company profiles as text strings
COMPANY_PROFILES = [
    """NovaTech Solutions specializes in cloud infrastructure and DevOps automation.
    Founded in 2018, they serve over 500 enterprise clients globally.
    Key products: CloudSync (infrastructure orchestration), DevPipeline (CI/CD platform).
    Headquarters: Austin, Texas. Employees: 1,200.""",
    
    """GreenLeaf Analytics provides environmental monitoring and sustainability reporting.
    Established in 2015, they work with governments and corporations on climate data.
    Key products: EcoTrack (emissions monitoring), SustainReport (ESG reporting).
    Headquarters: Seattle, Washington. Employees: 450.""",
    
    """QuantumBridge Financial offers algorithmic trading and risk management solutions.
    Started in 2012, they manage over $50 billion in assets for institutional clients.
    Key products: AlgoTrader Pro (trading platform), RiskShield (portfolio analytics).
    Headquarters: New York City. Employees: 800.""",
    
    """MediCore Health develops AI-powered diagnostic tools for healthcare providers.
    Founded in 2019, they partner with 200+ hospitals across North America.
    Key products: DiagnosAI (medical imaging analysis), PatientFlow (care coordination).
    Headquarters: Boston, Massachusetts. Employees: 350."""
]


def basic_rag_example():
    """Demonstrate basic RAG with context injection."""
    
    # Build context from knowledge base
    context = "\n\n".join(COMPANY_PROFILES)
    
    # Create an agent with instructions
    agent = Agent(
        name="Company Analyst",
        instructions=f"""You are a business analyst who answers questions about companies.
        Use only the following company information to answer questions accurately.
        If the information isn't available, say so clearly.
        
        COMPANY DATABASE:
        {context}""",
    )
    
    # Test queries
    queries = [
        "What products does NovaTech Solutions offer?",
        "Which company focuses on environmental monitoring?",
        "How many employees does QuantumBridge Financial have?",
        "What is MediCore Health's main focus area?"
    ]
    
    print("=" * 60)
    print("BASIC RAG EXAMPLE: Company Knowledge Base")
    print("=" * 60)
    
    for query in queries:
        print(f"\n📝 Query: {query}")
        response = agent.chat(query)
        print(f"💡 Answer: {response}")
        print("-" * 40)


def rag_with_query_context():
    """Demonstrate per-query context injection for RAG."""
    
    # Create a general agent
    agent = Agent(
        name="Research Assistant",
        instructions="You answer questions based on the context provided in each query.",
        verbose=False
    )
    
    # Simulate retrieved context (in real RAG, this comes from vector search)
    retrieved_context = """
    The Pacific Ocean is the largest and deepest ocean on Earth.
    It covers approximately 165.25 million square kilometers.
    The Mariana Trench, located in the Pacific, is the deepest known point at 10,994 meters.
    The Pacific Ocean was named by explorer Ferdinand Magellan in 1520.
    """
    
    query = "What is the deepest point in the Pacific Ocean?"
    
    # Build prompt with context (RAG pattern)
    prompt_with_context = f"""Use the following context to answer the question.

Context:
{retrieved_context}

Question: {query}

Answer based only on the context provided:"""
    
    print("\n" + "=" * 60)
    print("RAG WITH PER-QUERY CONTEXT INJECTION")
    print("=" * 60)
    
    print(f"\n📚 Context: {retrieved_context[:100]}...")
    print(f"\n📝 Query: {query}")
    
    response = agent.chat(prompt_with_context)
    print(f"\n💡 Answer: {response}")


def main():
    """Run all basic RAG examples."""
    print("\n🚀 PraisonAI Basic RAG Examples\n")
    
    # Example 1: Basic RAG with knowledge base
    basic_rag_example()
    
    # Example 2: Per-query context injection
    rag_with_query_context()
    
    print("\n✅ Basic RAG examples completed!")


if __name__ == "__main__":
    main()
