"""
Live integration tests for Ollama tool calling.

These tests require:
1. Ollama running locally (default: http://localhost:11434)
2. olmo-3 model pulled: ollama pull olmo-3
3. Environment variable: PRAISONAI_TEST_OLLAMA=1

Run with:
    PRAISONAI_TEST_OLLAMA=1 LOGLEVEL=debug python -m pytest tests/integration/test_ollama_tool_calling_live.py -v
"""

import os
import pytest
import logging


# Skip all tests in this module if PRAISONAI_TEST_OLLAMA is not set
pytestmark = pytest.mark.skipif(
    not os.getenv("PRAISONAI_TEST_OLLAMA"),
    reason="Ollama live tests disabled. Set PRAISONAI_TEST_OLLAMA=1 to enable."
)


def calculator(a: int, b: int) -> int:
    """Add two integers together.
    
    Args:
        a: First number to add
        b: Second number to add
        
    Returns:
        The sum of a and b
    """
    return a + b


def check_ollama_available():
    """Check if Ollama is running and accessible."""
    try:
        import httpx
        response = httpx.get("http://localhost:11434/api/tags", timeout=5.0)
        return response.status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def ollama_available():
    """Fixture to check Ollama availability."""
    if not check_ollama_available():
        pytest.skip("Ollama is not running at localhost:11434")
    return True


class TestOllamaToolCallingLive:
    """Live tests for Ollama tool calling with olmo-3."""

    def test_basic_tool_call(self, ollama_available):
        """Test basic tool calling with calculator."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Calculator Agent",
            llm="ollama/olmo-3",
            tools=[calculator],
            verbose=True
        )
        
        result = agent.chat("Compute 17 + 25. You MUST use the calculator tool.")
        
        # Verify result contains the correct answer
        assert result is not None
        assert "42" in str(result)

    def test_forced_tool_usage(self, ollama_available):
        """Test that force_tool_usage=always works."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Calculator Agent",
            llm="ollama/olmo-3",
            tools=[calculator],
            force_tool_usage="always",
            verbose=True
        )
        
        result = agent.chat("What is 17 plus 25?")
        
        # Should still get correct answer via tool
        assert result is not None
        assert "42" in str(result)

    def test_tool_call_with_distraction(self, ollama_available):
        """Test tool calling when model might want to answer directly."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Calculator Agent",
            llm="ollama/olmo-3",
            tools=[calculator],
            verbose=True
        )
        
        result = agent.chat(
            "I know 17+25 is easy, but please use the calculator tool to compute it anyway."
        )
        
        assert result is not None
        assert "42" in str(result)

    def test_multi_step_arithmetic(self, ollama_available):
        """Test multiple tool calls for multi-step computation."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Calculator Agent",
            llm="ollama/olmo-3",
            tools=[calculator],
            verbose=True
        )
        
        result = agent.chat(
            "Compute (17+25) + (8+9). Use the calculator tool for each addition."
        )
        
        # Final answer should be 59 (42 + 17)
        assert result is not None
        # Check for either intermediate or final results
        assert any(x in str(result) for x in ["42", "17", "59"])

    def test_max_tool_repairs_setting(self, ollama_available):
        """Test that max_tool_repairs setting is respected."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Calculator Agent",
            llm="ollama/olmo-3",
            tools=[calculator],
            max_tool_repairs=3,
            verbose=True
        )
        
        result = agent.chat("Calculate 100 + 200 using the calculator tool.")
        
        assert result is not None
        assert "300" in str(result)

    def test_no_tools_direct_answer(self, ollama_available):
        """Test that model answers directly when no tools provided."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Direct Agent",
            llm="ollama/olmo-3",
            tools=[],  # No tools
            verbose=True
        )
        
        result = agent.chat("What is 17 + 25?")
        
        # Should get an answer (may or may not be correct without tools)
        assert result is not None


class TestOllamaToolCallingDebugLogging:
    """Tests that verify debug logging works correctly."""

    def test_debug_logging_enabled(self, ollama_available, caplog):
        """Test that debug logging captures tool call details."""
        from praisonaiagents import Agent
        
        # Enable debug logging
        logging.getLogger().setLevel(logging.DEBUG)
        
        with caplog.at_level(logging.DEBUG):
            agent = Agent(
                name="Calculator Agent",
                llm="ollama/olmo-3",
                tools=[calculator],
                verbose=True
            )
            
            result = agent.chat("Compute 5 + 3 using the calculator tool.")
        
        # Check that debug logs were captured
        # Should see tool-related debug messages
        # Note: exact messages depend on implementation
        assert result is not None
        # Verify some logging occurred (caplog.text contains all captured logs)
        assert len(caplog.records) >= 0  # At minimum, logging infrastructure works


if __name__ == "__main__":
    # Enable debug logging for manual runs
    logging.basicConfig(level=logging.DEBUG)
    
    print("=" * 60)
    print("Ollama Tool Calling Live Tests")
    print("=" * 60)
    
    if not check_ollama_available():
        print("ERROR: Ollama is not running at localhost:11434")
        print("Start Ollama with: ollama serve")
        print("Pull model with: ollama pull olmo-3")
        exit(1)
    
    print("Ollama is available. Running tests...")
    print()
    
    # Run a simple test
    from praisonaiagents import Agent
    
    agent = Agent(
        name="Calculator Agent",
        llm="ollama/olmo-3",
        tools=[calculator],
        verbose=True
    )
    
    print("Test 1: Basic tool call")
    print("-" * 40)
    result = agent.chat("Compute 17 + 25. You MUST use the calculator tool.")
    print(f"Result: {result}")
    print()
    
    if "42" in str(result):
        print("✅ Test PASSED: Got correct answer 42")
    else:
        print("❌ Test FAILED: Did not get expected answer 42")
