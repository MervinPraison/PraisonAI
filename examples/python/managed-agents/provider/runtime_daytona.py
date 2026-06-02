"""Agent runtime with tools sandboxed in a Daytona cloud workspace.

The agent's LLM loop runs locally; tool / code execution runs in a Daytona-
managed workspace (disposable cloud dev environment, pre-configured images).

Requires:
  - ``OPENAI_API_KEY`` for the LLM
  - ``DAYTONA_API_KEY`` for the Daytona API
  - ``pip install daytona-sdk``
"""
import asyncio
import os

if not os.getenv("OPENAI_API_KEY"):
    print("[skip] OPENAI_API_KEY not set.")
    raise SystemExit(0)
if not os.getenv("DAYTONA_API_KEY"):
    print("[skip] DAYTONA_API_KEY not set.")
    raise SystemExit(0)

try:
    from praisonai import Agent
    from praisonai.integrations import SandboxedAgent, SandboxedAgentConfig
except ImportError as e:
    print(f"[skip] praisonai wrapper not importable ({e}).")
    raise SystemExit(0) from None


async def main():
    sandboxed = SandboxedAgent(
        compute="daytona",  # tool execution runs in a Daytona workspace
        config=SandboxedAgentConfig(
            model="gpt-4o-mini",
            system="You are a concise coding assistant.",
            name="DaytonaRuntimeAgent",
        ),
    )
    agent = Agent(name="daytona-runtime", backend=sandboxed)

    info = await sandboxed.provision_compute(idle_timeout_s=120)
    print(f"[1] Daytona workspace: {info.instance_id} ({info.status})")

    result = await sandboxed.execute_in_compute("python3 -c 'print(len([1,2,3,4,5]) ** 3)'")
    print(f"[2] Cloud compute result: {result['stdout'].strip()}")

    print("[3] Agent:", agent.start("What is 5 cubed? Just the number."))

    await sandboxed.shutdown_compute()
    print("[4] Daytona workspace shut down.")


asyncio.run(main())
