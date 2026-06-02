"""Agent runtime with tools sandboxed in an E2B cloud VM.

The agent's LLM loop runs locally; any tool / code execution is sandboxed
in an ephemeral E2B cloud instance. Uses ``SandboxedAgent`` — the honest
name for the "local loop + cloud tools" pattern.

Requires:
  - ``OPENAI_API_KEY`` for the LLM
  - ``E2B_API_KEY``    for the cloud sandbox
  - ``pip install e2b``
"""
import asyncio
import os

if not os.getenv("OPENAI_API_KEY"):
    print("[skip] OPENAI_API_KEY not set.")
    raise SystemExit(0)
if not os.getenv("E2B_API_KEY"):
    print("[skip] E2B_API_KEY not set — set it to run in the E2B cloud sandbox.")
    raise SystemExit(0)

try:
    from praisonai import Agent
    from praisonai.integrations import SandboxedAgent, SandboxedAgentConfig
except ImportError as e:
    print(f"[skip] praisonai wrapper not importable ({e}).")
    raise SystemExit(0) from None


async def main():
    sandboxed = SandboxedAgent(
        compute="e2b",  # tool execution runs in E2B cloud
        config=SandboxedAgentConfig(
            model="gpt-4o-mini",
            system="You are a concise coding assistant.",
            name="E2BRuntimeAgent",
        ),
    )
    agent = Agent(name="e2b-runtime", backend=sandboxed)

    # 1. Provision the cloud sandbox
    info = await sandboxed.provision_compute(idle_timeout_s=120)
    print(f"[1] E2B sandbox: {info.instance_id} ({info.status})")

    # 2. Execute code IN the cloud sandbox
    result = await sandboxed.execute_in_compute("python3 -c 'print(sum(range(1, 11)))'")
    print(f"[2] Cloud compute result: {result['stdout'].strip()}")

    # 3. Agent loop (LLM local, any tool calls auto-sandboxed in E2B)
    print("[3] Agent:", agent.start("What is 13 * 17? Just the number."))

    await sandboxed.shutdown_compute()
    print("[4] E2B sandbox shut down.")


asyncio.run(main())
