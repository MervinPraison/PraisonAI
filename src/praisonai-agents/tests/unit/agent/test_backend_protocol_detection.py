"""Agent(llm=<backend object>) must adopt the object, whichever protocol it implements.

The original fix for misrouted model objects duck-typed on `get_response`
alone. llm/protocols.py also documents LLMProviderProtocol (`chat`/`achat`) and
UnifiedLLMProtocol (`chat_completion`/`achat_completion`); backends
implementing either still fell through to the plain OpenAI branch, where
`self.llm` became the object itself and every turn was sent to OpenAI under a
`repr()` as the model name -- the opposite of what passing your own backend
means.
"""
from praisonaiagents import Agent


def _agent(backend):
    return Agent(instructions="t", llm=backend)


class TestEveryDocumentedBackendProtocolIsAdopted:
    def test_get_response_backend_is_adopted(self):
        class B:
            model = "custom/a"
            def get_response(self, *a, **k): return "x"
        agent = _agent(B())
        assert agent._using_custom_llm is True
        assert agent.llm == "custom/a"

    def test_chat_protocol_backend_is_adopted(self):
        class B:
            model = "custom/b"
            def chat(self, *a, **k): return "x"
        agent = _agent(B())
        assert agent._using_custom_llm is True
        assert agent.llm == "custom/b"

    def test_chat_completion_protocol_backend_is_adopted(self):
        class B:
            model = "custom/c"
            def chat_completion(self, *a, **k): return "x"
            async def achat_completion(self, *a, **k): return "x"
        agent = _agent(B())
        assert agent._using_custom_llm is True
        assert agent.llm == "custom/c"

    def test_control_a_plain_object_is_not_adopted(self):
        """Control: adoption must be earned by implementing a backend surface."""
        class NotABackend:
            pass
        assert _agent(NotABackend())._using_custom_llm is False

    def test_control_a_string_llm_is_unaffected(self):
        assert Agent(instructions="t", llm="gpt-4o-mini").llm == "gpt-4o-mini"
