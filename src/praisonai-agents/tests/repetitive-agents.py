from praisonaiagents import Agent, Task, Agents

agent = Agent(
    instructions="You are a loop agent that creating a loop of tasks.",
    llm="gpt-5-nano"
)

task = Task(
    description="complete the task",
    expected_output="task completed",
    agent=agent,
    task_type="loop",
    input_file="tasks.csv"
)

agents = Agents(
    agents=[agent],
    tasks=[task],
    process="workflow",
    max_iter=30
)

agents.start()