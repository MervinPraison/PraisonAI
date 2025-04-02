from praisonaiagents import Agent, MCP
import os

api_key = os.getenv("PERPLEXITY_API_KEY")

agent = Agent(
    instructions="You are a helpful assistant that can search the web for information. Use the available tools when relevant to answer user questions.",
    llm="gpt-4o-mini",
    tools=MCP("uvx perplexity-mcp", 
        env={"PERPLEXITY_API_KEY": api_key, "PERPLEXITY_MODEL": "sonar" })
)
result = agent.start("What is the latest news on AI?, Pass only the query parameter to the tool")

print(result)