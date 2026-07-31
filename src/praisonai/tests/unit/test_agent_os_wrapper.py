"""
TDD tests for AgentOS exports from praisonai wrapper.
"""

import pytest



class TestAgentOSWrapperExports:
    """Test AgentOS exports from praisonai wrapper."""
    
    def test_agent_os_importable_from_wrapper(self):
        """AgentOS should be importable from praisonai."""
        from praisonai import AgentOS
        assert AgentOS is not None
    
    def test_agent_app_is_alias_for_agent_os(self):
        """AgentApp should be silent alias for AgentOS."""
        from praisonai import AgentOS, AgentApp
        assert AgentApp is AgentOS
    
    def test_agent_os_in_all(self):
        """AgentOS should be in __all__."""
        import praisonai
        assert 'AgentOS' in praisonai.__all__
    
    def test_agent_app_in_all(self):
        """AgentApp should be in __all__ (silent alias)."""
        import praisonai
        assert 'AgentApp' in praisonai.__all__


class TestAgentAppNoDeprecationWarning:
    """Test that AgentApp alias is silent (no deprecation warnings)."""
    
    def test_agent_app_no_warning(self):
        """Importing AgentApp should not emit deprecation warning."""
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            from praisonai import AgentApp
            _ = AgentApp
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) == 0, f"Got deprecation warnings: {deprecation_warnings}"


class TestAgentOSChatSessionIsolation:
    """Gap 1: /chat must isolate a per-request agent, not share one instance."""

    def _client(self, monkeypatch):
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from praisonaiagents import Agent
        from praisonai import AgentOS

        template = Agent(name="assistant", instructions="Be helpful")

        # Record the object instance that actually handled each request and
        # avoid any real LLM call by stubbing achat on every clone.
        seen = []

        async def _fake_achat(self, message, *args, **kwargs):
            seen.append((id(self), getattr(self, "_session_id", None), list(self.chat_history)))
            self.chat_history.append({"role": "user", "content": message})
            return f"echo:{message}"

        # Patch the stub on the class (clones inherit it) via monkeypatch so it
        # is restored automatically after the test and cannot leak globally.
        monkeypatch.setattr(type(template), "achat", _fake_achat, raising=False)

        os_app = AgentOS(agents=[template])
        client = TestClient(os_app.get_app())
        prefix = os_app.config.api_prefix
        return client, template, seen, prefix

    def test_chat_clones_agent_per_request(self, monkeypatch):
        client, template, seen, prefix = self._client(monkeypatch)
        r1 = client.post(f"{prefix}/chat", json={"message": "hi", "session_id": "alice"})
        assert r1.status_code == 200, r1.text
        # The handling agent must not be the shared template instance.
        assert seen[-1][0] != id(template)

    def test_chat_binds_session_id(self, monkeypatch):
        client, template, seen, prefix = self._client(monkeypatch)
        r = client.post(f"{prefix}/chat", json={"message": "hi", "session_id": "bob"})
        assert r.status_code == 200, r.text
        assert seen[-1][1] == "bob"
        assert r.json()["session_id"] == "bob"

    def test_template_history_not_mutated_across_requests(self, monkeypatch):
        client, template, seen, prefix = self._client(monkeypatch)
        client.post(f"{prefix}/chat", json={"message": "a", "session_id": "s1"})
        client.post(f"{prefix}/chat", json={"message": "b", "session_id": "s2"})
        # The shared template's history must stay empty; each request used a clone.
        assert template.chat_history == []

    def test_agent_with_handoffs_is_not_cloned(self, monkeypatch):
        # ``clone_for_channel`` drops handoffs, so an agent configured with
        # delegation must NOT be cloned — it stays on the shared template to
        # preserve its handoff behaviour.
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from praisonaiagents import Agent
        from praisonai import AgentOS

        specialist = Agent(name="specialist", instructions="Specialise")
        template = Agent(
            name="router", instructions="Route", handoffs=[specialist]
        )
        assert template.handoffs  # sanity: handoffs configured

        seen = []

        async def _fake_achat(self, message, *args, **kwargs):
            seen.append(id(self))
            return f"echo:{message}"

        monkeypatch.setattr(type(template), "achat", _fake_achat, raising=False)

        os_app = AgentOS(agents=[template])
        client = TestClient(os_app.get_app())
        prefix = os_app.config.api_prefix

        r = client.post(f"{prefix}/chat", json={"message": "hi", "session_id": "x"})
        assert r.status_code == 200, r.text
        # The shared template (with handoffs intact) handled the request.
        assert seen[-1] == id(template)
