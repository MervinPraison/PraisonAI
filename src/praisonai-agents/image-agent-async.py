import asyncio
from praisonaiagents import ImageAgent

async def main():
    agent = ImageAgent(
        name="ImageCreator",
        llm="dall-e-3",
        style="natural"
    )

    result = await agent.achat("A cute baby sea otter playing with a laptop")
    print(f"Image generation result: {result}")

if __name__ == "__main__":
    asyncio.run(main())