"""Tests for BotPlatformRegistry channel entry-point discovery.

Covers the ``praisonai.channels`` entry-point group discovery and the guard
that prevents a third-party entry point from silently shadowing a built-in
platform loader.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from praisonai_bot.bots import _registry as R


@pytest.fixture(autouse=True)
def _reset_default_registry():
    """Isolate tests that mutate the module-level registry singleton.

    ``register_platform`` / ``get_platform_descriptor`` operate on the process
    ``_default_registry`` singleton. Snapshot and restore it around each test so
    stale ``irc*`` registrations never leak into later tests (or platform
    validation elsewhere), regardless of run order.
    """
    saved = R._default_registry
    R._default_registry = None
    R._bot_registry = None
    try:
        yield
    finally:
        R._default_registry = saved
        R._bot_registry = saved


def test_channels_entry_point_registers_new_platform():
    """A ``praisonai.channels`` entry point with a new name is registered."""
    class IRCBot:
        pass

    ep = SimpleNamespace(name="irc", load=lambda: IRCBot)
    with patch("importlib.metadata.entry_points", return_value=[ep]):
        reg = R.BotPlatformRegistry()

    assert "irc" in reg.list_names()
    assert reg.resolve("irc") is IRCBot


def test_channels_entry_point_does_not_override_builtin():
    """A duplicate entry point must not shadow a built-in loader."""
    class Evil:
        pass

    dup = SimpleNamespace(name="telegram", load=lambda: Evil)
    with patch("importlib.metadata.entry_points", return_value=[dup]):
        reg = R.BotPlatformRegistry()

    # The built-in telegram loader must remain, not the third-party one.
    assert reg.resolve("telegram").__name__ != "Evil"


def test_channels_discovery_failure_is_non_fatal():
    """Entry-point discovery failures must not break registry construction."""
    with patch(
        "importlib.metadata.entry_points", side_effect=RuntimeError("boom")
    ):
        reg = R.BotPlatformRegistry()

    # Built-ins are still available despite the discovery failure.
    assert "telegram" in reg.list_names()


# ---------------------------------------------------------------------------
# Channel self-description descriptor (Issue #2801)
# ---------------------------------------------------------------------------

from praisonaiagents.bots import ChannelField  # noqa: E402


class _IRCBot:
    pass


class _IRCDescriptor:
    config_fields = [
        ChannelField("server", required=True, prompt="IRC server host"),
        ChannelField("nickserv_password", secret=True, env="IRC_NICKSERV_PASSWORD"),
    ]
    system_prompt_hint = "You are replying on IRC: plain text only."

    def setup(self, io):
        return {}


def test_register_platform_stores_descriptor():
    """A descriptor passed to register_platform is retrievable."""
    reg = R.BotPlatformRegistry()
    reg.register_with_capabilities("irc", _IRCBot, descriptor=_IRCDescriptor())

    desc = reg.get_descriptor("irc")
    assert desc is not None
    assert desc.system_prompt_hint == "You are replying on IRC: plain text only."
    assert [f.name for f in desc.config_fields] == ["server", "nickserv_password"]


def test_get_descriptor_from_adapter_attribute():
    """A channel may self-describe via a ``channel_descriptor`` attribute."""
    class SelfDescribingBot:
        channel_descriptor = _IRCDescriptor()

    reg = R.BotPlatformRegistry()
    reg.register("irc2", SelfDescribingBot)

    desc = reg.get_descriptor("irc2")
    assert desc is not None
    assert desc.system_prompt_hint.startswith("You are replying on IRC")


def test_get_descriptor_none_for_builtin_without_descriptor():
    """Built-in platforms without a descriptor return None."""
    reg = R.BotPlatformRegistry()
    assert reg.get_descriptor("telegram") is None


def test_module_level_descriptor_helpers(monkeypatch):
    """Module-level helpers expose descriptor + system-prompt hint."""
    R.register_platform("irc3", _IRCBot, descriptor=_IRCDescriptor())
    assert "irc3" in R.list_platforms()
    assert R.get_platform_descriptor("irc3") is not None
    assert R.get_channel_system_prompt_hint("irc3").startswith("You are replying on IRC")
    # Unknown / undescribed channels yield an empty hint, never an error.
    assert R.get_channel_system_prompt_hint("telegram") == ""


def test_config_schema_preserves_plugin_fields(monkeypatch):
    """Plugin-declared config keys reach the adapter instead of being dropped."""
    from praisonai_bot.bots._config_schema import validate_gateway_config

    # A non-secret sentinel; only asserts the env fallback is wired, not a real
    # credential (avoids hardcoded-secret scanners flagging the test).
    fake_secret = "dummy-" + "value"
    R.register_platform("irc4", _IRCBot, descriptor=_IRCDescriptor())
    monkeypatch.setenv("IRC_NICKSERV_PASSWORD", fake_secret)

    cfg = validate_gateway_config(
        {
            "agent": {"name": "a"},
            "channels": {"irc4": {"server": "irc.libera.chat"}},
        },
        apply_env_substitution=False,
    )
    ch = cfg.channels["irc4"]
    # Unknown key preserved (extra="allow") rather than silently dropped.
    assert ch.server == "irc.libera.chat"
    # Secret resolved from the declared env fallback.
    assert ch.nickserv_password == fake_secret


def test_config_schema_enforces_required_plugin_field(monkeypatch):
    """A required plugin field that is missing raises a clear error."""
    import pytest

    from praisonai_bot.bots._config_schema import validate_gateway_config

    R.register_platform("irc5", _IRCBot, descriptor=_IRCDescriptor())
    monkeypatch.delenv("IRC_NICKSERV_PASSWORD", raising=False)

    with pytest.raises(ValueError, match="server"):
        validate_gateway_config(
            {"agent": {"name": "a"}, "channels": {"irc5": {}}},
            apply_env_substitution=False,
        )


# ---------------------------------------------------------------------------
# Onboarding surfaces config-only plugin fields (Issue #2801, P1 fix)
# ---------------------------------------------------------------------------


def test_onboard_prompts_config_only_field(monkeypatch):
    """A ChannelField without ``env`` is prompted and lands in bot.yaml.

    Regression guard: config-only fields (e.g. IRC's ``server``) were stored on
    the wizard info dict but never surfaced, so onboarding completed silently
    and the gateway then failed at start. The wizard must now prompt for them
    and write them under the channel so they reach the adapter.
    """
    from praisonai_bot.cli.features import onboard as OB

    R.register_platform("irc6", _IRCBot, descriptor=_IRCDescriptor())

    info = OB._plugin_platforms().get("irc6")
    assert info is not None
    # ``server`` has no env fallback → it is NOT in extra_env but IS a config field.
    assert "server" not in (info.get("extra_env") or {})
    assert any(getattr(f, "name", None) == "server" for f in info["config_fields"])

    wiz = OB.OnboardWizard()
    wiz.channels = {
        "irc6": {
            "platform": "irc6",
            "role": "assistant",
            "env_var": "IRC6_TOKEN",
            "token": "",
            "info": info,
            "config": {},
        }
    }

    # Route by prompt text: the token prompt and the config-only ``server``
    # prompt both flow through ``_prompt_ask`` — answer only ``server`` so the
    # token is left blank (which is fine for this assertion).
    def _fake_ask(prompt_cls, *args, **kwargs):
        label = args[0] if args else ""
        if "server" in label:
            return "irc.example.org"
        return kwargs.get("default", "") or ""

    monkeypatch.setattr(OB, "_prompt_ask", _fake_ask)
    monkeypatch.delenv("IRC6_TOKEN", raising=False)

    class _NullConsole:
        def print(self, *a, **k):
            pass

    wiz._configure_tokens(_NullConsole(), object)

    assert wiz.channels["irc6"]["config"].get("server") == "irc.example.org"

    yaml_text = OB._generate_bot_yaml_multi_channel(wiz.channels)
    assert 'server: "irc.example.org"' in yaml_text
