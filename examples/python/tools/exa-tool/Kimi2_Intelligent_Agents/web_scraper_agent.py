from praisonaiagents import Agent

agent = Agent(
    instructions="You are a web scraping AI agent. "
                "Help users create efficient and ethical web scrapers, data extraction tools, and automation scripts. "
                "Provide guidance on BeautifulSoup, Selenium, Scrapy, and best practices for responsible web scraping.",
    llm="openrouter/moonshotai/kimi-k2"
)

response = agent.start("Hello! I'm your web scraping assistant. "
                      "How can I help you extract and analyze web data today?") 