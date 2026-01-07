"""
RAG Multi-Agent Example

This example demonstrates how multiple agents can share
the same knowledge base for collaborative RAG.

Usage:
    python rag_multi_agent.py

Requirements:
    pip install praisonaiagents[knowledge]
"""

from praisonaiagents import Agent, Knowledge, PraisonAIAgents, Task


def main():
    print("=" * 60)
    print("Multi-Agent RAG: Shared Knowledge Base")
    print("=" * 60)
    
    # Create shared knowledge base
    shared_knowledge = Knowledge()
    shared_knowledge.add("documents/")  # Add your documents directory
    
    # Create specialized agents sharing the same knowledge
    researcher = Agent(
        name="Researcher",
        role="Research Analyst",
        goal="Find and analyze relevant information from documents",
        instructions="""You are a research analyst. Your job is to:
        1. Search the knowledge base for relevant information
        2. Extract key facts and data points
        3. Provide detailed analysis with citations""",
        knowledge=shared_knowledge,
    )
    
    summarizer = Agent(
        name="Summarizer",
        role="Content Summarizer",
        goal="Create concise summaries of complex information",
        instructions="""You are a content summarizer. Your job is to:
        1. Take research findings and create clear summaries
        2. Highlight the most important points
        3. Make complex information accessible""",
        knowledge=shared_knowledge,
    )
    
    writer = Agent(
        name="Writer",
        role="Report Writer",
        goal="Create well-structured reports",
        instructions="""You are a report writer. Your job is to:
        1. Combine research and summaries into a cohesive report
        2. Ensure proper structure and flow
        3. Include citations where appropriate""",
        knowledge=shared_knowledge,
    )
    
    # Define tasks
    research_task = Task(
        description="Research the main themes and findings in the documents",
        expected_output="Detailed research notes with citations",
        agent=researcher,
    )
    
    summary_task = Task(
        description="Summarize the research findings into key points",
        expected_output="Bullet-point summary of main findings",
        agent=summarizer,
    )
    
    report_task = Task(
        description="Write a comprehensive report based on the research and summary",
        expected_output="A well-structured report with introduction, findings, and conclusion",
        agent=writer,
    )
    
    # Run the multi-agent workflow
    agents = PraisonAIAgents(
        agents=[researcher, summarizer, writer],
        tasks=[research_task, summary_task, report_task],
        process="sequential",
    )
    
    result = agents.start()
    
    print("\n" + "=" * 60)
    print("Final Report")
    print("=" * 60)
    print(result)


if __name__ == "__main__":
    main()
