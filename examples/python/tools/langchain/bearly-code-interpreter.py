from praisonaiagents import Agent, PraisonAIAgents
from langchain_community.tools import BearlyInterpreterTool

coder_agent = Agent(instructions="""for i in range(0,10):
                                        print(f'The number is {i}')""", tools=[BearlyInterpreterTool])

agents = PraisonAIAgents(agents=[coder_agent])
agents.start()