"""
Test file for DeepResearchAgent

This file tests the OpenAI Deep Research API integration.
Requires OPENAI_API_KEY environment variable to be set.

Usage:
    python tests/deep_research_test.py
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from praisonaiagents import (
    DeepResearchAgent,
    DeepResearchResponse,
    Citation,
    ReasoningStep,
    WebSearchCall,
    CodeExecutionStep,
    MCPCall,
    FileSearchCall,
    Provider
)


def test_basic_import():
    """Test that all classes can be imported."""
    print("✓ All Deep Research classes imported successfully")
    print(f"  - DeepResearchAgent: {DeepResearchAgent}")
    print(f"  - DeepResearchResponse: {DeepResearchResponse}")
    print(f"  - Citation: {Citation}")
    print(f"  - ReasoningStep: {ReasoningStep}")
    print(f"  - WebSearchCall: {WebSearchCall}")
    print(f"  - CodeExecutionStep: {CodeExecutionStep}")
    print(f"  - MCPCall: {MCPCall}")
    print(f"  - FileSearchCall: {FileSearchCall}")
    print(f"  - Provider: {Provider}")
    print(f"  - Provider.OPENAI: {Provider.OPENAI}")
    print(f"  - Provider.GEMINI: {Provider.GEMINI}")
    print(f"  - Provider.LITELLM: {Provider.LITELLM}")
    return True


def test_agent_initialization():
    """Test DeepResearchAgent initialization."""
    # Check if API key is available
    if not os.environ.get("OPENAI_API_KEY"):
        print("⚠ Skipping initialization test - OPENAI_API_KEY not set")
        return True
    
    agent = DeepResearchAgent(
        name="Test Researcher",
        instructions="You are a professional researcher.",
        model="o3-deep-research",
        verbose=True
    )
    
    print(f"✓ Agent initialized: {agent}")
    print(f"  - Name: {agent.name}")
    print(f"  - Model: {agent.model}")
    print(f"  - Web search enabled: {agent.enable_web_search}")
    print(f"  - Code interpreter enabled: {agent.enable_code_interpreter}")
    return True


def test_data_classes():
    """Test data class creation and methods."""
    # Test Citation
    citation = Citation(
        title="Test Source",
        url="https://example.com",
        start_index=0,
        end_index=100
    )
    print(f"✓ Citation created: {citation}")
    
    # Test ReasoningStep
    reasoning = ReasoningStep(text="Analyzing the query...")
    print(f"✓ ReasoningStep created: {reasoning}")
    
    # Test WebSearchCall
    search = WebSearchCall(query="test query", status="completed")
    print(f"✓ WebSearchCall created: {search}")
    
    # Test CodeExecutionStep
    code = CodeExecutionStep(input_code="print('hello')", output="hello")
    print(f"✓ CodeExecutionStep created: {code}")
    
    # Test MCPCall
    mcp = MCPCall(name="fetch", server_label="internal", arguments={"file_id": "123"})
    print(f"✓ MCPCall created: {mcp}")
    
    # Test DeepResearchResponse
    response = DeepResearchResponse(
        report="This is a test report about AI.",
        citations=[citation],
        reasoning_steps=[reasoning],
        web_searches=[search],
        code_executions=[code],
        mcp_calls=[mcp]
    )
    print(f"✓ DeepResearchResponse created")
    print(f"  - Report length: {len(response.report)} chars")
    print(f"  - Citations: {len(response.citations)}")
    print(f"  - Sources: {response.get_all_sources()}")
    
    return True


def test_research_query():
    """Test actual research query (requires API key)."""
    if not os.environ.get("OPENAI_API_KEY"):
        print("⚠ Skipping research test - OPENAI_API_KEY not set")
        return True
    
    agent = DeepResearchAgent(
        name="Healthcare Researcher",
        instructions="""
        You are a professional researcher preparing a structured, data-driven report.
        Focus on data-rich insights with specific figures and trends.
        Include inline citations and prioritize reliable sources.
        """,
        model="o4-mini-deep-research",  # Use faster model for testing
        verbose=True,
        enable_code_interpreter=False
    )
    
    print("\n🔍 Starting deep research query...")
    print("   (This may take several minutes)")
    
    try:
        result = agent.research(
            "What are the key trends in AI adoption in healthcare in 2024?",
            summary_mode="concise"
        )
        
        print(f"\n✓ Research completed!")
        print(f"  - Report length: {len(result.report)} characters")
        print(f"  - Citations found: {len(result.citations)}")
        print(f"  - Reasoning steps: {len(result.reasoning_steps)}")
        print(f"  - Web searches: {len(result.web_searches)}")
        print(f"  - Code executions: {len(result.code_executions)}")
        
        # Print first 500 chars of report
        print(f"\n📄 Report excerpt:")
        print(f"   {result.report[:500]}...")
        
        # Print some citations
        if result.citations:
            print(f"\n📚 Sample citations:")
            for i, c in enumerate(result.citations[:3]):
                print(f"   {i+1}. {c.title}: {c.url}")
        
        # Print web searches
        if result.web_searches:
            print(f"\n🔎 Web searches performed:")
            for s in result.web_searches[:5]:
                print(f"   - {s.query} ({s.status})")
        
        return True
        
    except Exception as e:
        print(f"✗ Research failed: {e}")
        return False


def test_clarify_and_rewrite():
    """Test clarifying questions and query rewriting."""
    if not os.environ.get("OPENAI_API_KEY"):
        print("⚠ Skipping clarify/rewrite test - OPENAI_API_KEY not set")
        return True
    
    agent = DeepResearchAgent(
        name="Research Assistant",
        verbose=True
    )
    
    print("\n🤔 Testing clarifying questions...")
    try:
        questions = agent.clarify("Help me research AI trends")
        print(f"✓ Clarifying questions generated:")
        print(f"   {questions[:300]}...")
    except Exception as e:
        print(f"✗ Clarify failed: {e}")
        return False
    
    print("\n✍️ Testing query rewriting...")
    try:
        rewritten = agent.rewrite_query("Research AI in healthcare")
        print(f"✓ Query rewritten:")
        print(f"   {rewritten[:300]}...")
    except Exception as e:
        print(f"✗ Rewrite failed: {e}")
        return False
    
    return True


def test_mcp_configuration():
    """Test MCP server configuration."""
    if not os.environ.get("OPENAI_API_KEY"):
        print("⚠ Skipping MCP test - OPENAI_API_KEY not set")
        return True
    
    # Test agent with MCP configuration
    agent = DeepResearchAgent(
        name="MCP Researcher",
        instructions="You are a researcher with access to internal documents.",
        mcp_servers=[
            {
                "label": "internal_docs",
                "url": "https://example.com/mcp/sse/",
                "require_approval": "never"
            }
        ],
        verbose=True
    )
    
    print(f"✓ Agent with MCP configured: {agent}")
    print(f"  - MCP servers: {len(agent.mcp_servers)}")
    
    # Test tool building
    tools = agent._build_tools(
        web_search=True,
        code_interpreter=True,
        mcp_servers=agent.mcp_servers
    )
    
    print(f"✓ Tools built: {len(tools)} tools")
    for t in tools:
        print(f"  - {t.get('type', 'unknown')}")
    
    return True


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("DeepResearchAgent Test Suite")
    print("=" * 60)
    
    tests = [
        ("Import Test", test_basic_import),
        ("Data Classes Test", test_data_classes),
        ("Agent Initialization Test", test_agent_initialization),
        ("MCP Configuration Test", test_mcp_configuration),
        ("Clarify & Rewrite Test", test_clarify_and_rewrite),
        ("Research Query Test", test_research_query),
    ]
    
    results = []
    for name, test_fn in tests:
        print(f"\n{'─' * 40}")
        print(f"Running: {name}")
        print(f"{'─' * 40}")
        try:
            success = test_fn()
            results.append((name, success))
        except Exception as e:
            print(f"✗ Test failed with exception: {e}")
            results.append((name, False))
    
    # Summary
    print(f"\n{'=' * 60}")
    print("Test Summary")
    print(f"{'=' * 60}")
    passed = sum(1 for _, s in results if s)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    for name, success in results:
        status = "✓" if success else "✗"
        print(f"  {status} {name}")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
