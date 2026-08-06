"""Tests for plugin registry, trust gate, unload cleanup and config write path.

Covers issue #3728:
- get_plugin_registry() reports real plugins (no fake four-plugin list).
- Project single-file plugins are gated (PRAISONAI_ALLOW_PROJECT_PLUGINS).
- unload_plugin unregisters harvested tools (no leak).
- CLI enable/disable and runtime read the same config file (no split-brain).

Run with: pytest tests/test_plugin_registry_and_gate.py -v
"""

import os
import textwrap

import pytest


PLUGIN_BODY = textwrap.dedent(
    '''\
    """
    Plugin Name: gated_demo
    Description: A gated demo plugin
    Version: 1.2.3
    """

    from praisonaiagents import tool

    @tool
    def gated_demo_tool(query: str) -> str:
        """Echo the query."""
        return f"echo: {query}"
    '''
)


@pytest.fixture(autouse=True)
def _clear_config_cache():
    from praisonaiagents.config import loader

    loader.clear_config_cache()
    yield
    loader.clear_config_cache()


def _write_project_plugin(project_dir, name="gated_demo.py"):
    plugins_dir = project_dir / ".praisonai" / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    plugin_file = plugins_dir / name
    plugin_file.write_text(PLUGIN_BODY)
    return plugin_file


class TestTrustGate:
    def test_project_plugin_refused_when_ungated(self, tmp_path, monkeypatch):
        """An ungated project plugin must not execute."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("PRAISONAI_ALLOW_PROJECT_PLUGINS", raising=False)
        plugin_file = _write_project_plugin(tmp_path)

        from praisonaiagents.plugins.discovery import load_plugin

        result = load_plugin(str(plugin_file))
        assert result is None

    def test_project_plugin_loads_when_gated(self, tmp_path, monkeypatch):
        """Gated via env var, the project plugin loads and harvests its tool."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PRAISONAI_ALLOW_PROJECT_PLUGINS", "true")
        plugin_file = _write_project_plugin(tmp_path)

        from praisonaiagents.plugins.discovery import load_plugin

        result = load_plugin(str(plugin_file))
        assert result is not None
        assert result["name"] == "gated_demo"
        assert "gated_demo_tool" in result.get("tools", [])

    def test_gate_via_config(self, tmp_path, monkeypatch):
        """Gate can be opened via .praisonai/config.yaml too."""
        pytest.importorskip("yaml")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("PRAISONAI_ALLOW_PROJECT_PLUGINS", raising=False)
        cfg = tmp_path / ".praisonai" / "config.yaml"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text("plugins:\n  allow_project_plugins: true\n")

        from praisonaiagents.config import loader
        loader.clear_config_cache()
        plugin_file = _write_project_plugin(tmp_path, name="gated_demo2.py")

        from praisonaiagents.plugins.discovery import load_plugin

        result = load_plugin(str(plugin_file))
        assert result is not None


UNLOAD_PLUGIN_BODY = textwrap.dedent(
    '''\
    """
    Plugin Name: unload_demo
    Description: A plugin used to verify unload cleanup
    Version: 1.0.0
    """

    from praisonaiagents import tool

    @tool
    def unload_demo_tool(query: str) -> str:
        """Echo the query."""
        return f"unload-echo: {query}"
    '''
)


class TestUnloadCleanup:
    def test_unload_unregisters_harvested_tools(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PRAISONAI_ALLOW_PROJECT_PLUGINS", "true")
        plugins_dir = tmp_path / ".praisonai" / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)
        plugin_file = plugins_dir / "unload_demo.py"
        plugin_file.write_text(UNLOAD_PLUGIN_BODY)

        from praisonaiagents.plugins.discovery import load_plugin, unload_plugin
        from praisonaiagents.tools.registry import get_registry

        registry = get_registry()
        result = None
        try:
            result = load_plugin(str(plugin_file))
            assert result is not None
            module_name = result["module"]
            tool_name = result["tools"][0]
            assert tool_name == "unload_demo_tool"

            assert registry.get(tool_name) is not None

            assert unload_plugin(module_name) is True
            assert registry.get(tool_name) is None
        finally:
            # Guard against leaking the tool into other tests on failure.
            try:
                registry.unregister("unload_demo_tool")
            except Exception:
                pass


class TestSymlinkGate:
    def test_symlinked_project_plugin_is_gated(self, tmp_path, monkeypatch):
        """A symlink under .praisonai/plugins pointing elsewhere is still gated."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("PRAISONAI_ALLOW_PROJECT_PLUGINS", raising=False)

        # Real plugin body lives outside the project tree.
        outside = tmp_path / "outside"
        outside.mkdir()
        target = outside / "evil.py"
        target.write_text(PLUGIN_BODY)

        plugins_dir = tmp_path / ".praisonai" / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)
        link = plugins_dir / "evil.py"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not supported on this platform")

        from praisonaiagents.plugins.discovery import load_plugin

        # Ungated: the symlink must not bypass the project trust gate.
        assert load_plugin(str(link)) is None


class TestSetPluginEnabledBoolean:
    def test_enable_when_all_enabled_is_noop(self, tmp_path, monkeypatch):
        """enabled: true stays intact when enabling a plugin (no collapse to [])."""
        pytest.importorskip("yaml")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("PRAISONAI_PLUGINS", raising=False)
        cfg = tmp_path / ".praisonai" / "config.yaml"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text("plugins:\n  enabled: true\n")

        from praisonaiagents.config import loader

        loader.clear_config_cache()
        loader.set_plugin_enabled("x", True)
        loader.clear_config_cache()
        # Still "all enabled" (None), not a truncated allow-list.
        assert loader.get_enabled_plugins() is None

    def test_disable_when_all_enabled_is_rejected(self, tmp_path, monkeypatch):
        """Disabling under enabled: true is ambiguous and must be refused."""
        pytest.importorskip("yaml")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("PRAISONAI_PLUGINS", raising=False)
        cfg = tmp_path / ".praisonai" / "config.yaml"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text("plugins:\n  enabled: true\n")

        from praisonaiagents.config import loader

        loader.clear_config_cache()
        with pytest.raises(ValueError):
            loader.set_plugin_enabled("x", False)


class TestRegistry:
    def test_registry_has_no_fake_plugins(self):
        """The real registry never contains the old hardcoded fake names."""
        from praisonaiagents.plugins import get_plugin_registry

        names = {e["name"] for e in get_plugin_registry()}
        assert "memory-core" not in names
        assert "browser-tool" not in names
        assert "knowledge-rag" not in names
        assert "telemetry" not in names

    def test_registry_lists_project_plugin_without_exec(self, tmp_path, monkeypatch):
        """Single-file plugins are listed (metadata only, no gate needed)."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("PRAISONAI_ALLOW_PROJECT_PLUGINS", raising=False)
        _write_project_plugin(tmp_path, name="listed_demo.py")

        from praisonaiagents.plugins import get_plugin_registry

        entries = get_plugin_registry()
        demo = next((e for e in entries if e["name"] == "gated_demo"), None)
        assert demo is not None
        assert demo["source"] == "single_file"
        assert demo["version"] == "1.2.3"


class TestConfigSingleSourceOfTruth:
    def test_enable_writes_same_file_runtime_reads(self, tmp_path, monkeypatch):
        pytest.importorskip("yaml")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("PRAISONAI_PLUGINS", raising=False)

        from praisonaiagents.config import loader

        path = loader.set_plugin_enabled("my_plugin", True)
        # No stray JSON config was written.
        assert not (tmp_path / ".praisonai" / "config.json").exists()
        assert path.suffix in (".yaml", ".yml")

        loader.clear_config_cache()
        assert loader.get_enabled_plugins() == ["my_plugin"]

        # Disable removes it from the same file.
        loader.set_plugin_enabled("my_plugin", False)
        loader.clear_config_cache()
        assert loader.get_enabled_plugins() in (None, [])
