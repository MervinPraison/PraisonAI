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


class TestOriginFromConfig:
    """The persisted origin must actually reach the resolver from the schedulers.

    Both ``AgentScheduler`` and ``AsyncAgentScheduler`` carry the job's
    persisted origin in ``config`` and pass it through
    ``SchedulerDelivery.origin_from_config`` — otherwise ``deliver="origin"``
    would silently no-op in production (#3142).
    """

    def test_none_config(self):
        assert SchedulerDelivery.origin_from_config(None) is None

    def test_empty_config(self):
        assert SchedulerDelivery.origin_from_config({}) is None

    def test_missing_origin_key(self):
        assert SchedulerDelivery.origin_from_config({"agent_id": "x"}) is None

    def test_delivery_target_object_passthrough(self):
        origin = DeliveryTarget(channel="telegram", channel_id="123456")
        assert SchedulerDelivery.origin_from_config({"origin": origin}) is origin

    def test_dict_origin_normalised(self):
        cfg = {"origin": {"channel": "telegram", "channel_id": "123456"}}
        origin = SchedulerDelivery.origin_from_config(cfg)
        assert origin is not None
        assert origin.channel == "telegram"
        assert origin.channel_id == "123456"

    def test_dict_origin_end_to_end_resolves(self):
        cfg = {
            "origin": {
                "channel": "telegram",
                "channel_id": "123456",
                "thread_id": "789",
            }
        }
        origin = SchedulerDelivery.origin_from_config(cfg)
        d = SchedulerDelivery("origin", origin=origin)
        assert d._target.channel == "telegram"
        assert d._target.channel_id == "123456"
        assert d._target.thread_id == "789"
        assert d._target.deliver == "telegram:123456:789"

    def test_unusable_origin_type_ignored(self):
        assert SchedulerDelivery.origin_from_config({"origin": "telegram"}) is None
