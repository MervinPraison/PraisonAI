"""Tools module for PraisonAI Agents"""
from typing import List, Dict
import logging
import importlib

class Tools:
    @staticmethod
    def internet_search(query: str) -> List[Dict]:
        """
        Perform a search using DuckDuckGo.

        Args:
            query (str): The search query.

        Returns:
            list: A list of search result titles, URLs, and snippets.
        """
        # Check if duckduckgo_search is installed
        if importlib.util.find_spec("duckduckgo_search") is None:
            error_msg = "DuckDuckGo search is not available. Please install duckduckgo_search package using: pip install duckduckgo_search"
            logging.error(error_msg)
            return [{"error": error_msg}]

        try:
            # Import only when needed
            from duckduckgo_search import DDGS
            results = []
            ddgs = DDGS()
            for result in ddgs.text(keywords=query, max_results=5):
                results.append({
                    "title": result.get("title", ""),
                    "url": result.get("href", ""),
                    "snippet": result.get("body", "")
                })
            return results

        except Exception as e:
            error_msg = f"Error during DuckDuckGo search: {e}"
            logging.error(error_msg)
            return [{"error": error_msg}] 