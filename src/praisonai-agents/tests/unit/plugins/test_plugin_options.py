"""
Unit tests for per-plugin options delivered via the unified config.

Covers:
- loader.get_plugin_options / is_plugins_enabled / get_enabled_plugins with
  per-plugin option blocks.
- PluginManager.set_plugin_options / apply_plugin_options delivering each
  plugin its own options via on_config.
"""

import pytest

from praisonaiagents.config import loader
from praisonaiagents.config.loader import (
    PluginsConfig,
    _dict_to_plugins_config,
)
from praisonaiagents.plugins.manager import PluginManager
from praisonaiagents.plugins.plugin import Plugin, PluginInfo


class _RecordingPlugin(Plugin):
    """A minimal plugin that records the options passed to on_config."""

    def __init__(self, name: str):
        self._name = name
        self.received = None

    @property
    def info(self) -> PluginInfo:
        return PluginInfo(name=self._name, version="0.0.1", description="test")

    def on_config(self, config):
        self.received = config
        return config


class TestLoaderPluginOptions:
    def test_dict_to_plugins_config_collects_options(self):
        cfg = _dict_to_plugins_config({
            "enabled": True,
            "auto_discover": False,
            "pii_guardrail": {"redact": ["email", "phone"]},
            "memory_watchdog": {"interval": 30},
        })
        assert isinstance(cfg, PluginsConfig)
        assert cfg.enabled is True
        assert cfg.auto_discover is False
        assert cfg.options == {
            "pii_guardrail": {"redact": ["email", "phone"]},
            "memory_watchdog": {"interval": 30},
        }

    def test_reserved_keys_not_treated_as_options(self):
        cfg = _dict_to_plugins_config({
            "enabled": ["a"],
            "directories": ["/tmp/x"],
        })
        assert cfg.options == {}

    def test_get_plugin_options_reads_config(self, monkeypatch):
        monkeypatch.setattr(
            loader, "get_plugins_config",
            lambda: PluginsConfig(enabled=True, options={"p": {"k": 1}}),
        )
        assert loader.get_plugin_options() == {"p": {"k": 1}}

    def test_is_plugins_enabled_from_options_only(self, monkeypatch):
        monkeypatch.delenv("PRAISONAI_PLUGINS", raising=False)
        monkeypatch.setattr(loader, "_load_config", lambda: {"plugins": {"p": {"k": 1}}})
        monkeypatch.setattr(
            loader, "get_plugins_config",
            lambda: PluginsConfig(enabled=False, options={"p": {"k": 1}}),
        )
        assert loader.is_plugins_enabled() is True

    def test_per_plugin_disabled_flag(self, monkeypatch):
        monkeypatch.delenv("PRAISONAI_PLUGINS", raising=False)
        monkeypatch.setattr(
            loader, "get_plugins_config",
            lambda: PluginsConfig(
                enabled=True,
                options={"a": {"enabled": True}, "b": {"enabled": False}},
            ),
        )
        assert loader.get_enabled_plugins() == ["a"]


class TestManagerPluginOptionsDelivery:
    def test_apply_plugin_options_calls_on_config(self):
        manager = PluginManager()
        plugin = _RecordingPlugin("pii_guardrail")
        manager.register(plugin)
        manager.set_plugin_options({"pii_guardrail": {"redact": ["email"]}})

        delivered = manager.apply_plugin_options()

        assert delivered == 1
        assert plugin.received == {"redact": ["email"]}

    def test_apply_plugin_options_skips_disabled(self):
        manager = PluginManager()
        plugin = _RecordingPlugin("watchdog")
        manager.register(plugin)
        manager.disable("watchdog")
        manager.set_plugin_options({"watchdog": {"interval": 5}})

        delivered = manager.apply_plugin_options()

        assert delivered == 0
        assert plugin.received is None

    def test_get_plugin_options_returns_copy(self):
        manager = PluginManager()
        manager.set_plugin_options({"p": {"k": 1}})
        opts = manager.get_plugin_options("p")
        opts["k"] = 2
        assert manager.get_plugin_options("p") == {"k": 1}

    def test_unknown_plugin_options_ignored(self):
        manager = PluginManager()
        plugin = _RecordingPlugin("known")
        manager.register(plugin)
        manager.set_plugin_options({"unknown": {"x": 1}})

        delivered = manager.apply_plugin_options()

        assert delivered == 0
        assert plugin.received is None

    def test_set_options_replaces_stale_blocks(self):
        # A reused manager must drop option blocks removed from a later config
        # so removed plugins never receive stale options via on_config.
        manager = PluginManager()
        manager.set_plugin_options({"a": {"k": 1}, "b": {"k": 2}})
        manager.set_plugin_options({"a": {"k": 3}})
        assert manager.get_plugin_options("a") == {"k": 3}
        assert manager.get_plugin_options("b") == {}

    def test_set_options_merge_mode_keeps_existing(self):
        manager = PluginManager()
        manager.set_plugin_options({"a": {"k": 1}})
        manager.set_plugin_options({"b": {"k": 2}}, replace=False)
        assert manager.get_plugin_options("a") == {"k": 1}
        assert manager.get_plugin_options("b") == {"k": 2}


class TestStringEnabled:
    def test_is_plugins_enabled_from_string(self, monkeypatch):
        monkeypatch.delenv("PRAISONAI_PLUGINS", raising=False)
        monkeypatch.setattr(
            loader, "get_plugins_config",
            lambda: PluginsConfig(enabled="pii_guardrail"),
        )
        monkeypatch.setattr(loader, "_load_config", lambda: {})
        assert loader.is_plugins_enabled() is True

    def test_get_enabled_plugins_from_string(self, monkeypatch):
        monkeypatch.delenv("PRAISONAI_PLUGINS", raising=False)
        monkeypatch.setattr(
            loader, "get_plugins_config",
            lambda: PluginsConfig(enabled="pii_guardrail"),
        )
        assert loader.get_enabled_plugins() == ["pii_guardrail"]


class TestYamlConfigDiscovery:
    def test_load_config_parses_yaml_plugins(self, tmp_path, monkeypatch):
        pytest.importorskip("yaml")
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            "plugins:\n"
            "  enabled: true\n"
            "  pii_guardrail:\n"
            "    redact: [email]\n"
        )
        monkeypatch.setattr(loader, "_find_config_file", lambda: cfg)
        data = loader._load_config()
        assert data["plugins"]["enabled"] is True
        assert data["plugins"]["pii_guardrail"] == {"redact": ["email"]}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
