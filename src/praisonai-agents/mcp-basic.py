import asyncio
from praisonaiagents import Agent
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Define server configuration - pointing to your stock price app
server_params = StdioServerParameters(
    command="/Users/praison/miniconda3/envs/mcp/bin/python",
    args=[
        "/Users/praison/stockprice/app.py",
    ],
)

# Function to get stock price using MCP
async def get_stock_price(symbol):
    # Start server and connect client
    """
    Retrieves the stock price asynchronously.
    
    This function connects to a server via an asynchronous client session, retrieves the
    list of available tools, and searches for a tool capable of fetching stock prices. If a
    suitable tool is found, it invokes the tool with the provided stock symbol and returns
    its result; otherwise, it returns a message indicating that no appropriate tool was found.
    
    Args:
        symbol: The stock ticker symbol to query.
    """
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize the connection
            await session.initialize()
            
            # Get tools
            tools_result = await session.list_tools()
            tools = tools_result.tools
            print(f"Available tools: {[tool.name for tool in tools]}")
            
            # Find a tool that can get stock prices
            # Assuming there's a tool like "get_stock_price" or similar
            stock_tool = None
            for tool in tools:
                if "stock" in tool.name.lower() or "price" in tool.name.lower():
                    stock_tool = tool
                    break
            
            if stock_tool:
                print(f"Using tool: {stock_tool.name}")
                # Call the tool with the stock symbol
                result = await session.call_tool(
                    stock_tool.name, 
                    arguments={"ticker": symbol}
                )
                return result
            else:
                return "No suitable stock price tool found"

# Create a custom tool for the agent
def stock_price_tool(symbol: str) -> str:
    """
    Retrieve and format the current stock price for a specified symbol.
    
    This synchronous wrapper runs the asynchronous `get_stock_price` function using
    `asyncio.run` to obtain the latest stock price, and returns a formatted string
    displaying the price for the given stock symbol.
    
    Args:
        symbol: The stock ticker symbol for which the price is retrieved.
    
    Returns:
        A string representing the stock price in a human-readable format.
    """
    # Run the async function to get the stock price
    result = asyncio.run(get_stock_price(symbol))
    return f"Stock price for {symbol}: {result}"

# Create agent with the stock price tool
agent = Agent(
    instructions="You are a helpful assistant that can check stock prices. When asked about stock prices, use the stock_price_tool.",
    llm="gpt-4o-mini",
    tools=[stock_price_tool]
)

# Start the agent
agent.start("What is the stock price of Tesla?")