"""
Integration tests for the OpenAI Responses API implementation.

These tests verify that the Responses API is correctly wired into the LLM class
and that agents work end-to-end with both the Responses API path (Path P1) and
the Chat Completions path (P2 / fallback).

Usage:
    RUN_REAL_KEY_TESTS=1 pytest tests/integration/test_responses_api.py -v -s

Required environment variables:
    - OPENAI_API_KEY: OpenAI API key
"""
import os
import sys
import time
import pytest

# Note: Only real API tests are gated by RUN_REAL_KEY_TESTS.
# Unit-level tests (model detection, param building, extraction) always run.
_skip_real = pytest.mark.skipif(
    os.environ.get('RUN_REAL_KEY_TESTS', '').lower() not in ('1', 'true', 'yes'),
    reason="Real API key tests disabled. Set RUN_REAL_KEY_TESTS=1 to enable."
)


def clear_modules():
    """Clear all praisonai and litellm related modules from cache."""
    to_remove = [m for m in list(sys.modules.keys())
                 if 'praison' in m or 'litellm' in m]
    for mod in to_remove:
        del sys.modules[mod]


# ── Unit-level checks (no API key needed for these) ────────────────────

class TestResponsesAPIModelDetection:
    """Verify _supports_responses_api() returns correct values."""

    def test_openai_models_detected(self):
        from praisonaiagents.llm.llm import LLM

        positive_models = [
            "gpt-4o", "gpt-4o-mini", "gpt-4o-2024-08-06",
            "gpt-4-turbo", "gpt-4-turbo-preview",
            "gpt-4.1", "gpt-4.5-preview",
            "o1-preview", "o1-mini", "o3-mini", "o4-mini",
            "chatgpt-4o-latest",
            "azure/gpt-4o", "azure/o3-mini",
            "openai/gpt-4o",
        ]
        for model in positive_models:
            llm = LLM(model=model)
            assert llm._supports_responses_api(), f"{model} should support Responses API"

    def test_non_openai_models_rejected(self):
        from praisonaiagents.llm.llm import LLM

        negative_models = [
            "claude-3-opus-20240229", "claude-3-5-sonnet-20241022",
            "anthropic/claude-3-haiku",
            "ollama/llama3",
            "gemini/gemini-pro", "gemini/gemini-1.5-flash",
            "groq/llama-3.1-70b-versatile",
            "together_ai/mistral-7b",
            "deepseek/deepseek-chat",
            "gpt-3.5-turbo",  # Too old for Responses API
        ]
        for model in negative_models:
            llm = LLM(model=model)
            assert not llm._supports_responses_api(), f"{model} should NOT support Responses API"


class TestResponsesAPIParamBuilder:
    """Verify _build_responses_params() correctly translates Chat Completions messages."""

    def test_system_to_instructions(self):
        from praisonaiagents.llm.llm import LLM

        llm = LLM(model="gpt-4o")
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
        ]
        params = llm._build_responses_params(messages=messages, temperature=0.7)

        assert params["model"] == "gpt-4o"
        assert params["instructions"] == "You are a helpful assistant."
        assert len(params["input"]) == 1
        assert params["input"][0]["role"] == "user"
        assert params["temperature"] == 0.7

    def test_tools_pass_through(self):
        from praisonaiagents.llm.llm import LLM

        llm = LLM(model="gpt-4o")
        tools = [{"type": "function", "function": {"name": "add", "parameters": {}}}]
        params = llm._build_responses_params(messages=[{"role": "user", "content": "hi"}], tools=tools)

        assert params["tools"] == tools
        assert params["tool_choice"] == "auto"


class TestResponsesAPIOutputExtraction:
    """Verify _extract_from_responses_output() correctly parses output items."""

    def _make_mock_response(self, output_items):
        class MockResponse:
            def __init__(self, output):
                self.output = output
        return MockResponse(output_items)

    def test_text_only(self):
        from praisonaiagents.llm.llm import LLM

        llm = LLM(model="gpt-4o")
        resp = self._make_mock_response([
            {"type": "message", "content": [{"type": "output_text", "text": "Hello!"}]}
        ])
        text, tool_calls, reasoning = llm._extract_from_responses_output(resp)

        assert text == "Hello!"
        assert tool_calls is None
        assert reasoning is None

    def test_text_plus_tool_calls(self):
        """The key test: text and tool calls coexist without content:null."""
        from praisonaiagents.llm.llm import LLM

        llm = LLM(model="gpt-4o")
        resp = self._make_mock_response([
            {"type": "message", "content": [{"type": "output_text", "text": "Let me calculate."}]},
            {"type": "function_call", "call_id": "call_123", "name": "add", "arguments": '{"a":2,"b":2}'},
        ])
        text, tool_calls, reasoning = llm._extract_from_responses_output(resp)

        assert text == "Let me calculate."
        assert len(tool_calls) == 1
        assert tool_calls[0]["function"]["name"] == "add"
        assert tool_calls[0]["id"] == "call_123"

    def test_multiple_tool_calls(self):
        from praisonaiagents.llm.llm import LLM

        llm = LLM(model="gpt-4o")
        resp = self._make_mock_response([
            {"type": "function_call", "call_id": "c1", "name": "search", "arguments": '{"q":"a"}'},
            {"type": "function_call", "call_id": "c2", "name": "fetch", "arguments": '{"url":"b"}'},
        ])
        text, tool_calls, _ = llm._extract_from_responses_output(resp)

        assert text == ""
        assert len(tool_calls) == 2


# ── Real API integration tests ─────────────────────────────────────────

@_skip_real
class TestResponsesAPIRealAgent:
    """End-to-end agent tests using real OpenAI API calls."""

    @pytest.fixture(autouse=True)
    def setup(self):
        clear_modules()
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            pytest.skip("OPENAI_API_KEY not set")
        yield
        clear_modules()

    def test_responses_api_path_with_slash_model(self):
        """
        Test with 'openai/gpt-4o-mini' which routes through LLM class (Path P1)
        and uses the Responses API.
        """
        from praisonaiagents import Agent

        agent = Agent(
            name="ResponsesAPIAgent",
            instructions="You are a helpful assistant. Keep responses brief.",
            llm="openai/gpt-4o-mini",
        )
        response = agent.start(
            "Research the top 3 Python web frameworks (Django, FastAPI, Flask), then: "
            "1) Search the web for each framework's latest version and key features, "
            "2) Create a file called /tmp/framework_comparison.py that contains a Python dictionary with the comparison data, "
            "3) Execute the code to verify the dictionary is valid, "
            "4) Write a markdown report to /tmp/framework_report.md summarizing your findings in a table format, "
            "5) Read back the report file to verify it was written correctly, "
            "6) List the files in /tmp to confirm both files exist, "
            "7) Get system info to note what OS this report was generated on, "
            "8) Analyze the Python code you wrote for any issues, "
            "9) Format the Python code properly, "
            "10) Finally search for any recent news about Python 3.13 features"
        )

        assert response is not None
        assert len(response) > 100, f"Response too short ({len(response)} chars)"
        print(f"[PASS] openai/gpt-4o-mini - {len(response)} chars")

    def test_chat_completions_path_with_bare_model(self):
        """
        Test with 'gpt-4o-mini' which routes through OpenAIClient (Path P2)
        and uses the standard Chat Completions API.
        """
        from praisonaiagents import Agent

        agent = Agent(
            name="ChatCompletionsAgent",
            instructions="You are a helpful assistant. Keep responses brief.",
            llm="gpt-4o-mini",
        )
        response = agent.start(
            "Research the top 3 Python web frameworks (Django, FastAPI, Flask), then: "
            "1) Search the web for each framework's latest version and key features, "
            "2) Create a file called /tmp/framework_comparison.py that contains a Python dictionary with the comparison data, "
            "3) Execute the code to verify the dictionary is valid, "
            "4) Write a markdown report to /tmp/framework_report.md summarizing your findings in a table format, "
            "5) Read back the report file to verify it was written correctly, "
            "6) List the files in /tmp to confirm both files exist, "
            "7) Get system info to note what OS this report was generated on, "
            "8) Analyze the Python code you wrote for any issues, "
            "9) Format the Python code properly, "
            "10) Finally search for any recent news about Python 3.13 features"
        )

        assert response is not None
        assert len(response) > 100, f"Response too short ({len(response)} chars)"
        print(f"[PASS] gpt-4o-mini - {len(response)} chars")

    def test_responses_api_with_tool(self):
        """
        Test that Responses API correctly handles tool calls — the key
        scenario where content:null was previously a problem.
        """
        from praisonaiagents import Agent

        def add_numbers(a: int, b: int) -> int:
            """Add two numbers together."""
            return a + b

        agent = Agent(
            name="ToolAgent",
            instructions="You are a math assistant. Use the add_numbers tool.",
            llm="openai/gpt-4o-mini",
            tools=[add_numbers],
        )
        response = agent.chat("What is 15 + 27? Use the tool.")

        assert response is not None
        assert "42" in response, f"Expected '42' in response, got: {response[:200]}"
        print(f"[PASS] Tool call via Responses API - response contains '42'")


if __name__ == "__main__":
    if os.environ.get('RUN_REAL_KEY_TESTS', '').lower() not in ('1', 'true', 'yes'):
        print("Set RUN_REAL_KEY_TESTS=1 to run real API tests")
        print("Running unit tests only...\n")
        pytest.main([__file__, "-v", "-s", "-k", "not Real"])
    else:
        pytest.main([__file__, "-v", "-s"])
