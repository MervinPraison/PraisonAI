from praisonaiagents import Agent, MCP
import os

brave_api_key = os.getenv("BRAVE_API_KEY")

research_agent = Agent(
    instructions="Research Agent",
    llm="groq/meta-llama/llama-4-scout-17b-16e-instruct",
    tools=MCP("npx -y @modelcontextprotocol/server-brave-search", env={"BRAVE_API_KEY": brave_api_key})
)

research_agent.start("What is the latest research on the topic of AI and its impact on society?")