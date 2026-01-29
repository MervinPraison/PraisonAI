"""
Sandbox Example - Secure Code Execution

This example demonstrates how to configure and use sandboxes
for safe code execution.
"""

from praisonaiagents import (
    SandboxConfig, 
    ResourceLimits, 
    SandboxResult, 
    SandboxStatus
)
from praisonaiagents.sandbox import SecurityPolicy

# Minimal sandbox for untrusted code
minimal_sandbox = SandboxConfig(
    sandbox_type="subprocess",
    resource_limits=ResourceLimits.minimal(),
    security_policy=SecurityPolicy.strict(),
)

# Standard sandbox for general use
standard_sandbox = SandboxConfig(
    sandbox_type="subprocess",
    resource_limits=ResourceLimits.standard(),
    security_policy=SecurityPolicy.standard(),
)

# Docker sandbox for full isolation
docker_sandbox = SandboxConfig.docker(image="python:3.11-slim")

# Custom sandbox configuration
custom_sandbox = SandboxConfig(
    sandbox_type="subprocess",
    working_dir="/tmp/sandbox",
    resource_limits=ResourceLimits(
        memory_mb=256,
        cpu_percent=50,
        timeout_seconds=30,
        network_enabled=False,
        max_processes=5,
    ),
    security_policy=SecurityPolicy(
        allow_network=False,
        allow_file_write=True,
        allow_subprocess=False,
        blocked_imports=["subprocess", "os.system", "eval"],
    ),
    auto_cleanup=True,
)

def demonstrate_result_handling():
    """Show how to handle sandbox results."""
    
    # Simulated successful result
    success_result = SandboxResult(
        status=SandboxStatus.COMPLETED,
        exit_code=0,
        stdout="Hello, World!\n",
        stderr="",
        duration_seconds=0.1,
    )
    
    # Simulated timeout result
    timeout_result = SandboxResult(
        status=SandboxStatus.TIMEOUT,
        exit_code=None,
        stdout="Partial output...",
        stderr="",
        error="Execution timed out after 30 seconds",
        duration_seconds=30.0,
    )
    
    # Simulated error result
    error_result = SandboxResult(
        status=SandboxStatus.FAILED,
        exit_code=1,
        stdout="",
        stderr="NameError: name 'undefined_var' is not defined",
        error="Execution failed",
    )
    
    print("Result Handling Examples:")
    print()
    
    for name, result in [
        ("Success", success_result),
        ("Timeout", timeout_result),
        ("Error", error_result)
    ]:
        print(f"{name} Result:")
        print(f"  Status: {result.status.name}")
        print(f"  Success: {result.success}")
        if result.stdout:
            print(f"  Output: {result.stdout.strip()}")
        if result.stderr:
            print(f"  Error: {result.stderr.strip()}")
        if result.error:
            print(f"  Message: {result.error}")
        print()

if __name__ == "__main__":
    print("Sandbox Configurations:")
    print()
    
    print("Minimal Sandbox (for untrusted code):")
    print(f"  Type: {minimal_sandbox.sandbox_type}")
    print(f"  Memory: {minimal_sandbox.resource_limits.memory_mb}MB")
    print(f"  Timeout: {minimal_sandbox.resource_limits.timeout_seconds}s")
    print(f"  Network: {minimal_sandbox.resource_limits.network_enabled}")
    print()
    
    print("Standard Sandbox:")
    print(f"  Type: {standard_sandbox.sandbox_type}")
    print(f"  Memory: {standard_sandbox.resource_limits.memory_mb}MB")
    print(f"  Timeout: {standard_sandbox.resource_limits.timeout_seconds}s")
    print()
    
    print("Docker Sandbox:")
    print(f"  Type: {docker_sandbox.sandbox_type}")
    print(f"  Image: {docker_sandbox.image}")
    print()
    
    print("Custom Sandbox:")
    print(f"  Type: {custom_sandbox.sandbox_type}")
    print(f"  Working Dir: {custom_sandbox.working_dir}")
    print(f"  Memory: {custom_sandbox.resource_limits.memory_mb}MB")
    print(f"  Max Processes: {custom_sandbox.resource_limits.max_processes}")
    print()
    
    demonstrate_result_handling()
    
    print("To run code in sandbox via CLI:")
    print("  praisonai sandbox run \"print('Hello, World!')\"")
    print("  praisonai sandbox run --file script.py")
    print("  praisonai sandbox shell")
