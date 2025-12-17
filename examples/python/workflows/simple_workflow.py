"""
Simple Agentic Workflow Example

Demonstrates using Agent instances directly as workflow steps.
Each agent processes the input and passes output to the next agent.
"""

from praisonaiagents import Agent, Workflow

# Create agents with specific roles
researcher = Agent(
    name="Researcher",
    role="Research Analyst",
    goal="Research and provide information about topics",
    instructions="You are a research analyst. Provide concise, factual information."
)

writer = Agent(
    name="Writer", 
    role="Content Writer",
    goal="Write engaging content based on research",
    instructions="You are a content writer. Write clear, engaging content based on the research provided."
)

# Create workflow with agents as steps
workflow = Workflow(
    name="Simple Agentic Pipeline",
    steps=[researcher, writer]
)

if __name__ == "__main__":
    # Run workflow - agents process sequentially
    result = workflow.start(
        "What are the key benefits of AI agents?",
        verbose=True
    )
    
    print(f"\nFinal output:\n{result['output']}")
