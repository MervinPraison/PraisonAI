from praisonaiagents import Agent
import asyncio

agent = Agent(
    instructions="You are a helpful assistant",
    llm="gpt-4o-mini"
)
agent.run("Why sea is Blue?")

async def main():
    await agent.arun("Why sky is Blue?")    
    await agent.arun("What was my previous question?")

asyncio.run(main())