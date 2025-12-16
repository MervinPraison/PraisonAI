"""
Task Callbacks Example

Demonstrates using on_task_start and on_task_complete callbacks
with PraisonAIAgents for workflow monitoring and logging.
"""

from praisonaiagents import Agent, Task, PraisonAIAgents

# Create an agent
researcher = Agent(
    name="Researcher",
    role="Research Assistant",
    goal="Find and summarize information",
    llm="gpt-4o-mini"
)

# Create tasks with variables
task1 = Task(
    name="research",
    description="Research the topic: {{topic}}",
    expected_output="A brief summary of the topic",
    agent=researcher,
    variables={"topic": "artificial intelligence"}
)

task2 = Task(
    name="summarize",
    description="Create a one-paragraph summary of the research.",
    expected_output="A concise summary",
    agent=researcher
)

# Define callbacks
def on_start(task, task_id):
    """Called before each task starts."""
    print(f"🚀 Starting task: {task.name} (ID: {task_id})")

def on_complete(task, output):
    """Called after each task completes."""
    print(f"✅ Completed task: {task.name}")
    print(f"   Output preview: {str(output)[:100]}...")

if __name__ == "__main__":
    # Create agents with callbacks
    agents = PraisonAIAgents(
        agents=[researcher],
        tasks=[task1, task2],
        process="workflow",
        on_task_start=on_start,
        on_task_complete=on_complete,
        variables={"global_var": "shared_value"}  # Global variables
    )
    
    # Run the workflow
    result = agents.start()
    print("\n🎉 Workflow completed!")
