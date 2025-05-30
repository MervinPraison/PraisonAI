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

# Construct the MCP command properly without backslashes in f-string
quote = '"'
mcp_command = f'npx -y @smithery/cli@latest install @smithery-ai/brave-search --client claude --config "{{{quote}braveApiKey{quote}: {quote}{brave_api_key}{quote}}}"'

search_agent = Agent(
    instructions="""You are a helpful assistant that can search the web for information.
    Use the available tools when relevant to answer user questions.""",
    llm="gpt-4o-mini",
    tools=MCP(mcp_command)
)

stock_agent.start("What is the stock price of Tesla?")
search_agent.start("Search more information about Praison AI")