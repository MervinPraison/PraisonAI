from duckduckgo_search import DDGS
from langchain.tools import tool

@tool("Internet Search Tool")
def internet_search_tool(query: str) -> list:
    """Search Internet for relevant information based on a query."""
    ddgs = DDGS()
    results = ddgs.text(keywords=query, region='wt-wt', safesearch='moderate', max_results=5)
    return results