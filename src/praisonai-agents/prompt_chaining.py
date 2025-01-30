from praisonaiagents import Agent, Task, PraisonAIAgents
import time

def get_time_check():
    current_time = int(time.time())
    result = "even" if current_time % 2 == 0 else "odd"
    print(f"Time check: {current_time} is {result}")
    return result

# Create agents for each step in the chain
agent1 = Agent(
    name="Time Checker",
    role="Time checker",
    goal="Check if the time is even or odd",
    instructions="Check if the time is even or odd",
    tools=[get_time_check]
)

agent2 = Agent(
    name="Advanced Analyzer",
    role="Advanced data analyzer",
    goal="Perform in-depth analysis of processed data",
    instructions="Analyze the processed data in detail"
)

agent3 = Agent(
    name="Final Processor",
    role="Final data processor",
    goal="Generate final output based on analysis",
    instructions="Create final output based on analyzed data"
)

# Create tasks for each step
initial_task = Task(
    name="time_check",
    description="Getting time check and checking if it is even or odd",
    expected_output="Getting time check and checking if it is even or odd",
    agent=agent1,
    is_start=True,  # Mark as the starting task
    task_type="decision",  # This task will make a decision
    next_tasks=["advanced_analysis"],  # Next task if condition passes
    condition={
        "even": ["advanced_analysis"],  # If passes, go to advanced analysis
        "odd": "exit"  # If fails, exit the chain
    }
)

analysis_task = Task(
    name="advanced_analysis",
    description="Perform advanced analysis on the processed data",
    expected_output="Analyzed data ready for final processing",
    agent=agent2,
    next_tasks=["final_processing"]
)

final_task = Task(
    name="final_processing",
    description="Generate final output",
    expected_output="Final processed result",
    agent=agent3
)

# Create the workflow manager
workflow = PraisonAIAgents(
    agents=[agent1, agent2, agent3],
    tasks=[initial_task, analysis_task, final_task],
    process="workflow",  # Use workflow process type
    verbose=True
)

# Run the workflow
results = workflow.start()

# Print results
print("\nWorkflow Results:")
for task_id, result in results["task_results"].items():
    if result:
        print(f"Task {task_id}: {result.raw}")
