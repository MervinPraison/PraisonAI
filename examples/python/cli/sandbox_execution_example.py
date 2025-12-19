"""
Sandbox Execution Example for PraisonAI CLI.

Secure isolated command execution (--sandbox flag).
Docs: https://docs.praison.ai/cli/sandbox-execution
"""

from praisonai.cli.features import SandboxExecutorHandler
from praisonai.cli.features.sandbox_executor import SandboxMode

# Initialize with basic sandbox
handler = SandboxExecutorHandler(verbose=True)
sandbox = handler.initialize(mode="basic")

print(f"Sandbox mode: {handler.get_mode()}")
print(f"Sandbox enabled: {handler.is_enabled}")

# Execute a safe command
print("\n=== Safe Command ===")
result = handler.execute("echo 'Hello from sandbox!'")
print(f"Success: {result.success}")
print(f"Output: {result.stdout.strip()}")
print(f"Sandboxed: {result.was_sandboxed}")

# Try a blocked command
print("\n=== Blocked Command ===")
result = handler.execute("rm -rf /")
print(f"Success: {result.success}")
print(f"Violations: {result.policy_violations}")

# Validate command before execution
print("\n=== Command Validation ===")
violations = handler.validate_command("sudo apt install something")
if violations:
    print(f"Command blocked: {violations}")
else:
    print("Command allowed")

# Available modes
print("\n=== Available Modes ===")
for mode in SandboxMode:
    print(f"  {mode.value}")
