"""Daytona compute provider — run agent tools inside a Daytona cloud sandbox.

Requires: DAYTONA_API_KEY environment variable set.
          Organization must have a default region configured in Daytona Dashboard.
Install:  pip install daytona-sdk
"""
import asyncio
from praisonai import Agent, ManagedAgent, LocalManagedConfig

# ── 1. Create agent with Daytona compute ──
managed = ManagedAgent(
    provider="local",
    compute="daytona",
    config=LocalManagedConfig(
        model="gpt-4o-mini",
        system="You are a helpful coding assistant. Be concise.",
        name="DaytonaAgent",
    ),
)

agent = Agent(name="daytona-agent", backend=managed)

print("[1] Agent created with Daytona compute")
print(f"    Compute: {managed.compute_provider.provider_name}")

# ── 2. Provision Daytona sandbox ──
print("\n[2] Provisioning Daytona sandbox...")
info = asyncio.run(managed.provision_compute(idle_timeout_s=120))
print(f"    Instance: {info.instance_id}")
print(f"    Status:   {info.status}")

# ── 3. Execute commands ──
print("\n[3] Executing commands in Daytona...")
result = asyncio.run(managed.execute_in_compute("python3 -c 'import sys; print(sys.version)'"))
print(f"    Python version: {result['stdout'].strip()}")
print(f"    Exit code: {result['exit_code']}")

result = asyncio.run(managed.execute_in_compute("echo 'Hello from Daytona!'"))
print(f"    Echo: {result['stdout'].strip()}")

# ── 4. Agent LLM execution ──
print("\n[4] Agent LLM execution...")
result = agent.start("What is 11 * 13? Just the number.", stream=True)
print(f"    Result: {result}")

# ── 5. Usage ──
info = managed.retrieve_session()
print(f"\n[5] Usage: in={info['usage']['input_tokens']}, out={info['usage']['output_tokens']}")

# ── 6. Shutdown ──
print("\n[6] Shutting down Daytona sandbox...")
asyncio.run(managed.shutdown_compute())
print("    Shutdown complete.")

print("\nDone!")
