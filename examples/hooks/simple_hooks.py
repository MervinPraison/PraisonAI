#!/usr/bin/env python3
"""
Simple Hooks Example for PraisonAI Agents.

This example shows the SIMPLEST way to use hooks with the add_hook API.
Just a few lines of code to intercept tool calls!

No need to import HookResult - just return None/True to allow, 
False to deny, or a string to deny with a reason.

Usage:
    python simple_hooks.py
"""

from praisonaiagents.hooks import add_hook, has_hook


# =============================================================================
# Register hooks with simple string event names
# =============================================================================

@add_hook('before_tool')
def log_tools(event_data):
    """Log every tool call. Return nothing (None) to allow."""
    print(f"🔧 Tool: {event_data.tool_name}")
    # No return needed - defaults to allow


@add_hook('before_tool')
def block_dangerous(event_data):
    """Block delete operations. Return False or string to deny."""
    if 'delete' in event_data.tool_name.lower():
        print(f"🚫 Blocked: {event_data.tool_name}")
        return "Delete operations are not allowed"  # String = deny with reason
    # No return = allow


@add_hook('after_tool')
def log_completion(event_data):
    """Log tool completion."""
    print(f"✅ Done: {event_data.tool_name} ({event_data.execution_time_ms:.0f}ms)")


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
    print("\n📝 Hook returns:")
    print("   - None or True  → Allow the operation")
    print("   - False         → Deny the operation")
    print("   - 'reason'      → Deny with a custom message")
