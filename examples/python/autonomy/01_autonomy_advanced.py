"""
Advanced Agent Autonomy Example.

Demonstrates advanced autonomy features:
- Custom configuration
- Doom loop detection
- Verification hooks
- Subagent delegation

Run with: python 01_autonomy_advanced.py

Requirements:
- OPENAI_API_KEY environment variable set
"""

from praisonaiagents import Agent
from praisonaiagents.agents.profiles import get_profile, BUILTIN_PROFILES


def main():
    print("=" * 60)
    print("Agent Autonomy Advanced Example")
    print("=" * 60)
    
    # 1. Custom autonomy configuration
    print("\n1. Custom Autonomy Configuration:")
    agent = Agent(
        instructions="You are a coding assistant.",
        autonomy={
            "max_iterations": 30,
            "doom_loop_threshold": 5,
            "auto_escalate": True,
        },
    )
    print(f"   Max iterations: {agent.autonomy_config.get('max_iterations')}")
    print(f"   Doom loop threshold: {agent.autonomy_config.get('doom_loop_threshold')}")
    print(f"   Auto escalate: {agent.autonomy_config.get('auto_escalate')}")
    
    # 2. Doom loop detection
    print("\n2. Doom Loop Detection:")
    for i in range(5):
        agent._record_action("read_file", {"path": "test.py"}, "content", True)
    
    is_doom = agent._is_doom_loop()
    print(f"   After 5 repeated actions: doom_loop={is_doom}")
    
    agent._reset_doom_loop()
    is_doom_after = agent._is_doom_loop()
    print(f"   After reset: doom_loop={is_doom_after}")
    
    # 3. Verification hooks
    print("\n3. Verification Hooks:")
    
    class MockTestRunner:
        name = "pytest"
        def run(self, context=None):
            return {"success": True, "output": "5 tests passed"}
    
    agent_with_hooks = Agent(
        instructions="You are a test-driven developer.",
        autonomy=True,
        verification_hooks=[MockTestRunner()],
    )
    
    results = agent_with_hooks._run_verification_hooks()
    print(f"   Hook results: {results}")
    
    # 4. Subagent delegation
    print("\n4. Subagent Delegation:")
    subagent = agent._create_subagent("explorer")
    print(f"   Created subagent: {subagent.name}")
    print(f"   Profile: explorer (read-only)")
    
    # 5. Explorer profile details
    print("\n5. Explorer Profile:")
    explorer = get_profile("explorer")
    print(f"   Tools: {explorer.tools}")
    print(f"   Read-only: {explorer.metadata.get('read_only')}")
    print(f"   Blocked tools: {explorer.metadata.get('blocked_tools')}")
    
    # 6. Available profiles
    print("\n6. Available Agent Profiles:")
    for name in BUILTIN_PROFILES:
        profile = get_profile(name)
        if not profile.hidden:
            print(f"   - {name}: {profile.description[:50]}...")
    
    print("\n" + "=" * 60)
    print("✓ Advanced autonomy example completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
