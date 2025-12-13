"""
Deep Research Agent Examples

This file demonstrates how to use the DeepResearchAgent for automated
complex research workflows using multiple providers:

- **OpenAI**: o3-deep-research, o4-mini-deep-research (via Responses API)
- **Gemini**: deep-research-pro (via Interactions API)
- **LiteLLM**: Unified interface for OpenAI models

Requirements:
    - OPENAI_API_KEY for OpenAI/LiteLLM providers
    - GEMINI_API_KEY for Gemini provider
    - OpenAI SDK >= 1.0.0
    - google-genai for Gemini (pip install google-genai)
    - litellm for LiteLLM provider (pip install litellm)

Available models:
    OpenAI:
    - o3-deep-research: Higher quality, in-depth synthesis
    - o4-mini-deep-research: Faster, lightweight
    
    Gemini:
    - deep-research-pro: Gemini 3 Pro powered research agent
"""

from praisonaiagents import DeepResearchAgent, Provider


# =============================================================================
# Example 1: Basic Research Query
# =============================================================================
def basic_research_example():
    """Simple research query with default settings."""
    
    agent = DeepResearchAgent(
        name="Research Assistant",
        instructions="""
        You are a professional researcher. Focus on:
        - Data-rich insights with specific figures and trends
        - Reliable sources: peer-reviewed research, official reports
        - Include inline citations
        """,
        model="o4-mini-deep-research",  # Use faster model
        verbose=True
    )
    
    result = agent.research(
        "What are the key trends in renewable energy adoption in 2024?"
    )
    
    print("=" * 60)
    print("RESEARCH REPORT")
    print("=" * 60)
    print(result.report)
    
    print("\n" + "=" * 60)
    print("CITATIONS")
    print("=" * 60)
    for i, citation in enumerate(result.citations, 1):
        print(f"{i}. {citation.title}")
        print(f"   URL: {citation.url}")
    
    return result


# =============================================================================
# Example 2: Gemini Deep Research
# =============================================================================
def gemini_research_example():
    """Research using Gemini Deep Research Agent."""
    
    agent = DeepResearchAgent(
        name="Gemini Researcher",
        instructions="""
        You are a professional researcher. Focus on:
        - Comprehensive analysis with multiple perspectives
        - Data-backed insights and trends
        - Clear structure with executive summary
        """,
        model="deep-research-pro",  # Gemini model - auto-detected
        verbose=True
    )
    
    print(f"Using provider: {agent.provider}")  # Should be Provider.GEMINI
    
    result = agent.research(
        "What are the latest breakthroughs in fusion energy research?"
    )
    
    print("=" * 60)
    print("GEMINI RESEARCH REPORT")
    print("=" * 60)
    print(result.report[:1000] + "..." if len(result.report) > 1000 else result.report)
    
    return result


# =============================================================================
# Example 3: Research with Code Interpreter (OpenAI)
# =============================================================================
def research_with_code_example():
    """Research with code execution for data analysis."""
    
    agent = DeepResearchAgent(
        name="Data Analyst",
        instructions="""
        You are a data analyst. When appropriate:
        - Use code to analyze data and create visualizations
        - Summarize data in tables
        - Include specific statistics and metrics
        """,
        model="o3-deep-research",
        enable_code_interpreter=True,
        verbose=True
    )
    
    result = agent.research(
        "Analyze the global smartphone market share trends over the past 5 years.",
        summary_mode="detailed"
    )
    
    # Check if any code was executed
    if result.code_executions:
        print("\nCode executed during research:")
        for code in result.code_executions:
            print(f"  Input: {code.input_code[:100]}...")
            if code.output:
                print(f"  Output: {code.output[:100]}...")
    
    return result


# =============================================================================
# Example 4: Using LiteLLM Provider
# =============================================================================
def litellm_research_example():
    """Research using LiteLLM for unified interface."""
    
    agent = DeepResearchAgent(
        name="LiteLLM Researcher",
        instructions="You are a professional researcher.",
        model="o3-deep-research",
        use_litellm=True,  # Use LiteLLM instead of direct OpenAI
        verbose=True
    )
    
    print(f"Using provider: {agent.provider}")  # Should be Provider.LITELLM
    
    result = agent.research(
        "What are the key trends in sustainable agriculture?"
    )
    
    print(f"Report length: {len(result.report)} characters")
    return result


# =============================================================================
# Example 5: Research with MCP Integration (OpenAI)
# =============================================================================
def research_with_mcp_example():
    """Research with custom MCP server for internal documents."""
    
    agent = DeepResearchAgent(
        name="Internal Researcher",
        instructions="""
        You are a researcher with access to internal documents.
        - Use the internal file lookup tool to retrieve company data
        - Combine internal data with public research
        - Prioritize internal sources when available
        """,
        model="o3-deep-research",
        mcp_servers=[
            {
                "label": "internal_docs",
                "url": "https://your-mcp-server.com/sse/",
                "require_approval": "never"
            }
        ],
        verbose=True
    )
    
    result = agent.research(
        "What is our company's market position compared to competitors?"
    )
    
    # Check MCP calls
    if result.mcp_calls:
        print("\nMCP tools used:")
        for call in result.mcp_calls:
            print(f"  - {call.name}@{call.server_label}: {call.arguments}")
    
    return result


# =============================================================================
# Example 6: Gemini with File Search
# =============================================================================
def gemini_file_search_example():
    """Research using Gemini with your own data via File Search."""
    
    agent = DeepResearchAgent(
        name="Document Researcher",
        instructions="""
        Compare our internal documents against current public information.
        Prioritize insights from our internal data.
        """,
        model="deep-research-pro",
        enable_file_search=True,
        file_search_stores=["fileSearchStores/my-store-name"],
        verbose=True
    )
    
    result = agent.research(
        "Compare our 2025 fiscal year report against current market trends."
    )
    
    return result


# =============================================================================
# Example 7: Clarifying Questions Workflow
# =============================================================================
def clarifying_workflow_example():
    """Use clarifying questions before research."""
    
    agent = DeepResearchAgent(
        name="Research Assistant",
        verbose=True
    )
    
    # Step 1: Get clarifying questions
    initial_query = "Help me research AI trends"
    questions = agent.clarify(initial_query)
    
    print("Clarifying Questions:")
    print(questions)
    
    # Step 2: User provides more details (simulated)
    detailed_query = """
    I'd like to research AI trends in healthcare specifically.
    Focus on:
    - Diagnostic AI applications
    - FDA-approved AI tools
    - Cost savings for hospitals
    Time period: 2023-2024
    """
    
    # Step 3: Rewrite the query for optimal research
    rewritten = agent.rewrite_query(detailed_query)
    print("\nRewritten Query:")
    print(rewritten)
    
    # Step 4: Perform the research
    result = agent.research(rewritten)
    
    return result


# =============================================================================
# Example 5: Async Research
# =============================================================================
async def async_research_example():
    """Perform research asynchronously."""
    import asyncio
    
    agent = DeepResearchAgent(
        name="Async Researcher",
        model="o4-mini-deep-research",
        verbose=True
    )
    
    # Run multiple research queries concurrently
    queries = [
        "What are the latest developments in quantum computing?",
        "What are the trends in electric vehicle adoption?",
    ]
    
    tasks = [agent.aresearch(q) for q in queries]
    results = await asyncio.gather(*tasks)
    
    for query, result in zip(queries, results):
        print(f"\nQuery: {query}")
        print(f"Report length: {len(result.report)} chars")
        print(f"Citations: {len(result.citations)}")
    
    return results


# =============================================================================
# Example 6: Inspecting Intermediate Steps
# =============================================================================
def inspect_steps_example():
    """Inspect the research process steps."""
    
    agent = DeepResearchAgent(
        name="Detailed Researcher",
        model="o4-mini-deep-research",
        verbose=True
    )
    
    result = agent.research(
        "What are the environmental impacts of cryptocurrency mining?"
    )
    
    print("\n" + "=" * 60)
    print("RESEARCH PROCESS ANALYSIS")
    print("=" * 60)
    
    # Reasoning steps
    print(f"\nReasoning Steps ({len(result.reasoning_steps)}):")
    for i, step in enumerate(result.reasoning_steps, 1):
        print(f"  {i}. {step.text[:100]}...")
    
    # Web searches
    print(f"\nWeb Searches ({len(result.web_searches)}):")
    for search in result.web_searches:
        print(f"  - Query: {search.query}")
        print(f"    Status: {search.status}")
    
    # Sources
    print(f"\nUnique Sources ({len(result.get_all_sources())}):")
    for source in result.get_all_sources()[:10]:
        print(f"  - {source['title']}")
        print(f"    {source['url']}")
    
    return result


# =============================================================================
# Main
# =============================================================================
if __name__ == "__main__":
    import os
    
    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set")
        print("Please set it before running examples:")
        print("  export OPENAI_API_KEY='your-api-key'")
        exit(1)
    
    print("Running basic research example...")
    result = basic_research_example()
    print(f"\nCompleted! Report has {len(result.report)} characters and {len(result.citations)} citations.")
