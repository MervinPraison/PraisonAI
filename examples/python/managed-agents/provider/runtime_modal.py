"""Agent runtime with tools sandboxed in Modal cloud functions.

The agent's LLM loop runs locally; tool / code execution is sandboxed in
Modal's serverless cloud. Modal gives fast cold-starts and per-second billing.

Requires:
  - ``OPENAI_API_KEY`` for the LLM
  - Modal CLI configured: ``modal token set --token-id ... --token-secret ...``
  - ``pip install modal``
"""
import asyncio
import os

if not os.getenv("OPENAI_API_KEY"):
    print("[skip] OPENAI_API_KEY not set.")
    raise SystemExit(0)

try:
    import modal  # noqa: F401
except ImportError:
    print("[skip] 'modal' package not installed — pip install modal")
    raise SystemExit(0) from None

# Modal auth: presence of ~/.modal.toml or MODAL_TOKEN_ID + MODAL_TOKEN_SECRET
if not (os.path.exists(os.path.expanduser("~/.modal.toml"))
        or (os.getenv("MODAL_TOKEN_ID") and os.getenv("MODAL_TOKEN_SECRET"))):
    print("[skip] Modal not configured — run `modal token set ...`")
    raise SystemExit(0)

try:
    from praisonai import Agent
    from praisonai.integrations import SandboxedAgent, SandboxedAgentConfig
except ImportError as e:
    print(f"[skip] praisonai wrapper not importable ({e}).")
    raise SystemExit(0) from None


async def main():
    sandboxed = SandboxedAgent(
        compute="modal",  # tool execution runs in Modal's cloud
        config=SandboxedAgentConfig(
            model="gpt-4o-mini",
            system="You are a concise coding assistant.",
            name="ModalRuntimeAgent",
        ),
    )
    agent = Agent(name="modal-runtime", backend=sandboxed)

    info = await sandboxed.provision_compute(idle_timeout_s=120)
    print(f"[1] Modal instance: {info.instance_id} ({info.status})")

    result = await sandboxed.execute_in_compute("python3 -c 'import math; print(math.factorial(10))'")
    print(f"[2] Cloud compute result: {result['stdout'].strip()}")

    print("[3] Agent:", agent.start("What is the 10th Fibonacci number? Just the number."))

    await sandboxed.shutdown_compute()
    print("[4] Modal instance shut down.")


asyncio.run(main())
