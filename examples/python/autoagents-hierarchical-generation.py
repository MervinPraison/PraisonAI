"""
AutoAgents Hierarchical Generation Example

This example demonstrates hierarchical agent patterns using PraisonAI
for structured task delegation and coordinated workflows.
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import internet_search

print("=== AutoAgents Hierarchical Generation Example ===\n")

# Create manager agent for hierarchical coordination
manager_agent = Agent(
    name="Project Manager",
    role="Project Coordinator",
    goal="Coordinate hierarchical task execution and manage team workflow",
    backstory="Experienced manager who excels at breaking down complex projects and coordinating teams",
    tools=[internet_search],
    allow_delegation=True,
    verbose=True
)

# Create specialist agent for execution
research_agent = Agent(
    name="Research Specialist", 
    role="Market Research Analyst",
    goal="Conduct thorough market research and analysis",
    backstory="Expert researcher skilled in market analysis and competitive intelligence",
    tools=[internet_search],
    verbose=True
)

# Hierarchical task structure
planning_task = Task(
    description="""Plan a comprehensive market research project for electric vehicles:
    1. Define research scope and objectives
    2. Identify key research areas and methodologies
    3. Create task breakdown structure
    4. Set deliverable requirements for execution team
    
    Prepare clear instructions for the research specialist.""",
    expected_output="Detailed project plan with clear research instructions",
    agent=manager_agent
)

execution_task = Task(
    description="""Execute the market research plan:
    1. Follow the research plan from the project manager
    2. Conduct comprehensive market analysis
    3. Gather competitive intelligence and market data
    4. Prepare detailed findings report
    
    Use the planning guidance to ensure complete coverage.""",
    expected_output="Comprehensive market research report with findings",
    agent=research_agent,
    context=[planning_task]
)

# Run hierarchical workflow
agents_system = PraisonAIAgents(
    agents=[manager_agent, research_agent],
    tasks=[planning_task, execution_task],
    process="sequential",
    verbose=True
)

print("Starting hierarchical agent generation...")
result = agents_system.start()

print(f"\nHierarchical Result: {result[:200]}...")
print("\n✅ AutoAgents hierarchical generation complete!")
print("Demonstrated coordinated hierarchical workflow between manager and specialist agents.")