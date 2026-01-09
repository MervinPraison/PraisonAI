#!/usr/bin/env python3
"""
Example: Template Finder Agent

An Agent()-centric example that uses an AI agent to find templates
based on natural language queries.

Requires: OPENAI_API_KEY environment variable
"""

import json
import os
import urllib.request

CATALOG_URL = "https://mervinpraison.github.io/praisonai-template-catalog/data/templates.json"


def fetch_templates() -> list:
    """Fetch templates from catalog."""
    try:
        with urllib.request.urlopen(CATALOG_URL, timeout=10) as response:
            data = json.loads(response.read().decode())
            return data.get("templates", [])
    except Exception:
        return []


def search_templates_tool(query: str) -> str:
    """
    Search templates by keyword.
    
    Args:
        query: Search query (e.g., "video editing", "transcript", "data")
    
    Returns:
        JSON string with matching templates
    """
    templates = fetch_templates()
    query_lower = query.lower()
    
    results = []
    for t in templates:
        if (query_lower in t.get("name", "").lower() or
            query_lower in t.get("description", "").lower() or
            any(query_lower in tag.lower() for tag in t.get("tags", []))):
            results.append({
                "name": t.get("name"),
                "description": t.get("description", "")[:100],
                "tags": t.get("tags", []),
                "cli_command": f"praisonai templates run {t.get('name')}"
            })
    
    if not results:
        return json.dumps({"message": "No templates found matching your query", "templates": []})
    
    return json.dumps({"count": len(results), "templates": results})


def list_all_templates_tool() -> str:
    """
    List all available templates.
    
    Returns:
        JSON string with all template names and descriptions
    """
    templates = fetch_templates()
    
    if not templates:
        return json.dumps({"message": "No templates available", "templates": []})
    
    results = [
        {"name": t.get("name"), "description": t.get("description", "")[:80]}
        for t in templates
    ]
    
    return json.dumps({"count": len(results), "templates": results})


def get_template_details_tool(name: str) -> str:
    """
    Get detailed information about a specific template.
    
    Args:
        name: Template name (e.g., "ai-video-editor")
    
    Returns:
        JSON string with template details
    """
    templates = fetch_templates()
    
    for t in templates:
        if t.get("name") == name:
            return json.dumps({
                "name": t.get("name"),
                "version": t.get("version"),
                "description": t.get("description"),
                "author": t.get("author"),
                "tags": t.get("tags", []),
                "requires": t.get("requires", {}),
                "cli_commands": {
                    "run": f"praisonai templates run {name}",
                    "info": f"praisonai templates info {name}",
                    "init": f"praisonai templates init my-project --template {name}"
                }
            })
    
    return json.dumps({"error": f"Template '{name}' not found"})


def check_api_key() -> bool:
    """Check if API key is available."""
    key = os.environ.get("OPENAI_API_KEY") or os.environ.get("PRAISONAI_OPENAI_API_KEY")
    if key:
        print(f"API key present: ...{key[-4:]}")
        return True
    return False


def main():
    print("PraisonAI Template Finder Agent")
    print("=" * 40)
    
    # Check for API key
    if not check_api_key():
        print("\n⚠️  No API key found.")
        print("Set OPENAI_API_KEY or PRAISONAI_OPENAI_API_KEY to use the agent.")
        print("\nFalling back to direct tool usage:\n")
        
        # Demo the tools directly
        print("1. Listing all templates:")
        result = list_all_templates_tool()
        data = json.loads(result)
        for t in data.get("templates", [])[:5]:
            print(f"   - {t['name']}: {t['description'][:50]}...")
        
        print("\n2. Searching for 'video' templates:")
        result = search_templates_tool("video")
        data = json.loads(result)
        for t in data.get("templates", []):
            print(f"   - {t['name']}")
            print(f"     Run: {t['cli_command']}")
        
        return
    
    # Import Agent only if API key is available
    try:
        from praisonaiagents import Agent
    except ImportError:
        print("praisonaiagents not installed. Install with: pip install praisonaiagents")
        return
    
    # Create the Template Finder Agent
    agent = Agent(
        name="Template Finder",
        role="PraisonAI Template Expert",
        goal="Help users find the right template for their needs",
        backstory="""You are an expert on PraisonAI templates. You help users 
        discover templates that match their requirements. You can search templates,
        list all available templates, and provide detailed information about specific
        templates. Always provide the CLI command to run the template.""",
        tools=[
            search_templates_tool,
            list_all_templates_tool,
            get_template_details_tool
        ],
        output="verbose"  # Use new consolidated param
    )
    
    # Example queries
    queries = [
        "Find me a template for editing videos",
        "What templates are available for working with transcripts?",
        "Show me details about the ai-video-editor template"
    ]
    
    print("\nRunning Template Finder Agent...")
    print("-" * 40)
    
    for query in queries:
        print(f"\n📝 Query: {query}")
        print("-" * 40)
        
        try:
            result = agent.start(query)
            print(f"\n🤖 Response:\n{result}")
        except Exception as e:
            print(f"Error: {e}")
        
        print("\n" + "=" * 40)


if __name__ == "__main__":
    main()
