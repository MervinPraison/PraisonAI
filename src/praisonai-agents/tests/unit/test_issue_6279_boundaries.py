"""Regression tests for #6279: tools cache keyed on tool content, not name."""


# ── tools cache keyed on content, not name ───────────────────────────────

def _make(kind):
    if kind == "a":
        def search(query: str):
            "Search the web"
    else:
        def search(sql: str, limit: int):
            "Query the database"
    return search


class TestToolsCacheKey:
    def test_same_name_callables_formatted_independently(self):
        from praisonaiagents.llm.llm import LLM

        llm = LLM(model="gpt-4o-mini")
        fa = llm._format_tools_for_litellm([_make("a")])
        fb = llm._format_tools_for_litellm([_make("b")])
        assert list(fa[0]["function"]["parameters"]["properties"]) == ["query"]
        assert list(fb[0]["function"]["parameters"]["properties"]) == ["sql", "limit"]

    def test_same_name_dict_tools_formatted_independently(self):
        from praisonaiagents.llm.llm import LLM

        def spec(desc):
            return {"type": "function", "function": {
                "name": "lookup", "description": desc,
                "parameters": {"type": "object", "properties": {}}}}

        llm = LLM(model="gpt-4o-mini")
        assert llm._format_tools_for_litellm([spec("v1")])[0]["function"]["description"] == "v1"
        assert llm._format_tools_for_litellm([spec("v2")])[0]["function"]["description"] == "v2"

    def test_same_tool_hits_cache(self):
        from praisonaiagents.llm.llm import LLM

        tool = _make("a")
        llm = LLM(model="gpt-4o-mini")
        first = llm._format_tools_for_litellm([tool])
        assert llm._format_tools_for_litellm([tool]) is first

    def test_cache_evicts_instead_of_freezing(self):
        from praisonaiagents.llm.llm import LLM

        llm = LLM(model="gpt-4o-mini")
        llm._max_cache_size = 3
        specs = [{"type": "function", "function": {
            "name": f"t{i}", "description": "d",
            "parameters": {"type": "object", "properties": {}}}} for i in range(5)]
        for s in specs:
            llm._format_tools_for_litellm([s])
        assert len(llm._formatted_tools_cache) == 3
        newest = llm._get_tools_cache_key([specs[-1]])
        assert newest in llm._formatted_tools_cache

    def test_agent_and_openai_client_keys_distinguish_same_name(self):
        from praisonaiagents import Agent
        from praisonaiagents.llm.openai_client import OpenAIClient

        a, b = _make("a"), _make("b")
        agent = Agent(name="x", instructions="hi", output="silent")
        assert agent._get_tools_cache_key([a]) != agent._get_tools_cache_key([b])
        key = OpenAIClient._get_tools_cache_key
        assert key(None, [a]) != key(None, [b])

