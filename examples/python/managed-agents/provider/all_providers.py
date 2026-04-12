"""All compute providers — comprehensive test across Local, Docker, E2B, and Modal.

This example mirrors the Anthropic app.py but uses the local provider with
various compute backends instead of Anthropic's managed infrastructure.

Requires:
  - Docker running locally
  - E2B_API_KEY set
  - modal CLI configured (modal token set)
"""
import asyncio
from praisonai import Agent, ManagedAgent, LocalManagedConfig


async def test_provider(name, compute, extra_provision_kwargs=None):
    """Test a single compute provider end-to-end."""
    print(f"\n{'='*60}")
    print(f"  PROVIDER: {name}")
    print(f"{'='*60}")

    managed = ManagedAgent(
        provider="local",
        compute=compute,
        config=LocalManagedConfig(
            model="gpt-4o-mini",
            system="You are a helpful assistant. Be concise.",
            name=f"{name}Agent",
        ),
    )
    agent = Agent(name=f"{name}-test", backend=managed)

    # 1. Provision
    print(f"\n  [1] Provisioning {name}...")
    provision_kwargs = extra_provision_kwargs or {}
    info = await managed.provision_compute(**provision_kwargs)
    print(f"      Instance: {info.instance_id}")
    print(f"      Status:   {info.status}")

    # 2. Execute command
    print(f"\n  [2] Execute in {name}...")
    result = await managed.execute_in_compute("python3 -c 'print(42 * 13)'")
    stdout = result["stdout"].strip()
    assert "546" in stdout, f"Expected 546, got: {stdout}"
    print(f"      42 * 13 = {stdout} ✓")

    # 3. Execute echo
    result = await managed.execute_in_compute(f"echo 'Hello from {name}'")
    print(f"      Echo: {result['stdout'].strip()}")

    # 4. Agent LLM
    print(f"\n  [3] Agent LLM via {name}...")
    llm_result = agent.start("What is 9 * 8? Just the number.", stream=True)
    print(f"      LLM result: {llm_result}")

    # 5. Multi-turn
    print("\n  [4] Multi-turn...")
    llm_result = agent.start("Add 10 to that. Just the number.", stream=True)
    print(f"      Follow-up: {llm_result}")

    # 6. Usage
    session = managed.retrieve_session()
    usage = session["usage"]
    print(f"\n  [5] Usage: in={usage['input_tokens']}, out={usage['output_tokens']}")

    # 7. Shutdown
    print(f"\n  [6] Shutdown {name}...")
    await managed.shutdown_compute()
    print("      Done ✓")

    return {
        "name": name,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
    }


async def main():
    results = []

    # Docker
    try:
        r = await test_provider("Docker", "docker", {"image": "python:3.12-slim"})
        results.append(r)
    except Exception as e:
        print(f"\n  Docker FAILED: {e}")

    # E2B
    try:
        r = await test_provider("E2B", "e2b", {"idle_timeout_s": 120})
        results.append(r)
    except Exception as e:
        print(f"\n  E2B FAILED: {e}")

    # Modal
    try:
        r = await test_provider("Modal", "modal", {"idle_timeout_s": 120})
        results.append(r)
    except Exception as e:
        print(f"\n  Modal FAILED: {e}")

    # Summary
    print(f"\n\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    total_in = 0
    total_out = 0
    for r in results:
        total_in += r["input_tokens"]
        total_out += r["output_tokens"]
        print(f"  {r['name']:15s} | in: {r['input_tokens']:6d} | out: {r['output_tokens']:6d}")
    print(f"  {'TOTAL':15s} | in: {total_in:6d} | out: {total_out:6d}")
    print(f"{'='*60}")
    print(f"  {len(results)}/{3} providers passed")


if __name__ == "__main__":
    asyncio.run(main())
