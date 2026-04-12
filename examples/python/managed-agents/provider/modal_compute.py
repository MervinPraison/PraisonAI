"""Modal compute provider — run agent tools inside a Modal cloud sandbox.

Requires: modal CLI configured (modal token set) or MODAL_TOKEN_ID + MODAL_TOKEN_SECRET.
Install:  pip install modal
"""
import asyncio
from praisonai import Agent, ManagedAgent, LocalManagedConfig

# ── 1. Create agent with Modal compute ──
managed = ManagedAgent(
    provider="local",
    compute="modal",
    config=LocalManagedConfig(
        model="gpt-4o-mini",
        system="You are a helpful coding assistant. Be concise.",
        name="ModalAgent",
    ),
)

agent = Agent(name="modal-agent", backend=managed)

print("[1] Agent created with Modal compute")
print(f"    Compute: {managed.compute_provider.provider_name}")

# ── 2. Provision Modal sandbox ──
print("\n[2] Provisioning Modal sandbox...")
info = asyncio.run(managed.provision_compute(idle_timeout_s=120))
print(f"    Instance: {info.instance_id}")
print(f"    Status:   {info.status}")

# ── 3. Execute commands in the sandbox ──
print("\n[3] Executing commands in Modal...")
result = asyncio.run(managed.execute_in_compute("python3 -c 'import sys; print(sys.version)'"))
print(f"    Python version: {result['stdout'].strip()}")
print(f"    Exit code: {result['exit_code']}")

result = asyncio.run(managed.execute_in_compute("echo 'Hello from Modal!'"))
print(f"    Echo: {result['stdout'].strip()}")

# ── 4. Run a computation ──
print("\n[4] Running computation...")
result = asyncio.run(managed.execute_in_compute(
    "python3 -c 'print(sum(range(1, 101)))'"
))
print(f"    Sum 1..100 = {result['stdout'].strip()}")

# ── 5. Agent LLM execution ──
print("\n[5] Agent LLM execution...")
result = agent.start("What is 7 factorial? Just the number.", stream=True)
print(f"    Result: {result}")

# ── 6. Multi-turn ──
print("\n[6] Multi-turn...")
result = agent.start("Is that number even or odd?", stream=True)
print(f"    Result: {result}")

# ── 7. Usage ──
info = managed.retrieve_session()
print(f"\n[7] Usage: in={info['usage']['input_tokens']}, out={info['usage']['output_tokens']}")

# ── 8. Shutdown ──
print("\n[8] Shutting down Modal sandbox...")
asyncio.run(managed.shutdown_compute())
print("    Shutdown complete.")

print("\nDone!")
