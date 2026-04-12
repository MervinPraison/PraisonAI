"""Docker compute provider — run agent tools inside a Docker container.

Requires: Docker running locally.
"""
import asyncio
from praisonai import Agent, ManagedAgent, LocalManagedConfig

# ── 1. Basic agent with Docker compute ──
managed = ManagedAgent(
    provider="local",
    compute="docker",
    config=LocalManagedConfig(
        model="gpt-4o-mini",
        system="You are a helpful coding assistant. Be concise.",
        name="DockerAgent",
    ),
)

agent = Agent(name="docker-agent", backend=managed)

print("[1] Agent created with Docker compute")
print(f"    Agent ID: {managed.agent_id or '(lazy — created on first call)'}")
print(f"    Compute:  {managed.compute_provider.provider_name}")

# ── 2. Provision Docker container ──
print("\n[2] Provisioning Docker container...")
info = asyncio.run(managed.provision_compute(image="python:3.12-slim"))
print(f"    Instance: {info.instance_id}")
print(f"    Status:   {info.status}")

# ── 3. Execute commands inside the container ──
print("\n[3] Executing commands in Docker...")
result = asyncio.run(managed.execute_in_compute("python3 -c 'import sys; print(sys.version)'"))
print(f"    Python version: {result['stdout'].strip()}")
print(f"    Exit code: {result['exit_code']}")

result = asyncio.run(managed.execute_in_compute("echo 'Hello from Docker!'"))
print(f"    Echo: {result['stdout'].strip()}")

# ── 4. Install packages in the container ──
print("\n[4] Installing packages...")
result = asyncio.run(managed.execute_in_compute("pip install requests -q"))
print(f"    pip exit code: {result['exit_code']}")

result = asyncio.run(managed.execute_in_compute("python3 -c 'import requests; print(requests.__version__)'"))
print(f"    requests version: {result['stdout'].strip()}")

# ── 5. Use agent with LLM (runs locally, compute is for tool sandboxing) ──
print("\n[5] Agent LLM execution...")
result = agent.start("What is 15 * 23? Just the number.", stream=True)
print(f"    Result: {result}")

# ── 6. Multi-turn ──
print("\n[6] Multi-turn...")
result = agent.start("Double that number.", stream=True)
print(f"    Result: {result}")

# ── 7. Usage tracking ──
info = managed.retrieve_session()
print(f"\n[7] Usage: in={info['usage']['input_tokens']}, out={info['usage']['output_tokens']}")

# ── 8. Shutdown Docker container ──
print("\n[8] Shutting down Docker container...")
asyncio.run(managed.shutdown_compute())
print("    Shutdown complete.")

print("\nDone!")
