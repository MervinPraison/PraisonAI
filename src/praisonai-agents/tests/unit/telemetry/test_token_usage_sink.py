"""Tests for TokenUsageSinkProtocol (Gap 3).

Validates:
- Protocol structural subtyping
- NoOpTokenUsageSink (default — zero overhead)
- InMemoryTokenUsageSink for testing/debugging
- TokenCollector integration with sink
- Registry pattern for sink management
"""
import pytest


class TestTokenUsageSinkProtocol:
    """Test the protocol definition."""

    def test_protocol_exists(self):
        from praisonaiagents.telemetry.protocols import TokenUsageSinkProtocol
        assert TokenUsageSinkProtocol is not None

    def test_noop_satisfies_protocol(self):
        from praisonaiagents.telemetry.protocols import TokenUsageSinkProtocol, NoOpTokenUsageSink
        sink = NoOpTokenUsageSink()
        assert isinstance(sink, TokenUsageSinkProtocol)

    def test_inmemory_satisfies_protocol(self):
        from praisonaiagents.telemetry.protocols import TokenUsageSinkProtocol, InMemoryTokenUsageSink
        sink = InMemoryTokenUsageSink()
        assert isinstance(sink, TokenUsageSinkProtocol)


class TestNoOpTokenUsageSink:
    """Test NoOp sink does nothing."""

    def test_persist_is_noop(self):
        from praisonaiagents.telemetry.protocols import NoOpTokenUsageSink
        from praisonaiagents.telemetry.token_collector import TokenMetrics
        sink = NoOpTokenUsageSink()
        # Should not raise
        sink.persist(
            task_id="t1",
            agent_name="researcher",
            model="gpt-4o",
            metrics=TokenMetrics(input_tokens=100, output_tokens=50),
        )


class TestInMemoryTokenUsageSink:
    """Test InMemory sink stores records."""

    def test_persist_stores_record(self):
        from praisonaiagents.telemetry.protocols import InMemoryTokenUsageSink
        from praisonaiagents.telemetry.token_collector import TokenMetrics
        sink = InMemoryTokenUsageSink()
        sink.persist(
            task_id="t1",
            agent_name="researcher",
            model="gpt-4o",
            metrics=TokenMetrics(input_tokens=100, output_tokens=50),
        )
        assert len(sink.records) == 1
        assert sink.records[0]["task_id"] == "t1"
        assert sink.records[0]["model"] == "gpt-4o"

    def test_get_by_task(self):
        from praisonaiagents.telemetry.protocols import InMemoryTokenUsageSink
        from praisonaiagents.telemetry.token_collector import TokenMetrics
        sink = InMemoryTokenUsageSink()
        m = TokenMetrics(input_tokens=10, output_tokens=5)
        sink.persist(task_id="t1", agent_name="a", model="m1", metrics=m)
        sink.persist(task_id="t2", agent_name="b", model="m1", metrics=m)
        sink.persist(task_id="t1", agent_name="a", model="m2", metrics=m)
        result = sink.get_by_task("t1")
        assert len(result) == 2

    def test_get_by_agent(self):
        from praisonaiagents.telemetry.protocols import InMemoryTokenUsageSink
        from praisonaiagents.telemetry.token_collector import TokenMetrics
        sink = InMemoryTokenUsageSink()
        m = TokenMetrics(input_tokens=10, output_tokens=5)
        sink.persist(task_id="t1", agent_name="a", model="m1", metrics=m)
        sink.persist(task_id="t2", agent_name="b", model="m1", metrics=m)
        result = sink.get_by_agent("a")
        assert len(result) == 1

    def test_clear(self):
        from praisonaiagents.telemetry.protocols import InMemoryTokenUsageSink
        from praisonaiagents.telemetry.token_collector import TokenMetrics
        sink = InMemoryTokenUsageSink()
        sink.persist(task_id="t1", agent_name="a", model="m1", metrics=TokenMetrics())
        sink.clear()
        assert len(sink.records) == 0


class TestTokenCollectorSinkIntegration:
    """Test that TokenCollector calls the sink on track_tokens."""

    def test_collector_with_sink(self):
        from praisonaiagents.telemetry.token_collector import TokenCollector, TokenMetrics
        from praisonaiagents.telemetry.protocols import InMemoryTokenUsageSink
        sink = InMemoryTokenUsageSink()
        collector = TokenCollector()
        collector.set_sink(sink)
        collector.track_tokens(
            model="gpt-4o",
            agent="researcher",
            metrics=TokenMetrics(input_tokens=100, output_tokens=50),
            metadata={"task_id": "t1"},
        )
        assert len(sink.records) == 1
        assert sink.records[0]["task_id"] == "t1"

    def test_collector_without_sink_no_error(self):
        """Default collector with no sink should work fine."""
        from praisonaiagents.telemetry.token_collector import TokenCollector, TokenMetrics
        collector = TokenCollector()
        # Should not raise even without a sink
        collector.track_tokens(
            model="gpt-4o",
            agent="researcher",
            metrics=TokenMetrics(input_tokens=100, output_tokens=50),
        )

    def test_collector_sink_receives_task_id_from_metadata(self):
        from praisonaiagents.telemetry.token_collector import TokenCollector, TokenMetrics
        from praisonaiagents.telemetry.protocols import InMemoryTokenUsageSink
        sink = InMemoryTokenUsageSink()
        collector = TokenCollector()
        collector.set_sink(sink)
        collector.track_tokens(
            model="gpt-4o",
            agent="researcher",
            metrics=TokenMetrics(input_tokens=50, output_tokens=25),
            metadata={"task_id": "task-abc"},
        )
        assert sink.records[0]["task_id"] == "task-abc"
        assert sink.records[0]["agent_name"] == "researcher"
