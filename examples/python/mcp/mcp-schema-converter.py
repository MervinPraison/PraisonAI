"""MCP Schema Converter Example

Demonstrates how to convert Python functions to MCP-compatible schemas.

Usage:
    python mcp-schema-converter.py
"""

from typing import List, Dict, Any, Optional
from praisonaiagents.mcp import function_to_mcp_schema, get_tool_metadata


# Example functions with various type annotations

def simple_search(query: str) -> str:
    """Search for information."""
    return f"Results for {query}"


def advanced_search(
    query: str,
    max_results: int = 10,
    include_images: bool = False,
    filters: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Advanced search with multiple options.
    
    Args:
        query: The search query
        max_results: Maximum results to return
        include_images: Whether to include images
        filters: Optional filters to apply
    """
    return {}


def process_items(items: List[str], batch_size: int = 5) -> List[Dict[str, Any]]:
    """Process a list of items.
    
    Args:
        items: List of items to process
        batch_size: Size of each batch
    """
    return []


async def async_fetch(url: str, timeout: float = 30.0) -> Dict[str, Any]:
    """Fetch data from URL asynchronously.
    
    Args:
        url: The URL to fetch
        timeout: Request timeout in seconds
    """
    return {}


def main():
    functions = [simple_search, advanced_search, process_items, async_fetch]
    
    print("=" * 60)
    print("MCP Schema Converter Demo")
    print("=" * 60)
    
    for func in functions:
        print(f"\n### Function: {func.__name__}")
        
        # Get metadata
        metadata = get_tool_metadata(func)
        print(f"Name: {metadata['name']}")
        print(f"Description: {metadata['description']}")
        
        # Get full schema
        schema = function_to_mcp_schema(func)
        
        print("\nMCP Schema:")
        import json
        print(json.dumps(schema, indent=2))
        print("-" * 40)


if __name__ == "__main__":
    main()
