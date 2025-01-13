from praisonaiagents import Agent, Task, PraisonAIAgents

# Create generator and evaluator agents
generator = Agent(
    name="Generator",
    role="Solution generator",
    goal="Generate initial solutions and incorporate feedback",
    instructions="Generate solutions and refine based on evaluator feedback"
)

evaluator = Agent(
    name="Evaluator",
    role="Solution evaluator",
    goal="Evaluate solutions and provide improvement feedback",
    instructions="Evaluate solutions for accuracy and provide specific feedback for improvements"
)

# Create tasks for the feedback loop
generate_task = Task(
    name="generate",
    description="Generate or refine solution based on feedback",
    expected_output="Generated solution",
    agent=generator,
    is_start=True,
    task_type="decision",
    next_tasks=["evaluate"],
    condition={
        "more": ["evaluate"],  # Continue to evaluation
        "done": [""]  # Exit when optimization complete
    }
)

evaluate_task = Task(
    name="evaluate",
    description="Evaluate solution and provide feedback",
    expected_output="Evaluation score and feedback",
    agent=evaluator,
    next_tasks=["generate"],
    context=[generate_task]  # Access to previous generation for evaluation
)

# Create workflow manager
workflow = PraisonAIAgents(
    agents=[generator, evaluator],
    tasks=[generate_task, evaluate_task],
    process="workflow",
    verbose=True
)

# Run optimization workflow
results = workflow.start()

# Print results
print("\nEvaluator-Optimizer Results:")
for task_id, result in results["task_results"].items():
    if result:
        print(f"Task {task_id}: {result.raw}")
