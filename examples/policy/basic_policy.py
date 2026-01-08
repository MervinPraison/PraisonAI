#!/usr/bin/env python3
"""
Basic Policy Engine Example for PraisonAI Agents.

This example demonstrates how to use the policy engine with Agent:
1. Create an Agent with policy enforcement
2. Define policies with rules
3. Block dangerous operations
4. Use convenience policy creators

Usage:
    python basic_policy.py
"""

from praisonaiagents import Agent
from praisonaiagents.policy import (
    PolicyEngine, Policy, PolicyRule, PolicyAction,
    create_deny_tools_policy, create_read_only_policy
)


def main():
    print("=" * 60)
    print("Agent-Centric Policy Engine Demo")
    print("=" * 60)
    
    # Create a policy engine with rules
    engine = PolicyEngine()
    
    # Add policy to block dangerous tools
    print("\n--- Creating Policies ---")
    
    engine.add_policy(Policy(
        name="block_dangerous",
        description="Block dangerous file operations",
        rules=[
            PolicyRule(
                action=PolicyAction.DENY,
                resource="tool:delete_*",
                reason="Delete operations are blocked"
            ),
            PolicyRule(
                action=PolicyAction.DENY,
                resource="tool:rm_*",
                reason="Remove operations are blocked"
            ),
        ],
        priority=100
    ))
    print("✅ Added policy: block_dangerous")
    
    # Add read-only policy using convenience function
    engine.add_policy(create_read_only_policy())
    print("✅ Added policy: read_only")
    
    # Create an Agent with policy enforcement
    agent = Agent(
        name="SecureAgent",
        instructions="You are a file management assistant.",
        policy=engine
    )
    
    print("\n--- Agent with Policy Enforcement Created ---")
    print(f"Agent: {agent.name}")
    print(f"Policy engine: {agent.policy is not None}")
    
    # Test policy checks via agent's policy
    print("\n--- Testing Policy Checks ---")
    
    test_cases = [
        ("tool:read_file", "Reading a file"),
        ("tool:list_directory", "Listing directory"),
        ("tool:delete_file", "Deleting a file"),
        ("tool:write_file", "Writing a file"),
    ]
    
    for resource, description in test_cases:
        result = agent.policy.check(resource, {})
        status = "✅ ALLOWED" if result.allowed else "🚫 DENIED"
        reason = f" ({result.reason})" if result.reason else ""
        print(f"  {status}: {description}{reason}")
    
    # Using convenience functions
    print("\n--- Convenience Policy Creators ---")
    
    deny_tools = create_deny_tools_policy(
        ["execute_*", "shell_*", "system_*"],
        reason="System commands are blocked"
    )
    print(f"✅ create_deny_tools_policy: {len(deny_tools.rules)} rules")
    
    read_only = create_read_only_policy()
    print(f"✅ create_read_only_policy: {len(read_only.rules)} rules")
    
    print("\n" + "=" * 60)
    print("Demo Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
