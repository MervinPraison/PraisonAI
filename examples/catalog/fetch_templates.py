#!/usr/bin/env python3
"""
Example: Fetch and search PraisonAI templates from the catalog.

This example demonstrates how to:
- Fetch templates.json from the deployed catalog
- Search templates by keyword
- Filter by tags and requirements
- Generate CLI commands
"""

import json
import urllib.request
from typing import List, Dict, Any, Optional

CATALOG_URL = "https://mervinpraison.github.io/praisonai-template-catalog/data/templates.json"


def fetch_catalog(url: str = CATALOG_URL) -> Dict[str, Any]:
    """Fetch the template catalog from URL."""
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"Failed to fetch catalog: {e}")
        # Return empty catalog on failure
        return {"version": "0.0.0", "count": 0, "templates": []}


def search_templates(templates: List[Dict], query: str) -> List[Dict]:
    """Search templates by name, description, or tags."""
    query = query.lower()
    results = []
    for t in templates:
        if (query in t.get("name", "").lower() or 
            query in t.get("description", "").lower() or
            any(query in tag.lower() for tag in t.get("tags", []))):
            results.append(t)
    return results


def filter_by_tags(templates: List[Dict], tags: List[str]) -> List[Dict]:
    """Filter templates that have all specified tags."""
    return [
        t for t in templates
        if all(tag in t.get("tags", []) for tag in tags)
    ]


def filter_by_tool(templates: List[Dict], tool_name: str) -> List[Dict]:
    """Filter templates that require a specific tool."""
    return [
        t for t in templates
        if tool_name in t.get("requires", {}).get("tools", [])
    ]


def get_template(templates: List[Dict], name: str) -> Optional[Dict]:
    """Get a template by name."""
    for t in templates:
        if t.get("name") == name:
            return t
    return None


def generate_cli_command(template: Dict, action: str = "run") -> str:
    """Generate CLI command for a template."""
    name = template.get("name", "unknown")
    if action == "run":
        return f"praisonai templates run {name}"
    elif action == "info":
        return f"praisonai templates info {name}"
    elif action == "init":
        return f"praisonai templates init my-project --template {name}"
    return f"praisonai templates {action} {name}"


def print_template_summary(template: Dict):
    """Print a summary of a template."""
    print(f"\n{'='*60}")
    print(f"Name: {template.get('name')}")
    print(f"Version: {template.get('version')}")
    print(f"Description: {template.get('description', '')[:100]}...")
    print(f"Tags: {', '.join(template.get('tags', []))}")
    
    requires = template.get("requires", {})
    if requires.get("tools"):
        print(f"Tools: {', '.join(requires['tools'])}")
    if requires.get("packages"):
        print(f"Packages: {', '.join(requires['packages'])}")
    if requires.get("env"):
        print(f"Env vars: {', '.join(requires['env'])}")
    
    print(f"\nRun: {generate_cli_command(template, 'run')}")
    print(f"{'='*60}")


def main():
    print("PraisonAI Template Catalog - Python Example")
    print("-" * 45)
    
    # Fetch catalog
    print("\n1. Fetching template catalog...")
    catalog = fetch_catalog()
    templates = catalog.get("templates", [])
    
    print(f"   Catalog version: {catalog.get('version', 'unknown')}")
    print(f"   Total templates: {len(templates)}")
    
    if not templates:
        print("   No templates found. The catalog may not be deployed yet.")
        print("   Try building locally: praisonai templates catalog build")
        return
    
    # List all templates
    print("\n2. Available templates:")
    for t in templates:
        print(f"   - {t.get('name')} (v{t.get('version')})")
    
    # Search for video templates
    print("\n3. Searching for 'video' templates...")
    video_templates = search_templates(templates, "video")
    print(f"   Found {len(video_templates)} video templates:")
    for t in video_templates:
        print(f"   - {t.get('name')}: {t.get('description', '')[:50]}...")
    
    # Filter by tool
    print("\n4. Templates using 'shell_tool':")
    shell_templates = filter_by_tool(templates, "shell_tool")
    for t in shell_templates:
        print(f"   - {t.get('name')}")
    
    # Get specific template details
    if templates:
        first_template = templates[0]
        print(f"\n5. Template details for '{first_template.get('name')}':")
        print_template_summary(first_template)
    
    # Generate CLI commands
    print("\n6. CLI commands for all templates:")
    for t in templates[:5]:  # First 5 only
        print(f"   {generate_cli_command(t, 'run')}")
    
    print("\nDone!")


if __name__ == "__main__":
    main()
