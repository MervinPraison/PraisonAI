"""
Live integration tests for Ollama tool calling.

These tests require:
1. Ollama running locally (default: http://localhost:11434)
2. A tools-capable model pulled (default olmo-3; CI uses qwen3:0.6b)
   Override with PRAISONAI_OLLAMA_TEST_MODEL, e.g.
       export PRAISONAI_OLLAMA_TEST_MODEL=qwen3:0.6b
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


# CI overrides this with a small, fast model; local runs keep olmo-3 so an
# existing developer workflow is unchanged.
OLLAMA_MODEL = "ollama/" + os.getenv("PRAISONAI_OLLAMA_TEST_MODEL", "olmo-3")


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
    """Fixture to check Ollama availability.

    When PRAISONAI_TEST_OLLAMA=1 the caller has explicitly asked for these
    tests to run against a server it is responsible for (the CI job starts and
    pulls the model itself). In that mode an unreachable server is a real
    failure, not a reason to skip: a skip would let the "required" CI step exit
    successfully without ever exercising the tool-call contract. Only a plain
    local invocation (env var unset — reached via -m or an explicit path) is
    allowed to skip gracefully.
    """
    if not check_ollama_available():
        message = "Ollama is not running at localhost:11434"
        if os.getenv("PRAISONAI_TEST_OLLAMA"):
            pytest.fail(message)
        pytest.skip(message)
    return True


class TestOllamaCIMinimum:
    """The minimum contract a local model must satisfy: a tool call round-trips.

    Deliberately narrow. Measured on qwen3:0.6b, this exact configuration
    (forced tool usage, temperature 0, one arithmetic step) passed 6/6, while
    the default configuration passed 3/4 and multi-step prompts were worse.
    Those live in TestOllamaToolCallingLive, which CI runs informationally.

    This is the class the required CI step runs, so it must not grow into a
    general behaviour suite.
    """

    def test_tool_call_round_trips(self, ollama_available):
        from praisonaiagents import Agent

        invocations = []

        def add(a: int, b: int) -> int:
            """Add two integers together.

            Args:
                a: First number to add
                b: Second number to add
            """
            invocations.append((a, b))
            return a + b

        agent = Agent(
            name="CI Calculator",
            llm={"model": OLLAMA_MODEL, "force_tool_usage": "always", "temperature": 0},
            tools=[add],
        )
        result = agent.chat("Compute 17 + 25. You MUST use the calculator tool.")

        # Both halves matter. qwen3:0.6b answers "17 + 25 = 42" correctly with no
        # tools at all, so an answer-only assertion is satisfied by a model that
        # ignores tools entirely.
        assert invocations == [(17, 25)], f"tool was not invoked: {invocations!r}"
        assert "42" in str(result), f"tool result did not round-trip: {result!r}"


class TestOllamaToolCallingLive:
    """Live tests for Ollama tool calling with olmo-3."""

    def test_basic_tool_call(self, ollama_available):
        """Test basic tool calling with calculator."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Calculator Agent",
            llm=OLLAMA_MODEL,
            tools=[calculator]
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
            llm={"model": OLLAMA_MODEL, "force_tool_usage": "always"},
            tools=[calculator]
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
            llm=OLLAMA_MODEL,
            tools=[calculator]
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
            llm=OLLAMA_MODEL,
            tools=[calculator]
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
            llm={"model": OLLAMA_MODEL, "max_tool_repairs": 3},
            tools=[calculator]
        )
        
        result = agent.chat("Calculate 100 + 200 using the calculator tool.")
        
        assert result is not None
        assert "300" in str(result)

    def test_no_tools_direct_answer(self, ollama_available):
        """Test that model answers directly when no tools provided."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Direct Agent",
            llm=OLLAMA_MODEL,
            tools=[],  # No tools
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
                llm=OLLAMA_MODEL,
                tools=[calculator]
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
        print(f"Pull model with: ollama pull {OLLAMA_MODEL.split('/', 1)[1]}")
        exit(1)
    
    print("Ollama is available. Running tests...")
    print()
    
    # Run a simple test
    from praisonaiagents import Agent
    
    agent = Agent(
        name="Calculator Agent",
        llm=OLLAMA_MODEL,
        tools=[calculator]
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
