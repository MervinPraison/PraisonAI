from praisonaiagents.agent import Agent
from praisonaiagents.task import Task
from praisonaiagents.agents import PraisonAIAgents
import time

def get_time_check():
    current_time = int(time.time())
    result = "even" if current_time % 2 == 0 else "odd"
    print(f"Time check: {current_time} is {result}")
    return result

# Create specialized agents
router = Agent(
    name="Router",
    role="Input Router",
    goal="Evaluate input and determine routing path",
    instructions="Analyze input and decide whether to proceed or exit",
    tools=[get_time_check]
)

processor1 = Agent(
    name="Processor 1",
    role="Secondary Processor",
    goal="Process valid inputs that passed initial check",
    instructions="Process data that passed the routing check"
)

processor2 = Agent(
    name="Processor 2",
    role="Final Processor",
    goal="Perform final processing on validated data",
    instructions="Generate final output for processed data"
)

# Create tasks with routing logic
routing_task = Task(
    name="initial_routing",
    description="check the time and return according to what is returned",
    expected_output="pass or fail based on what is returned",
    agent=router,
    is_start=True,
    task_type="decision",
    condition={
        "pass": ["process_valid"],
        "fail": ["process_invalid"]
    }
)

processing_task = Task(
    name="process_valid",
    description="Process validated input",
    expected_output="Processed data ready for final step",
    agent=processor1,
)

final_task = Task(
    name="process_invalid",
    description="Generate final output",
    expected_output="Final processed result",
    agent=processor2
)

# Create and run workflow
workflow = PraisonAIAgents(
    agents=[router, processor1, processor2],
    tasks=[routing_task, processing_task, final_task],
    process="workflow",
    verbose=True
)

print("\nStarting Routing Workflow...")
print("=" * 50)

results = workflow.start()

print("\nWorkflow Results:")
print("=" * 50)
for task_id, result in results["task_results"].items():
    if result:
        task_name = result.description
        print(f"\nTask: {task_name}")
        print(f"Result: {result.raw}")
        print("-" * 50)
