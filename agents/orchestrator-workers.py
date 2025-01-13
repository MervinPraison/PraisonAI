from praisonaiagents import Agent, Task, PraisonAIAgents
import time

def get_time_check():
    current_time = int(time.time())
    if current_time % 3 == 0:
        result = 1
    elif current_time % 3 == 1:
        result = 2
    else:
        result = 3
    print(f"Time: {current_time}, Result: {result}")
    return result

# Create orchestrator and worker agents
router = Agent(
    name="Router",
    role="Task router",
    goal="Distribute tasks to based on response from get_time_check",
    tools=[get_time_check]
)

worker1 = Agent(
    name="Worker 1",
    role="Specialized worker",
    goal="Handle specific subtask type 1",
)

worker2 = Agent(
    name="Worker 2",
    role="Specialized worker",
    goal="Handle specific subtask type 2",
)

worker3 = Agent(
    name="Worker 3",
    role="Specialized worker",
    goal="Handle specific subtask type 3",
)

synthesizer = Agent(
    name="Synthesizer",
    role="Result synthesizer",
    goal="Combine and synthesize worker outputs",
)

# Create orchestrated workflow tasks
router_task = Task(
    name="route_task",
    description="Analyze input from get_time_check and route to appropriate workers",
    expected_output="Task routing decision, 1 , 2 or 3",
    agent=router,
    is_start=True,
    task_type="decision",
    next_tasks=["worker1_task", "worker2_task", "worker3_task"],
    condition={
        "1": ["worker1_task"],
        "2": ["worker2_task"],
        "3": ["worker3_task"]
    }
)

worker1_task = Task(
    name="worker1_task",
    description="Process type 1 operation",
    expected_output="Worker 1 result",
    agent=worker1,
    next_tasks=["synthesize_task"]
)

worker2_task = Task(
    name="worker2_task",
    description="Process type 2 operation",
    expected_output="Worker 2 result",
    agent=worker2,
    next_tasks=["synthesize_task"]
)

worker3_task = Task(
    name="worker3_task",
    description="Process type 3 operation",
    expected_output="Worker 3 result",
    agent=worker3,
    next_tasks=["synthesize_task"]
)

synthesize_task = Task(
    name="synthesize_task",
    description="Synthesize worker results into final output",
    expected_output="Final synthesized result",
    agent=synthesizer,
    context=[worker1_task, worker2_task, worker3_task]
)

# Create workflow manager
workflow = PraisonAIAgents(
    agents=[router, worker1, worker2, worker3, synthesizer],
    tasks=[router_task, worker1_task, worker2_task, worker3_task, synthesize_task],
    process="workflow",
    verbose=True
)

# Run orchestrated workflow
results = workflow.start()

# Print results
print("\nOrchestrator-Workers Results:")
for task_id, result in results["task_results"].items():
    if result:
        print(f"Task {task_id}: {result.raw}")
