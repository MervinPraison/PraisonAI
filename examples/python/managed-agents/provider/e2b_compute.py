"""E2B compute provider — run agent tools inside an E2B cloud sandbox.

Requires: E2B_API_KEY environment variable set.
Install:  pip install e2b
"""
import asyncio
from praisonai import Agent, ManagedAgent, LocalManagedConfig

# ── 1. Create agent with E2B compute ──
managed = ManagedAgent(
    provider="local",
    compute="e2b",
    config=LocalManagedConfig(
        model="gpt-4o-mini",
        system="You are a helpful coding assistant. Be concise.",
        name="E2BAgent",
    ),
)

agent = Agent(name="e2b-agent", backend=managed)

print("[1] Agent created with E2B compute")
print(f"    Compute: {managed.compute_provider.provider_name}")

# ── 2. Provision E2B sandbox ──
print("\n[2] Provisioning E2B sandbox...")
info = asyncio.run(managed.provision_compute(idle_timeout_s=120))
print(f"    Instance: {info.instance_id}")
print(f"    Status:   {info.status}")

# ── 3. Execute commands in the sandbox ──
print("\n[3] Executing commands in E2B...")
result = asyncio.run(managed.execute_in_compute("python3 -c 'import sys; print(sys.version)'"))
print(f"    Python version: {result['stdout'].strip()}")
print(f"    Exit code: {result['exit_code']}")

result = asyncio.run(managed.execute_in_compute("echo 'Hello from E2B!'"))
print(f"    Echo: {result['stdout'].strip()}")

# ── 4. Run a Python script ──
print("\n[4] Running Python script...")
result = asyncio.run(managed.execute_in_compute(
    "python3 -c 'for i in range(5): print(f\"Line {i}\")'"
))
print(f"    Output:\n{result['stdout']}")

# ── 5. Agent LLM execution ──
print("[5] Agent LLM execution...")
result = agent.start("What is the square root of 144? Just the number.", stream=True)
print(f"    Result: {result}")

# ── 6. Multi-turn ──
print("\n[6] Multi-turn...")
result = agent.start("Now cube that number.", stream=True)
print(f"    Result: {result}")

# ── 7. Usage ──
info = managed.retrieve_session()
print(f"\n[7] Usage: in={info['usage']['input_tokens']}, out={info['usage']['output_tokens']}")

# ── 8. Shutdown ──
print("\n[8] Shutting down E2B sandbox...")
asyncio.run(managed.shutdown_compute())
print("    Shutdown complete.")

print("\nDone!")
