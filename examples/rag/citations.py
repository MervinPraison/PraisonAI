"""
RAG with Citations: Source Attribution and Verification

This example demonstrates how to include citations and source references
in RAG responses for transparency and verification.

RAG Concept: Trust in AI-generated answers requires verification. Citations
link answers back to source documents, enabling fact-checking and building
user confidence.
"""

from praisonaiagents import Agent

# Sample knowledge base: Legal documents with clear sources
LEGAL_DOCUMENTS = [
    {
        "id": "policy_001",
        "source": "Employee Handbook v2024",
        "section": "Section 3.2 - Leave Policies",
        "content": """
        Annual Leave Entitlement:
        - Full-time employees: 20 days per year
        - Part-time employees: Pro-rated based on hours
        - Unused leave: Up to 5 days may carry over to next year
        - Leave requests: Submit at least 2 weeks in advance
        - Approval: Manager approval required for leave > 3 consecutive days
        """
    },
    {
        "id": "policy_002",
        "source": "Employee Handbook v2024",
        "section": "Section 4.1 - Remote Work",
        "content": """
        Remote Work Policy:
        - Eligibility: Employees in approved roles after 6 months tenure
        - Maximum: 3 days per week remote work allowed
        - Requirements: Reliable internet, dedicated workspace
        - Core hours: Must be available 10am-3pm local time
        - Equipment: Company provides laptop; employee provides internet
        """
    },
    {
        "id": "policy_003",
        "source": "Benefits Guide 2024",
        "section": "Chapter 2 - Health Insurance",
        "content": """
        Health Insurance Coverage:
        - Provider: BlueCross BlueShield
        - Coverage: Employee + dependents eligible
        - Premium: Company pays 80%, employee pays 20%
        - Deductible: $500 individual, $1000 family
        - Enrollment: During annual open enrollment or qualifying life event
        """
    },
    {
        "id": "policy_004",
        "source": "Benefits Guide 2024",
        "section": "Chapter 5 - Retirement",
        "content": """
        401(k) Retirement Plan:
        - Eligibility: After 90 days of employment
        - Company match: 100% up to 4% of salary
        - Vesting: Immediate vesting for employee contributions
        - Company match vesting: 3-year graded schedule
        - Investment options: 15 fund choices available
        """
    },
    {
        "id": "policy_005",
        "source": "Code of Conduct 2024",
        "section": "Article 7 - Conflicts of Interest",
        "content": """
        Conflict of Interest Policy:
        - Disclosure: All potential conflicts must be disclosed to HR
        - Outside employment: Requires written approval
        - Financial interests: Cannot hold >5% in competitors
        - Gifts: Cannot accept gifts valued over $50
        - Relationships: Must disclose family relationships with vendors
        """
    }
]


def basic_citations():
    """Demonstrate basic citation inclusion in RAG responses."""
    
    print("=" * 60)
    print("BASIC CITATIONS IN RAG")
    print("=" * 60)
    
    agent = Agent(
        name="HR Policy Expert",
        instructions="""You are an HR policy expert who answers employee questions.
        
        IMPORTANT: Always cite your sources using this format:
        [Source: Document Name, Section]
        
        Include the citation immediately after the relevant information.
        If information comes from multiple sources, cite each one.""",
        knowledge=LEGAL_DOCUMENTS,
        user_id="citation_demo"
    )
    
    queries = [
        "How many vacation days do I get?",
        "Can I work from home?",
        "What's the company match for 401k?"
    ]
    
    for query in queries:
        print(f"\n📝 Query: {query}")
        response = agent.chat(query)
        print(f"💡 Answer with Citations:\n{response}")
        print("-" * 40)


def structured_citations():
    """Demonstrate structured citation format."""
    
    print("\n" + "=" * 60)
    print("STRUCTURED CITATIONS")
    print("=" * 60)
    
    agent = Agent(
        name="Policy Researcher",
        instructions="""You provide policy information with structured citations.
        
        Format your response as:
        
        ANSWER:
        [Your answer here]
        
        SOURCES:
        1. [Document] - [Section] - [Relevant quote]
        2. [Document] - [Section] - [Relevant quote]
        
        Always include at least one source citation.""",
        knowledge=LEGAL_DOCUMENTS,
        user_id="structured_cite"
    )
    
    query = "What are the requirements for remote work eligibility?"
    
    print(f"\n📝 Query: {query}")
    response = agent.chat(query)
    print(f"\n💡 Structured Response:\n{response}")


def inline_citations():
    """Demonstrate inline citation style."""
    
    print("\n" + "=" * 60)
    print("INLINE CITATIONS (Academic Style)")
    print("=" * 60)
    
    agent = Agent(
        name="Academic Researcher",
        instructions="""You write responses with inline citations like academic papers.
        
        Use numbered citations [1], [2], etc. in the text.
        List full references at the end.
        
        Example:
        "Employees receive 20 days of leave [1]. Remote work is allowed
        for up to 3 days per week [2]."
        
        References:
        [1] Employee Handbook v2024, Section 3.2
        [2] Employee Handbook v2024, Section 4.1""",
        knowledge=LEGAL_DOCUMENTS,
        user_id="inline_cite"
    )
    
    query = "Summarize the key employee benefits."
    
    print(f"\n📝 Query: {query}")
    response = agent.chat(query)
    print(f"\n💡 Academic-Style Response:\n{response}")


def citation_verification():
    """Demonstrate citation verification concept."""
    
    print("\n" + "=" * 60)
    print("CITATION VERIFICATION")
    print("=" * 60)
    
    print("""
    🔍 Citation Verification Process:
    
    1. **Extract Citations**
       Parse the agent's response to find citation markers
       
    2. **Locate Source Documents**
       Match citations to documents in knowledge base
       
    3. **Verify Claims**
       Check if the cited text supports the claim
       
    4. **Flag Discrepancies**
       Highlight any mismatches or unsupported claims
    
    Example Verification:
    """)
    
    # Simulated verification
    claim = "Employees get 20 days of annual leave"
    cited_source = "Employee Handbook v2024, Section 3.2"
    source_text = "Full-time employees: 20 days per year"
    
    print(f"   Claim: \"{claim}\"")
    print(f"   Citation: {cited_source}")
    print(f"   Source Text: \"{source_text}\"")
    print("   Verification: ✅ SUPPORTED")
    
    print("""
    
    Implementation:
    ```python
    def verify_citation(claim: str, source_id: str, knowledge) -> bool:
        # Get source document
        source = knowledge.get(source_id)
        
        # Check if claim is supported by source
        # (In practice, use semantic similarity)
        return claim_supported_by_source(claim, source)
    ```
    """)


def multi_source_synthesis():
    """Demonstrate synthesizing from multiple sources with citations."""
    
    print("\n" + "=" * 60)
    print("MULTI-SOURCE SYNTHESIS WITH CITATIONS")
    print("=" * 60)
    
    agent = Agent(
        name="Benefits Advisor",
        instructions="""You synthesize information from multiple policy documents.
        
        When answering:
        1. Gather relevant information from all sources
        2. Synthesize into a coherent answer
        3. Cite each source for the specific information it provides
        4. Note if sources have different or complementary information
        
        Format: Include [Source: X] after each piece of information.""",
        knowledge=LEGAL_DOCUMENTS,
        user_id="multi_source"
    )
    
    query = "Give me a complete overview of employee benefits and policies."
    
    print(f"\n📝 Query: {query}")
    response = agent.chat(query)
    print(f"\n💡 Multi-Source Synthesis:\n{response}")


def citation_best_practices():
    """Share best practices for citations in RAG."""
    
    print("\n" + "=" * 60)
    print("CITATION BEST PRACTICES")
    print("=" * 60)
    
    print("""
    📚 Best Practices for RAG Citations:
    
    1. **Include Metadata in Knowledge Base**
       ```python
       documents = [
           {
               "id": "doc_001",
               "source": "Policy Manual",
               "section": "Chapter 3",
               "date": "2024-01-15",
               "author": "HR Department",
               "content": "..."
           }
       ]
       ```
    
    2. **Instruct Agent to Cite**
       - Be explicit in instructions about citation format
       - Provide examples of expected citation style
       - Require citations for factual claims
    
    3. **Use Consistent Citation Format**
       - Inline: [1], [2] with reference list
       - Parenthetical: (Source, Section)
       - Footnote style: ¹, ² with notes
    
    4. **Enable Verification**
       - Include document IDs for programmatic lookup
       - Store enough metadata to locate original
       - Consider including page numbers or paragraphs
    
    5. **Handle Missing Sources**
       - Instruct agent to acknowledge when info isn't in sources
       - Distinguish between sourced and general knowledge
       - Use phrases like "Based on the provided documents..."
    
    6. **Citation Granularity**
       - Document level: Good for general attribution
       - Section level: Better for verification
       - Quote level: Best for accuracy-critical applications
    
    Example Agent Instructions:
    ```python
    instructions = '''
    Answer questions using the provided documents.
    
    Rules:
    - Cite sources for all factual claims
    - Use format: [Source: Document Name, Section]
    - If information isn't in the documents, say so
    - Never make claims without citation
    '''
    ```
    """)


def main():
    """Run all citation examples."""
    print("\n🚀 PraisonAI RAG Citations Examples\n")
    
    # Example 1: Basic citations
    basic_citations()
    
    # Example 2: Structured citations
    structured_citations()
    
    # Example 3: Inline citations
    inline_citations()
    
    # Example 4: Citation verification
    citation_verification()
    
    # Example 5: Multi-source synthesis
    multi_source_synthesis()
    
    # Example 6: Best practices
    citation_best_practices()
    
    print("\n✅ Citation examples completed!")


if __name__ == "__main__":
    main()
