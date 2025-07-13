#!/usr/bin/env python3
"""
Example: Using Trafilatura Tools for High-Quality URL Content Extraction

This example demonstrates how to use Trafilatura tools in PraisonAI
for extracting high-quality content from web pages.
"""

import asyncio
from praisonaiagents import Agent, Task, PraisonAIAgents

# Example 1: Basic content extraction
async def basic_extraction_example():
    """Extract content from a URL using Trafilatura"""
    from praisonaiagents.tools import extract_content
    
    # Extract content from a URL
    url = "https://www.python.org/about/"
    content = extract_content(url)
    
    if 'error' not in content:
        print(f"Title: {content.get('title', 'N/A')}")
        print(f"Author: {content.get('author', 'N/A')}")
        print(f"Date: {content.get('date', 'N/A')}")
        print(f"Text preview: {content.get('text', '')[:200]}...")
    else:
        print(f"Error: {content['error']}")

# Example 2: Extract text only
async def text_only_example():
    """Extract only the main text content"""
    from praisonaiagents.tools import extract_text_only
    
    url = "https://www.python.org/about/"
    text = extract_text_only(url)
    
    print(f"Extracted text ({len(text)} characters):")
    print(f"{text[:300]}...")

# Example 3: Extract metadata
async def metadata_example():
    """Extract metadata from a web page"""
    from praisonaiagents.tools import extract_metadata
    
    url = "https://www.python.org/about/"
    metadata = extract_metadata(url)
    
    print("Page metadata:")
    for key, value in metadata.items():
        if key != 'url':
            print(f"  {key}: {value}")

# Example 4: Compare extraction methods
async def comparison_example():
    """Compare Trafilatura with other extraction tools"""
    from praisonaiagents.tools import compare_extraction
    
    url = "https://www.python.org/about/"
    comparison = compare_extraction(
        url, 
        include_newspaper=True,  # Compare with newspaper3k
        include_spider=True      # Compare with spider_tools
    )
    
    print("Extraction comparison:")
    for tool, result in comparison.items():
        if tool != 'url' and result:
            if isinstance(result, dict) and 'error' not in result:
                print(f"\n{tool.upper()}:")
                if 'title' in result:
                    print(f"  Title: {result.get('title', 'N/A')}")
                if 'text' in result:
                    text_len = len(result.get('text', ''))
                    print(f"  Text length: {text_len} characters")
            else:
                print(f"\n{tool.upper()}: {result}")

# Example 5: Using Trafilatura with an Agent
async def agent_example():
    """Use Trafilatura tools with an AI agent"""
    from praisonaiagents.tools import extract_content, extract_metadata
    
    # Create a research agent with Trafilatura tools
    research_agent = Agent(
        name="Research Assistant",
        role="Web Content Analyzer",
        goal="Extract and analyze content from web pages",
        backstory="You are an expert at extracting and analyzing web content",
        tools=[extract_content, extract_metadata],
        llm="gpt-4o-mini"
    )
    
    # Create a task for content analysis
    analysis_task = Task(
        description="""
        Extract content from this URL: https://www.python.org/about/
        
        Provide a summary of:
        1. The main content and purpose of the page
        2. Key metadata (author, date, language)
        3. The overall quality and structure of the content
        """,
        expected_output="A comprehensive analysis of the web page content",
        agent=research_agent
    )
    
    # Run the analysis
    agents = PraisonAIAgents(
        agents=[research_agent],
        tasks=[analysis_task]
    )
    
    result = await agents.astart()
    print("\nAgent Analysis Result:")
    print(result)

# Example 6: Content extraction with language specification
async def language_example():
    """Extract content with specific language targeting"""
    from praisonaiagents.tools import extract_content
    
    # Extract content targeting specific language
    url = "https://www.python.org/about/"
    content = extract_content(
        url,
        target_language="en",  # Target English content
        include_links=True,    # Include links in extraction
        include_comments=False # Exclude comments
    )
    
    if 'error' not in content:
        print(f"Language: {content.get('language', 'N/A')}")
        print(f"Number of links: {len(content.get('links', []))}")

# Example 7: Output format options
async def format_example():
    """Demonstrate different output formats"""
    from praisonaiagents.tools import extract_content
    
    url = "https://www.python.org/about/"
    
    # JSON format (default)
    json_content = extract_content(url, output_format='json')
    print("JSON format - type:", type(json_content))
    
    # Text format
    text_content = extract_content(url, output_format='text')
    print("\nText format - first 200 chars:")
    print(text_content[:200] + "...")
    
    # XML format
    xml_content = extract_content(url, output_format='xml')
    print("\nXML format - first 200 chars:")
    print(xml_content[:200] + "...")

async def main():
    """Run all examples"""
    print("=== Trafilatura Tools Examples ===\n")
    
    print("1. Basic Content Extraction")
    print("-" * 40)
    await basic_extraction_example()
    
    print("\n2. Text-Only Extraction")
    print("-" * 40)
    await text_only_example()
    
    print("\n3. Metadata Extraction")
    print("-" * 40)
    await metadata_example()
    
    print("\n4. Tool Comparison")
    print("-" * 40)
    await comparison_example()
    
    print("\n5. Language-Specific Extraction")
    print("-" * 40)
    await language_example()
    
    print("\n6. Output Format Options")
    print("-" * 40)
    await format_example()
    
    print("\n7. Agent-Based Analysis")
    print("-" * 40)
    await agent_example()

if __name__ == "__main__":
    # Run the examples
    asyncio.run(main())