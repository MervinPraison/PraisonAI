from praisonaiagents import Agent, PraisonAIAgents
from langchain_agentql.tools import ExtractWebDataTool
from dotenv import load_dotenv

load_dotenv()
import os

os.environ["AGENTQL_API_KEY"] = os.getenv('AGENTQL_API_KEY')

def extract_web_data_tool(url, query):
    agentql_tool = ExtractWebDataTool().invoke(
        {
            "url": url,
            "prompt": query,
        },)
    return agentql_tool


# Create agent with web extraction instructions
orchestration_agent = Agent(
    instructions="""Extract All 37 products from the url https://www.colorbarcosmetics.com/bestsellers along with its name, overview, description, price and additional information by recursively clicking on each product""",
    tools=[extract_web_data_tool]
)

# Initialize and run agents
agents = PraisonAIAgents(agents=[orchestration_agent])
agents.start()