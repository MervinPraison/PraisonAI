# tools.py
from duckduckgo_search import DDGS
from praisonai_tools import BaseTool
from langchain_community.tools.pubmed.tool import PubmedQueryRun
from langchain.utilities.tavily_search import TavilySearchAPIWrapper

class InternetSearchTool(BaseTool):
    name: str = "InternetSearchTool"
    description: str = "Search Internet for relevant information based on a query or latest news"

    def _run(self, query: str):
        ddgs = DDGS()
        results = ddgs.text(keywords=query, region='wt-wt', safesearch='moderate', max_results=5)
        return results
    

class TavilyTool(BaseTool):
    name: str = "TavilyTool"
    description: str = "Search Tavily for relevant information based on a query."

    def _run(self, query: str):
        api_wrapper = TavilySearchAPIWrapper()
        results = api_wrapper.results(query=query, max_results=5)
        return results