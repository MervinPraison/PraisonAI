"""
RAG Multi-Agent Example

This example demonstrates how multiple agents can work together
on a shared knowledge base for collaborative RAG.

Usage:
    python rag_multi_agent.py
"""

from praisonaiagents import Agent, PraisonAIAgents, Task


# Shared knowledge base content
SHARED_KNOWLEDGE = """
# Climate Technology Report 2024

## Executive Summary
Global investment in climate technology reached $150 billion in 2024, 
a 25% increase from the previous year. Key areas of growth include 
renewable energy, carbon capture, and sustainable transportation.

## Key Findings

### Renewable Energy
- Solar capacity grew by 40% globally
- Wind energy now provides 15% of global electricity
- Battery storage costs decreased by 20%

### Carbon Capture
- Direct air capture costs fell to $400/ton
- 50 new carbon capture facilities announced
- Total captured CO2 reached 50 million tons

### Sustainable Transportation
- Electric vehicle sales reached 25 million units
- Hydrogen fuel cell technology advancing rapidly
- Sustainable aviation fuel production doubled

## Recommendations
1. Increase investment in grid infrastructure
2. Accelerate carbon capture deployment
3. Support EV charging network expansion
"""


def main():
    print("=" * 60)
    print("Multi-Agent RAG: Collaborative Analysis")
    print("=" * 60)
    
    # Create specialized agents with shared knowledge
    researcher = Agent(
        name="Researcher",
        role="Research Analyst",
        goal="Find and analyze relevant information",
        instructions=f"""You are a research analyst. Your job is to:
        1. Extract key facts and data points
        2. Provide detailed analysis
        3. Cite specific sections
        
        KNOWLEDGE BASE:
        {SHARED_KNOWLEDGE}""",
        verbose=False
    )
    
    summarizer = Agent(
        name="Summarizer",
        role="Content Summarizer",
        goal="Create concise summaries",
        instructions=f"""You are a content summarizer. Your job is to:
        1. Take research findings and create clear summaries
        2. Highlight the most important points
        3. Make complex information accessible
        
        KNOWLEDGE BASE:
        {SHARED_KNOWLEDGE}""",
        verbose=False
    )
    
    writer = Agent(
        name="Writer",
        role="Report Writer",
        goal="Create well-structured reports",
        instructions=f"""You are a report writer. Your job is to:
        1. Combine research and summaries into a cohesive report
        2. Ensure proper structure and flow
        3. Include key statistics
        
        KNOWLEDGE BASE:
        {SHARED_KNOWLEDGE}""",
        verbose=False
    )
    
    # Define tasks
    research_task = Task(
        description="Research the main investment trends and growth areas in climate technology",
        expected_output="Detailed research notes with key statistics",
        agent=researcher,
    )
    
    summary_task = Task(
        description="Summarize the research findings into 5 key bullet points",
        expected_output="Bullet-point summary of main findings",
        agent=summarizer,
    )
    
    report_task = Task(
        description="Write a brief executive briefing based on the research and summary",
        expected_output="A 2-paragraph executive briefing",
        agent=writer,
    )
    
    # Run the multi-agent workflow
    print("\n🔄 Running multi-agent workflow...")
    
    agents = PraisonAIAgents(
        agents=[researcher, summarizer, writer],
        tasks=[research_task, summary_task, report_task],
        process="sequential",
        verbose=False
    )
    
    result = agents.start()
    
    print("\n" + "=" * 60)
    print("Final Report")
    print("=" * 60)
    print(result)
    
    print("\n✅ Multi-agent RAG example completed!")


if __name__ == "__main__":
    main()
