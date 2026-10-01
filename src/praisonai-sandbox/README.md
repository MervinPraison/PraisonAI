# praisonai-sandbox

Isolated agent code execution for PraisonAI — Docker, subprocess, E2B, Modal, Novita, Sandlock, and SSH backends.

## Install

```bash
pip install praisonai-sandbox[docker]
```

## Usage

```python
from praisonai_sandbox import DockerSandbox
from praisonaiagents.sandbox import SandboxConfig

config = SandboxConfig.docker("python:3.12-slim")
sandbox = DockerSandbox(image=config.image, config=config)
```

Or via the agents manager:

```python
from praisonaiagents.sandbox import SandboxManager, SandboxConfig

manager = SandboxManager(SandboxConfig.subprocess())
result = await manager.run_code("print('hello')")
```

## Tenki compute lifecycle

Install `praisonai-sandbox[tenki]` to use `TenkiCompute` with Tenki SDK 1.4.0 or
newer. With `ComputeConfig(auto_shutdown=True)`, the provider terminates the
sandbox after `idle_timeout_s` without an active command, package installation,
or file transfer. Activity restarts the idle countdown; status checks do not.

Idle cleanup runs while the Python process is alive and does not track background
processes after their launching command returns. Always call `shutdown()` in a
`finally` block (or use the framework's managed cleanup). Tenki's server-side
maximum lifetime is a separate safeguard and is not an idle timeout.

Timed-out commands return exit code `124` and preserve any partial output.

## Console script

```bash
praisonai-sandbox --help
```

Backward-compatible imports via the umbrella package:

```python
from praisonai.sandbox import SubprocessSandbox  # shim → praisonai_sandbox
```

## Validating your install

> **Note:** The `e2e-validation/` bundle and `tests/` ship with the source
> repository, not the published wheel. Run these commands from a checkout of
> this repo (`src/praisonai-sandbox/`), not from a `pip install`ed environment.

Run the single-command end-to-end smoke suite (no API keys needed for the
subprocess path; Docker is optional and skipped when unavailable):

```bash
python e2e-validation/run_e2e.py
```

Or use the pytest live probes:

```bash
python -m pytest tests/test_live_sandbox.py -v
```

See [`e2e-validation/`](./e2e-validation/) for the manual guide.
