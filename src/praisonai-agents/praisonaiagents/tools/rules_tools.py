"""
Rules Tools for PraisonAI Agents.

Provides tools for agents to create, read, and manage rules dynamically.
This enables Agent-Requested rules similar to Cursor's agent-requested rules feature.

Usage:
    from praisonaiagents.tools.rules_tools import (
        create_rule_tool,
        list_rules_tool,
        get_rule_tool,
        delete_rule_tool
    )
    
    agent = Agent(
        name="Assistant",
        tools=[create_rule_tool, list_rules_tool, get_rule_tool]
    )
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Singleton RulesManager instance
_rules_manager = None


def _get_rules_manager():
    """Get or create the RulesManager singleton."""
    global _rules_manager
    if _rules_manager is None:
        from praisonaiagents.memory.rules_manager import RulesManager
        _rules_manager = RulesManager()
    return _rules_manager


def create_rule_tool(
    name: str,
    content: str,
    description: str = "",
    globs: Optional[str] = None,
    activation: str = "always",
    priority: int = 0,
    scope: str = "workspace"
) -> str:
    """
    Create a new rule for the AI agent to follow.
    
    This tool allows the agent to create persistent rules that will be
    applied to future conversations and tasks.
    
    Args:
        name: Rule name (used as filename, no spaces or special chars)
        content: The rule content in markdown format
        description: Short description of what the rule does
        globs: Comma-separated glob patterns for file matching (e.g., "**/*.py,**/*.js")
        activation: When to apply the rule:
            - "always": Always apply this rule
            - "glob": Apply when working with files matching globs
            - "manual": Only apply when explicitly mentioned
            - "ai_decision": Let AI decide when to apply
        priority: Priority (higher = applied first, default 0)
        scope: Where to save ("workspace" or "global")
        
    Returns:
        Success message with rule details
        
    Example:
        create_rule_tool(
            name="python-style",
            content="- Use type hints for all functions\\n- Follow PEP 8",
            description="Python coding standards",
            globs="**/*.py",
            activation="glob"
        )
    """
    try:
        manager = _get_rules_manager()
        
        # Parse globs
        glob_list = None
        if globs:
            glob_list = [g.strip() for g in globs.split(",") if g.strip()]
        
        # Validate activation
        valid_activations = ["always", "glob", "manual", "ai_decision"]
        if activation not in valid_activations:
            return f"Error: activation must be one of {valid_activations}"
        
        # Validate scope
        if scope not in ["workspace", "global"]:
            return "Error: scope must be 'workspace' or 'global'"
        
        # Create the rule
        rule = manager.create_rule(
            name=name,
            content=content,
            description=description,
            globs=glob_list,
            activation=activation,
            priority=priority,
            scope=scope
        )
        
        return f"""Successfully created rule '{name}'
Location: {rule.file_path}
Activation: {activation}
Priority: {priority}
Description: {description or 'None'}
Globs: {glob_list or 'None'}

The rule will be applied according to its activation mode."""
        
    except Exception as e:
        logger.error(f"Error creating rule: {e}")
        return f"Error creating rule: {str(e)}"


def list_rules_tool() -> str:
    """
    List all available rules.
    
    Returns a formatted list of all rules with their metadata.
    
    Returns:
        Formatted string with rule information
    """
    try:
        manager = _get_rules_manager()
        rules = manager.get_all_rules()
        
        if not rules:
            return "No rules found. Use create_rule_tool to create new rules."
        
        lines = ["# Available Rules\n"]
        
        for rule in rules:
            scope = "global" if "global:" in (rule.file_path or "") else "workspace"
            lines.append(f"## {rule.name}")
            lines.append(f"- **Activation**: {rule.activation}")
            lines.append(f"- **Priority**: {rule.priority}")
            if rule.description:
                lines.append(f"- **Description**: {rule.description}")
            if rule.globs:
                lines.append(f"- **Globs**: {', '.join(rule.globs)}")
            lines.append(f"- **Scope**: {scope}")
            lines.append("")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Error listing rules: {e}")
        return f"Error listing rules: {str(e)}"


def get_rule_tool(name: str) -> str:
    """
    Get the content of a specific rule.
    
    Args:
        name: The name of the rule to retrieve
        
    Returns:
        The rule content and metadata
    """
    try:
        manager = _get_rules_manager()
        rule = manager.get_rule(name)
        
        if not rule:
            return f"Rule '{name}' not found. Use list_rules_tool to see available rules."
        
        return f"""# Rule: {rule.name}

**Description**: {rule.description or 'None'}
**Activation**: {rule.activation}
**Priority**: {rule.priority}
**Globs**: {', '.join(rule.globs) if rule.globs else 'None'}
**File**: {rule.file_path}

## Content:
{rule.content}
"""
        
    except Exception as e:
        logger.error(f"Error getting rule: {e}")
        return f"Error getting rule: {str(e)}"


def delete_rule_tool(name: str, scope: Optional[str] = None) -> str:
    """
    Delete a rule.
    
    Args:
        name: The name of the rule to delete
        scope: Optional scope to delete from ("workspace" or "global")
        
    Returns:
        Success or error message
    """
    try:
        manager = _get_rules_manager()
        
        if scope and scope not in ["workspace", "global"]:
            return "Error: scope must be 'workspace' or 'global'"
        
        success = manager.delete_rule(name, scope)
        
        if success:
            return f"Successfully deleted rule '{name}'"
        else:
            return f"Rule '{name}' not found or could not be deleted"
        
    except Exception as e:
        logger.error(f"Error deleting rule: {e}")
        return f"Error deleting rule: {str(e)}"


def get_active_rules_tool(file_path: Optional[str] = None) -> str:
    """
    Get all rules that are currently active for a given file or context.
    
    Args:
        file_path: Optional file path to check which rules apply
        
    Returns:
        Formatted string with active rules
    """
    try:
        manager = _get_rules_manager()
        
        if file_path:
            rules = manager.get_rules_for_file(file_path)
        else:
            rules = manager.get_active_rules()
        
        if not rules:
            return "No active rules for this context."
        
        lines = ["# Active Rules\n"]
        
        for rule in rules:
            lines.append(f"## {rule.name}")
            if rule.description:
                lines.append(f"*{rule.description}*\n")
            lines.append(rule.content)
            lines.append("")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Error getting active rules: {e}")
        return f"Error getting active rules: {str(e)}"


# Export all tools
__all__ = [
    "create_rule_tool",
    "list_rules_tool",
    "get_rule_tool",
    "delete_rule_tool",
    "get_active_rules_tool"
]
