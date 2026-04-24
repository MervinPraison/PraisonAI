"""Agent runtime with tools sandboxed on Fly.io Machines.

The agent's LLM loop runs locally; tool / code execution runs in a Fly.io
Machine (fast-booting micro-VM with per-second billing and global regions).

Requires:
  - ``OPENAI_API_KEY`` for the LLM
  - ``FLY_API_TOKEN``  for the Fly.io Machines API
  - ``FLY_APP_NAME``   (optional) existing Fly app; auto-created otherwise
"""
import asyncio
import os

if not os.getenv("OPENAI_API_KEY"):
    print("[skip] OPENAI_API_KEY not set.")
    raise SystemExit(0)
if not os.getenv("FLY_API_TOKEN"):
    print("[skip] FLY_API_TOKEN not set — get one via `fly auth token`.")
    raise SystemExit(0)

try:
    from praisonai import Agent
    from praisonai.integrations import SandboxedAgent, SandboxedAgentConfig
except ImportError as e:
    print(f"[skip] praisonai wrapper not importable ({e}).")
    raise SystemExit(0) from None


async def main():
    sandboxed = SandboxedAgent(
        compute="flyio",  # tool execution runs on Fly.io Machines
        config=SandboxedAgentConfig(
            model="gpt-4o-mini",
            system="You are a concise coding assistant.",
            name="FlyioRuntimeAgent",
        ),
    )
    agent = Agent(name="fly-runtime", backend=sandboxed)

    info = await sandboxed.provision_compute(
        image="python:3.12-slim",
        cpu=1,
        memory_mb=512,
        idle_timeout_s=120,
    )
    print(f"[1] Fly Machine: {info.instance_id} ({info.status})")

    result = await sandboxed.execute_in_compute("python3 -c 'print(2 ** 20)'")
    print(f"[2] Cloud compute result: {result['stdout'].strip()}")

    print("[3] Agent:", agent.start("What is 2 raised to the 20th power? Just the number."))

    await sandboxed.shutdown_compute()
    print("[4] Fly Machine shut down.")


asyncio.run(main())
