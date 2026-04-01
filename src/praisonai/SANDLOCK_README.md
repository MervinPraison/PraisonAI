# SandlockSandbox: Kernel-Level Code Isolation

SandlockSandbox provides the highest security level available for code execution on Linux systems, using kernel-level isolation via **Landlock** and **seccomp-bpf**.

## 🔒 Security Features

### Current Issues with Subprocess Sandbox
- ❌ Can read arbitrary files (`/etc/passwd`, SSH keys, `.aws` credentials)
- ❌ Can make network connections (data exfiltration)  
- ❌ Can import dangerous Python modules (`os.system`, `subprocess`)
- ❌ Can access `/proc`, `/sys` kernel interfaces
- ❌ Only process-level isolation

### SandlockSandbox Solutions  
- ✅ **Landlock**: Kernel-enforced filesystem allowlisting
- ✅ **seccomp-bpf**: System call filtering at kernel level
- ✅ **Network isolation**: Block unauthorized connections
- ✅ **Resource limits**: Memory, CPU, process, file descriptor limits
- ✅ **~5ms overhead**: Faster than Docker containers
- ✅ **No root required**: User-space security

## 🚀 Installation

```bash
# Install with sandbox support
pip install "praisonai[sandbox]"

# Or install sandlock directly
pip install sandlock
```

## 📖 Usage

### Basic Usage

```python
import asyncio
from praisonai.sandbox import SandlockSandbox
from praisonaiagents.sandbox import ResourceLimits

async def main():
    # Create sandbox with strict security
    sandbox = SandlockSandbox()
    await sandbox.start()
    
    # Execute code with kernel-level isolation
    result = await sandbox.execute(
        "print('Hello from secure sandbox!')",
        limits=ResourceLimits.minimal()  # Strict limits for untrusted code
    )
    
    print(f"Output: {result.stdout}")
    print(f"Secure: {result.metadata['landlock_enabled']}")
    
    await sandbox.stop()

asyncio.run(main())
```

### Advanced Configuration

```python
from praisonaiagents.sandbox import SandboxConfig
from praisonai.sandbox import SandlockSandbox

# Create native sandbox with specific allowed paths
config = SandboxConfig.native(
    writable_paths=["./workspace", "./output"],
    network=False,  # Block all network access
)

sandbox = SandlockSandbox(config)
```

### Resource Limits

```python
from praisonaiagents.sandbox import ResourceLimits

# Minimal limits for untrusted code
limits = ResourceLimits.minimal()  # 128MB, 5 processes, 30s timeout

# Standard limits
limits = ResourceLimits.standard()  # 512MB, 10 processes, 60s timeout

# Custom limits
limits = ResourceLimits(
    memory_mb=256,
    max_processes=3,
    timeout_seconds=15,
    network_enabled=False,
)
```

## 🛡️ Security Guarantees

### Filesystem Isolation (Landlock)
```python
# ✅ Allowed: Read Python libraries
# ✅ Allowed: Write to workspace directory  
# ❌ Blocked: Read /etc/passwd, ~/.ssh, ~/.aws
# ❌ Blocked: Write to system directories

await sandbox.execute("""
# This will be blocked at kernel level
with open('/etc/passwd', 'r') as f:
    print(f.read())
""")
```

### Network Isolation
```python
# ❌ Blocked: All network connections when network=False
await sandbox.execute("""
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(('evil.com', 80))  # Blocked by kernel
""")
```

### System Call Filtering (seccomp-bpf)
```python
# ❌ Blocked: Dangerous system calls
await sandbox.execute("""
import subprocess
subprocess.run(['rm', '-rf', '/'])  # Blocked by seccomp
""")
```

## 🔄 Integration with Existing Code

SandlockSandbox implements the same `SandboxProtocol` as other sandbox types, making it a drop-in replacement:

```python
from praisonai.sandbox import SubprocessSandbox, SandlockSandbox

# Easy migration - same API
# old_sandbox = SubprocessSandbox()
new_sandbox = SandlockSandbox()  # Much more secure!

# All methods work the same
result = await new_sandbox.execute("print('hello')")
result = await new_sandbox.run_command(["python", "--version"])
await new_sandbox.write_file("test.txt", "content")
content = await new_sandbox.read_file("test.txt")
```

## 🎯 Use Cases

### 1. Agent Code Execution
```python
from praisonaiagents import Agent
from praisonai.sandbox import SandlockSandbox

# Secure agent that can execute user/LLM-generated code
agent = Agent(
    name="code_agent",
    instructions="Execute code securely",
    execution=ExecutionConfig(
        code_execution=True,
        sandbox=SandlockSandbox(),  # Kernel-level isolation
    )
)
```

### 2. Untrusted Code Evaluation
```python
async def evaluate_untrusted_code(user_code: str):
    sandbox = SandlockSandbox()
    await sandbox.start()
    
    # User code cannot escape sandbox
    result = await sandbox.execute(
        user_code,
        limits=ResourceLimits.minimal(),  # Strict limits
    )
    
    return result.success, result.output
```

### 3. Multi-Tenant Code Runner
```python
async def run_tenant_code(tenant_id: str, code: str):
    # Each tenant gets isolated workspace
    config = SandboxConfig.native(
        writable_paths=[f"./tenants/{tenant_id}"],
        network=False,
    )
    
    sandbox = SandlockSandbox(config)
    return await sandbox.execute(code)
```

## ⚡ Performance

| Feature | SubprocessSandbox | SandlockSandbox | Docker |
|---------|------------------|-----------------|--------|
| Startup | ~1ms | ~5ms | ~100ms |
| Security | ⚠️ Process-only | ✅ Kernel-level | ✅ Kernel-level |
| Root Required | ❌ No | ❌ No | ✅ Yes (usually) |
| Dependencies | None | sandlock | Docker daemon |

## 🐛 Troubleshooting

### ImportError: No module named 'sandlock'
```bash
pip install "praisonai[sandbox]"
# or
pip install sandlock
```

### Landlock not supported
```python
from praisonai.sandbox import SandlockSandbox

sandbox = SandlockSandbox()
if not sandbox.is_available:
    print("Landlock not supported - using fallback")
    # Automatically falls back to SubprocessSandbox
```

### Permission denied errors
```python
# Make sure writable paths exist and are accessible
config = SandboxConfig.native(
    writable_paths=["/absolute/path/to/workspace"],  # Must be absolute
    network=False,
)
```

## 🏗️ Architecture

SandlockSandbox follows PraisonAI's protocol-driven design:

- **Core SDK** (`praisonaiagents`): Contains only `SandboxProtocol`
- **Wrapper** (`praisonai`): Contains `SandlockSandbox` implementation
- **Optional dependency**: `sandlock` is lazy-loaded, won't slow imports

This maintains the clean separation between lightweight protocols and heavy implementations.

## 🤝 Contributing

The SandlockSandbox implementation lives in:
- Implementation: `src/praisonai/praisonai/sandbox/sandlock.py`
- Tests: `src/praisonai/tests/unit/sandbox/test_sandlock_sandbox.py`  
- Protocol: `src/praisonai-agents/praisonaiagents/sandbox/protocols.py`

When contributing:
1. Follow the existing `SandboxProtocol` interface
2. Add comprehensive tests for security features
3. Ensure graceful fallback when sandlock unavailable
4. Update documentation with new capabilities