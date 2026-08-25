"""
Rules command group for PraisonAI CLI.

Provides native rules management (list/add/clear) for the standalone
``praisonai-code`` terminal product. The underlying storage is core's
``praisonaiagents.memory.RulesManager`` (PRAISON.md / CLAUDE.md / AGENTS.md and
``.praison/rules/*.md``), so these commands work without the optional
``praisonai`` wrapper. The wrapper bridge is retained only as a fallback for
environments where core is unexpectedly unavailable.
"""

from __future__ import annotations

import os

import typer

app = typer.Typer(help="Rules management")


def _rules_manager():
    """Return a core ``RulesManager`` for the current workspace, or ``None``.

    Core (``praisonaiagents``) is a hard dependency of ``praisonai-code``, so
    this normally succeeds on a standalone install. ``None`` is returned only
    when core is genuinely unavailable, letting the caller fall back to the
    wrapper bridge with a single clear notice rather than crashing.
    """
    try:
        from praisonaiagents.memory import RulesManager
    except ImportError:
        return None
    return RulesManager(workspace_path=os.getcwd())


def _fallback(argv: list[str]) -> None:
    """Delegate to the wrapper bridge for a rules subcommand (last resort)."""
    from praisonai_code._wrapper_bridge import run_wrapper_command

    run_wrapper_command(argv, feature="rules")


@app.command("list")
def rules_list():
    """List active rules."""
    manager = _rules_manager()
    if manager is None:
        _fallback(['rules', 'list'])
        return

    try:
        all_rules = manager.get_all_rules()
    except Exception as exc:  # noqa: BLE001 - never crash the CLI on rules read
        typer.echo(f"Failed to load rules: {exc}", err=True)
        raise typer.Exit(1)

    if not all_rules:
        typer.echo(
            "No rules found. Create PRAISON.md, CLAUDE.md, AGENTS.md, "
            "or files in .praison/rules/"
        )
        return

    for rule in all_rules:
        desc = rule.description or ""
        if len(desc) > 60:
            desc = desc[:57] + "..."
        suffix = f" - {desc}" if desc else ""
        typer.echo(f"{rule.name} [{rule.activation}]{suffix}")


@app.command("add")
def rules_add(
    rule: str = typer.Argument(..., help="Rule name"),
    content: str = typer.Argument(None, help="Rule content"),
):
    """Add a rule (workspace scope)."""
    manager = _rules_manager()
    if manager is None:
        argv = ['rules', 'add', rule]
        if content:
            argv.append(content)
        _fallback(argv)
        return

    if not content:
        typer.echo(
            "Rule content required. Usage: praisonai rules add <name> <content>",
            err=True,
        )
        raise typer.Exit(1)

    try:
        manager.create_rule(
            name=rule,
            content=content,
            description=f"Rule created via CLI: {rule}",
            activation="always",
            scope="workspace",
        )
    except Exception as exc:  # noqa: BLE001 - surface a clean error, no traceback
        typer.echo(f"Failed to add rule '{rule}': {exc}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Rule added: {rule}")


def _workspace_rule_names(manager) -> list[str]:
    """Names of rules stored under the workspace ``.praison/rules/`` directory.

    ``rules add`` creates ``workspace``-scoped rules; the manager keys every
    loaded rule as ``"{scope}:{name}"`` and also surfaces discovered project
    files (``AGENTS.md``/``CLAUDE.md``/``PRAISON.md``), global rules, git-root
    rules and nested subdir rules. Clearing must therefore be constrained to the
    ``workspace:`` scope so it only removes CLI-created rules and never unlinks
    the user's hand-authored instruction files or global/nested rules.

    Reads the manager's rule registry directly (public accessors do not expose
    the scope key) and returns the names under the ``workspace:`` prefix,
    de-duplicated in insertion order.
    """
    names: list[str] = []
    seen: set[str] = set()
    for key in getattr(manager, "_rules", {}):
        scope, _, name = key.partition(":")
        if scope == "workspace" and name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


@app.command("clear")
def rules_clear():
    """Clear workspace rules created via the CLI.

    Only ``workspace``-scoped rules (those created by ``rules add`` under
    ``.praison/rules/``) are removed. Discovered project files
    (``AGENTS.md``/``CLAUDE.md``/``PRAISON.md``), global rules, git-root rules
    and nested subdirectory rules are intentionally left untouched so this
    command can never destroy hand-authored instructions outside its scope.
    """
    manager = _rules_manager()
    if manager is None:
        _fallback(['rules', 'clear'])
        return

    try:
        # Ensure the registry reflects on-disk state before enumerating.
        names = _workspace_rule_names(manager)
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"Failed to load rules: {exc}", err=True)
        raise typer.Exit(1)

    removed = 0
    for name in names:
        try:
            # Scope the delete to ``workspace`` so a same-named global/subdir
            # rule is never removed as a side effect.
            if manager.delete_rule(name, scope="workspace"):
                removed += 1
        except Exception:  # noqa: BLE001 - skip undeletable rules, keep going
            continue

    typer.echo(f"Cleared {removed} rule(s).")
