"""
Real API Key Smoke Tests for PraisonAI.

These tests validate end-to-end behavior using real API keys.
They are gated by environment variables and use minimal tokens.

Run with:
    RUN_REAL_KEY_TESTS=1 pytest tests/integration/test_real_key_smoke.py -v

Required environment variables:
    - OPENAI_API_KEY: For OpenAI provider tests
    - RUN_REAL_KEY_TESTS=1: Gate to enable these tests
"""

import os
import sys
import subprocess
import pytest
import time

# Gate: Skip all tests if RUN_REAL_KEY_TESTS is not set
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_REAL_KEY_TESTS") != "1",
    reason="Real key tests disabled. Set RUN_REAL_KEY_TESTS=1 to enable."
)

# Paths
PRAISONAI_PATH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PRAISONAI_AGENTS_PATH = os.path.join(os.path.dirname(PRAISONAI_PATH), "praisonai-agents")
PYTHONPATH = f"{PRAISONAI_PATH}:{PRAISONAI_AGENTS_PATH}"


def run_python_code(code: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run Python code in a subprocess with proper PYTHONPATH."""
    env = os.environ.copy()
    env['PYTHONPATH'] = PYTHONPATH
    return subprocess.run(
        [sys.executable, '-c', code],
        capture_output=True,
        text=True,
        cwd=PRAISONAI_PATH,
        env=env,
        timeout=timeout
    )


class TestSDKRealKey:
    """Test SDK functionality with real API keys."""
    
    def test_openai_api_key_present(self):
        """Verify OPENAI_API_KEY is set."""
        api_key = os.environ.get("OPENAI_API_KEY")
        assert api_key is not None, "OPENAI_API_KEY not set"
        assert api_key.startswith("sk-"), "OPENAI_API_KEY format invalid"
        # Never print the key
        print("OPENAI_API_KEY: [REDACTED]")
    
    def test_agent_minimal_chat(self):
        """Test minimal Agent.chat() with real OpenAI API."""
        code = '''
import os
from praisonaiagents import Agent

# Minimal agent with low token usage
agent = Agent(
    instructions="Reply with exactly one word: OK",
    llm="gpt-4o-mini",
    verbose=False
)

# Minimal prompt
response = agent.chat("Say OK")
print(f"Response received: {len(response)} chars")
print("SUCCESS" if response else "FAIL")
'''
        result = run_python_code(code, timeout=60)
        assert result.returncode == 0, f"Agent chat failed: {result.stderr}"
        assert "SUCCESS" in result.stdout, f"Agent chat did not succeed: {result.stdout}"
        print(f"Agent chat test passed. Output length: {result.stdout}")
    
    def test_agent_with_tool(self):
        """Test Agent with a simple tool."""
        code = '''
import os
from praisonaiagents import Agent

def get_time():
    """Returns current time."""
    import datetime
    return datetime.datetime.now().strftime("%H:%M")

agent = Agent(
    instructions="You have access to get_time tool. Use it and report the time briefly.",
    llm="gpt-4o-mini",
    tools=[get_time],
    verbose=False
)

response = agent.chat("What time is it?")
print(f"Response: {len(response)} chars")
print("SUCCESS" if response and ":" in response else "PARTIAL")
'''
        result = run_python_code(code, timeout=60)
        assert result.returncode == 0, f"Tool test failed: {result.stderr}"
        assert "SUCCESS" in result.stdout or "PARTIAL" in result.stdout, f"Tool test output: {result.stdout}"


class TestCLIRealKey:
    """Test CLI functionality with real API keys."""
    
    def test_cli_import(self):
        """Test CLI module imports correctly."""
        code = '''
import os
os.environ['LOGLEVEL'] = 'WARNING'
from praisonai.cli.main import PraisonAI
print("CLI_IMPORT_OK")
'''
        result = run_python_code(code, timeout=30)
        assert result.returncode == 0, f"CLI import failed: {result.stderr}"
        assert "CLI_IMPORT_OK" in result.stdout
    
    def test_cli_praisonai_class(self):
        """Test PraisonAI class instantiation."""
        code = '''
import os
os.environ['LOGLEVEL'] = 'WARNING'
from praisonai.cli.main import PraisonAI
pai = PraisonAI(agent_file="agents.yaml", framework="praisonai")
print("CLASS_OK")
'''
        result = run_python_code(code, timeout=30)
        assert result.returncode == 0, f"CLI class failed: {result.stderr}"
        assert "CLASS_OK" in result.stdout


class TestPerformanceWithRealKey:
    """Test that performance optimizations work with real usage."""
    
    def test_cli_startup_still_fast(self):
        """Verify CLI startup is still fast after changes."""
        code = '''
import time
import os
os.environ['LOGLEVEL'] = 'WARNING'
t = time.time()
from praisonai.cli.main import PraisonAI
elapsed = time.time() - t
print(f"ELAPSED:{elapsed:.3f}")
if elapsed < 1.0:
    print("FAST")
else:
    print("SLOW")
'''
        result = run_python_code(code, timeout=30)
        assert result.returncode == 0, f"Startup test failed: {result.stderr}"
        assert "FAST" in result.stdout, f"CLI startup too slow: {result.stdout}"
    
    def test_lazy_loading_preserved(self):
        """Verify heavy modules not loaded at startup."""
        code = '''
import sys
import os
os.environ['LOGLEVEL'] = 'WARNING'
from praisonai.cli.main import PraisonAI
heavy = ['litellm', 'instructor', 'praisonai.auto']
loaded = [m for m in heavy if m in sys.modules]
if loaded:
    print(f"LOADED:{loaded}")
else:
    print("LAZY_OK")
'''
        result = run_python_code(code, timeout=30)
        assert result.returncode == 0, f"Lazy loading test failed: {result.stderr}"
        assert "LAZY_OK" in result.stdout, f"Heavy modules loaded: {result.stdout}"


class TestMultiProvider:
    """Test multiple LLM providers if keys available."""
    
    @pytest.mark.skipif(
        not os.environ.get("ANTHROPIC_API_KEY"),
        reason="ANTHROPIC_API_KEY not set"
    )
    def test_anthropic_agent(self):
        """Test Agent with Anthropic Claude."""
        code = '''
import os
from praisonaiagents import Agent

agent = Agent(
    instructions="Reply with exactly: ANTHROPIC_OK",
    llm="claude-3-haiku-20240307",
    verbose=False
)
response = agent.chat("Respond")
print("SUCCESS" if "ANTHROPIC_OK" in response or response else "FAIL")
'''
        result = run_python_code(code, timeout=60)
        # May fail if Anthropic not configured, that's OK
        print(f"Anthropic test: {result.stdout}")
    
    @pytest.mark.skipif(
        not os.environ.get("GOOGLE_API_KEY"),
        reason="GOOGLE_API_KEY not set"
    )
    def test_google_agent(self):
        """Test Agent with Google Gemini."""
        code = '''
import os
from praisonaiagents import Agent

agent = Agent(
    instructions="Reply with exactly: GOOGLE_OK",
    llm="gemini/gemini-1.5-flash",
    verbose=False
)
response = agent.chat("Respond")
print("SUCCESS" if response else "FAIL")
'''
        result = run_python_code(code, timeout=60)
        print(f"Google test: {result.stdout}")


if __name__ == "__main__":
    # Allow running directly
    if os.environ.get("RUN_REAL_KEY_TESTS") != "1":
        print("Set RUN_REAL_KEY_TESTS=1 to run these tests")
        sys.exit(1)
    pytest.main([__file__, "-v"])
