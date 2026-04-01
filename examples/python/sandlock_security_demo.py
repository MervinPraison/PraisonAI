"""
SandlockSandbox Security Demo

Demonstrates how to use SandlockSandbox for kernel-level code isolation.
Requires: pip install 'praisonai[sandbox]' (installs sandlock)
"""

import asyncio
from praisonaiagents.sandbox import ResourceLimits, SecurityPolicy, SandboxConfig


async def demonstrate_sandlock_security():
    """Show SandlockSandbox blocking malicious operations."""
    
    try:
        from praisonai.sandbox import SandlockSandbox
    except ImportError:
        print("❌ SandlockSandbox requires: pip install 'praisonai[sandbox]'")
        print("   Falling back to SubprocessSandbox (less secure)")
        from praisonai.sandbox import SubprocessSandbox
        sandbox = SubprocessSandbox()
    else:
        # Create sandbox with strict security policy
        config = SandboxConfig.native(
            writable_paths=["./safe_workspace"],  # Only allow writes to this dir
            network=False,  # Block all network access
        )
        sandbox = SandlockSandbox(config)
        print("✅ Using SandlockSandbox with kernel-level isolation")
    
    await sandbox.start()
    
    # Test 1: Safe code execution
    print("\n🟢 Test 1: Safe Python code")
    result = await sandbox.execute(
        "print('Hello from isolated sandbox!')", 
        limits=ResourceLimits.minimal()
    )
    print(f"Status: {result.status}")
    print(f"Output: {result.stdout}")
    
    # Test 2: Attempt file system access (should be blocked by Landlock)
    print("\n🔒 Test 2: Attempt to read sensitive files")
    result = await sandbox.execute("""
try:
    with open('/etc/passwd', 'r') as f:
        print(f.read()[:100])
except Exception as e:
    print(f'Access blocked: {e}')
    """)
    print(f"Status: {result.status}")
    print(f"Output: {result.stdout}")
    if result.stderr:
        print(f"Stderr: {result.stderr}")
    
    # Test 3: Attempt network access (should be blocked)
    print("\n🌐 Test 3: Attempt network access")
    result = await sandbox.execute("""
try:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('example.com', 80))
    print('Network connection successful')
    s.close()
except Exception as e:
    print(f'Network blocked: {e}')
    """)
    print(f"Status: {result.status}")
    print(f"Output: {result.stdout}")
    
    # Test 4: Attempt subprocess execution (blocked by seccomp)
    print("\n🚫 Test 4: Attempt subprocess execution")
    result = await sandbox.execute("""
try:
    import subprocess
    result = subprocess.run(['ls', '/'], capture_output=True, text=True)
    print(f'Command output: {result.stdout}')
except Exception as e:
    print(f'Subprocess blocked: {e}')
    """)
    print(f"Status: {result.status}")
    print(f"Output: {result.stdout}")
    
    # Test 5: Resource limits in action
    print("\n⏱️ Test 5: Resource limits (timeout)")
    result = await sandbox.execute(
        "import time; time.sleep(100)",  # Will timeout
        limits=ResourceLimits(timeout_seconds=2)
    )
    print(f"Status: {result.status}")
    print(f"Error: {result.error}")
    
    await sandbox.stop()
    
    # Show security features
    status = sandbox.get_status()
    if 'features' in status:
        print(f"\n🛡️ Security features enabled:")
        for feature, enabled in status['features'].items():
            emoji = "✅" if enabled else "❌"
            print(f"  {emoji} {feature}: {enabled}")


if __name__ == "__main__":
    print("🔒 SandlockSandbox Security Demonstration")
    print("="*50)
    
    asyncio.run(demonstrate_sandlock_security())
    
    print("\n" + "="*50)
    print("🎯 Key Security Benefits:")
    print("   • Landlock: Kernel-enforced filesystem allowlisting") 
    print("   • seccomp-bpf: System call filtering")
    print("   • Resource limits: Memory, CPU, process constraints")
    print("   • Network isolation: Block unauthorized connections")
    print("   • ~5ms overhead: Faster than Docker containers")
    print("   • No root required: User-space security")