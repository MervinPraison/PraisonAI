from praisonaiagents import Agent, Task, PraisonAIAgents
from datetime import datetime
import asyncio

def process_time():
    """Simulate processing"""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Processing at: {current_time}")
    return f"Processed at {current_time}"

# Create parallel processing agents
agent1 = Agent(
    name="Processor 1",
    role="Time collector",
    goal="Get the time and return it",
    tools=[process_time]
)

agent2 = Agent(
    name="Processor 2",
    role="Time collector",
    goal="Get the time and return it",
    tools=[process_time]
)

agent3 = Agent(
    name="Processor 3",
    role="Time collector",
    goal="Get the time and return it",
    tools=[process_time]
)

aggregator = Agent(
    name="Aggregator",
    role="Result aggregator",
    goal="Collect all the processed time from all tasks"
)

# Create parallel tasks with memory disabled
task1 = Task(
    name="process_1",
    description="Use process_time tool to get the time",
    expected_output="processed time",
    agent=agent1,
    is_start=True,
    async_execution=True
)

task2 = Task(
    name="process_2",
    description="Use process_time tool to get the time",
    expected_output="processed time",
    agent=agent2,
    is_start=True,
    async_execution=True
)

task3 = Task(
    name="process_3",
    description="Use process_time tool to get the time",
    expected_output="processed time",
    agent=agent3,
    is_start=True,
    async_execution=True
)

aggregate_task = Task(
    name="aggregate",
    description="Collect all the processed time from all tasks",
    expected_output="Output all the processed time from all tasks and just the time",
    agent=aggregator,
    context=[task1, task2, task3]
)

async def main():

    # Create workflow manager
    workflow = PraisonAIAgents(
        agents=[agent1, agent2, agent3, aggregator],
        tasks=[task1, task2, task3, aggregate_task],
        process="workflow"
    )

    # Run parallel workflow
    results = await workflow.astart()

    # Print results
    print("\nParallel Processing Results:")
    for task_id, result in results["task_results"].items():
        if result:
            print(f"Task {task_id}: {result.raw}")

# Run the async main function
if __name__ == "__main__":
    asyncio.run(main())
