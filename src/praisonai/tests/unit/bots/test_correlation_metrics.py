"""Tests for end-to-end correlation IDs and gateway message-flow metrics."""
from __future__ import annotations

import asyncio

import pytest


class TestCorrelationId:
    def test_mint_is_unique_and_nonempty(self):
        from praisonai.bots import new_correlation_id

        a = new_correlation_id()
        b = new_correlation_id()
        assert a and b
        assert a != b

    def test_adopt_correlation_id_key(self):
        from praisonai.bots import correlation_id_from

        assert correlation_id_from({"correlation_id": "abc"}) == "abc"

    def test_adopt_message_id_when_no_correlation_id(self):
        from praisonai.bots import correlation_id_from

        assert correlation_id_from({"message_id": "55"}) == "55"

    def test_adopt_skips_empty_values(self):
        from praisonai.bots import correlation_id_from

        cid = correlation_id_from({"correlation_id": "", "message_id": "55"})
        assert cid == "55"

    def test_mints_new_when_no_inbound(self):
        from praisonai.bots import correlation_id_from

        assert correlation_id_from(None)
        assert correlation_id_from({})

    def test_adopt_from_object_attribute(self):
        from praisonai.bots import correlation_id_from

        class Msg:
            message_id = "77"

        assert correlation_id_from(Msg()) == "77"

    def test_use_correlation_id_context(self):
        from praisonai.bots import use_correlation_id, current_correlation_id

        assert current_correlation_id() is None
        with use_correlation_id("zzz") as cid:
            assert cid == "zzz"
            assert current_correlation_id() == "zzz"
        assert current_correlation_id() is None

    def test_use_correlation_id_restores_previous(self):
        from praisonai.bots import use_correlation_id, current_correlation_id

        with use_correlation_id("outer"):
            with use_correlation_id("inner"):
                assert current_correlation_id() == "inner"
            assert current_correlation_id() == "outer"

    def test_correlation_log_fields(self):
        from praisonai.bots._correlation import (
            use_correlation_id,
            correlation_log_fields,
        )

        with use_correlation_id("cid123"):
            fields = correlation_log_fields({"platform": "telegram"})
            assert fields["correlation_id"] == "cid123"
            assert fields["platform"] == "telegram"

    def test_propagates_across_async_tasks(self):
        from praisonai.bots._correlation import (
            set_correlation_id,
            current_correlation_id,
        )

        async def main():
            set_correlation_id("task-cid")

            async def child():
                return current_correlation_id()

            return await asyncio.create_task(child())

        # A child task started after the id is set inherits the context copy.
        assert asyncio.run(main()) == "task-cid"


class TestGatewayMetrics:
    def test_counter_increment(self):
        from praisonai.bots import GatewayMetrics

        m = GatewayMetrics()
        m.inc("messages_inbound_total")
        m.inc("messages_inbound_total", 2)
        assert m.counter_value("messages_inbound_total") == 3

    def test_counter_with_labels(self):
        from praisonai.bots import GatewayMetrics

        m = GatewayMetrics()
        m.inc("outbound_failed_total", labels={"channel": "telegram"})
        m.inc("outbound_failed_total", labels={"channel": "slack"})
        assert m.counter_value("outbound_failed_total", {"channel": "telegram"}) == 1
        assert m.counter_value("outbound_failed_total", {"channel": "slack"}) == 1

    def test_gauge_set(self):
        from praisonai.bots import GatewayMetrics

        m = GatewayMetrics()
        m.set_gauge("outbox_depth", 5)
        assert m.gauge_value("outbox_depth") == 5
        m.set_gauge("outbox_depth", 2)
        assert m.gauge_value("outbox_depth") == 2

    def test_gauge_provider(self):
        from praisonai.bots import GatewayMetrics

        depth = {"value": 7}
        m = GatewayMetrics()
        m.register_gauge_provider("outbox_depth", lambda: depth["value"])
        assert m.gauge_value("outbox_depth") == 7
        depth["value"] = 3
        assert m.gauge_value("outbox_depth") == 3

    def test_render_prometheus_format(self):
        from praisonai.bots import GatewayMetrics

        m = GatewayMetrics()
        m.inc("messages_inbound_total", 4)
        m.set_gauge("outbox_depth", 1)
        text = m.render_prometheus()
        assert "# TYPE messages_inbound_total counter" in text
        assert "messages_inbound_total 4" in text
        assert "# TYPE outbox_depth gauge" in text
        assert "outbox_depth 1" in text

    def test_render_labels_escaped(self):
        from praisonai.bots import GatewayMetrics

        m = GatewayMetrics()
        m.inc("channel_errors_total", labels={"channel": "tele\"gram"})
        text = m.render_prometheus()
        assert 'channel="tele\\"gram"' in text

    def test_snapshot(self):
        from praisonai.bots import GatewayMetrics

        m = GatewayMetrics()
        m.inc("messages_inbound_total", 2)
        m.inc("outbound_failed_total", labels={"channel": "slack"})
        m.set_gauge("active_sessions", 3)
        snap = m.snapshot()
        assert snap["counters"]["messages_inbound_total"] == 2
        assert snap["counters"]['outbound_failed_total{channel="slack"}'] == 1
        assert snap["gauges"]["active_sessions"] == 3
