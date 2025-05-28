import asyncio
from praisonaiagents import Agent

async def main():
    agent = Agent(
        instructions="You are a helpful assistant",
        llm="gemini/gemini-1.5-flash-8b",
        self_reflect=True,
        verbose=True
    )

    # Use achat instead of start/chat for async operation
    response = await agent.achat("Why sky is Blue in 1000 words?")
    print(response)

if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())