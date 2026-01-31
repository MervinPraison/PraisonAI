from praisonaiagents import Agent, AgentTeam
from langchain_community.tools.riza.command import ExecPython

coder_agent = Agent(instructions="""word = "strawberry"
                                    count = word.count("r")
                                    print(f"There are {count}'R's in the word 'Strawberry'")""", tools=[ExecPython])

agents = AgentTeam(agents=[coder_agent])
agents.start()