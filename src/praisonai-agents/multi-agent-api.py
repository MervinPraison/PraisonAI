from praisonaiagents import Agent

# Create a weather agent
weather_agent = Agent(
    instructions="""You are a weather agent that can provide weather information for a given city.""",
    llm="gpt-4o-mini"
)

# Create a stock market agent 
stock_agent = Agent(
    instructions="""You are a stock market agent that can provide information about stock prices and market trends.""",
    llm="gpt-4o-mini"
)

# Create a travel agent
travel_agent = Agent(
    instructions="""You are a travel agent that can provide recommendations for destinations, hotels, and activities.""",
    llm="gpt-4o-mini"
)

# Register the first two agents with blocking=False so they don't block execution
weather_agent.launch(path="/weather", port=3030, blocking=False)
stock_agent.launch(path="/stock", port=3030, blocking=False)

# Register the last agent with blocking=True to keep the server running
# This must be the last launch() call
travel_agent.launch(path="/travel", port=3030, blocking=True)

# The script will block at the last launch() call until the user presses Ctrl+C
