"""Agent(llm=<backend object>) must adopt a backend only if the tool loop can drive it.

The original fix for misrouted model objects duck-typed on ``get_response``.
A follow-up widened detection to every protocol name in ``llm/protocols.py``
(``chat``/``achat``, ``chat_completion``/``achat_completion``) -- but the
custom-LLM tool loop only ever calls ``llm_instance.get_response(...)`` (and the
async ``get_response_async``) with PraisonAI-internal kwargs. A backend exposing
only the other surfaces was adopted and then raised ``AttributeError`` on the
first turn. Detection is therefore pinned to the surface the executor actually
invokes: adoption is only granted when it can be honoured.
"""
from praisonaiagents import Agent


def _agent(backend):
    return Agent(instructions="t", llm=backend)


class TestBackendAdoptionMatchesExecutedSurface:
    def test_get_response_backend_is_adopted(self):
        class B:
            model = "custom/a"
            def get_response(self, *a, **k): return "x"
        agent = _agent(B())
        assert agent._using_custom_llm is True
        assert agent.llm == "custom/a"

    def test_async_only_get_response_backend_is_adopted(self):
        class B:
            model = "custom/async"
            async def get_response_async(self, *a, **k): return "x"
        agent = _agent(B())
        assert agent._using_custom_llm is True
        assert agent.llm == "custom/async"

    def test_chat_only_backend_is_not_adopted(self):
        """``chat``/``achat`` is not wired into the tool loop -- adopting it would
        raise AttributeError on the first turn, so it must NOT be adopted."""
        class B:
            model = "custom/b"
            def chat(self, *a, **k): return "x"
        assert _agent(B())._using_custom_llm is False

    def test_chat_completion_only_backend_is_not_adopted(self):
        """``chat_completion``/``achat_completion`` is likewise undriveable here."""
        class B:
            model = "custom/c"
            def chat_completion(self, *a, **k): return "x"
            async def achat_completion(self, *a, **k): return "x"
        assert _agent(B())._using_custom_llm is False

    def test_control_a_plain_object_is_not_adopted(self):
        """Control: adoption must be earned by implementing the executed surface."""
        class NotABackend:
            pass
        assert _agent(NotABackend())._using_custom_llm is False

    def test_control_a_string_llm_is_unaffected(self):
        assert Agent(instructions="t", llm="gpt-4o-mini").llm == "gpt-4o-mini"
