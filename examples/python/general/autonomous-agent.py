from praisonaiagents import Agent, Task, PraisonAIAgents
import time

def get_environment_state():
    """Simulates getting current environment state"""
    current_time = int(time.time())
    states = ["normal", "critical", "optimal"]
    state = states[current_time % 3]
    print(f"Environment state: {state}")
    return state

def perform_action(state: str):
    """Simulates performing an action based on state"""
    actions = {
        "normal": "maintain",
        "critical": "fix",
        "optimal": "enhance"
    }
    action = actions.get(state, "observe")
    print(f"Performing action: {action} for state: {state}")
    return action

def get_feedback():
    """Simulates environment feedback"""
    current_time = int(time.time())
    feedback = "positive" if current_time % 2 == 0 else "negative"
    print(f"Feedback received: {feedback}")
    return feedback

# Create specialized agents
llm_caller = Agent(
    name="Environment Monitor",
    role="State analyzer",
    goal="Monitor environment and analyze state",
    instructions="Check environment state and provide analysis",
    tools=[get_environment_state]
)

action_agent = Agent(
    name="Action Executor",
    role="Action performer",
    goal="Execute appropriate actions based on state",
    instructions="Determine and perform actions based on environment state",
    tools=[perform_action]
)

feedback_agent = Agent(
    name="Feedback Processor",
    role="Feedback analyzer",
    goal="Process environment feedback and adapt strategy",
    instructions="Analyze feedback and provide adaptation recommendations",
    tools=[get_feedback]
)

# Create tasks for autonomous workflow
monitor_task = Task(
    name="monitor_environment",
    description="Monitor and analyze environment state",
    expected_output="Current environment state analysis",
    agent=llm_caller,
    is_start=True,
    task_type="decision",
    next_tasks=["execute_action"],
    condition={
        "normal": ["execute_action"],
        "critical": ["execute_action"],
        "optimal": "exit"
    }
)

action_task = Task(
    name="execute_action",
    description="Execute appropriate action based on state",
    expected_output="Action execution result",
    agent=action_agent,
    next_tasks=["process_feedback"]
)

feedback_task = Task(
    name="process_feedback",
    description="Process feedback and adapt strategy",
    expected_output="Strategy adaptation based on feedback",
    agent=feedback_agent,
    next_tasks=["monitor_environment"],  # Create feedback loop
    context=[monitor_task, action_task]  # Access to previous states and actions
)

# Create workflow manager
workflow = PraisonAIAgents(
    agents=[llm_caller, action_agent, feedback_agent],
    tasks=[monitor_task, action_task, feedback_task],
    process="workflow",
    verbose=True
)

def main():
    print("\nStarting Autonomous Agent Workflow...")
    print("=" * 50)
    
    # Run autonomous workflow
    results = workflow.start()
    
    # Print results
    print("\nAutonomous Agent Results:")
    print("=" * 50)
    for task_id, result in results["task_results"].items():
        if result:
            task_name = result.description
            print(f"\nTask: {task_name}")
            print(f"Result: {result.raw}")
            print("-" * 50)

if __name__ == "__main__":
    main()
