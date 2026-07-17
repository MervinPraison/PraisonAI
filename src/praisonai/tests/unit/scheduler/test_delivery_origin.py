"""Unit tests for lightweight scheduler delivery 'origin' resolution (#3142).

`origin` is the most natural delivery target for a scheduled/interval agent —
"send the result back to wherever this job was created". These tests verify that
``SchedulerDelivery`` resolves the symbolic ``"origin"`` token to the concrete
target persisted on ``ScheduleJob.origin`` — without standing up the full
BotOS gateway — while leaving ``all`` and the absent-origin case as
unresolvable no-ops.
"""

from praisonai.scheduler._delivery import SchedulerDelivery
from praisonaiagents.scheduler import DeliveryTarget


class TestOriginResolution:
    def test_origin_resolves_to_persisted_channel(self):
        origin = DeliveryTarget(channel="telegram", channel_id="123456")
        d = SchedulerDelivery("origin", origin=origin)
        assert d.enabled
        assert d._target.channel == "telegram"
        assert d._target.channel_id == "123456"
        assert d._target.deliver == "telegram:123456"

    def test_origin_preserves_thread_id(self):
        origin = DeliveryTarget(
            channel="telegram", channel_id="123456", thread_id="789"
        )
        d = SchedulerDelivery("origin", origin=origin)
        assert d._target.channel == "telegram"
        assert d._target.channel_id == "123456"
        assert d._target.thread_id == "789"
        assert d._target.deliver == "telegram:123456:789"

    def test_origin_bare_platform_no_channel_id(self):
        origin = DeliveryTarget(channel="telegram")
        d = SchedulerDelivery("origin", origin=origin)
        assert d._target.channel == "telegram"
        assert d._target.deliver == "telegram"

    def test_origin_without_persisted_origin_stays_symbolic(self):
        d = SchedulerDelivery("origin")
        assert d._target is not None
        assert (d._target.channel or "") == ""
        assert d._target.deliver == "origin"

    def test_origin_with_empty_origin_target_stays_symbolic(self):
        d = SchedulerDelivery("origin", origin=DeliveryTarget())
        assert (d._target.channel or "") == ""
        assert d._target.deliver == "origin"

    def test_explicit_target_unaffected_by_origin(self):
        origin = DeliveryTarget(channel="telegram", channel_id="123456")
        d = SchedulerDelivery("discord:999", origin=origin)
        assert d._target.channel == "discord"
        assert d._target.channel_id == "999"

    def test_all_is_not_rewritten(self):
        origin = DeliveryTarget(channel="telegram", channel_id="123456")
        d = SchedulerDelivery("all", origin=origin)
        assert (d._target.channel or "") == ""
        assert d._target.deliver == "all"

    def test_empty_deliver_disabled(self):
        d = SchedulerDelivery("", origin=DeliveryTarget(channel="telegram"))
        assert not d.enabled
        assert d._target is None
