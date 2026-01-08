from praisonaiagents import Agent, Agents
from langchain_community.tools import BearlyInterpreterTool

coder_agent = Agent(instructions="""for i in range(0,10):
                                        print(f'The number is {i}')""", tools=[BearlyInterpreterTool])

agents = Agents(agents=[coder_agent])
agents.start()