"""
Verification Hooks Example.

Demonstrates how to use verification hooks with Agent autonomy.

Run with: python 03_verification_hooks.py

Requirements:
- OPENAI_API_KEY environment variable set
"""

from praisonaiagents import Agent

# Agent-centric quickstart
agent = Agent(
    name="VerificationHooksDemo",
    instructions="You are a helpful assistant demonstrating verification hooks."
)

# --- Advanced: Low-level Verification API ---
from praisonaiagents.hooks.verification import (
    VerificationHook,
    VerificationResult,
    BaseVerificationHook,
    CommandVerificationHook,
)


class SimpleTestHook(BaseVerificationHook):
    """A simple test verification hook."""
    
    name = "simple_test"
    
    def _execute(self, context=None):
        return VerificationResult(
            success=True,
            output="All tests passed!",
            details={"tests_run": 5, "passed": 5, "failed": 0},
        )


class LintHook(BaseVerificationHook):
    """A lint verification hook."""
    
    name = "lint"
    
    def _execute(self, context=None):
        return VerificationResult(
            success=True,
            output="No lint errors found",
            details={"files_checked": 10, "errors": 0, "warnings": 2},
        )


def main():
    print("=" * 60)
    print("Verification Hooks Example")
    print("=" * 60)
    
    # 1. Create hooks
    print("\n1. Creating Verification Hooks:")
    test_hook = SimpleTestHook()
    lint_hook = LintHook()
    
    print(f"   - {test_hook.name}: {type(test_hook).__name__}")
    print(f"   - {lint_hook.name}: {type(lint_hook).__name__}")
    
    # 2. Run hooks manually
    print("\n2. Running Hooks Manually:")
    test_result = test_hook.run()
    lint_result = lint_hook.run()
    
    print(f"   Test result: success={test_result.success}, output='{test_result.output}'")
    print(f"   Lint result: success={lint_result.success}, output='{lint_result.output}'")
    
    # 3. Create agent with verification hooks
    print("\n3. Agent with Verification Hooks:")
    agent = Agent(
        instructions="You are a test-driven developer.",
        autonomy=True,
        verification_hooks=[test_hook, lint_hook],
    )
    
    print(f"   Hooks registered: {len(agent._verification_hooks)}")
    
    # 4. Run verification hooks through agent
    print("\n4. Running Hooks Through Agent:")
    results = agent._run_verification_hooks()
    
    for result in results:
        print(f"   - {result['hook']}: success={result['success']}")
    
    # 5. CommandVerificationHook example (without running)
    print("\n5. CommandVerificationHook (structure only):")
    cmd_hook = CommandVerificationHook(
        name="pytest",
        command=["python", "-m", "pytest", "-v"],
        timeout=30.0,
    )
    print(f"   Name: {cmd_hook.name}")
    print(f"   Command: {cmd_hook.command}")
    print(f"   Timeout: {cmd_hook.timeout_seconds}s")
    
    print("\n" + "=" * 60)
    print("✓ Verification hooks example completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
