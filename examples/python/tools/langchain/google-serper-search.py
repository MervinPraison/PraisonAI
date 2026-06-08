from praisonaiagents import Agent, AgentTeam
from langchain_community.utilities import GoogleSerperAPIWrapper
import os
from dotenv import load_dotenv

load_dotenv()

serper_api_key = os.getenv("SERPER_API_KEY")
if serper_api_key is not None:
    os.environ["SERPER_API_KEY"] = serper_api_key


if __name__ == "__main__":
    if not serper_api_key:
        print("SERPER_API_KEY is not set. Skipping Google Serper example.")
    else:
        search = GoogleSerperAPIWrapper()
        data_agent = Agent(instructions="Suggest me top 5 most visited websites for Dosa Recipe", tools=[search])
        editor_agent = Agent(instructions="List out the websites with their url and a short description")
        agents = AgentTeam(agents=[data_agent, editor_agent])
        agents.start()