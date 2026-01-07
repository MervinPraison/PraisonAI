"""
Multi-Document RAG: Synthesizing Information Across Sources

This example demonstrates retrieving and synthesizing information from
multiple documents to answer complex questions.

RAG Concept: Real-world questions often require combining information
from multiple sources. Multi-document RAG retrieves relevant chunks
from different documents and synthesizes a coherent answer.
"""

from praisonaiagents import Agent

# Sample knowledge base: Multiple documents on different topics
CLIMATE_REPORT = {
    "id": "climate_2024",
    "source": "Global Climate Report 2024",
    "content": """
    Global Climate Report 2024 - Executive Summary
    
    Global temperatures in 2024 reached 1.45°C above pre-industrial levels,
    making it the warmest year on record. Key findings:
    
    - Arctic sea ice extent hit a new minimum in September
    - Ocean heat content reached unprecedented levels
    - Extreme weather events increased by 23% compared to the decade average
    - CO2 concentrations reached 422 ppm, up from 417 ppm in 2023
    
    Regional impacts varied significantly. Europe experienced its hottest
    summer, while parts of South America faced severe drought conditions.
    The economic cost of climate-related disasters exceeded $380 billion.
    """
}

ENERGY_REPORT = {
    "id": "energy_2024",
    "source": "World Energy Outlook 2024",
    "content": """
    World Energy Outlook 2024 - Key Highlights
    
    Renewable energy capacity grew by 35% in 2024, led by solar and wind.
    Major developments:
    
    - Solar installations reached 1.5 TW cumulative capacity globally
    - Wind power generated 12% of global electricity
    - Battery storage capacity doubled to 500 GWh
    - Electric vehicle sales reached 20 million units
    
    Despite progress, fossil fuels still account for 75% of primary energy.
    Investment in clean energy reached $1.8 trillion, but $4 trillion annually
    is needed to meet net-zero targets by 2050.
    """
}

POLICY_REPORT = {
    "id": "policy_2024",
    "source": "Climate Policy Tracker 2024",
    "content": """
    Climate Policy Tracker 2024 - Global Progress
    
    145 countries have now committed to net-zero emissions targets.
    Policy developments:
    
    - EU Carbon Border Adjustment Mechanism fully implemented
    - US Inflation Reduction Act drove $300B in clean energy investment
    - China pledged to peak emissions before 2030
    - India launched National Green Hydrogen Mission
    
    Carbon pricing now covers 23% of global emissions, up from 20% in 2023.
    Average carbon price increased to $45/ton. However, only 4% of emissions
    are priced at levels consistent with Paris Agreement goals ($100+/ton).
    """
}

TECH_REPORT = {
    "id": "tech_2024",
    "source": "Climate Technology Review 2024",
    "content": """
    Climate Technology Review 2024 - Breakthrough Innovations
    
    Several climate technologies reached commercial viability in 2024:
    
    - Direct Air Capture: Costs fell to $400/ton CO2, down from $600 in 2022
    - Green Hydrogen: Production costs reached $3/kg in optimal locations
    - Solid-state Batteries: Energy density improved 40%, enabling longer EV range
    - Perovskite Solar Cells: Efficiency reached 33%, approaching silicon limits
    
    Emerging technologies to watch:
    - Enhanced geothermal systems showing promise in non-volcanic regions
    - Ocean-based carbon removal gaining investment interest
    - AI-optimized grid management reducing curtailment by 15%
    """
}

# Combine all documents
ALL_DOCUMENTS = [CLIMATE_REPORT, ENERGY_REPORT, POLICY_REPORT, TECH_REPORT]


def multi_document_rag():
    """Demonstrate RAG across multiple documents."""
    
    # Create agent with multi-document knowledge
    agent = Agent(
        name="Climate Analyst",
        instructions="""You are a climate and energy analyst.
        Synthesize information from multiple reports to answer questions.
        When information comes from different sources, mention which reports
        you're drawing from. Provide comprehensive, well-rounded answers.""",
        knowledge=ALL_DOCUMENTS,
        user_id="multi_doc_demo"
    )
    
    # Questions that require multi-document synthesis
    queries = [
        "What is the current state of global climate and what are we doing about it?",
        "How is renewable energy progressing and what policies support it?",
        "What technologies are emerging to address climate change?",
        "Compare the economic investment in clean energy with climate damage costs."
    ]
    
    print("=" * 60)
    print("MULTI-DOCUMENT RAG: Climate Analysis")
    print("=" * 60)
    print(f"\nKnowledge base: {len(ALL_DOCUMENTS)} documents")
    print(f"Sources: {[d['source'] for d in ALL_DOCUMENTS]}")
    
    for query in queries:
        print(f"\n📝 Query: {query}")
        response = agent.chat(query)
        print(f"💡 Answer: {response[:400]}..." if len(str(response)) > 400 else f"💡 Answer: {response}")
        print("-" * 40)


def cross_reference_example():
    """Show how agents can cross-reference information."""
    
    print("\n" + "=" * 60)
    print("CROSS-REFERENCING ACROSS DOCUMENTS")
    print("=" * 60)
    
    agent = Agent(
        name="Cross-Reference Analyst",
        instructions="""You are an analyst who excels at finding connections
        between different reports. When answering:
        1. Identify relevant information from each source
        2. Note any contradictions or complementary data
        3. Synthesize a coherent narrative
        4. Cite your sources explicitly.""",
        knowledge=ALL_DOCUMENTS,
        user_id="cross_ref_demo"
    )
    
    query = """
    Analyze the relationship between renewable energy growth (from Energy Report),
    policy support (from Policy Report), and technology costs (from Tech Report).
    How do these factors reinforce each other?
    """
    
    print(f"\n📝 Complex Query: {query.strip()}")
    response = agent.chat(query)
    print(f"\n💡 Synthesized Answer:\n{response}")


def document_filtering():
    """Demonstrate filtering documents by metadata."""
    
    print("\n" + "=" * 60)
    print("DOCUMENT FILTERING BY SOURCE")
    print("=" * 60)
    
    # Create agents focused on specific document types
    policy_agent = Agent(
        name="Policy Expert",
        instructions="You are a policy expert. Focus only on policy-related information.",
        knowledge=[POLICY_REPORT],
        user_id="policy_expert"
    )
    
    tech_agent = Agent(
        name="Technology Expert",
        instructions="You are a technology expert. Focus on technical innovations.",
        knowledge=[TECH_REPORT],
        user_id="tech_expert"
    )
    
    query = "What progress has been made in addressing climate change?"
    
    print(f"\n📝 Query: {query}")
    
    print("\n🏛️ Policy Expert's View:")
    policy_response = policy_agent.chat(query)
    print(f"   {policy_response[:250]}...")
    
    print("\n🔬 Technology Expert's View:")
    tech_response = tech_agent.chat(query)
    print(f"   {tech_response[:250]}...")
    
    print("\n💡 Note: Different document subsets yield different perspectives!")


def multi_document_best_practices():
    """Share best practices for multi-document RAG."""
    
    print("\n" + "=" * 60)
    print("MULTI-DOCUMENT RAG BEST PRACTICES")
    print("=" * 60)
    
    print("""
    📚 Best Practices for Multi-Document RAG:
    
    1. **Document Metadata**
       - Include source, date, author in each document
       - Enables filtering and citation
    
    2. **Consistent Chunking**
       - Use similar chunk sizes across documents
       - Maintains balanced retrieval
    
    3. **Source Diversity**
       - Retrieve from multiple sources when possible
       - Reduces single-source bias
    
    4. **Conflict Resolution**
       - Instruct agent how to handle contradictions
       - Prefer newer sources or authoritative ones
    
    5. **Citation Requirements**
       - Ask agent to cite sources in responses
       - Enables verification and trust
    
    Example configuration:
    ```python
    documents = [
        {"id": "doc1", "source": "Report A", "date": "2024-01", "content": "..."},
        {"id": "doc2", "source": "Report B", "date": "2024-06", "content": "..."},
    ]
    
    agent = Agent(
        knowledge=documents,
        instructions="Always cite which report your information comes from."
    )
    ```
    """)


def main():
    """Run all multi-document RAG examples."""
    print("\n🚀 PraisonAI Multi-Document RAG Examples\n")
    
    # Example 1: Basic multi-document RAG
    multi_document_rag()
    
    # Example 2: Cross-referencing
    cross_reference_example()
    
    # Example 3: Document filtering
    document_filtering()
    
    # Example 4: Best practices
    multi_document_best_practices()
    
    print("\n✅ Multi-document RAG examples completed!")


if __name__ == "__main__":
    main()
