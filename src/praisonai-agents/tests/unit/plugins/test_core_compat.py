"""Load-time praisonaiagents compatibility gate for plugins (#5951)."""

from praisonaiagents._version import __version__
from praisonaiagents.plugins.discovery import load_plugin
from praisonaiagents.plugins.manager import PluginManager
from praisonaiagents.plugins.plugin import Plugin, PluginInfo, core_incompatibility


class _P(Plugin):
    def __init__(self, deps):
        self._deps = deps

    @property
    def info(self):
        return PluginInfo(name="compat_probe", dependencies=self._deps)


def test_no_core_entry_is_compatible():
    assert core_incompatibility([]) is None
    assert core_incompatibility(["requests>=2", "praisonaiagents"]) is None
    assert core_incompatibility(["not a valid req!!"]) is None


def test_satisfied_and_unsatisfied_ranges():
    assert core_incompatibility([f"praisonaiagents>={__version__}"]) is None
    reason = core_incompatibility(["praisonaiagents>=999"])
    assert "praisonaiagents>=999" in reason and __version__ in reason


def test_comma_split_header_fragments_are_rejoined():
    assert core_incompatibility(["praisonaiagents>=0.0.1", "<999"]) is None
    assert core_incompatibility(["praisonaiagents>=0.0.1", "<0.0.2"]) is not None


def test_register_skips_incompatible_plugin():
    pm = PluginManager()
    assert pm.register(_P(["praisonaiagents>=999"])) is False
    assert pm.get_plugin("compat_probe") is None
    assert pm.register(_P([])) is True


def test_single_file_plugin_not_executed_when_incompatible(tmp_path):
    marker = tmp_path / "ran"
    plugin = tmp_path / "p.py"
    plugin.write_text(
        '"""\nPlugin Name: Compat\nDependencies: praisonaiagents>=999\n"""\n'
        f"open({str(marker)!r}, 'w').close()\n"
    )
    assert load_plugin(str(plugin)) is None
    assert not marker.exists()
