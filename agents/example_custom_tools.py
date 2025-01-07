from praisonaiagents import Agent, Task, PraisonAIAgents
from typing import List, Dict, Union
from duckduckgo_search import DDGS
from langchain_community.tools import YouTubeSearchTool
from langchain_community.utilities import WikipediaAPIWrapper

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
    
def youtube_search_tool(query: str, inspect: bool = False, max_results: int = 2):
    """
    Provide a custom wrapper around the YouTubeSearchTool.
    
    Args:
        query (str): The search query for YouTube.
        inspect (bool): If True, returns tool inspection info instead of search results.
        max_results (int): Maximum number of results to return (default: 2).
    Returns:
        Union[List[str], dict]: List of YouTube video URLs or tool inspection info.
    """
    yt = YouTubeSearchTool()
    
    if inspect:
        inspection_info = {
            "type": type(yt),
            "attributes": [attr for attr in dir(yt) if not attr.startswith('_')],
            "methods": {
                "run": getattr(yt, 'run', None),
                "arun": getattr(yt, 'arun', None)
            },
            "properties": {
                "name": getattr(yt, 'name', 'youtube_search'),
                "description": getattr(yt, 'description', 'Search YouTube videos'),
                "return_direct": getattr(yt, 'return_direct', False)
            }
        }
        return inspection_info
    
    # Format query with max_results
    formatted_query = f"{query}, {max_results}"
    return yt.run(formatted_query)

def wikipedia_search_tool(query: str, inspect: bool = False, max_chars: int = 4000, top_k: int = 3):
    """
    Provide a custom wrapper around langchain_community's WikipediaAPIWrapper.

    Args:
        query (str): A search query for Wikipedia.
        inspect (bool): If True, returns tool inspection info instead of search results.
        max_chars (int): Maximum characters to return (default: 4000).
        top_k (int): Number of top results to consider (default: 3).
    Returns:
        Union[str, dict]: Summary from Wikipedia or tool inspection info if inspect=True.
    """
    w = WikipediaAPIWrapper(
        top_k_results=top_k,
        doc_content_chars_max=max_chars,
        lang='en'
    )
    
    if inspect:
        inspection_info = {
            "type": type(w),
            "attributes": [attr for attr in dir(w) if not attr.startswith('_')],
            "methods": {
                "run": getattr(w, 'run', None),
                "arun": getattr(w, 'arun', None)
            },
            "properties": {
                "name": "wikipedia",
                "description": "Search and get summaries from Wikipedia",
                "top_k": w.top_k_results,
                "lang": w.lang,
                "max_chars": w.doc_content_chars_max
            }
        }
        return inspection_info
    
    try:
        result = w.run(query)
        return result
    except Exception as e:
        return f"Error searching Wikipedia: {str(e)}"

# 2. Agent
data_agent = Agent(
    name="DataCollector",
    role="Search Specialist",
    goal="Perform internet searches to collect relevant information.",
    backstory="Expert in finding and organizing internet data from multiple sources.",
    tools=[internet_search_tool, youtube_search_tool, wikipedia_search_tool],
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

# 4. Workflow
agents = PraisonAIAgents(
    agents=[data_agent],
    tasks=[collect_task, validate_task],
    verbose=1,
    process="workflow"
)

agents.start()