from praisonaiagents import Agent, Task, AgentTeam

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

agents = AgentTeam(
    agents=[agent],
    tasks=[task],
    process="workflow",
    max_iter=30
)

agents.start()