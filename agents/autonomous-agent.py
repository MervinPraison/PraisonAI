from praisonaiagents import Agent, Task, PraisonAIAgents
import time

def get_environment_feedback():
    """Simulates environment feedback based on time"""
    current_time = int(time.time())
    feedback = "positive" if current_time % 2 == 0 else "negative"
    print(f"Environment feedback: {feedback}")
    return feedback

# Create autonomous agent
autonomous_agent = Agent(
    name="Autonomous Agent",
    role="Environment interactor",
    goal="Interact with environment and learn from feedback",
    instructions="Take actions based on environment state and adapt from feedback",
    tools=[get_environment_feedback]
)

# Create tasks for the autonomous loop
action_task = Task(
    name="take_action",
    description="Analyze environment and take appropriate action",
    expected_output="Action taken and its rationale",
    agent=autonomous_agent,
    is_start=True,
    task_type="decision",
    next_tasks=["process_feedback"],
    condition={
        "continue": ["process_feedback"],  # Continue to get feedback
        "stop": [""]  # Stop when goal is achieved
    }
)

feedback_task = Task(
    name="process_feedback",
    description="Process environment feedback and adapt strategy",
    expected_output="Adapted strategy based on feedback",
    agent=autonomous_agent,
    next_tasks=["take_action"],
    context=[action_task]  # Access to previous action for learning
)

# Create workflow manager
workflow = PraisonAIAgents(
    agents=[autonomous_agent],
    tasks=[action_task, feedback_task],
    process="workflow",
    verbose=True
)

# Run autonomous workflow
results = workflow.start()

# Print results
print("\nAutonomous Agent Results:")
for task_id, result in results["task_results"].items():
    if result:
        print(f"Task {task_id}: {result.raw}")
