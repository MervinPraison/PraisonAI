from praisonaiagents import Agent, MCP

stock_agent = Agent(
    instructions="""You are a helpful assistant that can check stock prices and perform other tasks.
    Use the available tools when relevant to answer user questions.""",
    llm="gpt-4o-mini",
    tools=MCP(
        command="/Users/praison/miniconda3/envs/mcp/bin/python",
        args=["/Users/praison/stockprice/app.py"]
    )
)

search_agent = Agent(
    instructions="""You are a helpful assistant that can search the web for information.
    Use the available tools when relevant to answer user questions.""",
    llm="gpt-4o-mini",
    tools=MCP('npx -y @smithery/cli@latest install @smithery-ai/brave-search --client claude --config "{\"braveApiKey\":\"BSANfDaqLKO9wq7e08mrPth9ZlJvKtc\"}"')
)

stock_agent.start("What is the stock price of Tesla?")
search_agent.start("What is the weather in San Francisco?")