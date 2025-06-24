"""Tools module for PraisonAI Agents"""
from .duckduckgo_tools import internet_search

class Tools:
    """Tools class for backward compatibility"""
    internet_search = staticmethod(internet_search)

# Re-export the function
__all__ = ['Tools', 'internet_search']