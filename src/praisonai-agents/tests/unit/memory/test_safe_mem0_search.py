"""
Unit tests for the consolidated ``safe_mem0_search`` helper.

The helper is the single source of truth for the defensive workaround around
the upstream mem0 MongoDB vector store bug (mem0ai/mem0#3185), where
``mem0_client.search(...)`` raises ``TypeError: ... unexpected keyword
argument 'vectors'``. These tests exercise the three code paths (normal
return, the specific ``vectors`` TypeError, and any other TypeError) against
both the helper directly and the ``Memory._safe_mem0_search`` delegation,
using a fake mem0 client so no real mem0 dependency is required.
"""

import pytest

from praisonaiagents.memory.adapters.factories import safe_mem0_search


class _FakeMem0Client:
    """Minimal stand-in for a mem0 client exposing ``search``."""

    def __init__(self, result=None, error=None):
        self._result = result if result is not None else []
        self._error = error
        self.called_with = None

    def search(self, **kwargs):
        self.called_with = kwargs
        if self._error is not None:
            raise self._error
        return self._result


def test_normal_search_returns_results_and_forwards_kwargs():
    client = _FakeMem0Client(result=[{"id": "1"}])

    result = safe_mem0_search(client, query="hello", limit=3)

    assert result == [{"id": "1"}]
    assert client.called_with == {"query": "hello", "limit": 3}


def test_vectors_type_error_returns_empty_list():
    error = TypeError("search() got an unexpected keyword argument 'vectors'")
    client = _FakeMem0Client(error=error)

    result = safe_mem0_search(client, query="hello")

    assert result == []


def test_other_type_error_is_reraised():
    error = TypeError("search() got an unexpected keyword argument 'foo'")
    client = _FakeMem0Client(error=error)

    with pytest.raises(TypeError):
        safe_mem0_search(client, query="hello")


def test_memory_delegates_to_shared_helper():
    from praisonaiagents.memory.memory import Memory

    normal = _FakeMem0Client(result=[{"id": "1"}])
    assert Memory._safe_mem0_search(None, normal, query="x") == [{"id": "1"}]

    vectors_err = _FakeMem0Client(
        error=TypeError("got an unexpected keyword argument 'vectors'")
    )
    assert Memory._safe_mem0_search(None, vectors_err, query="x") == []

    other_err = _FakeMem0Client(
        error=TypeError("got an unexpected keyword argument 'foo'")
    )
    with pytest.raises(TypeError):
        Memory._safe_mem0_search(None, other_err, query="x")
