"""
Real API key integration tests for praisonaiagents.

These tests are gated by the RUN_REAL_KEY_TESTS environment variable.
They require valid API keys to be set in the environment.

Usage:
    RUN_REAL_KEY_TESTS=1 pytest tests/integration/test_real_api.py -v

Required environment variables:
    - OPENAI_API_KEY: OpenAI API key
    
Optional:
    - ANTHROPIC_API_KEY: Anthropic API key (for Claude tests)
    - GOOGLE_API_KEY: Google API key (for Gemini tests)
"""
import os
import sys
import pytest

# Gate all tests in this module
pytestmark = pytest.mark.skipif(
    os.environ.get('RUN_REAL_KEY_TESTS', '').lower() not in ('1', 'true', 'yes'),
    reason="Real API key tests disabled. Set RUN_REAL_KEY_TESTS=1 to enable."
)


def clear_modules():
    """Clear all praisonai and litellm related modules from cache."""
    to_remove = [m for m in list(sys.modules.keys()) 
                 if 'praison' in m or 'litellm' in m]
    for mod in to_remove:
        del sys.modules[mod]


class TestAgentRealAPI:
    """Test Agent with real API calls."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        clear_modules()
        
        # Verify API key is set (without printing it)
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            pytest.skip("OPENAI_API_KEY not set")
        
        yield
        clear_modules()
    
    def test_agent_simple_chat(self):
        """Test basic Agent.chat() with real API."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="TestAgent",
            instructions="You are a helpful assistant. Keep responses very brief.",
            llm="gpt-4o-mini",
            verbose=False
        )
        
        response = agent.chat("Say 'hello' and nothing else.")
        
        assert response is not None
        assert len(response) > 0
        assert 'hello' in response.lower()
        
        print(f"[PASS] Agent response received (length: {len(response)})")
    
    def test_agent_with_tool(self):
        """Test Agent with a simple tool."""
        from praisonaiagents import Agent
        
        # Define a simple deterministic tool
        def add_numbers(a: int, b: int) -> int:
            """Add two numbers together."""
            return a + b
        
        agent = Agent(
            name="MathAgent",
            instructions="You are a math assistant. Use the add_numbers tool when asked to add.",
            llm="gpt-4o-mini",
            tools=[add_numbers],
            verbose=False
        )
        
        response = agent.chat("What is 5 + 3? Use the add_numbers tool.")
        
        assert response is not None
        assert '8' in response
        
        print(f"[PASS] Tool call successful, response contains '8'")
    
    def test_agent_chat_history(self):
        """Test that chat history is maintained."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="HistoryAgent",
            instructions="You are a helpful assistant. Remember what the user tells you.",
            llm="gpt-4o-mini",
            verbose=False
        )
        
        # First message
        agent.chat("My favorite color is blue.")
        
        # Second message referencing first
        response = agent.chat("What is my favorite color?")
        
        assert response is not None
        assert 'blue' in response.lower()
        
        print(f"[PASS] Chat history maintained correctly")


class TestLiteAgentRealAPI:
    """Test LiteAgent with real API using OpenAI SDK directly."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        clear_modules()
        
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            pytest.skip("OPENAI_API_KEY not set")
        
        yield
        clear_modules()
    
    def test_lite_agent_with_openai(self):
        """Test LiteAgent with OpenAI SDK."""
        from praisonaiagents.lite import LiteAgent, create_openai_llm_fn
        
        # Create LLM function using OpenAI
        llm_fn = create_openai_llm_fn(model="gpt-4o-mini")
        
        agent = LiteAgent(
            name="LiteTestAgent",
            llm_fn=llm_fn,
            instructions="You are a helpful assistant. Keep responses very brief."
        )
        
        response = agent.chat("Say 'hello' and nothing else.")
        
        assert response is not None
        assert len(response) > 0
        
        print(f"[PASS] LiteAgent with OpenAI response received")
    
    def test_lite_agent_no_litellm_loaded(self):
        """Verify LiteAgent doesn't load litellm."""
        from praisonaiagents.lite import LiteAgent, create_openai_llm_fn
        
        llm_fn = create_openai_llm_fn(model="gpt-4o-mini")
        agent = LiteAgent(llm_fn=llm_fn)
        
        response = agent.chat("Hi")
        
        assert response is not None
        assert 'litellm' not in sys.modules, \
            "LiteAgent should not load litellm"
        
        print(f"[PASS] LiteAgent works without litellm")


class TestAnthropicAPI:
    """Test with Anthropic API (optional)."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        clear_modules()
        
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            pytest.skip("ANTHROPIC_API_KEY not set")
        
        yield
        clear_modules()
    
    def test_agent_with_claude(self):
        """Test Agent with Claude model."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="ClaudeAgent",
            instructions="You are a helpful assistant. Keep responses very brief.",
            llm="claude-3-5-sonnet-20241022",
            verbose=False
        )
        
        response = agent.chat("Say 'hello' and nothing else.")
        
        assert response is not None
        assert len(response) > 0
        
        print(f"[PASS] Claude response received")


class TestGoogleAPI:
    """Test with Google API (optional)."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        clear_modules()
        
        api_key = os.environ.get('GOOGLE_API_KEY')
        if not api_key:
            pytest.skip("GOOGLE_API_KEY not set")
        
        yield
        clear_modules()
    
    def test_agent_with_gemini(self):
        """Test Agent with Gemini model."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="GeminiAgent",
            instructions="You are a helpful assistant. Keep responses very brief.",
            llm="gemini/gemini-2.0-flash",
            verbose=False
        )
        
        response = agent.chat("Say 'hello' and nothing else.")
        
        assert response is not None
        assert len(response) > 0
        
        print(f"[PASS] Gemini response received")


if __name__ == "__main__":
    # Run with real API keys
    if os.environ.get('RUN_REAL_KEY_TESTS', '').lower() not in ('1', 'true', 'yes'):
        print("Set RUN_REAL_KEY_TESTS=1 to run these tests")
        sys.exit(1)
    
    pytest.main([__file__, "-v", "-s"])
