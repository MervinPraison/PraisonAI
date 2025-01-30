from praisonaiagents import Agent, Task, PraisonAIAgents

agent = Agent(
    instructions="You are a loop agent that creating a loop of tasks.",
    llm="gpt-4o-mini"
)

task = Task(
    description="complete the task",
    expected_output="task completed",
    agent=agent,
    task_type="loop",
    input_file="tasks.csv"
)

agents = PraisonAIAgents(
    agents=[agent],
    tasks=[task],
    process="workflow",
    max_iter=30
)

agents.start()