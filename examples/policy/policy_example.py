#!/usr/bin/env python3
"""
PraisonAI Policy Packs Example

This example demonstrates:
1. Creating and loading policy packs
2. Tool permission checking
3. Policy modes (dev/prod)
4. Merging policies

Prerequisites:
- pip install praisonai

Usage:
    python policy_example.py
"""

import tempfile
from pathlib import Path


def main():
    """Main example function."""
    print("=" * 60)
    print("PraisonAI Policy Packs Example")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # =====================================================
        # Default Policies
        # =====================================================
        print("\n" + "=" * 40)
        print("Default Policies")
        print("=" * 40)
        
        from praisonai.recipe.policy import get_default_policy, PolicyPack, PolicyDeniedError
        
        print("\n1. Loading default dev policy...")
        dev_policy = get_default_policy("dev")
        print(f"   Name: {dev_policy.name}")
        print(f"   Allowed tools: {len(dev_policy.allowed_tools)}")
        print(f"   Denied tools: {len(dev_policy.denied_tools)}")
        print(f"   PII mode: {dev_policy.pii_mode}")
        
        print("\n2. Loading default prod policy...")
        prod_policy = get_default_policy("prod")
        print(f"   Name: {prod_policy.name}")
        print(f"   PII mode: {prod_policy.pii_mode}")
        
        # =====================================================
        # Tool Permission Checking
        # =====================================================
        print("\n" + "=" * 40)
        print("Tool Permission Checking")
        print("=" * 40)
        
        print("\n3. Checking tool permissions...")
        
        # Check allowed tool
        try:
            dev_policy.check_tool("web.search")
            print("   web.search: ✓ Allowed")
        except PolicyDeniedError as e:
            print(f"   web.search: ✗ Denied - {e}")
        
        # Check denied tool
        try:
            dev_policy.check_tool("shell.exec")
            print("   shell.exec: ✓ Allowed")
        except PolicyDeniedError:
            print("   shell.exec: ✗ Denied")
        
        # Check another denied tool
        try:
            dev_policy.check_tool("file.write")
            print("   file.write: ✓ Allowed")
        except PolicyDeniedError:
            print("   file.write: ✗ Denied")
        
        # =====================================================
        # Custom Policy Pack
        # =====================================================
        print("\n" + "=" * 40)
        print("Custom Policy Pack")
        print("=" * 40)
        
        print("\n4. Creating custom policy pack...")
        custom_policy = PolicyPack(
            name="my-org-policy",
            config={
                "tools": {
                    "allow": ["web.search", "db.query", "file.read"],
                    "deny": ["shell.exec", "network.unrestricted"],
                },
                "network": {
                    "allow_domains": ["api.openai.com", "api.anthropic.com"],
                    "deny_domains": ["localhost", "127.0.0.1"],
                },
                "pii": {
                    "mode": "redact",
                    "fields": ["email", "phone", "ssn"],
                },
                "data": {
                    "retention_days": 30,
                    "export_allowed": True,
                },
                "modes": {
                    "dev": {
                        "allow_interactive_prompts": True,
                        "strict_tool_enforcement": False,
                    },
                    "prod": {
                        "allow_interactive_prompts": False,
                        "strict_tool_enforcement": True,
                        "require_auth": True,
                    },
                },
            },
        )
        
        print(f"   Name: {custom_policy.name}")
        print(f"   Allowed tools: {list(custom_policy.allowed_tools)}")
        print(f"   PII mode: {custom_policy.pii_mode}")
        print(f"   Retention days: {custom_policy.retention_days}")
        
        # =====================================================
        # Saving and Loading Policies
        # =====================================================
        print("\n" + "=" * 40)
        print("Saving and Loading Policies")
        print("=" * 40)
        
        print("\n5. Saving policy to file...")
        policy_file = tmp_path / "my-policy.yaml"
        custom_policy.save(policy_file)
        print(f"   Saved to: {policy_file}")
        
        print("\n6. Loading policy from file...")
        loaded_policy = PolicyPack.load(policy_file)
        print(f"   Loaded: {loaded_policy.name}")
        print(f"   PII mode: {loaded_policy.pii_mode}")
        
        # =====================================================
        # Merging Policies
        # =====================================================
        print("\n" + "=" * 40)
        print("Merging Policies")
        print("=" * 40)
        
        print("\n7. Creating base and override policies...")
        base_policy = PolicyPack(
            name="base",
            config={
                "tools": {"allow": ["web.search"]},
                "pii": {"mode": "allow"},
            },
        )
        
        override_policy = PolicyPack(
            name="override",
            config={
                "tools": {"allow": ["db.query"]},
                "pii": {"mode": "redact", "fields": ["email"]},
            },
        )
        
        print("\n8. Merging policies...")
        merged = base_policy.merge(override_policy)
        print(f"   Merged name: {merged.name}")
        print(f"   Allowed tools: {list(merged.allowed_tools)}")
        print(f"   PII mode: {merged.pii_mode}")
        
        # =====================================================
        # Mode-Specific Configuration
        # =====================================================
        print("\n" + "=" * 40)
        print("Mode-Specific Configuration")
        print("=" * 40)
        
        print("\n9. Getting mode-specific config...")
        dev_config = custom_policy.get_mode_config("dev")
        prod_config = custom_policy.get_mode_config("prod")
        
        print("   Dev mode:")
        print(f"     - Interactive prompts: {dev_config.get('allow_interactive_prompts')}")
        print(f"     - Strict enforcement: {dev_config.get('strict_tool_enforcement')}")
        
        print("   Prod mode:")
        print(f"     - Interactive prompts: {prod_config.get('allow_interactive_prompts')}")
        print(f"     - Strict enforcement: {prod_config.get('strict_tool_enforcement')}")
        print(f"     - Require auth: {prod_config.get('require_auth')}")
        
        # =====================================================
        # Data Policy
        # =====================================================
        print("\n" + "=" * 40)
        print("Data Policy")
        print("=" * 40)
        
        print("\n10. Getting data policy...")
        data_policy = custom_policy.get_data_policy()
        print(f"   PII mode: {data_policy['pii']['mode']}")
        print(f"   PII fields: {data_policy['pii']['fields']}")
        print(f"   Retention days: {data_policy['retention_days']}")
        print(f"   Export allowed: {data_policy['export_allowed']}")
        
        print("\n" + "=" * 60)
        print("Example completed successfully!")
        print("=" * 60)


if __name__ == "__main__":
    main()
