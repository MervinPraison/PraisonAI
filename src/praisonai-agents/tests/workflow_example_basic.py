from praisonaiagents import Agent, Task, PraisonAIAgents
from typing import List, Dict
from duckduckgo_search import DDGS

# 1. Tool
def internet_search_tool(query: str) -> List[Dict]:
    """
    Perform a search using DuckDuckGo.

    Args:
        query (str): The search query.

    Returns:
        list: A list of search result titles, URLs, and snippets.
    """
    try:
        results = []
        ddgs = DDGS()
        for result in ddgs.text(keywords=query, max_results=10):
            results.append({
                "title": result.get("title", ""),
                "url": result.get("href", ""),
                "snippet": result.get("body", "")
            })
        return results

    except Exception as e:
        print(f"Error during DuckDuckGo search: {e}")
        return []

# 2. Agent
data_agent = Agent(
    name="DataCollector",
    role="Search Specialist",
    goal="Perform internet searches to collect relevant information.",
    backstory="Expert in finding and organising internet data.",
    tools=[internet_search_tool],
    self_reflect=False
)

# 3. Tasks
collect_task = Task(
    description="Perform an internet search using the query: 'AI job trends in 2024'. Return results as a list of title, URL, and snippet.",
    expected_output="List of search results with titles, URLs, and snippets.",
    agent=data_agent,
    name="collect_data",
    is_start=True,
    next_tasks=["validate_data"]
)

validate_task = Task(
    description="""Validate the collected data. Check if:
    1. At least 5 results are returned.
    2. Each result contains a title and a URL.
    Return validation_result as 'valid' or 'invalid' only no other text.""",
    expected_output="Validation result indicating if data is valid or invalid.",
    agent=data_agent,
    name="validate_data",
    task_type="decision",
    condition={
        "valid": [],  # End the workflow on valid data
        "invalid": ["collect_data"]  # Retry data collection on invalid data
    },
)

# 4. AI Agents Workflow
agents = PraisonAIAgents(
    agents=[data_agent],
    tasks=[collect_task, validate_task],
    verbose=1,
    process="workflow"
)

agents.start()