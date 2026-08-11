# Manual E2E validation guide — praisonai-sandbox

Step-by-step validation for the sandbox package. Use this when you want to
confirm each backend path by hand, or to debug a failure surfaced by
`run_e2e.py`.

## Prerequisites

- Python 3.9+
- `praisonai-sandbox` and `praisonaiagents` installed (editable installs are fine)
- Docker (optional — only needed for the Docker path)

## 1. One-command runner

```bash
cd src/praisonai-sandbox
python e2e-validation/run_e2e.py
```

Expected: a summary table with `PASS` for the required checks and `SKIP` for
Docker when the daemon is unavailable. Exit code `0`.

## 2. Subprocess path (no dependencies)

```python
import asyncio
from praisonai_sandbox import SubprocessSandbox


async def main():
    sandbox = SubprocessSandbox()
    await sandbox.start()
    try:
        result = await sandbox.execute("print('hello')")
        print(result.stdout)
    finally:
        await sandbox.stop()
        await sandbox.cleanup()


asyncio.run(main())
```

Expected stdout: `hello`.

## 3. SandboxManager path

```python
import asyncio
from praisonaiagents.sandbox import SandboxConfig, SandboxManager


async def main():
    manager = SandboxManager(SandboxConfig.subprocess())
    result = await manager.run_code("print('manager-ok')")
    print(result.stdout)


asyncio.run(main())
```

Expected stdout: `manager-ok`.

## 4. Docker path (optional)

Requires a running Docker daemon and the `python:3.11-slim` image.

```python
import asyncio
from praisonai_sandbox import DockerSandbox


async def main():
    sandbox = DockerSandbox(image="python:3.11-slim")
    await sandbox.start()
    try:
        result = await sandbox.execute("print('docker-ok')")
        print(result.stdout)
    finally:
        await sandbox.stop()
        await sandbox.cleanup()


asyncio.run(main())
```

Expected stdout: `docker-ok`. If Docker is unavailable, skip this step.

## 5. CLI smoke

```bash
python -m praisonai_sandbox backends
# or, when installed on PATH:
praisonai-sandbox backends
```

Expected: a list of backends with `available` / `unavailable` flags.

## 6. Pytest live probes

```bash
python -m pytest tests/test_live_sandbox.py -v --tb=short
```

Expected: subprocess/manager/shim tests pass; Docker/E2B/Daytona skip without
credentials or Docker.
