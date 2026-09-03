"""Guard against dangling lazy-command module paths (issue #4693).

``praisonai_code.cli.app._LAZY_COMMANDS`` maps each CLI command to the module
that provides its Typer sub-app. ``LazyCommandGroup._resolve_command`` imports
exactly ``module_path`` from that table (after hiding resident commands whose
owning package is not installed), so *every* entry must resolve — the resident
ones (``praisonai``, ``praisonai_bot``, ``praisonai_train``, ``praisonai_browser``,
``praisonai_mcp``) included.

History: resident entries used to carry placeholder ``.commands.<name>`` paths
that named modules which do not exist in ``praisonai_code`` (``schedule`` after
``66dcb788a`` was the reported one; there were 30). The dispatcher hard-coded the
real path and never read the table, so the lie was invisible. The dispatcher now
reads the table, and these tests import each entry the same way it does.

Resident entries whose owning package is not installed are skipped (standalone
``praisonai-code`` install); the owning-package test below still bites there,
because a placeholder ``.commands.*`` path resolves into ``praisonai_code``.
"""

import importlib
import importlib.util

import click
import pytest

from praisonai_code.cli import app as cli_app


def _absolute(module_path: str) -> str:
    """Resolve a table path exactly as the dispatcher's ``import_module`` does."""
    return importlib.util.resolve_name(module_path, cli_app.__package__)


def _root_package(module_path: str) -> str:
    return _absolute(module_path).split(".")[0]


_RESIDENT_OWNERS = (
    (cli_app._WRAPPER_RESIDENT_COMMANDS, "praisonai"),
    (cli_app._BOT_RESIDENT_COMMANDS, "praisonai_bot"),
    (cli_app._TRAIN_RESIDENT_COMMANDS, "praisonai_train"),
    (cli_app._BROWSER_RESIDENT_COMMANDS, "praisonai_browser"),
    (cli_app._MCP_RESIDENT_COMMANDS, "praisonai_mcp"),
)


@pytest.mark.parametrize(
    "name,module_path,attr_name",
    [(n, mp, a) for n, (mp, a, _desc) in cli_app._LAZY_COMMANDS.items()],
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_every_lazy_command_module_resolves(name, module_path, attr_name):
    """Import each table entry the way ``_resolve_command`` does."""
    root = _root_package(module_path)
    if importlib.util.find_spec(root) is None:
        pytest.skip(f"owning package {root!r} for command {name!r} is not installed")
    module = importlib.import_module(module_path, cli_app.__package__)
    assert hasattr(module, attr_name), (
        f"lazy command {name!r} maps to {module_path}:{attr_name} "
        f"but attribute {attr_name!r} is missing"
    )


def test_resident_entries_target_their_owning_package():
    """A resident command's table path must live in the package that serves it.

    This is what makes the original defect impossible even in a standalone
    install where the sibling packages are absent: ``.commands.schedule`` resolves
    into ``praisonai_code`` and fails here regardless of what is installed.
    """
    bad = []
    for names, owner in _RESIDENT_OWNERS:
        for name in sorted(names):
            if name not in cli_app._LAZY_COMMANDS:
                # ``app``/``standardise`` are resident but wired outside the table.
                continue
            module_path = cli_app._LAZY_COMMANDS[name][0]
            if _root_package(module_path) != owner:
                bad.append(f"{name!r} -> {module_path} (expected {owner}.cli.commands.*)")
    assert not bad, "resident lazy-command entries point outside their owning package:\n  " + "\n  ".join(bad)


def test_special_command_modules_resolve():
    for name, (module_path, attr_name, _desc) in cli_app._SPECIAL_COMMANDS.items():
        module = importlib.import_module(module_path, cli_app.__package__)
        assert hasattr(module, attr_name), (
            f"special command {name!r} maps to {module_path}:{attr_name} "
            f"but attribute {attr_name!r} is missing"
        )


def test_schedule_dispatches_from_table_when_wrapper_installed():
    """End-to-end: the reported command still resolves through the real dispatcher."""
    if not cli_app.wrapper_available():
        pytest.skip("requires the praisonai wrapper (schedule is wrapper-resident)")
    from typer.main import get_command as typer_get_command

    root = typer_get_command(cli_app.app)
    ctx = click.Context(root)
    cmd = root.get_command(ctx, "schedule")
    assert isinstance(cmd, click.Command)
    assert cmd.name == "schedule"
    assert "schedule" in root.list_commands(ctx)
