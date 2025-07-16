import asyncio
from praisonaiagents import Agent, Task, PraisonAIAgents

# Example tools (replace with real implementations as needed)
def fetch_favorite_article():
    # Simulate fetching your favorite morning article
    return "Your favorite morning article: 'How to Start Your Day Right'"

def search_trending_kenya():
    # Simulate searching for trending news in Kenya
    return "Trending in Kenya: 'Kenya launches new tech hub in Nairobi'"

def fetch_twitter_feed():
    # Simulate fetching Twitter feed
    return "Latest tweet: 'AI is transforming the world!'"

# Agents for each unique task
article_agent = Agent(
    name="ArticleAgent",
    role="Morning Article Fetcher",
    goal="Fetch the user's favorite morning article",
    tools=[fetch_favorite_article],
    llm="gemini/gemini-2.5-flash-lite-preview-06-17",
    verbose=True
)

news_agent = Agent(
    name="KenyaNewsAgent",
    role="Kenya News Searcher",
    goal="Search for trending news in Kenya",
    tools=[search_trending_kenya],
    llm="gemini/gemini-2.5-flash-lite-preview-06-17",
    verbose=True
)

twitter_agent = Agent(
    name="TwitterAgent",
    role="Twitter Feed Fetcher",
    goal="Fetch the latest Twitter feed",
    tools=[fetch_twitter_feed],
    llm="gemini/gemini-2.5-flash-lite-preview-06-17",
    verbose=True
)

aggregator = Agent(
    name="Aggregator",
    role="Result Aggregator",
    goal="Aggregate and summarize all results",
    llm="gemini/gemini-2.5-flash-lite-preview-06-17",
    verbose=True
)

# Tasks for each agent
article_task = Task(
    name="fetch_article",
    description="Fetch the user's favorite morning article.",
    expected_output="The favorite morning article.",
    agent=article_agent,
    is_start=True,
    async_execution=True
)

news_task = Task(
    name="search_kenya_news",
    description="Search for trending news in Kenya.",
    expected_output="Trending news in Kenya.",
    agent=news_agent,
    is_start=True,
    async_execution=True
)

twitter_task = Task(
    name="fetch_twitter",
    description="Fetch the latest Twitter feed.",
    expected_output="Latest Twitter feed.",
    agent=twitter_agent,
    is_start=True,
    async_execution=True
)

# Aggregator task that depends on the above tasks
aggregate_task = Task(
    name="aggregate_results",
    description="Summarize the article, news, and Twitter feed results.",
    expected_output="A summary of all fetched information.",
    agent=aggregator,
    context=[article_task, news_task, twitter_task]
)

async def main():
    workflow = PraisonAIAgents(
        agents=[article_agent, news_agent, twitter_agent, aggregator],
        tasks=[article_task, news_task, twitter_task, aggregate_task],
        process="workflow",
        verbose=True
    )
    results = await workflow.astart(dict_output=True)

    print("\nParallel Processing Results:")
    
    # Handle both string and dictionary return types
    if isinstance(results, dict) and "task_results" in results:
        for task_id, result in results["task_results"].items():
            if result:
                print(f"Task {task_id}: {result.raw}")
    else:
        print("Final result:", results)

if __name__ == "__main__":
    asyncio.run(main())