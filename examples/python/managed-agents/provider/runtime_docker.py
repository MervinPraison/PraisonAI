"""Agent runtime with tools sandboxed in a local Docker container.

The agent's LLM loop runs locally; tool / code execution is isolated in a
Docker container. Not a cloud provider, but the same pattern — useful for
local development and CI.

Requires:
  - ``OPENAI_API_KEY`` for the LLM
  - Docker daemon running (``docker info`` must succeed)
"""
import asyncio
import os
import subprocess

if not os.getenv("OPENAI_API_KEY"):
    print("[skip] OPENAI_API_KEY not set.")
    raise SystemExit(0)

try:
    subprocess.run(
        ["docker", "info"],
        check=True, capture_output=True, timeout=5,
    )
except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
    print("[skip] Docker daemon not available — start Docker Desktop.")
    raise SystemExit(0) from None

try:
    from praisonai import Agent
    from praisonai.integrations import SandboxedAgent, SandboxedAgentConfig
except ImportError as e:
    print(f"[skip] praisonai wrapper not importable ({e}).")
    raise SystemExit(0) from None


async def main():
    sandboxed = SandboxedAgent(
        compute="docker",  # tool execution runs in a local Docker container
        config=SandboxedAgentConfig(
            model="gpt-4o-mini",
            system="You are a concise coding assistant.",
            name="DockerRuntimeAgent",
        ),
    )
    agent = Agent(name="docker-runtime", backend=sandboxed)

    info = await sandboxed.provision_compute(image="python:3.12-slim")
    print(f"[1] Docker container: {info.instance_id} ({info.status})")

    result = await sandboxed.execute_in_compute("python3 -c 'print(sum(i*i for i in range(1, 11)))'")
    print(f"[2] Container compute result: {result['stdout'].strip()}")

    print("[3] Agent:", agent.start("What is the sum of squares from 1 to 10? Just the number."))

    await sandboxed.shutdown_compute()
    print("[4] Docker container shut down.")


asyncio.run(main())
