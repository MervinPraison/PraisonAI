"""Prompt-cache ordering: tool schemas sorted by name, and the cache boundary marker.

These were script-style checks that returned True/False and caught every
exception, so pytest passed them whatever happened. They now assert.
"""

from praisonaiagents.agent.chat_mixin import ChatMixin
from praisonaiagents.memory.memory import CACHE_BOUNDARY, Memory
from praisonaiagents.tools.base import BaseTool, get_sorted_tool_schemas


def _tool(tool_name):
    class _T(BaseTool):
        name = tool_name
        description = f"{tool_name} tool"

        def run(self, query: str) -> str:
            return query

    return _T()


def test_tool_schemas_are_sorted_by_name():
    schemas = get_sorted_tool_schemas([_tool("zebra_tool"), _tool("alpha_tool"), _tool("beta_tool")])
    assert [s["function"]["name"] for s in schemas] == ["alpha_tool", "beta_tool", "zebra_tool"]
    assert get_sorted_tool_schemas([]) == []


def test_cache_optimized_context_boundary():
    memory = Memory({})
    memory.build_context_for_task = lambda task_descr, **kwargs: "test context"

    enabled = memory.build_cache_optimized_context(task_descr="test task", include_cache_boundary=True)
    assert "stable_prefix" in enabled
    assert enabled["cache_boundary"] == CACHE_BOUNDARY and CACHE_BOUNDARY

    disabled = memory.build_cache_optimized_context(task_descr="test task", include_cache_boundary=False)
    assert disabled["cache_boundary"] == ""


def test_agent_formats_tools_in_name_order():
    class _Agent(ChatMixin):
        def __init__(self):
            self.tools = []
            self._formatted_tools_cache = {}
            self._system_prompt_cache = {}
            self._memory_instance = None
            self.use_system_prompt = True
            self.role = self.goal = self.backstory = "test"
            self._rules_manager_initialized = False
            self._rules_manager = None
            self._skills = None
            self._skills_dirs = None
            self.verbose = False

        def _cache_get(self, cache, key):
            return cache.get(key)

        def _cache_put(self, cache, key, value):
            cache[key] = value

        def _get_tools_cache_key(self, tools):
            return str(tools)

    tools = [
        {"type": "function", "function": {"name": "zebra_tool", "description": "Z tool"}},
        {"type": "function", "function": {"name": "alpha_tool", "description": "A tool"}},
    ]
    formatted = _Agent()._format_tools_for_completion(tools)
    assert [t["function"]["name"] for t in formatted] == ["alpha_tool", "zebra_tool"]
