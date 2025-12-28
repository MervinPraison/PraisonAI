"""
Unit tests for Ollama tool calling reliability features.

Tests cover:
1. Tool call parsing from JSON response
2. Force tool usage prompting
3. Tool call repair loop
4. max_tool_repairs configuration
5. force_tool_usage modes (auto/always/never)
6. Loop prevention

These tests mock the LLM class to avoid requiring litellm.
"""

import pytest
import os
import json

# Set dummy API key for tests
os.environ.setdefault('OPENAI_API_KEY', 'test-key-for-unit-tests')


class MockLLM:
    """Mock LLM class for testing tool reliability features without litellm."""
    
    # Prompt templates (copied from actual LLM class)
    FORCE_TOOL_USAGE_PROMPT = """You MUST use one of the available tools to answer this question.
Do NOT provide a direct answer. Respond ONLY with a tool call.

Available tools: {tool_names}

Respond with a JSON object in this format:
{{"name": "tool_name", "arguments": {{"arg1": value1, "arg2": value2}}}}"""

    TOOL_CALL_REPAIR_PROMPT = """Your previous tool call was malformed: {error}

Please try again. Available tools:
{tool_schemas}

Respond with ONLY a valid JSON tool call in this format:
{{"name": "tool_name", "arguments": {{"arg1": value1, "arg2": value2}}}}"""

    def __init__(self, model, max_tool_repairs=None, force_tool_usage=None, base_url=None, **kwargs):
        self.model = model
        self.base_url = base_url
        
        # Track if values were explicitly set
        self._max_tool_repairs_explicit = max_tool_repairs is not None
        self._force_tool_usage_explicit = force_tool_usage is not None
        
        # Set defaults
        self.max_tool_repairs = max_tool_repairs if max_tool_repairs is not None else 0
        self.force_tool_usage = force_tool_usage if force_tool_usage is not None else 'never'
        
        # Apply Ollama defaults
        self._apply_ollama_defaults()
    
    def _is_ollama_provider(self) -> bool:
        """Detect if this is an Ollama provider."""
        if not self.model:
            return False
        if self.model.startswith("ollama/"):
            return True
        if self.base_url and ("ollama" in self.base_url.lower() or ":11434" in self.base_url):
            return True
        return False
    
    def _apply_ollama_defaults(self):
        """Apply Ollama-specific defaults for tool calling reliability."""
        if self._is_ollama_provider():
            if not self._max_tool_repairs_explicit:
                self.max_tool_repairs = 2
            if not self._force_tool_usage_explicit:
                self.force_tool_usage = 'auto'

    def _get_tool_names_for_prompt(self, formatted_tools):
        """Extract tool names from formatted tools for prompts."""
        if not formatted_tools:
            return "None"
        names = []
        for tool in formatted_tools:
            if isinstance(tool, dict) and 'function' in tool:
                names.append(tool['function'].get('name', 'unknown'))
        return ', '.join(names) if names else "None"

    def _get_tool_schemas_for_prompt(self, formatted_tools):
        """Generate compact tool schemas for repair prompts."""
        if not formatted_tools:
            return "None"
        schemas = []
        for tool in formatted_tools:
            if isinstance(tool, dict) and 'function' in tool:
                func = tool['function']
                name = func.get('name', 'unknown')
                params = func.get('parameters', {})
                required = params.get('required', [])
                props = params.get('properties', {})
                param_strs = []
                for pname, pinfo in props.items():
                    ptype = pinfo.get('type', 'any')
                    req = '*' if pname in required else ''
                    param_strs.append(f"{pname}{req}: {ptype}")
                schemas.append(f"- {name}({', '.join(param_strs)})")
        return '\n'.join(schemas) if schemas else "None"

    def _should_force_tool_usage(self, response_text, tool_calls, formatted_tools, iteration_count):
        """Determine if we should force tool usage."""
        if not formatted_tools:
            return False
        if tool_calls:
            return False
        
        if self.force_tool_usage == 'never':
            return False
        elif self.force_tool_usage == 'always':
            return True
        elif self.force_tool_usage == 'auto':
            return self._is_ollama_provider() and iteration_count == 0
        return False

    def _try_parse_tool_call_json(self, response_text, iteration_count):
        """Try to parse tool call from JSON response text."""
        if not response_text or not response_text.strip():
            return None, None
        
        try:
            response_json = json.loads(response_text.strip())
            if isinstance(response_json, dict) and "name" in response_json:
                tool_calls = [{
                    "id": f"tool_{iteration_count}",
                    "type": "function",
                    "function": {
                        "name": response_json["name"],
                        "arguments": json.dumps(response_json.get("arguments", {}))
                    }
                }]
                return tool_calls, None
            elif isinstance(response_json, list):
                tool_calls = []
                for idx, tool_json in enumerate(response_json):
                    if isinstance(tool_json, dict) and "name" in tool_json:
                        tool_calls.append({
                            "id": f"tool_{iteration_count}_{idx}",
                            "type": "function",
                            "function": {
                                "name": tool_json["name"],
                                "arguments": json.dumps(tool_json.get("arguments", {}))
                            }
                        })
                return tool_calls if tool_calls else None, None
            else:
                return None, "Response is not a valid tool call format (missing 'name' field)"
        except json.JSONDecodeError as e:
            return None, f"JSON parse error: {str(e)}"

    def _validate_tool_call(self, tool_call, formatted_tools):
        """Validate a tool call against available tools."""
        if not formatted_tools:
            return None
        
        try:
            func_info = tool_call.get('function', {})
            tool_name = func_info.get('name', '')
            arguments_str = func_info.get('arguments', '{}')
            
            available_names = [t['function']['name'] for t in formatted_tools if isinstance(t, dict) and 'function' in t]
            if tool_name not in available_names:
                return f"Unknown tool '{tool_name}'. Available: {', '.join(available_names)}"
            
            try:
                arguments = json.loads(arguments_str) if isinstance(arguments_str, str) else arguments_str
            except json.JSONDecodeError as e:
                return f"Invalid arguments JSON: {str(e)}"
            
            for tool in formatted_tools:
                if isinstance(tool, dict) and tool.get('function', {}).get('name') == tool_name:
                    params = tool['function'].get('parameters', {})
                    required = params.get('required', [])
                    missing = [r for r in required if r not in arguments]
                    if missing:
                        return f"Missing required arguments for '{tool_name}': {', '.join(missing)}"
                    break
            
            return None
        except Exception as e:
            return f"Validation error: {str(e)}"

    def _format_ollama_tool_result_message(self, function_name, tool_result):
        """Format tool result message for Ollama provider."""
        tool_result_str = str(tool_result)
        return {
            "role": "user",
            "content": f"""Tool execution complete.
Function: {function_name}
Result: {tool_result_str}

Now provide your final answer using this result."""
        }


class TestOllamaToolReliability:
    """Tests for Ollama tool calling reliability enhancements."""

    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM instance for testing."""
        return MockLLM(model="ollama/olmo-3")

    @pytest.fixture
    def mock_llm_openai(self):
        """Create a mock LLM instance for OpenAI (non-Ollama)."""
        return MockLLM(model="gpt-4o-mini")

    @pytest.fixture
    def sample_formatted_tools(self):
        """Sample formatted tools for testing."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "calculator",
                    "description": "Add two integers",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "a": {"type": "integer"},
                            "b": {"type": "integer"}
                        },
                        "required": ["a", "b"]
                    }
                }
            }
        ]

    # ===== Test Ollama Defaults =====

    def test_ollama_defaults_applied(self, mock_llm):
        """Test that Ollama-specific defaults are applied."""
        assert mock_llm.max_tool_repairs == 2
        assert mock_llm.force_tool_usage == 'auto'

    def test_non_ollama_defaults(self, mock_llm_openai):
        """Test that non-Ollama models get default values."""
        assert mock_llm_openai.max_tool_repairs == 0
        assert mock_llm_openai.force_tool_usage == 'never'

    def test_explicit_override_respected(self):
        """Test that explicit user overrides are respected."""
        llm = MockLLM(model="ollama/olmo-3", max_tool_repairs=5, force_tool_usage='always')
        assert llm.max_tool_repairs == 5
        assert llm.force_tool_usage == 'always'

    # ===== Test Tool Call Parsing =====

    def test_try_parse_tool_call_json_valid(self, mock_llm):
        """Test parsing valid tool call JSON."""
        response_text = '{"name": "calculator", "arguments": {"a": 17, "b": 25}}'
        tool_calls, error = mock_llm._try_parse_tool_call_json(response_text, 0)
        
        assert tool_calls is not None
        assert len(tool_calls) == 1
        assert tool_calls[0]['function']['name'] == 'calculator'
        assert error is None

    def test_try_parse_tool_call_json_invalid(self, mock_llm):
        """Test parsing invalid JSON returns error."""
        response_text = 'This is not JSON'
        tool_calls, error = mock_llm._try_parse_tool_call_json(response_text, 0)
        
        assert tool_calls is None
        assert error is not None
        assert "JSON parse error" in error

    def test_try_parse_tool_call_json_empty(self, mock_llm):
        """Test parsing empty response."""
        tool_calls, error = mock_llm._try_parse_tool_call_json("", 0)
        assert tool_calls is None
        assert error is None

    def test_try_parse_tool_call_json_list(self, mock_llm):
        """Test parsing list of tool calls."""
        response_text = '[{"name": "calculator", "arguments": {"a": 1, "b": 2}}, {"name": "calculator", "arguments": {"a": 3, "b": 4}}]'
        tool_calls, error = mock_llm._try_parse_tool_call_json(response_text, 0)
        
        assert tool_calls is not None
        assert len(tool_calls) == 2

    # ===== Test Tool Call Validation =====

    def test_validate_tool_call_valid(self, mock_llm, sample_formatted_tools):
        """Test validation of valid tool call."""
        tool_call = {
            "id": "tool_0",
            "type": "function",
            "function": {
                "name": "calculator",
                "arguments": '{"a": 17, "b": 25}'
            }
        }
        error = mock_llm._validate_tool_call(tool_call, sample_formatted_tools)
        assert error is None

    def test_validate_tool_call_unknown_tool(self, mock_llm, sample_formatted_tools):
        """Test validation fails for unknown tool."""
        tool_call = {
            "id": "tool_0",
            "type": "function",
            "function": {
                "name": "unknown_tool",
                "arguments": '{}'
            }
        }
        error = mock_llm._validate_tool_call(tool_call, sample_formatted_tools)
        assert error is not None
        assert "Unknown tool" in error

    def test_validate_tool_call_missing_required_args(self, mock_llm, sample_formatted_tools):
        """Test validation fails for missing required arguments."""
        tool_call = {
            "id": "tool_0",
            "type": "function",
            "function": {
                "name": "calculator",
                "arguments": '{"a": 17}'  # Missing 'b'
            }
        }
        error = mock_llm._validate_tool_call(tool_call, sample_formatted_tools)
        assert error is not None
        assert "Missing required arguments" in error

    def test_validate_tool_call_invalid_json_args(self, mock_llm, sample_formatted_tools):
        """Test validation fails for invalid JSON arguments."""
        tool_call = {
            "id": "tool_0",
            "type": "function",
            "function": {
                "name": "calculator",
                "arguments": 'not valid json'
            }
        }
        error = mock_llm._validate_tool_call(tool_call, sample_formatted_tools)
        assert error is not None
        assert "Invalid arguments JSON" in error

    # ===== Test Force Tool Usage =====

    def test_should_force_tool_usage_auto_ollama(self, mock_llm, sample_formatted_tools):
        """Test force tool usage in auto mode for Ollama."""
        # First iteration, no tool calls, has tools
        result = mock_llm._should_force_tool_usage(
            response_text="I'll just answer directly",
            tool_calls=None,
            formatted_tools=sample_formatted_tools,
            iteration_count=0
        )
        assert result is True

    def test_should_force_tool_usage_auto_not_first_iteration(self, mock_llm, sample_formatted_tools):
        """Test force tool usage doesn't trigger after first iteration."""
        result = mock_llm._should_force_tool_usage(
            response_text="I'll just answer directly",
            tool_calls=None,
            formatted_tools=sample_formatted_tools,
            iteration_count=1
        )
        assert result is False

    def test_should_force_tool_usage_never(self, mock_llm, sample_formatted_tools):
        """Test force tool usage never mode."""
        mock_llm.force_tool_usage = 'never'
        result = mock_llm._should_force_tool_usage(
            response_text="I'll just answer directly",
            tool_calls=None,
            formatted_tools=sample_formatted_tools,
            iteration_count=0
        )
        assert result is False

    def test_should_force_tool_usage_always(self, mock_llm, sample_formatted_tools):
        """Test force tool usage always mode."""
        mock_llm.force_tool_usage = 'always'
        result = mock_llm._should_force_tool_usage(
            response_text="I'll just answer directly",
            tool_calls=None,
            formatted_tools=sample_formatted_tools,
            iteration_count=5  # Even on later iterations
        )
        assert result is True

    def test_should_force_tool_usage_with_existing_tool_calls(self, mock_llm, sample_formatted_tools):
        """Test force tool usage doesn't trigger when tool calls exist."""
        mock_llm.force_tool_usage = 'always'
        tool_calls = [{"id": "tool_0", "function": {"name": "calculator"}}]
        result = mock_llm._should_force_tool_usage(
            response_text="",
            tool_calls=tool_calls,
            formatted_tools=sample_formatted_tools,
            iteration_count=0
        )
        assert result is False

    def test_should_force_tool_usage_no_tools(self, mock_llm):
        """Test force tool usage doesn't trigger without tools."""
        mock_llm.force_tool_usage = 'always'
        result = mock_llm._should_force_tool_usage(
            response_text="I'll just answer directly",
            tool_calls=None,
            formatted_tools=None,
            iteration_count=0
        )
        assert result is False

    # ===== Test Helper Methods =====

    def test_get_tool_names_for_prompt(self, mock_llm, sample_formatted_tools):
        """Test extracting tool names for prompts."""
        names = mock_llm._get_tool_names_for_prompt(sample_formatted_tools)
        assert names == "calculator"

    def test_get_tool_names_for_prompt_empty(self, mock_llm):
        """Test extracting tool names from empty list."""
        names = mock_llm._get_tool_names_for_prompt(None)
        assert names == "None"

    def test_get_tool_schemas_for_prompt(self, mock_llm, sample_formatted_tools):
        """Test generating tool schemas for prompts."""
        schemas = mock_llm._get_tool_schemas_for_prompt(sample_formatted_tools)
        assert "calculator" in schemas
        assert "a*" in schemas  # Required arg marked with *
        assert "b*" in schemas

    def test_format_ollama_tool_result_message(self, mock_llm):
        """Test formatting tool result message for Ollama."""
        result = mock_llm._format_ollama_tool_result_message("calculator", 42)
        assert result["role"] == "user"
        assert "calculator" in result["content"]
        assert "42" in result["content"]
        assert "final answer" in result["content"].lower()

    # ===== Test Prompt Templates =====

    def test_force_tool_usage_prompt_template(self, mock_llm):
        """Test force tool usage prompt template."""
        prompt = mock_llm.FORCE_TOOL_USAGE_PROMPT.format(tool_names="calculator")
        assert "MUST use" in prompt
        assert "calculator" in prompt
        assert "tool call" in prompt.lower()

    def test_tool_call_repair_prompt_template(self, mock_llm):
        """Test tool call repair prompt template."""
        prompt = mock_llm.TOOL_CALL_REPAIR_PROMPT.format(
            error="Missing required argument 'b'",
            tool_schemas="- calculator(a*: integer, b*: integer)"
        )
        assert "malformed" in prompt.lower()
        assert "Missing required argument" in prompt
        assert "calculator" in prompt


class TestOllamaToolReliabilityIntegration:
    """Integration-style tests for tool reliability using MockLLM."""

    def test_force_tool_usage_flow(self):
        """Test the complete force tool usage flow with MockLLM."""
        llm = MockLLM(model="ollama/olmo-3")
        
        sample_tools = [{
            "type": "function",
            "function": {
                "name": "calculator",
                "parameters": {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"]}
            }
        }]
        
        # Simulate: model returns text instead of tool call
        response_text = "The answer is 42"
        tool_calls = None
        
        # Should trigger force tool usage on first iteration
        should_force = llm._should_force_tool_usage(response_text, tool_calls, sample_tools, 0)
        assert should_force is True
        
        # Should NOT trigger on second iteration
        should_force = llm._should_force_tool_usage(response_text, tool_calls, sample_tools, 1)
        assert should_force is False

    def test_repair_loop_flow(self):
        """Test the complete repair loop flow with MockLLM."""
        llm = MockLLM(model="ollama/olmo-3")
        
        sample_tools = [{
            "type": "function",
            "function": {
                "name": "calculator",
                "parameters": {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"]}
            }
        }]
        
        # Simulate: malformed tool call (unknown tool)
        bad_tool_call = {
            "id": "tool_0",
            "type": "function",
            "function": {"name": "unknown_tool", "arguments": "{}"}
        }
        
        error = llm._validate_tool_call(bad_tool_call, sample_tools)
        assert error is not None
        assert "Unknown tool" in error
        
        # Simulate: valid tool call after repair
        good_tool_call = {
            "id": "tool_1",
            "type": "function",
            "function": {"name": "calculator", "arguments": '{"a": 17}'}
        }
        
        error = llm._validate_tool_call(good_tool_call, sample_tools)
        assert error is None


class TestOllamaProviderDetection:
    """Tests for Ollama provider detection."""

    def test_detect_ollama_prefix(self):
        """Test detection via ollama/ prefix."""
        llm = MockLLM(model="ollama/llama3.2")
        assert llm._is_ollama_provider() is True

    def test_detect_ollama_base_url(self):
        """Test detection via base_url containing ollama."""
        llm = MockLLM(model="llama3.2", base_url="http://localhost:11434")
        assert llm._is_ollama_provider() is True

    def test_detect_non_ollama(self):
        """Test non-Ollama models are not detected as Ollama."""
        llm = MockLLM(model="gpt-4o-mini")
        assert llm._is_ollama_provider() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
