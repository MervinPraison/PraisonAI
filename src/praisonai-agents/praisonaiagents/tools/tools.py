"""Tools module for PraisonAI Agents - uses lazy loading for performance"""

# Lazy loading for internet_search to avoid importing duckduckgo_tools at startup
_internet_search = None

def _get_internet_search():
    """Lazy load internet_search function."""
    global _internet_search
    if _internet_search is None:
        from .duckduckgo_tools import internet_search as _is
        _internet_search = _is
    return _internet_search

class Tools:
    """Tools class for backward compatibility"""
    @staticmethod
    def internet_search(*args, **kwargs):
        """Lazy-loaded internet search function."""
        return _get_internet_search()(*args, **kwargs)

def internet_search(*args, **kwargs):
    """Lazy-loaded internet search function."""
    return _get_internet_search()(*args, **kwargs)

# Re-export the function
__all__ = ['Tools', 'internet_search']