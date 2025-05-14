from praisonaiagents import Agent

weather_agent = Agent(
    instructions="""You are a weather agent that can provide weather information for a given city.""",
    llm="gpt-4o-mini"
)

stock_agent = Agent(
    instructions="""You are a stock market agent that can provide information about stock prices and market trends.""",
    llm="gpt-4o-mini"
)

travel_agent = Agent(
    instructions="""You are a travel agent that can provide recommendations for destinations, hotels, and activities.""",
    llm="gpt-4o-mini"
)

weather_agent.launch(path="/weather", port=3030)
stock_agent.launch(path="/stock", port=3030)
travel_agent.launch(path="/travel", port=3030) 