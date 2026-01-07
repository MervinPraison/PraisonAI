"""
Graph-Assisted RAG: Relationship-Aware Retrieval

This example demonstrates how graph structures can enhance RAG by
capturing relationships between entities and enabling path-based retrieval.

RAG Concept: Traditional vector search finds similar documents but misses
relationships. Graph-assisted RAG understands connections between entities,
enabling multi-hop reasoning and relationship-aware answers.
"""

from praisonaiagents import Agent

# Sample knowledge base: Interconnected entities (simulating a knowledge graph)
ENTITY_KNOWLEDGE = [
    {
        "id": "person_einstein",
        "type": "person",
        "content": """
        Albert Einstein (1879-1955) was a theoretical physicist who developed
        the theory of relativity. He received the Nobel Prize in Physics in 1921
        for his explanation of the photoelectric effect. Einstein worked at the
        Institute for Advanced Study in Princeton from 1933 until his death.
        Key relationships: Collaborated with Niels Bohr, influenced by Max Planck,
        mentored by Heinrich Weber.
        """
    },
    {
        "id": "person_bohr",
        "type": "person",
        "content": """
        Niels Bohr (1885-1962) was a Danish physicist who made foundational
        contributions to understanding atomic structure and quantum theory.
        He received the Nobel Prize in Physics in 1922. Bohr founded the
        Institute of Theoretical Physics in Copenhagen.
        Key relationships: Debated with Einstein on quantum mechanics,
        mentored Werner Heisenberg, influenced by Ernest Rutherford.
        """
    },
    {
        "id": "person_heisenberg",
        "type": "person",
        "content": """
        Werner Heisenberg (1901-1976) was a German physicist and pioneer of
        quantum mechanics. He formulated the uncertainty principle in 1927.
        He received the Nobel Prize in Physics in 1932.
        Key relationships: Student of Niels Bohr, collaborated with Max Born,
        worked with Wolfgang Pauli.
        """
    },
    {
        "id": "concept_relativity",
        "type": "concept",
        "content": """
        Theory of Relativity: A framework developed by Albert Einstein consisting
        of special relativity (1905) and general relativity (1915). Special
        relativity deals with objects moving at constant speeds, introducing
        E=mc². General relativity describes gravity as the curvature of spacetime.
        Related concepts: Spacetime, time dilation, gravitational waves.
        Applications: GPS satellites, particle accelerators, cosmology.
        """
    },
    {
        "id": "concept_quantum",
        "type": "concept",
        "content": """
        Quantum Mechanics: A fundamental theory describing nature at atomic scales.
        Key principles include wave-particle duality, superposition, and entanglement.
        Developed through contributions from Planck, Bohr, Heisenberg, Schrödinger.
        Related concepts: Uncertainty principle, quantum tunneling, wave function.
        Applications: Semiconductors, lasers, MRI machines, quantum computing.
        """
    },
    {
        "id": "institution_princeton",
        "type": "institution",
        "content": """
        Institute for Advanced Study (Princeton): A private research center
        founded in 1930. Notable members include Albert Einstein, John von Neumann,
        Kurt Gödel, and Robert Oppenheimer. The institute focuses on theoretical
        research in mathematics, natural sciences, and humanities.
        Location: Princeton, New Jersey, USA.
        """
    },
    {
        "id": "institution_copenhagen",
        "type": "institution",
        "content": """
        Niels Bohr Institute (Copenhagen): Founded in 1921 by Niels Bohr as the
        Institute of Theoretical Physics. It became a world center for quantum
        mechanics research. Notable visitors included Heisenberg, Pauli, and Dirac.
        The "Copenhagen interpretation" of quantum mechanics originated here.
        Location: Copenhagen, Denmark.
        """
    },
    {
        "id": "event_solvay",
        "type": "event",
        "content": """
        Solvay Conferences: Series of physics conferences held in Brussels since 1911.
        The 1927 Fifth Solvay Conference is famous for the Bohr-Einstein debates
        on quantum mechanics. Attendees included Einstein, Bohr, Heisenberg,
        Schrödinger, Dirac, and Marie Curie. These conferences shaped modern physics.
        """
    }
]


def graph_aware_rag():
    """Demonstrate relationship-aware retrieval."""
    
    # Build context from entity knowledge
    context = "\n\n".join([f"[{e['type'].upper()}: {e['id']}]\n{e['content']}" for e in ENTITY_KNOWLEDGE])
    
    # Create agent with entity knowledge
    agent = Agent(
        name="Physics Historian",
        instructions=f"""You are a physics historian who understands the relationships
        between scientists, concepts, and institutions. When answering:
        1. Trace connections between entities
        2. Explain how ideas and people influenced each other
        3. Reference specific relationships mentioned in the knowledge base
        4. Build a narrative that shows the interconnected nature of physics history.
        
        KNOWLEDGE GRAPH:
        {context}""",
        verbose=False
    )
    
    # Relationship-focused queries
    queries = [
        "How were Einstein and Bohr connected?",
        "Trace the lineage of quantum mechanics through its key figures.",
        "What institutions were central to 20th century physics?",
        "How did the Solvay Conferences shape physics?"
    ]
    
    print("=" * 60)
    print("GRAPH-ASSISTED RAG: Physics History Network")
    print("=" * 60)
    print("\nKnowledge graph entities:")
    for entity in ENTITY_KNOWLEDGE:
        print(f"  - [{entity['type']}] {entity['id']}")
    
    for query in queries:
        print(f"\n📝 Query: {query}")
        response = agent.chat(query)
        print(f"💡 Answer: {response[:350]}..." if len(str(response)) > 350 else f"💡 Answer: {response}")
        print("-" * 40)


def multi_hop_reasoning():
    """Demonstrate multi-hop reasoning across entities."""
    
    print("\n" + "=" * 60)
    print("MULTI-HOP REASONING")
    print("=" * 60)
    
    # Build context
    context = "\n\n".join([f"[{e['type'].upper()}: {e['id']}]\n{e['content']}" for e in ENTITY_KNOWLEDGE])
    
    agent = Agent(
        name="Connection Finder",
        instructions=f"""You excel at finding indirect connections between entities.
        When asked about relationships, trace the path through intermediate entities.
        Format your answer to show the chain of connections.
        
        KNOWLEDGE GRAPH:
        {context}""",
        verbose=False
    )
    
    # Multi-hop query requiring traversal
    query = """
    What is the connection between the uncertainty principle and Princeton?
    (Hint: trace through people and their relationships)
    """
    
    print(f"\n📝 Multi-hop Query: {query.strip()}")
    print("\n🔗 Expected path: Uncertainty Principle → Heisenberg → Bohr → Einstein → Princeton")
    
    response = agent.chat(query)
    print(f"\n💡 Answer:\n{response}")


def entity_type_filtering():
    """Show filtering by entity type."""
    
    print("\n" + "=" * 60)
    print("ENTITY TYPE FILTERING")
    print("=" * 60)
    
    # Filter to only people
    people_only = [e for e in ENTITY_KNOWLEDGE if e['type'] == 'person']
    people_context = "\n\n".join([f"[{e['id']}]\n{e['content']}" for e in people_only])
    
    people_agent = Agent(
        name="Biographer",
        instructions=f"""You are a biographer focused on scientists' lives and relationships.
        
        SCIENTISTS:
        {people_context}""",
        verbose=False
    )
    
    # Filter to only concepts
    concepts_only = [e for e in ENTITY_KNOWLEDGE if e['type'] == 'concept']
    concepts_context = "\n\n".join([f"[{e['id']}]\n{e['content']}" for e in concepts_only])
    
    concept_agent = Agent(
        name="Concept Explainer",
        instructions=f"""You explain scientific concepts and their relationships.
        
        CONCEPTS:
        {concepts_context}""",
        verbose=False
    )
    
    query = "Tell me about the major developments in early 20th century physics."
    
    print(f"\n📝 Query: {query}")
    
    print("\n👤 People-focused view:")
    response1 = people_agent.chat(query)
    print(f"   {response1[:250]}...")
    
    print("\n💡 Concept-focused view:")
    response2 = concept_agent.chat(query)
    print(f"   {response2[:250]}...")


def graph_rag_patterns():
    """Explain graph RAG patterns."""
    
    print("\n" + "=" * 60)
    print("GRAPH RAG PATTERNS")
    print("=" * 60)
    
    print("""
    📊 Graph-Assisted RAG Patterns:
    
    1. **Entity-Centric Retrieval**
       - Store entities with their relationships
       - Query retrieves entity + connected entities
       - Good for: "Tell me about X and its connections"
    
    2. **Path-Based Retrieval**
       - Find paths between two entities
       - Retrieve all nodes along the path
       - Good for: "How is X related to Y?"
    
    3. **Neighborhood Expansion**
       - Start with query-matched entities
       - Expand to include 1-hop or 2-hop neighbors
       - Good for: Comprehensive context
    
    4. **Subgraph Extraction**
       - Extract relevant subgraph for query
       - Include nodes and edges as context
       - Good for: Complex multi-entity questions
    
    Implementation in PraisonAI:
    ```python
    # Structure knowledge as entities with relationships
    entities = [
        {
            "id": "entity_1",
            "type": "person",
            "content": "...",
            "relationships": ["entity_2", "entity_3"]
        },
        ...
    ]
    
    # Agent retrieves related entities automatically
    agent = Agent(
        knowledge=entities,
        instructions="Trace relationships between entities..."
    )
    ```
    """)


def main():
    """Run all graph-assisted RAG examples."""
    print("\n🚀 PraisonAI Graph-Assisted RAG Examples\n")
    
    # Example 1: Graph-aware retrieval
    graph_aware_rag()
    
    # Example 2: Multi-hop reasoning
    multi_hop_reasoning()
    
    # Example 3: Entity type filtering
    entity_type_filtering()
    
    # Example 4: Graph RAG patterns
    graph_rag_patterns()
    
    print("\n✅ Graph-assisted RAG examples completed!")


if __name__ == "__main__":
    main()
