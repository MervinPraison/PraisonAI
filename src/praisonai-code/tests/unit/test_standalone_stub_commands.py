"""Regression tests for issue #2837.

Fourteen Typer stub command groups (``agents``, ``workflow``, ``registry`` and
peers) re-entered the legacy ``PraisonAI().main()`` by mutating ``sys.argv``.
On a standalone ``pip install praisonai-code`` (no ``praisonai`` wrapper) the
legacy path imports the wrapper-only ``argparse_builder`` and crashed with a
Rich ``ImportError`` traceback before reaching any feature handler.

The migrated commands route through
``praisonai_code._wrapper_bridge.run_wrapper_command`` which fails fast with a
single-line install hint (exit 1) when the wrapper is absent, and re-enters the
legacy CLI only when the wrapper is installed.

These tests verify:
1. ``run_wrapper_command`` exits 1 with a hint (no traceback) when the wrapper
   is unavailable.
2. The migrated Typer commands do not raise a Rich traceback on standalone.
3. No migrated command module still calls ``PraisonAI().main()``.
"""

import pathlib

import pytest


STUB_MODULES = [
    "agents",
    "workflow",
    "registry",
    "memory",
    "skills",
    "hooks",
    "rules",
    "eval",
    "package",
    "templates",
    "todo",
    "research",
    "commit",
    "call",
]


def test_run_wrapper_command_exits_one_without_traceback(monkeypatch):
    """Standalone (no wrapper) → SystemExit(1) with a hint, not an ImportError."""
    import praisonai_code._wrapper_bridge as bridge

    monkeypatch.setattr(bridge, "wrapper_available", lambda: False)

    with pytest.raises(SystemExit) as excinfo:
        bridge.run_wrapper_command(["list"], feature="agents")

    assert excinfo.value.code == 1


@pytest.mark.parametrize(
    "module_name,argv",
    [
        ("agents", ["list"]),
        ("workflow", ["list"]),
        ("registry", ["list"]),
        ("memory", ["show"]),
        ("skills", ["list"]),
    ],
)
def test_stub_command_no_traceback_standalone(monkeypatch, module_name, argv):
    """Migrated commands fail fast (exit 1) with no Rich traceback standalone."""
    typer_testing = pytest.importorskip("typer.testing")
    import praisonai_code._wrapper_bridge as bridge

    monkeypatch.setattr(bridge, "wrapper_available", lambda: False)

    module = __import__(
        f"praisonai_code.cli.commands.{module_name}", fromlist=["app"]
    )
    runner = typer_testing.CliRunner()
    result = runner.invoke(module.app, argv)

    assert "Traceback" not in result.output
    assert "argparse_builder" not in result.output
    assert result.exit_code == 1


def test_no_legacy_main_reentry_in_stub_modules():
    """No migrated command module re-enters ``PraisonAI().main()`` (issue #2837)."""
    base = pathlib.Path(__file__).resolve().parents[2] / (
        "praisonai_code/cli/commands"
    )
    offenders = []
    for name in STUB_MODULES:
        text = (base / f"{name}.py").read_text()
        if "praison.main()" in text:
            offenders.append(name)
    assert offenders == [], f"legacy re-entry still present in: {offenders}"
