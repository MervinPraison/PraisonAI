"""
RAG Document Q&A Example

This example demonstrates how to use RAG to answer questions
about documents with proper context injection.

Usage:
    python rag_pdf_qa.py
"""

from praisonaiagents import Agent


# Sample document content (simulating PDF content)
DOCUMENT_CONTENT = """
# Research Study: Impact of Remote Work on Productivity

## Abstract
This study examines the effects of remote work arrangements on employee 
productivity across 50 technology companies during 2023-2024.

## Methodology
- Survey of 5,000 employees across 50 companies
- Productivity metrics tracked over 12 months
- Control group: in-office workers
- Test group: remote and hybrid workers

## Key Findings

### Productivity Impact
- Remote workers showed 13% higher productivity on average
- Hybrid workers (3 days remote) showed 18% higher productivity
- Fully remote workers reported 25% better work-life balance

### Challenges Identified
- Communication delays increased by 15%
- Collaboration on complex projects took 10% longer
- New employee onboarding was 20% slower remotely

### Cost Analysis
- Companies saved average of $11,000 per remote employee annually
- Employees saved average of $4,500 in commuting costs
- Office space reduction saved 30% on real estate costs

## Recommendations
1. Implement hybrid work model (2-3 days remote)
2. Invest in collaboration tools
3. Create structured onboarding for remote hires
4. Establish clear communication protocols

## Conclusion
Remote work, when properly implemented, leads to improved productivity
and significant cost savings for both employers and employees.
"""


def main():
    # Method 1: Simple Agent with Context
    print("=" * 60)
    print("Method 1: Agent with Document Context")
    print("=" * 60)
    
    agent = Agent(
        name="Document Assistant",
        instructions=f"""You are a helpful assistant that answers questions about documents.
        Always cite specific sections when answering.
        
        DOCUMENT:
        {DOCUMENT_CONTENT}""",
        output="silent"
    )
    
    query = "What are the main topics covered in this document?"
    response = agent.chat(query)
    print(f"\n📝 Query: {query}")
    print(f"💡 Answer: {response}\n")
    
    # Method 2: Q&A with Citations
    print("=" * 60)
    print("Method 2: Q&A with Citations")
    print("=" * 60)
    
    citation_agent = Agent(
        name="Citation Assistant",
        instructions=f"""You answer questions about research documents.
        Always include citations in format [Section: Name].
        Be precise and reference specific data points.
        
        DOCUMENT:
        {DOCUMENT_CONTENT}""",
        output="silent"
    )
    
    queries = [
        "What methodology was used in this research?",
        "What were the key findings about productivity?",
        "What are the recommendations?"
    ]
    
    for query in queries:
        print(f"\n📝 Query: {query}")
        response = citation_agent.chat(query)
        print(f"💡 Answer: {response[:300]}...")
    
    # Method 3: Comparative Analysis
    print("\n" + "=" * 60)
    print("Method 3: Analytical Questions")
    print("=" * 60)
    
    analyst = Agent(
        name="Research Analyst",
        instructions=f"""You are a research analyst who provides insights from documents.
        Analyze data, identify trends, and provide actionable insights.
        
        DOCUMENT:
        {DOCUMENT_CONTENT}""",
        output="silent"
    )
    
    analysis_query = "Compare the benefits vs challenges of remote work based on this study"
    print(f"\n📝 Query: {analysis_query}")
    response = analyst.chat(analysis_query)
    print(f"💡 Analysis:\n{response}")
    
    print("\n✅ Document Q&A example completed!")


if __name__ == "__main__":
    main()
