"""
Auto RAG: Intelligent Retrieval Decisions

This example demonstrates AutoRagAgent - an agent that automatically decides
when to retrieve context based on the query type.

RAG Concept: Conditional retrieval - not every query needs RAG. Simple greetings
or general knowledge questions can be answered directly, while domain-specific
questions benefit from retrieval.
"""

from praisonaiagents import Agent, AutoRagAgent

# Sample knowledge base: Software development best practices as text strings
DEV_PRACTICES = [
    """Code Review Guidelines:
    - Review code within 24 hours of submission
    - Focus on logic, security, and maintainability
    - Limit reviews to 400 lines of code at a time
    - Use constructive language and suggest alternatives
    - Automate style checks with linters""",
    
    """Testing Strategy:
    - Aim for 80% code coverage minimum
    - Write unit tests before integration tests
    - Use mocking for external dependencies
    - Run tests in CI/CD pipeline before merge
    - Include edge cases and error scenarios""",
    
    """Documentation Standards:
    - Document public APIs with examples
    - Keep README files up to date
    - Use inline comments for complex logic only
    - Maintain a changelog for version history
    - Include setup instructions for new developers""",
    
    """Security Practices:
    - Never commit secrets or API keys
    - Use environment variables for configuration
    - Validate all user inputs
    - Keep dependencies updated
    - Conduct regular security audits"""
]


def auto_rag_basic():
    """Demonstrate AutoRagAgent with automatic retrieval decisions."""
    
    # Build context from knowledge
    context = "\n\n".join(DEV_PRACTICES)
    
    # Create base agent with context in instructions
    base_agent = Agent(
        name="Dev Coach",
        instructions=f"""You are a software development coach.
        Answer questions about development best practices.
        Be concise and practical in your responses.
        
        KNOWLEDGE BASE:
        {context}""",
        output="silent"
    )
    
    # Wrap with AutoRagAgent for intelligent retrieval
    auto_agent = AutoRagAgent(agent=base_agent)
    
    # Mix of queries - some need retrieval, some don't
    queries = [
        # Should trigger retrieval (domain-specific)
        "What are the code review guidelines?",
        "How much code coverage should we aim for?",
        
        # Should skip retrieval (general/greeting)
        "Hello, how are you?",
        "What is 2 + 2?",
        
        # Should trigger retrieval (domain-specific)
        "What security practices should we follow?",
    ]
    
    print("=" * 60)
    print("AUTO RAG: Intelligent Retrieval Decisions")
    print("=" * 60)
    print("\nAutoRagAgent decides when to retrieve based on query type.\n")
    
    for query in queries:
        print(f"📝 Query: {query}")
        response = auto_agent.chat(query)
        print(f"💡 Answer: {response[:200]}..." if len(str(response)) > 200 else f"💡 Answer: {response}")
        print("-" * 40)


def auto_rag_with_policies():
    """Demonstrate different retrieval policies."""
    from praisonaiagents import AutoRagConfig
    from praisonaiagents.agents.auto_rag_agent import RetrievalPolicy
    
    # Build context
    context = "\n\n".join(DEV_PRACTICES)
    
    # Create base agent
    base_agent = Agent(
        name="Policy Demo Agent",
        instructions=f"""You answer questions about software development.
        
        KNOWLEDGE BASE:
        {context}""",
        output="silent"
    )
    
    print("\n" + "=" * 60)
    print("RETRIEVAL POLICIES COMPARISON")
    print("=" * 60)
    
    query = "What are the documentation standards?"
    
    # Policy: AUTO (default) - agent decides
    auto_config = AutoRagConfig(retrieval_policy=RetrievalPolicy.AUTO)
    auto_agent = AutoRagAgent(agent=base_agent, config=auto_config)
    
    print(f"\n📝 Query: {query}")
    print("\n🔄 Policy: AUTO (agent decides)")
    response = auto_agent.chat(query)
    print(f"   Answer: {response[:150]}...")
    
    # Policy: ALWAYS - always retrieve
    always_config = AutoRagConfig(retrieval_policy=RetrievalPolicy.ALWAYS)
    always_agent = AutoRagAgent(agent=base_agent, config=always_config)
    
    print("\n🔄 Policy: ALWAYS (force retrieval)")
    response = always_agent.chat(query)
    print(f"   Answer: {response[:150]}...")
    
    # Policy: NEVER - never retrieve (use parametric knowledge only)
    never_config = AutoRagConfig(retrieval_policy=RetrievalPolicy.NEVER)
    never_agent = AutoRagAgent(agent=base_agent, config=never_config)
    
    print("\n🔄 Policy: NEVER (no retrieval)")
    response = never_agent.chat(query)
    print(f"   Answer: {response[:150]}...")


def auto_rag_config_options():
    """Demonstrate AutoRagConfig options."""
    from praisonaiagents import AutoRagConfig
    
    # Build context
    context = "\n\n".join(DEV_PRACTICES)
    
    base_agent = Agent(
        name="Config Demo",
        instructions=f"""You are a helpful assistant with development knowledge.
        
        KNOWLEDGE BASE:
        {context}""",
        output="silent"
    )
    
    print("\n" + "=" * 60)
    print("AUTO RAG CONFIG OPTIONS")
    print("=" * 60)
    
    # Config with citations enabled
    config_with_citations = AutoRagConfig(
        include_citations=True,
        top_k=3,
        max_context_tokens=2000
    )
    agent_with_citations = AutoRagAgent(agent=base_agent, config=config_with_citations)
    
    query = "What testing practices should we follow?"
    print(f"\n📝 Query: {query}")
    
    print("\n🔄 With citations enabled (top_k=3):")
    response = agent_with_citations.chat(query)
    print(f"   {response[:200]}...")
    
    # Config without citations
    config_no_citations = AutoRagConfig(
        include_citations=False,
        top_k=5
    )
    agent_no_citations = AutoRagAgent(agent=base_agent, config=config_no_citations)
    
    print("\n🔄 Without citations (top_k=5):")
    response = agent_no_citations.chat(query)
    print(f"   {response[:200]}...")


def main():
    """Run all auto RAG examples."""
    print("\n🚀 PraisonAI Auto RAG Examples\n")
    
    # Example 1: Basic AutoRagAgent
    auto_rag_basic()
    
    # Example 2: Different retrieval policies
    auto_rag_with_policies()
    
    # Example 3: Config options
    auto_rag_config_options()
    
    print("\n✅ Auto RAG examples completed!")


if __name__ == "__main__":
    main()
