"""`praisonai.knowledge.clear` must not claim success when nothing was cleared.

``Knowledge.reset()`` deliberately no-ops (with a warning) when the configured
memory backend has no ``reset``. The MCP tool called it and returned the fixed
string "Knowledge cleared" regardless, so a user asking to clear a knowledge
base was told the destructive operation succeeded when it had not run at all.
"""
import pytest

pytest.importorskip("praisonaiagents")


@pytest.fixture
def isolated_registry():
    import praisonai_mcp.mcp_server.registry as reg
    from praisonai_mcp.mcp_server.registry import MCPToolRegistry, MCPResourceRegistry

    saved_tool, saved_resource = reg._tool_registry, reg._resource_registry
    reg._tool_registry = MCPToolRegistry()
    reg._resource_registry = MCPResourceRegistry()
    try:
        yield reg
    finally:
        reg._tool_registry, reg._resource_registry = saved_tool, saved_resource


def _tool(reg, name):
    tool = reg._tool_registry.get(name)
    assert tool is not None, f"tool not registered: {name}"
    return tool.handler


class _BackendWithoutReset:
    """A memory backend that cannot be reset (e.g. ChromaKnowledgeAdapter)."""


class _BackendWithReset:
    def __init__(self):
        self.was_reset = False

    def reset(self):
        self.was_reset = True


def _fake_knowledge_cls(backend):
    """A Knowledge stand-in reusing the REAL Knowledge.reset implementation."""
    from praisonaiagents.knowledge import Knowledge

    class _FakeKnowledge:
        def __init__(self):
            self.memory = backend

        reset = Knowledge.reset

    return _FakeKnowledge


def _run_clear(monkeypatch, isolated_registry, backend):
    import praisonaiagents.knowledge as kmod
    from praisonai_mcp.mcp_server.adapters.knowledge import register_knowledge_tools

    monkeypatch.setattr(kmod, "Knowledge", _fake_knowledge_cls(backend))
    register_knowledge_tools()
    return _tool(isolated_registry, "praisonai.knowledge.clear")()


def test_clear_does_not_claim_success_when_backend_cannot_reset(
    monkeypatch, isolated_registry
):
    backend = _BackendWithoutReset()
    out = _run_clear(monkeypatch, isolated_registry, backend)
    assert "cleared" not in out.lower() or "not" in out.lower(), (
        "tool reported a destructive operation as done when the backend "
        f"silently no-opped; returned: {out!r}"
    )


def test_clear_still_reports_success_when_it_really_clears(
    monkeypatch, isolated_registry
):
    """Control: the honest path must still confirm a real clear."""
    backend = _BackendWithReset()
    out = _run_clear(monkeypatch, isolated_registry, backend)
    assert backend.was_reset, "control backend was never reset - test is vacuous"
    assert "cleared" in out.lower(), f"real clear should be confirmed; got {out!r}"
