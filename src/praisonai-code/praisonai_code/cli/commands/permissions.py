"""
Permission management commands for PraisonAI CLI.

Provides commands to view, add, remove, and reset permission rules.
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from praisonaiagents.permissions import (
    PermissionManager,
    PermissionRule,
    PermissionAction,
)


console = Console()


@click.group()
def permissions():
    """Manage tool execution permissions and approval rules."""
    pass


def get_project_permissions_dir() -> str:
    """Get the project-scoped permissions directory."""
    project_dir = os.getcwd()
    return os.path.join(project_dir, ".praisonai", "permissions")


@permissions.command(name="list")
def list_rules():
    """List all permission rules."""
    permissions_dir = get_project_permissions_dir()
    manager = PermissionManager(storage_dir=permissions_dir)
    
    rules = manager.get_rules()
    
    if not rules:
        console.print("[yellow]No permission rules configured.[/yellow]")
        console.print("\nRules are created automatically when you choose 'Always allow' or 'Always deny' during tool approval.")
        return
    
    # Create table
    table = Table(title="Permission Rules", show_header=True)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Pattern", style="bright_blue")
    table.add_column("Action", style="green")
    table.add_column("Description")
    table.add_column("Agent", style="magenta")
    table.add_column("Priority", style="yellow")
    table.add_column("Enabled", style="green")
    
    for rule in sorted(rules, key=lambda r: -r.priority):
        action_color = {
            PermissionAction.ALLOW: "green",
            PermissionAction.DENY: "red",
            PermissionAction.ASK: "yellow"
        }.get(rule.action, "white")
        
        table.add_row(
            rule.id[:8],
            rule.pattern,
            f"[{action_color}]{rule.action.value}[/{action_color}]",
            rule.description or "-",
            rule.agent_name or "all",
            str(rule.priority),
            "✓" if rule.enabled else "✗"
        )
    
    console.print(table)


@permissions.command()
@click.argument("pattern")
@click.option("--agent", help="Apply rule to specific agent only")
@click.option("--description", help="Rule description")
@click.option("--priority", default=100, help="Rule priority (higher = checked first)")
def allow(pattern: str, agent: Optional[str], description: Optional[str], priority: int):
    """Add an ALLOW rule for the specified pattern.
    
    Examples:
        praisonai permissions allow "bash:git *" --description "Allow all git commands"
        praisonai permissions allow "read:*" --agent researcher
        praisonai permissions allow "bash:ls *" --priority 200
    """
    permissions_dir = get_project_permissions_dir()
    manager = PermissionManager(storage_dir=permissions_dir)
    
    rule = PermissionRule(
        pattern=pattern,
        action=PermissionAction.ALLOW,
        description=description or f"Allow {pattern}",
        agent_name=agent,
        priority=priority,
    )
    
    manager.add_rule(rule)
    
    console.print(f"[green]✓ Added ALLOW rule for pattern: {pattern}[/green]")


@permissions.command()
@click.argument("pattern")
@click.option("--agent", help="Apply rule to specific agent only")
@click.option("--description", help="Rule description")
@click.option("--priority", default=100, help="Rule priority (higher = checked first)")
def deny(pattern: str, agent: Optional[str], description: Optional[str], priority: int):
    """Add a DENY rule for the specified pattern.
    
    Examples:
        praisonai permissions deny "bash:rm *" --description "Block rm commands"
        praisonai permissions deny "write:*.env" --agent writer
        praisonai permissions deny "bash:sudo *" --priority 200
    """
    permissions_dir = get_project_permissions_dir()
    manager = PermissionManager(storage_dir=permissions_dir)
    
    rule = PermissionRule(
        pattern=pattern,
        action=PermissionAction.DENY,
        description=description or f"Deny {pattern}",
        agent_name=agent,
        priority=priority,
    )
    
    manager.add_rule(rule)
    
    console.print(f"[red]✓ Added DENY rule for pattern: {pattern}[/red]")


@permissions.command()
@click.argument("pattern")
@click.option("--agent", help="Apply rule to specific agent only")
@click.option("--description", help="Rule description")
@click.option("--priority", default=50, help="Rule priority (higher = checked first)")
def ask(pattern: str, agent: Optional[str], description: Optional[str], priority: int):
    """Add an ASK rule for the specified pattern.
    
    Examples:
        praisonai permissions ask "bash:*" --description "Ask for all shell commands"
        praisonai permissions ask "edit:*.py" --agent coder
    """
    permissions_dir = get_project_permissions_dir()
    manager = PermissionManager(storage_dir=permissions_dir)
    
    rule = PermissionRule(
        pattern=pattern,
        action=PermissionAction.ASK,
        description=description or f"Ask for {pattern}",
        agent_name=agent,
        priority=priority,
    )
    
    manager.add_rule(rule)
    
    console.print(f"[yellow]✓ Added ASK rule for pattern: {pattern}[/yellow]")


@permissions.command(name="test")
@click.argument("target")
@click.option("--agent", help="Evaluate as a specific agent")
@click.option("--json", "as_json", is_flag=True, help="Output the decision as JSON")
def test_target(target: str, agent: Optional[str], as_json: bool):
    """Show the effective decision for a tool call, without running it.

    TARGET is "<tool>:<argument>", the same form the live approval uses.
    It is checked against this project's rules with PermissionManager.check().
    Order: persistent approvals, then rules (highest priority first),
    otherwise the default is ask. Shell commands are split into their
    sub-commands, and a deny on any part wins.

    Source is one of: rule, approval, sub-operations (every part of a
    compound shell command allowed), default, or safety-gate (built-in
    checks such as secret-file reads or unparseable shell).

    Examples:
        praisonai permissions test "bash:rm -rf build"
        praisonai permissions test "read:.env" --json
    """
    tool, sep, arg = target.partition(":")
    tool = tool.strip()
    # Trim the space after a shell prefix only; file arguments are kept
    # exactly as the live backend would see them.
    if sep and f"{tool}:" in PermissionManager._SHELL_PREFIXES:
        arg = arg.lstrip()
    target = f"{tool}{sep}{arg}" if sep else target.strip()

    storage_dir = get_project_permissions_dir()
    if os.path.isdir(storage_dir):
        result = PermissionManager(storage_dir=storage_dir).check(target, agent_name=agent)
    else:
        # No project store yet: evaluate against an empty one without
        # creating .praisonai/ (PermissionManager makes its storage dir).
        import tempfile
        with tempfile.TemporaryDirectory() as empty_dir:
            result = PermissionManager(storage_dir=empty_dir).check(target, agent_name=agent)

    rule = result.rule
    if rule is not None:
        source = "rule"
    elif result.approved is not None:
        source = "approval"
    elif result.action == PermissionAction.ALLOW:
        # Compound shell command whose sub-operations were all allowed.
        source = "sub-operations"
    elif "No matching rule" in result.reason:
        source = "default"
    else:
        # Built-in gate: unparseable/expanding shell, secret read, etc.
        source = "safety-gate"

    if as_json:
        print(json.dumps({
            "target": target,
            "decision": result.action.value,
            "source": source,
            "rule_id": rule.id if rule else None,
            "pattern": rule.pattern if rule else None,
            "agent": agent,
            "reason": result.reason,
        }, indent=2))
        return

    color = {
        PermissionAction.ALLOW: "green",
        PermissionAction.DENY: "red",
        PermissionAction.ASK: "yellow",
    }.get(result.action, "white")
    console.print(f"Target:   {escape(target)}")
    console.print(f"Decision: [{color}]{result.action.value}[/{color}]")
    console.print(f"Source:   {source}")
    if rule is not None:
        console.print(f"Rule:     {rule.id[:8]} ({escape(rule.pattern)}, priority {rule.priority})")
    console.print(f"Reason:   {escape(result.reason)}")


@permissions.command()
@click.argument("rule_id")
def remove(rule_id: str):
    """Remove a permission rule by ID (use 'list' to see IDs)."""
    permissions_dir = get_project_permissions_dir()
    manager = PermissionManager(storage_dir=permissions_dir)
    
    rules = manager.get_rules()
    
    # Find all rules matching the prefix
    matches = [rule for rule in rules if rule.id.startswith(rule_id)]
    
    if not matches:
        console.print(f"[red]✗ No rule found with ID starting with: {rule_id}[/red]")
        return
    
    if len(matches) > 1:
        console.print(
            f"[yellow]✗ Multiple rules match '{rule_id}'. Please provide a longer ID prefix.[/yellow]"
        )
        console.print("Matching rules:")
        for rule in matches:
            console.print(f"  - {rule.id}: {rule.pattern} ({rule.action.value})")
        return
    
    rule_to_remove = matches[0]
    manager.remove_rule(rule_to_remove.id)
    
    console.print(f"[green]✓ Removed rule: {rule_to_remove.pattern} ({rule_to_remove.action.value})[/green]")


@permissions.command()
@click.confirmation_option(prompt="Are you sure you want to reset all permission rules?")
def reset():
    """Reset all permission rules (requires confirmation)."""
    permissions_dir = get_project_permissions_dir()
    
    rules_file = os.path.join(permissions_dir, "rules.json")
    approvals_file = os.path.join(permissions_dir, "approvals.json")
    
    removed_count = 0
    
    if os.path.exists(rules_file):
        os.remove(rules_file)
        removed_count += 1
    
    if os.path.exists(approvals_file):
        os.remove(approvals_file)
        removed_count += 1
    
    if removed_count > 0:
        console.print("[green]✓ All permission rules have been reset.[/green]")
    else:
        console.print("[yellow]No permission rules to reset.[/yellow]")


@permissions.command()
def export():
    """Export permission rules as JSON."""
    permissions_dir = get_project_permissions_dir()
    manager = PermissionManager(storage_dir=permissions_dir)
    
    rules = manager.get_rules()
    
    if not rules:
        console.print("[yellow]No permission rules to export.[/yellow]")
        return
    
    export_data = {
        "version": "1.0",
        "rules": [rule.to_dict() for rule in rules]
    }
    
    print(json.dumps(export_data, indent=2))


@permissions.command()
@click.argument("file", type=click.Path(exists=True))
def import_rules(file: str):
    """Import permission rules from JSON file."""
    permissions_dir = get_project_permissions_dir()
    manager = PermissionManager(storage_dir=permissions_dir)
    
    with open(file, "r") as f:
        data = json.load(f)
    
    if "rules" not in data:
        console.print("[red]✗ Invalid import file: missing 'rules' field[/red]")
        return
    
    imported_count = 0
    for rule_data in data["rules"]:
        try:
            rule = PermissionRule.from_dict(rule_data)
            manager.add_rule(rule)
            imported_count += 1
        except Exception as e:
            console.print(f"[yellow]Warning: Failed to import rule: {e}[/yellow]")
    
    manager.save_rules()
    console.print(f"[green]✓ Imported {imported_count} rule(s)[/green]")


if __name__ == "__main__":
    permissions()