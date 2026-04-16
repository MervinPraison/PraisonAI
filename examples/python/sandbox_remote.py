#!/usr/bin/env python3
"""
Remote Sandbox Examples for PraisonAI

Demonstrates how to use SSH, Modal, and Daytona sandbox backends
for remote code execution.
"""

import asyncio
import os
from typing import Optional

from praisonai.sandbox import SSHSandbox, ModalSandbox, DaytonaSandbox
from praisonaiagents.sandbox import ResourceLimits


async def ssh_example():
    """Example using SSH sandbox for remote execution."""
    print("🔗 SSH Sandbox Example")
    print("=" * 50)
    
    # Configure SSH connection
    # Note: You need actual SSH server access for this to work
    ssh_host = os.getenv("SSH_HOST", "localhost")
    ssh_user = os.getenv("SSH_USER", "ubuntu")
    ssh_key = os.getenv("SSH_KEY_FILE", "~/.ssh/id_rsa")
    
    print(f"Connecting to {ssh_user}@{ssh_host}")
    
    try:
        sandbox = SSHSandbox(
            host=ssh_host,
            user=ssh_user,
            key_file=ssh_key,
            working_dir="/tmp/praisonai_demo"
        )
        
        # Check availability
        if not sandbox.is_available:
            print("❌ SSH backend not available. Install with: pip install praisonai[ssh]")
            return
        
        # Start sandbox
        await sandbox.start()
        print("✅ SSH connection established")
        
        # Execute Python code
        print("\n📄 Executing Python code...")
        result = await sandbox.execute("""
import sys
import platform
print(f"Python version: {sys.version}")
print(f"Platform: {platform.platform()}")
print("Hello from remote SSH server! 🚀")
        """, language="python")
        
        print(f"Exit code: {result.exit_code}")
        print(f"Output:\n{result.stdout}")
        if result.stderr:
            print(f"Errors:\n{result.stderr}")
        
        # Execute shell command
        print("\n🐚 Executing shell command...")
        result = await sandbox.run_command("uname -a && uptime")
        print(f"System info:\n{result.stdout}")
        
        # Write and read file
        print("\n📝 File operations...")
        await sandbox.write_file("/tmp/praisonai_demo/hello.py", "print('Hello from file!')")
        content = await sandbox.read_file("/tmp/praisonai_demo/hello.py")
        print(f"File content: {content}")
        
        # Execute the file
        result = await sandbox.execute_file("/tmp/praisonai_demo/hello.py")
        print(f"File execution result: {result.stdout}")
        
        # Test resource limits
        print("\n⏱️ Testing resource limits...")
        limits = ResourceLimits(timeout_seconds=5, memory_mb=128)
        result = await sandbox.execute("""
import time
print("Starting long task...")
time.sleep(10)  # This will timeout
print("Task completed")
        """, limits=limits)
        
        print(f"Limited execution status: {result.status}")
        if result.error:
            print(f"Error (expected timeout): {result.error}")
        
        await sandbox.stop()
        print("✅ SSH sandbox stopped")
        
    except Exception as e:
        print(f"❌ SSH example failed: {e}")


async def modal_example():
    """Example using Modal sandbox for serverless GPU execution."""
    print("\n☁️ Modal Sandbox Example")
    print("=" * 50)
    
    try:
        # Note: Requires Modal account and API key
        sandbox = ModalSandbox(
            gpu="A100",  # Request A100 GPU
            timeout=120
        )
        
        # Check availability
        if not sandbox.is_available:
            print("❌ Modal backend not available. Install with: pip install praisonai[modal]")
            return
        
        print("🚀 Starting Modal app...")
        await sandbox.start()
        print("✅ Modal app initialized")
        
        # Execute GPU-accelerated Python code
        print("\n🔥 Executing GPU code...")
        result = await sandbox.execute("""
import torch
import numpy as np

print(f"PyTorch version: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")

if torch.cuda.is_available():
    device = torch.cuda.get_device_name()
    print(f"GPU device: {device}")
    
    # Simple tensor operations on GPU
    x = torch.randn(1000, 1000, device='cuda')
    y = torch.randn(1000, 1000, device='cuda')
    z = torch.matmul(x, y)
    print(f"GPU computation result shape: {z.shape}")
else:
    print("Running on CPU")
    x = torch.randn(100, 100)
    y = torch.randn(100, 100)
    z = torch.matmul(x, y)
    print(f"CPU computation result shape: {z.shape}")

print("🚀 Modal execution completed!")
        """, language="python")
        
        print(f"Exit code: {result.exit_code}")
        print(f"Output:\n{result.stdout}")
        if result.stderr:
            print(f"Errors:\n{result.stderr}")
        
        # Test different languages
        print("\n🐚 Testing bash execution...")
        result = await sandbox.run_command("nvidia-smi || echo 'No GPU info available'")
        print(f"GPU info:\n{result.stdout}")
        
        await sandbox.stop()
        print("✅ Modal sandbox stopped")
        
    except Exception as e:
        print(f"❌ Modal example failed: {e}")


async def daytona_example():
    """Example using Daytona sandbox for cloud dev environment."""
    print("\n🌤️ Daytona Sandbox Example")
    print("=" * 50)
    
    try:
        # Configure Daytona workspace
        sandbox = DaytonaSandbox(
            workspace_template="python-dev",
            provider="aws",  # or "gcp", "azure", "local"
            timeout=180
        )
        
        # Check availability
        if not sandbox.is_available:
            print("❌ Daytona backend not available. Install with: pip install praisonai[daytona]")
            return
        
        print(f"🏗️ Creating Daytona workspace: {sandbox.workspace_name}")
        await sandbox.start()
        print("✅ Daytona workspace ready")
        
        # Execute development tasks
        print("\n💻 Running development tasks...")
        result = await sandbox.execute("""
import sys
import os
import subprocess

print("🐍 Python Development Environment")
print(f"Python version: {sys.version}")
print(f"Working directory: {os.getcwd()}")

# Check installed packages
try:
    result = subprocess.run([sys.executable, "-m", "pip", "list"], 
                          capture_output=True, text=True)
    print("📦 Installed packages:")
    print(result.stdout[:500] + "..." if len(result.stdout) > 500 else result.stdout)
except Exception as e:
    print(f"Could not list packages: {e}")

print("✨ Daytona workspace is ready for development!")
        """, language="python")
        
        print(f"Exit code: {result.exit_code}")
        print(f"Output:\n{result.stdout}")
        
        # Test file operations
        print("\n📁 Workspace file operations...")
        await sandbox.write_file("/workspace/demo.py", """
def hello_daytona():
    print("Hello from Daytona workspace!")
    return "🎉 Success!"

if __name__ == "__main__":
    result = hello_daytona()
    print(result)
""")
        
        # Execute the file
        result = await sandbox.execute_file("/workspace/demo.py")
        print(f"Demo script output: {result.stdout}")
        
        # List workspace files
        files = await sandbox.list_files("/workspace")
        print(f"Workspace files: {files}")
        
        await sandbox.stop()
        print("✅ Daytona workspace stopped")
        
    except Exception as e:
        print(f"❌ Daytona example failed: {e}")


async def comparison_example():
    """Compare execution across different sandbox backends."""
    print("\n⚖️ Sandbox Comparison")
    print("=" * 50)
    
    # Simple test code
    test_code = """
import time
import sys
start_time = time.time()
print(f"Hello from {sys.platform}!")
print(f"Execution time: {time.time() - start_time:.3f}s")
"""
    
    # Test each sandbox type
    sandboxes = [
        ("SSH", SSHSandbox(host=os.getenv("SSH_HOST", "localhost"))),
        ("Modal", ModalSandbox()),
        ("Daytona", DaytonaSandbox())
    ]
    
    for name, sandbox in sandboxes:
        print(f"\n🧪 Testing {name} sandbox...")
        
        if not sandbox.is_available:
            print(f"❌ {name} not available")
            continue
        
        try:
            await sandbox.start()
            result = await sandbox.execute(test_code, language="python")
            
            print(f"✅ {name}: {result.status}")
            print(f"   Duration: {result.duration_seconds:.3f}s")
            print(f"   Output: {result.stdout.strip()}")
            
            await sandbox.stop()
            
        except Exception as e:
            print(f"❌ {name} failed: {e}")


async def main():
    """Run all examples."""
    print("🚀 PraisonAI Remote Sandbox Examples")
    print("=" * 70)
    
    # Run examples
    await ssh_example()
    await modal_example()
    await daytona_example()
    await comparison_example()
    
    print("\n✅ All examples completed!")
    print("\nNext steps:")
    print("1. Set up SSH access to remote servers")
    print("2. Configure Modal account for GPU workloads")
    print("3. Set up Daytona for cloud development")
    print("4. Use these sandboxes in your PraisonAI agents!")


if __name__ == "__main__":
    asyncio.run(main())