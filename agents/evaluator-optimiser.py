from praisonaiagents import Agent, Task, PraisonAIAgents

# Create generator and evaluator agents
generator = Agent(
    name="Generator",
    role="Solution generator",
    goal="Generate initial solutions and incorporate feedback",
    instructions=(
        "1. Look at the context from previous tasks.\n"
        "2. If you see that you have already produced 2 points, then add another 2 new points "
        "   so that the total becomes 10.\n"
        "3. Otherwise, just produce the first 2 points.\n"
        "4. Return only the final list of points, with no extra explanation."
    )
)

evaluator = Agent(
    name="Evaluator",
    role="Solution evaluator",
    goal="Evaluate solutions and provide improvement feedback",
    instructions=(
        "1. Count how many lines in the response start with a number and a period (like '1. ' or '2. ').\n"
        "2. If there are 10 or more, respond with 'done'.\n"
        "3. Otherwise, respond with 'more'.\n"
        "4. Return only the single word: 'done' or 'more'."
    )
)


# Create tasks for the feedback loop
generate_task = Task(
    name="generate",
    description="Write 2 points about AI incuding if anything exiting from previous points",
    expected_output="2 points",
    agent=generator,
    is_start=True,
    task_type="decision",
    next_tasks=["evaluate"]
)

evaluate_task = Task(
    name="evaluate",
    description="Check if there are 10 points about AI",
    expected_output="more or done",
    agent=evaluator,
    next_tasks=["generate"],
    context=[generate_task],
    task_type="decision",
    condition={
        "more": ["generate"],  # Continue to generate
        "done": [""]  # Exit when optimization complete
    }
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
