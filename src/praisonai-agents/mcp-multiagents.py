from praisonaiagents import Agent, MCP
import os
stock_agent = Agent(
    instructions="""You are a helpful assistant that can check stock prices and perform other tasks.
    Use the available tools when relevant to answer user questions.""",
    llm="gpt-4o-mini",
    tools=MCP(
        command="/Users/praison/miniconda3/envs/mcp/bin/python",
        args=["/Users/praison/stockprice/app.py"]
    )
)

brave_api_key = os.getenv("BRAVE_API_KEY")

search_agent = Agent(
    instructions="""You are a helpful assistant that can search the web for information.
    Use the available tools when relevant to answer user questions.""",
    llm="gpt-4o-mini",
    tools=MCP(f'npx -y @smithery/cli@latest install @smithery-ai/brave-search --client claude --config "{{\\\"braveApiKey\\\":\\\"{brave_api_key}\\\"}}"')
)

stock_agent.start("What is the stock price of Tesla?")
search_agent.start("Search more information about Praison AI")