"""Two remaining asymmetries from the local-model audit.

1. `tool_result_mapping` substituted a prior tool's result for ANY argument
   whose string value matched a function name -- so a legitimate
   `city="get_weather"` silently became a number scraped from an earlier result.
2. The stream loop appended two messages per iteration with nothing trimming
   them, while sync and async both ran in-loop context management.
"""

import pytest

from praisonaiagents.llm.llm import LLM


@pytest.fixture
def llm(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    return LLM(model="ollama/qwen3:0.6b", base_url="http://127.0.0.1:11434")


TOOLS = [{
    "type": "function",
    "function": {
        "name": "lookup",
        "parameters": {"type": "object", "properties": {
            "city": {"type": "string"},
            "count": {"type": "integer"},
            "either": {"type": ["string", "null"]},
        }},
    },
}]


class TestResultSubstitutionIsNarrowed:
    """A declared string parameter must keep the value the model sent."""

    def test_a_string_parameter_is_left_alone(self, llm):
        assert llm._param_accepts_string("lookup", "city", TOOLS) is True

    def test_a_numeric_parameter_is_eligible_for_substitution(self, llm):
        assert llm._param_accepts_string("lookup", "count", TOOLS) is False

    def test_a_union_including_string_is_left_alone(self, llm):
        """Optional[str] must not be corrupted either."""
        assert llm._param_accepts_string("lookup", "either", TOOLS) is True

    def test_an_unknown_parameter_is_not_treated_as_a_string(self, llm):
        assert llm._param_accepts_string("lookup", "nope", TOOLS) is False

    def test_an_unknown_tool_is_not_treated_as_a_string(self, llm):
        assert llm._param_accepts_string("other", "city", TOOLS) is False

    def test_a_malformed_schema_does_not_raise(self, llm):
        """A schema read must never break a tool call."""
        assert llm._param_accepts_string("lookup", "city", [{"function": None}]) is False
        assert llm._param_accepts_string("lookup", "city", None) is False

    def test_anyof_optional_string_is_left_alone(self, llm):
        """The repo's own generator (tools/schema.py) emits Optional[str] as an
        `anyOf`, not a list-typed `type`. That shape must be recognised too, or a
        genuine Optional[str] argument is still silently overwritten."""
        tools = [{
            "type": "function",
            "function": {
                "name": "lookup",
                "parameters": {"type": "object", "properties": {
                    "note": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "num": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                }},
            },
        }]
        assert llm._param_accepts_string("lookup", "note", tools) is True
        assert llm._param_accepts_string("lookup", "num", tools) is False

    def test_anyof_union_including_string_is_left_alone(self, llm):
        tools = [{
            "type": "function",
            "function": {
                "name": "lookup",
                "parameters": {"type": "object", "properties": {
                    "mixed": {"anyOf": [{"type": "integer"}, {"type": "string"}]},
                }},
            },
        }]
        assert llm._param_accepts_string("lookup", "mixed", tools) is True


class TestStreamManagesContext:
    def test_the_stream_loop_calls_context_management(self):
        """Sync and async both do; the stream loop grew messages unbounded."""
        import ast
        import inspect
        import praisonaiagents.llm.llm as mod

        src = inspect.getsource(mod)
        lines = src.split("\n")
        tree = ast.parse(src)
        spans = {
            n.name: (n.lineno, n.end_lineno)
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name.startswith("get_response")
        }
        for path in ("get_response", "get_response_async", "get_response_stream"):
            a, b = spans[path]
            hits = sum(1 for l in lines[a - 1:b] if "_manage_context_in_loop" in l)
            assert hits >= 1, f"{path} does not manage context in its tool loop"
