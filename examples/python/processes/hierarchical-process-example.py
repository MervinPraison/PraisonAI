"""
Hierarchical Process Example

This example demonstrates how to create a hierarchical process where a manager agent
delegates tasks to specialized worker agents. The manager orchestrates the workflow
and each specialized agent performs their specific tasks.

Features demonstrated:
- Hierarchical agent structure with manager and workers  
- Task delegation and coordination
- Specialized agent roles with different capabilities
- Process-level orchestration
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import duckduckgo

# Create Manager Agent
manager = Agent(
    name="Manager",
    role="Project Manager",
    goal="Coordinate research and analysis tasks among specialized agents",
    backstory="You are an experienced project manager who delegates tasks to specialized team members and synthesizes their work into a comprehensive report.",
    instructions="You coordinate tasks between researchers and analysts. Delegate research to the researcher, data analysis to the analyst, and writing to the writer."
)

# Create Specialized Worker Agents
researcher = Agent(
    name="Researcher", 
    role="Senior Researcher",
    goal="Conduct thorough research on given topics",
    backstory="You are a senior researcher with expertise in gathering and analyzing information from various sources.",
    tools=[duckduckgo],
    instructions="Conduct comprehensive research using web search. Provide detailed, factual information with sources."
)

data_analyst = Agent(
    name="DataAnalyst",
    role="Data Analyst", 
    goal="Analyze trends and patterns in research data",
    backstory="You are a skilled data analyst who can identify trends, patterns, and insights from research data.",
    instructions="Analyze research data to identify key trends, patterns, and actionable insights. Provide data-driven conclusions."
)

writer = Agent(
    name="Writer",
    role="Technical Writer",
    goal="Create well-structured reports and documentation", 
    backstory="You are a technical writer who excels at creating clear, comprehensive reports from research and analysis.",
    instructions="Create well-structured, professional reports that synthesize research findings and analysis into actionable insights."
)

# Define Hierarchical Tasks
research_task = Task(
    name="research_task",
    description="Research the latest trends in artificial intelligence and machine learning for business applications",
    expected_output="Comprehensive research report with current AI/ML trends, key players, and business applications",
    agent=researcher
)

analysis_task = Task(
    name="analysis_task", 
    description="Analyze the research findings to identify the most promising AI/ML trends for business adoption",
    expected_output="Analysis report highlighting top 5 AI/ML trends with business impact assessment",
    agent=data_analyst,
    context=[research_task]  # Depends on research task
)

writing_task = Task(
    name="writing_task",
    description="Create a final executive summary combining research and analysis into actionable business recommendations",
    expected_output="Executive summary with strategic recommendations for AI/ML adoption",
    agent=writer,
    context=[research_task, analysis_task]  # Depends on both previous tasks
)

coordination_task = Task(
    name="coordination_task",
    description="Oversee the entire research project, ensure quality and coordination between all team members",
    expected_output="Project oversight report confirming successful completion and quality of all deliverables",
    agent=manager,
    context=[research_task, analysis_task, writing_task]  # Oversees all tasks
)

# Create Hierarchical Process
agents = PraisonAIAgents(
    agents=[manager, researcher, data_analyst, writer],
    tasks=[research_task, analysis_task, writing_task, coordination_task],
    process="hierarchical",  # Hierarchical process type
    verbose=True
)

# Execute Hierarchical Process
result = agents.start()

print("\n" + "="*50)
print("HIERARCHICAL PROCESS COMPLETED")
print("="*50)
print(f"Final Result:\n{result}")