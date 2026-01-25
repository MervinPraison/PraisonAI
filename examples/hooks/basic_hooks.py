#!/usr/bin/env python3
"""
Basic Hooks Example for PraisonAI Agents.

This example demonstrates the simplified hook API using add_hook():
1. Log tool calls before execution
2. Block dangerous operations
3. Add context to agent responses
4. Monitor session lifecycle

For the simplest example, see simple_hooks.py

Usage:
    python basic_hooks.py
"""

import asyncio
from praisonaiagents.hooks import (
    add_hook, remove_hook, has_hook, get_default_registry,
    HookRunner, HookEvent, HookResult,
    BeforeToolInput, AfterToolInput
)


def main():
    # Clear any existing hooks from previous runs
    get_default_registry().clear()
    
    # ==========================================================================
    # Hook 1: Log all tool calls (using string event name)
    # ==========================================================================
    @add_hook('before_tool')
    def log_tool_calls(event_data: BeforeToolInput) -> HookResult:
        """Log every tool call before execution."""
        print(f"\n📝 [LOG] Tool: {event_data.tool_name}")
        print(f"   Input: {event_data.tool_input}")
        return HookResult.allow()
    
    # ==========================================================================
    # Hook 2: Block dangerous file operations
    # ==========================================================================
    @add_hook('before_tool')
    def block_delete_operations(event_data: BeforeToolInput) -> HookResult:
        """Block any delete or remove operations."""
        dangerous_keywords = ['delete', 'remove', 'rm', 'unlink']
        tool_lower = event_data.tool_name.lower()
        
        if any(kw in tool_lower for kw in dangerous_keywords):
            print(f"\n🚫 [BLOCKED] Dangerous operation: {event_data.tool_name}")
            return HookResult.deny(
                f"Operation '{event_data.tool_name}' is blocked by security policy"
            )
        return HookResult.allow()
    
    # ==========================================================================
    # Hook 3: Require confirmation for write operations
    # ==========================================================================
    @add_hook('before_tool')
    def confirm_write_operations(event_data: BeforeToolInput) -> HookResult:
        """Request confirmation for write operations."""
        write_keywords = ['write', 'save', 'create', 'update']
        tool_lower = event_data.tool_name.lower()
        
        if any(kw in tool_lower for kw in write_keywords):
            print(f"\n⚠️  [CONFIRM] Write operation: {event_data.tool_name}")
            # In a real scenario, you might prompt the user here
            return HookResult.allow("Auto-approved for demo")
        return HookResult.allow()
    
    # ==========================================================================
    # Hook 4: Add timing information after tool execution
    # ==========================================================================
    @add_hook('after_tool')
    def log_tool_completion(event_data: AfterToolInput) -> HookResult:
        """Log tool completion with timing."""
        print(f"\n✅ [DONE] Tool: {event_data.tool_name}")
        print(f"   Duration: {event_data.execution_time_ms:.2f}ms")
        if event_data.tool_error:
            print(f"   Error: {event_data.tool_error}")
        return HookResult.allow()
    
    # ==========================================================================
    # Test the hooks
    # ==========================================================================
    print("=" * 60)
    print("Testing Hooks System (using add_hook API)")
    print("=" * 60)
    
    # Check hooks are registered
    print(f"\nHooks registered for 'before_tool': {has_hook('before_tool')}")
    print(f"Hooks registered for 'after_tool': {has_hook('after_tool')}")
    
    runner = HookRunner(get_default_registry())
    
    # Test 1: Normal tool call (should be logged and allowed)
    print("\n--- Test 1: Normal read operation ---")
    input1 = BeforeToolInput(
        session_id="test",
        cwd="/tmp",
        event_name="before_tool",
        timestamp="2024-01-01T00:00:00",
        tool_name="read_file",
        tool_input={"path": "/tmp/test.txt"}
    )
    results = asyncio.run(runner.execute(HookEvent.BEFORE_TOOL, input1))
    print(f"Result: {'ALLOWED' if not HookRunner.is_blocked(results) else 'BLOCKED'}")
    
    # Test 2: Delete operation (should be blocked)
    print("\n--- Test 2: Delete operation ---")
    input2 = BeforeToolInput(
        session_id="test",
        cwd="/tmp",
        event_name="before_tool",
        timestamp="2024-01-01T00:00:00",
        tool_name="delete_file",
        tool_input={"path": "/important/data.txt"}
    )
    results = asyncio.run(runner.execute(HookEvent.BEFORE_TOOL, input2))
    print(f"Result: {'ALLOWED' if not HookRunner.is_blocked(results) else 'BLOCKED'}")
    if HookRunner.is_blocked(results):
        print(f"Reason: {HookRunner.get_blocking_reason(results)}")
    
    # Test 3: Write operation (should be confirmed)
    print("\n--- Test 3: Write operation ---")
    input3 = BeforeToolInput(
        session_id="test",
        cwd="/tmp",
        event_name="before_tool",
        timestamp="2024-01-01T00:00:00",
        tool_name="write_file",
        tool_input={"path": "/tmp/output.txt", "content": "Hello"}
    )
    results = asyncio.run(runner.execute(HookEvent.BEFORE_TOOL, input3))
    print(f"Result: {'ALLOWED' if not HookRunner.is_blocked(results) else 'BLOCKED'}")
    
    # Show registered hooks
    print("\n" + "=" * 60)
    print("Registered Hooks:")
    print("=" * 60)
    for event, hooks in get_default_registry().list_hooks().items():
        print(f"\n{event}:")
        for hook in hooks:
            print(f"  - {hook['name']} (matcher: {hook['matcher'] or '*'})")


if __name__ == "__main__":
    main()
