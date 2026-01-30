"""
RouteLLM Multi-Agent Example

Prerequisites:
1. pip install routellm
2. export OPENAI_API_KEY=your-api-key
3. Start RouteLLM server:
   python -m routellm.openai_server \
     --routers mf \
     --strong-model gpt-4o \
     --weak-model gpt-4o-mini \
     --port 6060
"""

from praisonaiagents import Agent, Agents, Task

ROUTELLM_URL = "http://localhost:6060/v1"

researcher = Agent(
    name="Researcher",
    role="Research analyst",
    goal="Find and analyze information",
    llm="router-mf-0.5",
    base_url=ROUTELLM_URL
)

writer = Agent(
    name="Writer",
    role="Content writer",
    goal="Write clear and engaging content",
    llm="router-mf-0.5",
    base_url=ROUTELLM_URL
)

task1 = Task(
    description="Research the latest AI trends in 2024",
    agent=researcher,
    expected_output="Research summary with key findings"
)

task2 = Task(
    description="Write a brief article based on the research",
    agent=writer,
    expected_output="Short article about AI trends"
)

agents = AgentManager(agents=[researcher, writer], tasks=[task1, task2])
result = agents.start()
print(result)
