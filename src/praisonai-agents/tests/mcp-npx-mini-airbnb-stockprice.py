from praisonaiagents import Agent, MCP

search_agent = Agent(
    instructions="""You help book apartments on Airbnb.""",
    llm="gpt-4o-mini",
    tools=MCP("npx -y @openbnb/mcp-server-airbnb --ignore-robots-txt")
)

search_agent.start("I want to book an apartment in Paris for 2 nights. 03/28 - 03/30 for 2 adults")

agent = Agent(
    instructions="""You are a helpful assistant that can check stock prices and perform other tasks.
    Use the available tools when relevant to answer user questions.""",
    llm="gpt-4o-mini",
    tools = MCP("/Users/praison/miniconda3/envs/mcp/bin/python /Users/praison/stockprice/app.py")
)

agent.start("What is the stock price of Tesla?")