"""
Workflow with Agents Example

Demonstrates using Agent instances directly as workflow steps.
Agents are automatically wrapped and executed in sequence.
"""

from praisonaiagents import Workflow, Agent

# Create agents
researcher = Agent(
    name="Researcher",
    role="Research Specialist",
    goal="Find accurate information",
    llm="gpt-4o-mini"
)

writer = Agent(
    name="Writer", 
    role="Content Writer",
    goal="Write engaging content",
    llm="gpt-4o-mini"
)

editor = Agent(
    name="Editor",
    role="Content Editor", 
    goal="Polish and improve content",
    llm="gpt-4o-mini"
)

# Create workflow with agents as steps
workflow = Workflow(
    name="Content Pipeline",
    steps=[researcher, writer, editor]
)

if __name__ == "__main__":
    # Run the workflow
    result = workflow.start(
        "Write a short paragraph about artificial intelligence",
        verbose=True
    )
    
    print(f"\nFinal output:\n{result['output']}")
