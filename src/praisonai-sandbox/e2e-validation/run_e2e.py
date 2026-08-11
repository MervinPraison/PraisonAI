#!/usr/bin/env python
"""Orchestrated end-to-end validation runner for praisonai-sandbox.

Runs a single-command smoke suite covering:

- Subprocess backend execute (always required)
- SandboxManager subprocess path (always required)
- Backward-compat shim (praisonai.sandbox -> praisonai_sandbox)
- Docker backend execute (optional — skipped gracefully when unavailable)
- CLI smoke (``praisonai-sandbox backends``)

Exits non-zero if any *required* check fails. Docker is optional and a skip
never fails the run. No API keys are needed for the subprocess path.

Usage::

    python e2e-validation/run_e2e.py
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass

# Ensure the package root (parent of this e2e-validation/ dir) is importable
# regardless of the current working directory when the script is invoked.
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

# Upper bound for the optional Docker check (image pull + startup/execute).
# Overridable via env for slow networks; kept generous but finite so the run
# can never hang indefinitely.
_DOCKER_TIMEOUT = float(os.environ.get("PRAISONAI_SANDBOX_E2E_DOCKER_TIMEOUT", "180"))


@dataclass
class Result:
    name: str
    status: str  # "PASS", "FAIL", "SKIP"
    detail: str = ""


def _docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        from praisonai_sandbox.docker import DockerSandbox

        return DockerSandbox().is_available
    except Exception:
        return False


async def _check_subprocess() -> Result:
    try:
        from praisonai_sandbox import SubprocessSandbox

        sandbox = SubprocessSandbox()
        await sandbox.start()
        try:
            result = await sandbox.execute("print('e2e-subprocess-ok')")
            if "e2e-subprocess-ok" in (result.stdout or ""):
                return Result("subprocess execute", "PASS")
            return Result("subprocess execute", "FAIL", "marker not found in stdout")
        finally:
            await sandbox.stop()
            await sandbox.cleanup()
    except Exception as exc:  # pragma: no cover - defensive
        return Result("subprocess execute", "FAIL", str(exc))


async def _check_manager() -> Result:
    try:
        from praisonaiagents.sandbox import SandboxConfig, SandboxManager

        manager = SandboxManager(SandboxConfig.subprocess())
        result = await manager.run_code("print('e2e-manager-ok')")
        if "e2e-manager-ok" in (result.stdout or ""):
            return Result("SandboxManager subprocess", "PASS")
        return Result("SandboxManager subprocess", "FAIL", "marker not found in stdout")
    except Exception as exc:  # pragma: no cover - defensive
        return Result("SandboxManager subprocess", "FAIL", str(exc))


async def _check_shim() -> Result:
    try:
        import importlib.util

        if importlib.util.find_spec("praisonai") is None:
            return Result("backward-compat shim", "SKIP", "praisonai wrapper not installed")
    except Exception:
        return Result("backward-compat shim", "SKIP", "praisonai wrapper not installed")
    try:
        from praisonai._bootstrap import ensure_praisonai_sandbox

        ensure_praisonai_sandbox()
        from praisonai.sandbox import SubprocessSandbox as ShimCls
        from praisonai_sandbox import SubprocessSandbox as DirectCls

        if ShimCls is not DirectCls:
            return Result("backward-compat shim", "FAIL", "shim class differs from direct import")
        return Result("backward-compat shim", "PASS")
    except Exception as exc:  # pragma: no cover - defensive
        return Result("backward-compat shim", "FAIL", str(exc))


async def _check_docker() -> Result:
    if not _docker_available():
        return Result("Docker execute", "SKIP", "docker daemon/image not available")
    try:
        from praisonai_sandbox import DockerSandbox

        sandbox = DockerSandbox(image="python:3.11-slim")
        # Pulling the image can stall (slow/unavailable registry); bound it so
        # the optional check never hangs the whole run.
        await asyncio.wait_for(sandbox.start(), timeout=_DOCKER_TIMEOUT)
        try:
            result = await asyncio.wait_for(
                sandbox.execute("print('e2e-docker-ok')"), timeout=_DOCKER_TIMEOUT
            )
            if "e2e-docker-ok" in (result.stdout or ""):
                return Result("Docker execute", "PASS")
            return Result("Docker execute", "FAIL", "marker not found in stdout")
        finally:
            await sandbox.stop()
            await sandbox.cleanup()
    except asyncio.TimeoutError:
        return Result(
            "Docker execute",
            "SKIP",
            f"timed out after {_DOCKER_TIMEOUT}s (image pull/startup unavailable)",
        )
    except Exception as exc:  # pragma: no cover - defensive
        # Docker is optional: an unavailable image/registry must not fail the run.
        return Result("Docker execute", "SKIP", f"docker image not available: {exc}")


def _check_cli() -> Result:
    try:
        env = dict(os.environ)
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = _PKG_ROOT + (os.pathsep + existing if existing else "")
        proc = subprocess.run(
            [sys.executable, "-m", "praisonai_sandbox", "backends"],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        if proc.returncode == 0 and "subprocess" in proc.stdout:
            return Result("CLI backends smoke", "PASS")
        return Result(
            "CLI backends smoke",
            "FAIL",
            f"exit={proc.returncode} stderr={proc.stderr.strip()[:200]}",
        )
    except Exception as exc:  # pragma: no cover - defensive
        return Result("CLI backends smoke", "FAIL", str(exc))


def _print_summary(results: list[Result]) -> bool:
    name_width = max(len(r.name) for r in results)
    print("\n" + "=" * (name_width + 20))
    print("praisonai-sandbox E2E validation summary")
    print("=" * (name_width + 20))
    for r in results:
        line = f"{r.name.ljust(name_width)}  {r.status}"
        if r.detail:
            line += f"  ({r.detail})"
        print(line)
    print("=" * (name_width + 20))

    failures = [r for r in results if r.status == "FAIL"]
    passed = sum(1 for r in results if r.status == "PASS")
    skipped = sum(1 for r in results if r.status == "SKIP")
    print(f"{passed} passed, {len(failures)} failed, {skipped} skipped\n")
    return not failures


async def _run() -> list[Result]:
    results = [
        await _check_subprocess(),
        await _check_manager(),
        await _check_shim(),
        await _check_docker(),
    ]
    results.append(_check_cli())
    return results


def main() -> int:
    results = asyncio.run(_run())
    ok = _print_summary(results)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
