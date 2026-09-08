"""A knowledge-store failure must not look like an empty result set.

SmartRetriever._search used to do `except Exception: return []` with no log
line, so a store that was unreachable, misconfigured or refusing auth produced
byte-identical output to a healthy store with no matches. The agent then
answered from the model's own knowledge and nothing -- not the caller, not the
log, not the model -- recorded that retrieval had failed.
"""
import logging
import pytest

from praisonaiagents.rag.retriever import SmartRetriever


class BrokenStore:
    """A store that is down: search raises."""
    def search(self, *a, **k):
        raise RuntimeError("vector store unreachable: connection refused")


class EmptyStore:
    """A healthy store that genuinely has no matching documents."""
    def search(self, *a, **k):
        return []


class PopulatedStore:
    def search(self, *a, **k):
        return [{"memory": "Refunds are issued within 30 days.", "score": 0.9}]


def test_broken_store_is_flagged_as_a_failure():
    result = SmartRetriever(BrokenStore()).retrieve("refund policy", top_k=3)
    assert result.retrieval_failed is True
    assert result.error is not None
    assert "unreachable" in result.error
    assert result.metadata["retrieval_error"] == result.error


def test_control_empty_store_is_not_a_failure():
    """The control: no matches is an answer, not an error."""
    result = SmartRetriever(EmptyStore()).retrieve("refund policy", top_k=3)
    assert result.retrieval_failed is False
    assert result.error is None
    assert result.chunks == []


def test_broken_and_empty_are_now_distinguishable():
    """The defect itself: these two were once identical."""
    broken = SmartRetriever(BrokenStore()).retrieve("refund policy", top_k=3)
    empty = SmartRetriever(EmptyStore()).retrieve("refund policy", top_k=3)
    assert broken.chunks == empty.chunks == []      # still true
    assert broken.retrieval_failed != empty.retrieval_failed


def test_broken_store_logs_an_error(caplog):
    with caplog.at_level(logging.ERROR, logger="praisonaiagents.rag.retriever"):
        SmartRetriever(BrokenStore()).retrieve("refund policy", top_k=3)
    messages = [r.getMessage() for r in caplog.records]
    assert any("Knowledge retrieval failed" in m for m in messages), caplog.text
    assert any("unreachable" in m for m in messages), caplog.text


def test_control_healthy_store_logs_no_error(caplog):
    with caplog.at_level(logging.ERROR, logger="praisonaiagents.rag.retriever"):
        SmartRetriever(EmptyStore()).retrieve("refund policy", top_k=3)
    assert caplog.records == []


def test_control_successful_retrieval_still_returns_chunks():
    result = SmartRetriever(PopulatedStore()).retrieve("refund policy", top_k=3)
    assert result.retrieval_failed is False
    assert len(result.chunks) == 1


def test_a_later_success_clears_the_previous_error():
    """One broken call must not poison the next healthy one."""
    r = SmartRetriever(BrokenStore())
    assert r.retrieve("q", top_k=3).retrieval_failed is True
    r._knowledge = PopulatedStore()
    second = r.retrieve("q", top_k=3)
    assert second.retrieval_failed is False
    assert second.error is None
