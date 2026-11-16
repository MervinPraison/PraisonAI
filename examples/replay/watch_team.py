"""Watch two agents work together, live (calls the LLM: needs OPENAI_API_KEY).

    python watch_team.py          # opens http://127.0.0.1:8090/, press Run
"""

from praisonaiagents import Agent, AgentTeam, Task
from praisonai.replay import watch

researcher = Agent(name="Researcher", instructions="Give 3 short facts.", llm="gpt-4o-mini")
writer = Agent(name="Writer", instructions="Write one short paragraph from the facts.", llm="gpt-4o-mini")
team = AgentTeam(
    agents=[researcher, writer],
    tasks=[
        Task(name="research", description="3 facts about solar sails", agent=researcher, expected_output="3 facts"),
        Task(name="write", description="One paragraph using the facts", agent=writer, expected_output="a paragraph"),
    ],
)
watch(team)
