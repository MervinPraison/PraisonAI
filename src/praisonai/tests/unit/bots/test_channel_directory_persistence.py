"""Tests for durable + refreshable ChannelDirectory (issue #2185)."""

import json

import pytest

from praisonai.bots.delivery import ChannelDirectory


def _paths(tmp_path):
    return tmp_path / "channel_directory.json", tmp_path / "channel_aliases.json"


def test_observed_channels_persist_across_restart(tmp_path):
    persist, aliases = _paths(tmp_path)

    d1 = ChannelDirectory(persist_path=persist, aliases_path=aliases)
    d1.observe_channel("discord", "123")  # auto-persists

    d2 = ChannelDirectory(persist_path=persist, aliases_path=aliases)
    assert d2.has_channel("discord", "123")


def test_home_channel_persists_across_restart(tmp_path):
    persist, aliases = _paths(tmp_path)

    d1 = ChannelDirectory(persist_path=persist, aliases_path=aliases)
    d1.set_home_channel("slack", "C999")

    d2 = ChannelDirectory(persist_path=persist, aliases_path=aliases)
    assert d2.get_home_channel("slack") == "C999"


def test_alias_overlay_applied_on_load(tmp_path):
    persist, aliases = _paths(tmp_path)
    aliases.write_text(json.dumps({
        "engineering": {"platform": "discord", "channel_id": "555"},
        "ops": "slack:C111",
    }))

    d = ChannelDirectory(persist_path=persist, aliases_path=aliases)

    assert d.resolve_alias("engineering") == ("discord", "555")
    assert d.resolve_alias("ops") == ("slack", "C111")
    # Aliased channels become reachable even without prior traffic.
    assert d.has_channel("discord", "555")


def test_alias_overlay_survives_restart_without_traffic(tmp_path):
    persist, aliases = _paths(tmp_path)
    aliases.write_text(json.dumps({"engineering": "discord:555"}))

    d1 = ChannelDirectory(persist_path=persist, aliases_path=aliases)
    assert d1.resolve_alias("engineering") == ("discord", "555")

    d2 = ChannelDirectory(persist_path=persist, aliases_path=aliases)
    assert d2.resolve_alias("engineering") == ("discord", "555")


def test_invalid_alias_overlay_entry_skipped(tmp_path):
    persist, aliases = _paths(tmp_path)
    aliases.write_text(json.dumps({
        "good": "discord:1",
        "bad": {"platform": "discord"},  # missing channel_id
        "also_bad": "no-colon",
    }))

    d = ChannelDirectory(persist_path=persist, aliases_path=aliases)
    assert d.resolve_alias("good") == ("discord", "1")
    assert d.resolve_alias("bad") is None
    assert d.resolve_alias("also_bad") is None


class _FakeChannel:
    def __init__(self, cid):
        self.id = cid


class _FakeAdapter:
    def __init__(self, channels):
        self._channels = channels

    def list_channels(self):
        return self._channels


class _NoListAdapter:
    pass


def test_refresh_from_adapters_enumerates_channels(tmp_path):
    persist, aliases = _paths(tmp_path)
    d = ChannelDirectory(persist_path=persist, aliases_path=aliases)

    adapters = {
        "discord": _FakeAdapter([_FakeChannel("100"), _FakeChannel("200")]),
        "slack": _FakeAdapter(["C300"]),  # plain string id
        "telegram": _NoListAdapter(),  # skipped, no list_channels
    }
    d.refresh_from_adapters(adapters)

    assert d.has_channel("discord", "100")
    assert d.has_channel("discord", "200")
    assert d.has_channel("slack", "C300")

    # Persisted so a fresh directory sees the same reachable channels.
    d2 = ChannelDirectory(persist_path=persist, aliases_path=aliases)
    assert d2.has_channel("discord", "100")
    assert d2.has_channel("slack", "C300")


def test_refresh_handles_adapter_errors(tmp_path):
    persist, aliases = _paths(tmp_path)
    d = ChannelDirectory(persist_path=persist, aliases_path=aliases)

    class _BrokenAdapter:
        def list_channels(self):
            raise RuntimeError("boom")

    # Should not raise; broken adapter is skipped.
    d.refresh_from_adapters({"discord": _BrokenAdapter()})
    assert d.describe_targets() == []


def test_describe_targets_includes_observed(tmp_path):
    persist, aliases = _paths(tmp_path)
    d = ChannelDirectory(persist_path=persist, aliases_path=aliases)
    d.observe_channel("discord", "777")

    names = {(t["platform"], t["channel_id"], t["kind"]) for t in d.describe_targets()}
    assert ("discord", "777", "observed") in names


def test_refresh_reapplies_alias_overlay(tmp_path):
    persist, aliases = _paths(tmp_path)
    d = ChannelDirectory(persist_path=persist, aliases_path=aliases)

    # Alias added after construction (hand-edited overlay), then refresh.
    aliases.write_text(json.dumps({"eng": "discord:42"}))
    d.refresh_from_adapters({})

    assert d.resolve_alias("eng") == ("discord", "42")


def test_deleted_alias_pruned_on_refresh(tmp_path):
    persist, aliases = _paths(tmp_path)
    aliases.write_text(json.dumps({"eng": "discord:42", "ops": "slack:C1"}))

    d = ChannelDirectory(persist_path=persist, aliases_path=aliases)
    assert d.resolve_alias("eng") == ("discord", "42")
    assert d.resolve_alias("ops") == ("slack", "C1")

    # User removes an alias from the overlay; a refresh should honour it.
    aliases.write_text(json.dumps({"eng": "discord:42"}))
    d.refresh_from_adapters({})

    assert d.resolve_alias("eng") == ("discord", "42")
    assert d.resolve_alias("ops") is None


def test_manual_alias_not_pruned_by_overlay(tmp_path):
    persist, aliases = _paths(tmp_path)
    d = ChannelDirectory(persist_path=persist, aliases_path=aliases)

    # Alias added programmatically (not from the overlay file).
    d.add_alias("manual", "discord", "9")
    aliases.write_text(json.dumps({"eng": "discord:42"}))
    d.refresh_from_adapters({})

    assert d.resolve_alias("manual") == ("discord", "9")
    assert d.resolve_alias("eng") == ("discord", "42")


def test_missing_files_default_to_empty(tmp_path):
    persist, aliases = _paths(tmp_path)
    d = ChannelDirectory(persist_path=persist, aliases_path=aliases)
    assert d.describe_targets() == []
    assert d.get_home_channel("discord") is None
