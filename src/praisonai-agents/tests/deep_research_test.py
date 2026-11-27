"""
Test file for DeepResearchAgent

This file tests the OpenAI Deep Research API integration.
Requires OPENAI_API_KEY environment variable to be set.

Usage:
    python tests/deep_research_test.py
"""

import os
import sys

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from praisonaiagents import (
    DeepResearchAgent,
    DeepResearchResponse,
    ReasoningStep,
    WebSearchCall,
    CodeExecutionStep,
    MCPCall,
    FileSearchCall,
    Provider
)
from praisonaiagents.agent.deep_research_agent import Citation


def test_basic_import():
    """Test that all classes can be imported."""
    assert DeepResearchAgent is not None
    assert DeepResearchResponse is not None
    assert Citation is not None
    assert ReasoningStep is not None
    assert WebSearchCall is not None
    assert CodeExecutionStep is not None
    assert MCPCall is not None
    assert FileSearchCall is not None
    assert Provider.OPENAI is not None
    assert Provider.GEMINI is not None
    assert Provider.LITELLM is not None


def test_agent_initialization():
    """Test DeepResearchAgent initialization."""
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")
    
    agent = DeepResearchAgent(
        name="Test Researcher",
        instructions="You are a professional researcher.",
        model="o3-deep-research",
        verbose=True
    )
    
    assert agent.name == "Test Researcher"
    assert agent.model == "o3-deep-research"


def test_data_classes():
    """Test data class creation and methods."""
    citation = Citation(
        title="Test Source",
        url="https://example.com",
        start_index=0,
        end_index=100
    )
    reasoning = ReasoningStep(text="Analyzing the query...")
    search = WebSearchCall(query="test query", status="completed")
    code = CodeExecutionStep(input_code="print('hello')", output="hello")
    mcp = MCPCall(name="fetch", server_label="internal", arguments={"file_id": "123"})

    response = DeepResearchResponse(
        report="This is a test report about AI.",
        citations=[citation],
        reasoning_steps=[reasoning],
        web_searches=[search],
        code_executions=[code],
        mcp_calls=[mcp]
    )
    assert response.report == "This is a test report about AI."
    assert len(response.citations) == 1
    assert len(response.reasoning_steps) == 1
    assert len(response.web_searches) == 1
    assert len(response.code_executions) == 1
    assert len(response.mcp_calls) == 1
    assert response.get_all_sources()


def test_research_query():
    """Test actual research query (requires API key)."""
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")
    
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
    
    result = agent.research(
        "What are the key trends in AI adoption in healthcare in 2024?",
        summary_mode="concise"
    )
    assert result is not None
    assert result.report


def test_clarify_and_rewrite():
    """Test clarifying questions and query rewriting."""
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")
    
    agent = DeepResearchAgent(
        name="Research Assistant",
        verbose=True
    )
    
    questions = agent.clarify("Help me research AI trends")
    assert questions

    rewritten = agent.rewrite_query("Research AI in healthcare")
    assert rewritten


def test_mcp_configuration():
    """Test MCP server configuration."""
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")
    
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
    
    assert len(agent.mcp_servers) == 1
    tools = agent._build_tools(
        web_search=True,
        code_interpreter=True,
        mcp_servers=agent.mcp_servers
    )
    assert len(tools) >= 1


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
            test_fn()
            results.append((name, True))
        except pytest.skip.Exception as e:
            print(f"⚠ Skipped: {e}")
            results.append((name, True))
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
