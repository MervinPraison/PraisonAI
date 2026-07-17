# praisonai-sandbox

Isolated agent code execution for PraisonAI — Docker, subprocess, E2B, Modal, Sandlock, and SSH backends.

## Install

```bash
pip install praisonai-sandbox[docker]
```

## Usage

```python
from praisonai_sandbox import DockerSandbox
from praisonaiagents.sandbox import SandboxConfig

config = SandboxConfig.docker("python:3.11-slim")
sandbox = DockerSandbox(image=config.image, config=config)
```

Or via the agents manager:

```python
from praisonaiagents.sandbox import SandboxManager, SandboxConfig

manager = SandboxManager(SandboxConfig.subprocess())
result = await manager.run_code("print('hello')")
```

## Console script

```bash
praisonai-sandbox --help
```

Backward-compatible imports via the umbrella package:

```python
from praisonai.sandbox import SubprocessSandbox  # shim → praisonai_sandbox
```
