from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import get_article, get_news_sources, get_articles_from_source, get_trending_topics

# Create Wikipedia agent
news_agent = Agent(
    name="NewsAgent",
    role="News Analyst",
    goal="Collect and analyze news articles from various sources.",
    backstory="Expert in news gathering and content analysis.",
    tools=[get_article, get_news_sources, get_articles_from_source, get_trending_topics],
    self_reflect=False
)


# Define research task
news_task = Task(
    description="Analyze news articles about 'AI developments' from major tech news sources.",
    expected_output="Summary of key AI developments with source articles.",
    agent=news_agent,
    name="ai_news"
)


# Run agent
agents = PraisonAIAgents(
    agents=[news_agent],
    tasks=[news_task],
    process="sequential"
)
agents.start()
