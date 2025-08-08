#!/usr/bin/env python3
"""
Example: Using Custom Trafilatura Tools for High-Quality URL Content Extraction

This example demonstrates how to create and use custom Trafilatura tools in PraisonAI
for extracting high-quality content from web pages.

This shows how to create custom tools that are not part of the core package.

Install dependencies:
pip install trafilatura newspaper3k requests beautifulsoup4
"""

import asyncio
from praisonaiagents import Agent, Task, PraisonAIAgents
from custom_trafilatura_tools import TrafilaturaTools, create_trafilatura_tools

# Create tools instance (global for reuse across examples)
tools = None

def get_tools():
    """Get or create tools instance"""
    global tools
    if tools is None:
        tools = create_trafilatura_tools()
    return tools

# Example 1: Basic content extraction
async def basic_extraction_example():
    """Extract content from a URL using custom Trafilatura tools"""
    tools_instance = get_tools()
    
    # Extract content from a URL
    url = "https://www.python.org/about/"
    content = await asyncio.to_thread(tools_instance.extract_content, url)
    
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
    tools_instance = get_tools()
    
    url = "https://www.python.org/about/"
    text = await asyncio.to_thread(tools_instance.extract_text_only, url)
    
    print(f"Extracted text ({len(text)} characters):")
    print(f"{text[:300]}...")

# Example 3: Extract metadata
async def metadata_example():
    """Extract metadata from a web page"""
    tools_instance = get_tools()
    
    url = "https://www.python.org/about/"
    metadata = await asyncio.to_thread(tools_instance.extract_metadata, url)
    
    print("Page metadata:")
    for key, value in metadata.items():
        if key != 'url':
            print(f"  {key}: {value}")

# Example 4: Compare extraction methods
async def comparison_example():
    """Compare Trafilatura with other extraction tools"""
    tools_instance = get_tools()
    
    url = "https://www.python.org/about/"
    comparison = await asyncio.to_thread(
        tools_instance.compare_extraction,
        url, 
        include_newspaper=True,  # Compare with newspaper3k
        include_spider=True      # Compare with basic scraping
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

# Example 5: Using Custom Trafilatura tools with an Agent
async def agent_example():
    """Use custom Trafilatura tools with an AI agent"""
    tools_instance = get_tools()
    
    # Create wrapper functions for the agent to use
    def extract_content_tool(url: str) -> dict:
        """Extract content from URL using Trafilatura"""
        return tools_instance.extract_content(url)
    
    def extract_metadata_tool(url: str) -> dict:
        """Extract metadata from URL using Trafilatura"""
        return tools_instance.extract_metadata(url)
    
    # Create a research agent with custom Trafilatura tools
    research_agent = Agent(
        name="Research Assistant",
        role="Web Content Analyzer",
        goal="Extract and analyze content from web pages using custom tools",
        backstory="You are an expert at extracting and analyzing web content using custom Trafilatura tools",
        tools=[extract_content_tool, extract_metadata_tool],
        llm="gpt-5-nano"
    )
    
    # Create a task for content analysis
    analysis_task = Task(
        description="""
        Extract content from this URL: https://www.python.org/about/
        
        Use the custom Trafilatura tools to provide a summary of:
        1. The main content and purpose of the page
        2. Key metadata (author, date, language)
        3. The overall quality and structure of the content
        """,
        expected_output="A comprehensive analysis of the web page content using custom tools",
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
    tools_instance = get_tools()
    
    # Extract content targeting specific language
    url = "https://www.python.org/about/"
    content = await asyncio.to_thread(
        tools_instance.extract_content,
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
    tools_instance = get_tools()
    
    url = "https://www.python.org/about/"
    
    # JSON format (default)
    json_content = await asyncio.to_thread(tools_instance.extract_content, url, output_format='json')
    print("JSON format - type:", type(json_content))
    
    # Text format
    text_content = await asyncio.to_thread(tools_instance.extract_content, url, output_format='text')
    print("\nText format - first 200 chars:")
    print(text_content[:200] + "...")
    
    # XML format
    xml_content = await asyncio.to_thread(tools_instance.extract_content, url, output_format='xml')
    print("\nXML format - first 200 chars:")
    print(xml_content[:200] + "...")

# Example 8: Show available methods
async def available_methods_example():
    """Show what methods are available in the custom tool"""
    tools_instance = get_tools()
    
    methods = tools_instance.get_available_methods()
    print("Available methods in custom Trafilatura tools:")
    for method in methods:
        print(f"  - {method}")

# Example 9: Security testing
async def security_example():
    """Test URL validation security features"""
    tools_instance = get_tools()
    
    print("Testing URL security validation:")
    unsafe_urls = [
        "http://localhost/test",
        "http://127.0.0.1/test", 
        "http://169.254.169.254/metadata"
    ]
    
    for unsafe_url in unsafe_urls:
        result = await asyncio.to_thread(tools_instance.extract_content, unsafe_url)
        if isinstance(result, dict) and 'error' in result:
            print(f"✓ Correctly rejected: {unsafe_url}")
        else:
            print(f"✗ Failed to reject: {unsafe_url}")

async def main():
    """Run all examples"""
    print("=== Custom Trafilatura Tools Examples ===\n")
    
    try:
        # First check if we can create the tools
        tools_instance = get_tools()
        print("✓ Successfully created custom Trafilatura tools\n")
        
        print("1. Available Methods")
        print("-" * 40)
        await available_methods_example()
        
        print("\n2. Basic Content Extraction")
        print("-" * 40)
        await basic_extraction_example()
        
        print("\n3. Text-Only Extraction")
        print("-" * 40)
        await text_only_example()
        
        print("\n4. Metadata Extraction")
        print("-" * 40)
        await metadata_example()
        
        print("\n5. Tool Comparison")
        print("-" * 40)
        await comparison_example()
        
        print("\n6. Language-Specific Extraction")
        print("-" * 40)
        await language_example()
        
        print("\n7. Output Format Options")
        print("-" * 40)
        await format_example()
        
        print("\n8. Security Testing")
        print("-" * 40)
        await security_example()
        
        print("\n9. Agent-Based Analysis")
        print("-" * 40)
        await agent_example()
        
    except ImportError as e:
        print(f"✗ Error: {e}")
        print("\nPlease install required dependencies:")
        print("pip install trafilatura newspaper3k requests beautifulsoup4")
    except Exception as e:
        print(f"✗ Unexpected error: {e}")

if __name__ == "__main__":
    # Run the examples
    asyncio.run(main())
