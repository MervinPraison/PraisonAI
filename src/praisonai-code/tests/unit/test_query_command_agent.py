"""Regression tests for `praisonai query` Agent construction (issue #2774).

The query command must NOT pass an invalid ``retrieval_config=`` kwarg to
``Agent.__init__`` (the Agent-first API consolidates RAG under ``knowledge=``
and exposes ``_retrieval_config`` internally). It must also tolerate Agent API
versions that expose ``output=`` instead of ``verbose=``.
"""

import sys
import types

import pytest
from typer.testing import CliRunner


runner = CliRunner()


class _StubResult:
    answer = "Paris"
    citations = []
    metadata = {}


def _install_stub_praisonaiagents(monkeypatch, *, agent_accepts=("name", "instructions", "knowledge", "verbose")):
    """Install a minimal fake praisonaiagents package tree.

    ``Agent.__init__`` only accepts the whitelisted params so passing any
    unexpected kwarg (e.g. ``retrieval_config=``) raises TypeError, mirroring
    the real crash from issue #2774.
    """
    captured = {}

    class _StubKnowledgeConfig:
        pass

    class _StubRetrievalConfig:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

        def to_knowledge_config(self):
            return _StubKnowledgeConfig()

    class _RetrievalPolicy:
        ALWAYS = "always"

    class _CitationsMode:
        def __init__(self, value):
            self.value = value

    class _StubKnowledge:
        def __init__(self, *args, **kwargs):
            pass

    class _StubAgent:
        def __init__(self, **kwargs):
            for key in kwargs:
                if key not in agent_accepts:
                    raise TypeError(
                        f"Agent.__init__() got an unexpected keyword argument '{key}'"
                    )
            self.__dict__.update(kwargs)
            self._retrieval_config = None
            captured["agent"] = self

        def query(self, question, **kwargs):
            captured["question"] = question
            return _StubResult()

    pkg = types.ModuleType("praisonaiagents")
    pkg.Agent = _StubAgent

    rag_pkg = types.ModuleType("praisonaiagents.rag")
    rc_mod = types.ModuleType("praisonaiagents.rag.retrieval_config")
    rc_mod.RetrievalConfig = _StubRetrievalConfig
    rc_mod.RetrievalPolicy = _RetrievalPolicy
    rc_mod.CitationsMode = _CitationsMode

    knowledge_pkg = types.ModuleType("praisonaiagents.knowledge")
    knowledge_pkg.Knowledge = _StubKnowledge

    monkeypatch.setitem(sys.modules, "praisonaiagents", pkg)
    monkeypatch.setitem(sys.modules, "praisonaiagents.rag", rag_pkg)
    monkeypatch.setitem(sys.modules, "praisonaiagents.rag.retrieval_config", rc_mod)
    monkeypatch.setitem(sys.modules, "praisonaiagents.knowledge", knowledge_pkg)
    return captured


def _load_app():
    from praisonai_code.cli.commands.retrieval import app

    return app


def test_query_command_instantiates_agent_without_retrieval_config(monkeypatch):
    captured = _install_stub_praisonaiagents(monkeypatch)
    result = runner.invoke(_load_app(), ["query", "What capital?", "-c", "fixture"])
    assert result.exit_code == 0, result.output
    assert "retrieval_config" not in result.output
    assert "unexpected keyword" not in result.output
    # _retrieval_config must still be attached so .query()/.rag work.
    assert captured["agent"]._retrieval_config is not None


def test_query_command_maps_verbose_to_output_when_needed(monkeypatch):
    # Newer Agent API exposes output= instead of verbose=.
    captured = _install_stub_praisonaiagents(
        monkeypatch, agent_accepts=("name", "instructions", "knowledge", "output")
    )
    result = runner.invoke(_load_app(), ["query", "What capital?", "-c", "fixture", "-v"])
    assert result.exit_code == 0, result.output
    assert "unexpected keyword" not in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
