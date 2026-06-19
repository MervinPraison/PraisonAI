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


@permissions.command()
def list():
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
    manager.save_rules()
    
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
    manager.save_rules()
    
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
    manager.save_rules()
    
    console.print(f"[yellow]✓ Added ASK rule for pattern: {pattern}[/yellow]")


@permissions.command()
@click.argument("rule_id")
def remove(rule_id: str):
    """Remove a permission rule by ID (use 'list' to see IDs)."""
    permissions_dir = get_project_permissions_dir()
    manager = PermissionManager(storage_dir=permissions_dir)
    
    rules = manager.get_rules()
    rule_to_remove = None
    
    for rule in rules:
        if rule.id.startswith(rule_id):
            rule_to_remove = rule
            break
    
    if not rule_to_remove:
        console.print(f"[red]✗ No rule found with ID starting with: {rule_id}[/red]")
        return
    
    manager.remove_rule(rule_to_remove.id)
    manager.save_rules()
    
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