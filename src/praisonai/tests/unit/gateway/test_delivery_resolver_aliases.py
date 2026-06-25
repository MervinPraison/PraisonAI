"""Tests for alias-aware gateway DeliveryResolver (issue #2285).

Verifies the gateway DeliveryResolver can resolve friendly aliases/names via an
optional channel directory while remaining fully backward compatible with the
existing single home-channel resolution.
"""

from praisonai.gateway.home_channels import DeliveryResolver, HomeChannelRegistry


def _registry(tmp_path):
    return HomeChannelRegistry(persist_path=tmp_path / "home_channels.json")


class _FakeDirectory:
    """Minimal channel directory exposing resolve_alias."""

    def __init__(self, mapping):
        self._mapping = mapping

    def resolve_alias(self, name):
        return self._mapping.get(name)


def test_backward_compatible_without_directory(tmp_path):
    reg = _registry(tmp_path)
    reg.set_home("telegram", "111")
    resolver = DeliveryResolver(reg)

    targets = resolver.resolve("telegram")
    assert len(targets) == 1
    assert targets[0].channel == "telegram"
    assert targets[0].channel_id == "111"


def test_unknown_token_without_directory_returns_empty(tmp_path):
    resolver = DeliveryResolver(_registry(tmp_path))
    assert resolver.resolve("family") == []


def test_alias_resolution_via_directory(tmp_path):
    reg = _registry(tmp_path)
    directory = _FakeDirectory(
        {"family": ("telegram", "111"), "ops": ("telegram", "222")}
    )
    resolver = DeliveryResolver(reg, directory=directory)

    family = resolver.resolve("family")
    assert len(family) == 1
    assert (family[0].channel, family[0].channel_id) == ("telegram", "111")

    ops = resolver.resolve("ops")
    assert (ops[0].channel, ops[0].channel_id) == ("telegram", "222")


def test_multiple_aliases_same_platform(tmp_path):
    """The core scenario: two channels on one platform, both addressable."""
    reg = _registry(tmp_path)
    directory = _FakeDirectory(
        {"family": ("telegram", "111"), "ops": ("telegram", "222")}
    )
    resolver = DeliveryResolver(reg, directory=directory)

    assert resolver.resolve("family")[0].channel_id == "111"
    assert resolver.resolve("ops")[0].channel_id == "222"


def test_platform_home_takes_precedence_over_alias(tmp_path):
    reg = _registry(tmp_path)
    reg.set_home("telegram", "home-id")
    directory = _FakeDirectory({"telegram": ("telegram", "alias-id")})
    resolver = DeliveryResolver(reg, directory=directory)

    targets = resolver.resolve("telegram")
    assert targets[0].channel_id == "home-id"


def test_unknown_alias_falls_back_to_empty(tmp_path):
    reg = _registry(tmp_path)
    directory = _FakeDirectory({"family": ("telegram", "111")})
    resolver = DeliveryResolver(reg, directory=directory)

    assert resolver.resolve("nonexistent") == []


def test_explicit_target_unaffected_by_directory(tmp_path):
    reg = _registry(tmp_path)
    directory = _FakeDirectory({"family": ("telegram", "111")})
    resolver = DeliveryResolver(reg, directory=directory)

    targets = resolver.resolve("slack:C123")
    assert (targets[0].channel, targets[0].channel_id) == ("slack", "C123")


def test_directory_without_resolve_alias_is_ignored(tmp_path):
    class _NoAliasDir:
        pass

    resolver = DeliveryResolver(_registry(tmp_path), directory=_NoAliasDir())
    assert resolver.resolve("family") == []


def test_directory_error_is_swallowed(tmp_path):
    class _BrokenDir:
        def resolve_alias(self, name):
            raise RuntimeError("boom")

    resolver = DeliveryResolver(_registry(tmp_path), directory=_BrokenDir())
    assert resolver.resolve("family") == []
