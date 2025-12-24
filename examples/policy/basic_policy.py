#!/usr/bin/env python3
"""
Basic Policy Engine Example for PraisonAI Agents.

This example demonstrates how to use the policy engine to:
1. Create policies with rules
2. Check if actions are allowed
3. Block dangerous operations
4. Use convenience policy creators

Usage:
    python basic_policy.py
"""

from praisonaiagents.policy import (
    PolicyEngine, Policy, PolicyRule, PolicyAction, PolicyConfig,
    create_deny_tools_policy, create_read_only_policy
)


def main():
    print("=" * 60)
    print("Policy Engine Demo")
    print("=" * 60)
    
    # Create a policy engine
    engine = PolicyEngine()
    
    # ==========================================================================
    # Policy 1: Block dangerous tools
    # ==========================================================================
    print("\n--- Creating Policies ---")
    
    dangerous_tools_policy = Policy(
        name="block_dangerous",
        description="Block dangerous file operations",
        rules=[
            PolicyRule(
                action=PolicyAction.DENY,
                resource="tool:delete_*",
                reason="Delete operations are blocked",
                name="deny_delete"
            ),
            PolicyRule(
                action=PolicyAction.DENY,
                resource="tool:rm_*",
                reason="Remove operations are blocked",
                name="deny_rm"
            ),
        ],
        priority=100
    )
    engine.add_policy(dangerous_tools_policy)
    print(f"✅ Added policy: {dangerous_tools_policy.name}")
    
    # ==========================================================================
    # Policy 2: Allow read operations
    # ==========================================================================
    read_policy = Policy(
        name="allow_read",
        description="Allow read operations",
        rules=[
            PolicyRule(
                action=PolicyAction.ALLOW,
                resource="tool:read_*",
                name="allow_read"
            ),
            PolicyRule(
                action=PolicyAction.ALLOW,
                resource="tool:list_*",
                name="allow_list"
            ),
        ]
    )
    engine.add_policy(read_policy)
    print(f"✅ Added policy: {read_policy.name}")
    
    # ==========================================================================
    # Test policy checks
    # ==========================================================================
    print("\n--- Testing Policy Checks ---")
    
    test_cases = [
        ("tool:read_file", "Reading a file"),
        ("tool:list_directory", "Listing directory"),
        ("tool:delete_file", "Deleting a file"),
        ("tool:rm_directory", "Removing directory"),
        ("tool:write_file", "Writing a file"),
    ]
    
    for resource, description in test_cases:
        result = engine.check(resource, {})
        status = "✅ ALLOWED" if result.allowed else "🚫 DENIED"
        reason = f" ({result.reason})" if result.reason else ""
        print(f"  {status}: {description}{reason}")
    
    # ==========================================================================
    # Using convenience functions
    # ==========================================================================
    print("\n--- Using Convenience Functions ---")
    
    # Create a read-only policy
    read_only = create_read_only_policy()
    print(f"✅ Created read-only policy with {len(read_only.rules)} rules")
    
    # Create a deny tools policy
    deny_tools = create_deny_tools_policy(
        ["execute_*", "shell_*", "system_*"],
        reason="System commands are blocked"
    )
    print(f"✅ Created deny-tools policy with {len(deny_tools.rules)} rules")
    
    # ==========================================================================
    # Strict mode example
    # ==========================================================================
    print("\n--- Strict Mode Example ---")
    
    strict_engine = PolicyEngine(PolicyConfig(strict_mode=True))
    
    # In strict mode, unknown resources are denied
    result = strict_engine.check("tool:unknown_operation", {})
    print(f"  Unknown operation in strict mode: {'DENIED' if not result.allowed else 'ALLOWED'}")
    
    # ==========================================================================
    # Policy serialization
    # ==========================================================================
    print("\n--- Policy Serialization ---")
    
    policy_dict = dangerous_tools_policy.to_dict()
    print(f"  Serialized policy: {policy_dict['name']} with {len(policy_dict['rules'])} rules")
    
    # Recreate from dict
    restored = Policy.from_dict(policy_dict)
    print(f"  Restored policy: {restored.name}")
    
    print("\n" + "=" * 60)
    print("Demo Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
