#!/usr/bin/env python3
"""
Simple Hooks Example for PraisonAI Agents.

This example shows the SIMPLEST way to use hooks with the add_hook API.
Just a few lines of code to intercept tool calls!

Usage:
    python simple_hooks.py
"""

from praisonaiagents.hooks import add_hook, has_hook, HookResult


# =============================================================================
# Register hooks with simple string event names
# =============================================================================

@add_hook('before_tool')
def log_tools(event_data):
    """Log every tool call."""
    print(f"🔧 Tool: {event_data.tool_name}")
    return HookResult.allow()


@add_hook('before_tool')
def block_dangerous(event_data):
    """Block delete operations."""
    if 'delete' in event_data.tool_name.lower():
        print(f"🚫 Blocked: {event_data.tool_name}")
        return HookResult.deny("Delete operations blocked")
    return HookResult.allow()


@add_hook('after_tool')
def log_completion(event_data):
    """Log tool completion."""
    print(f"✅ Done: {event_data.tool_name} ({event_data.execution_time_ms:.0f}ms)")
    return HookResult.allow()


# =============================================================================
# Test the hooks
# =============================================================================

if __name__ == "__main__":
    print("=" * 50)
    print("Simple Hooks Example")
    print("=" * 50)
    
    # Check hooks are registered
    print(f"\nHooks registered for 'before_tool': {has_hook('before_tool')}")
    print(f"Hooks registered for 'after_tool': {has_hook('after_tool')}")
    
    # You can now create an Agent and the hooks will be applied
    print("\n💡 Hooks are now globally registered!")
    print("   Any Agent will automatically use these hooks.")
    print("\n   Example:")
    print("   from praisonaiagents import Agent")
    print("   agent = Agent(instructions='You are helpful')")
    print("   agent.start('Help me with files')")
