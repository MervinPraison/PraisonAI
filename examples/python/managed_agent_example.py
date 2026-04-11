#!/usr/bin/env python3
"""
Managed Agent Backend Example — Real end-to-end test.

Demonstrates using Anthropic's Managed Agents API as an execution backend
for a PraisonAI Agent. The agent runs in Anthropic's managed infrastructure.

Prerequisites:
    export ANTHROPIC_API_KEY="your-key"
    pip install 'anthropic>=0.94.0' praisonaiagents praisonai

Usage:
    python examples/python/managed_agent_example.py
"""

import os
import sys
import logging

# ── Setup logging so we can see what the integration does ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# ── Guard: API key must be set ──
if not os.getenv("ANTHROPIC_API_KEY"):
    print("ERROR: ANTHROPIC_API_KEY not set. Export it first.")
    sys.exit(1)


def example_1_standalone():
    """Example 1: Use ManagedAgentIntegration directly (no PraisonAI Agent)."""
    print("\n" + "=" * 60)
    print("Example 1: Standalone ManagedAgentIntegration")
    print("=" * 60)

    from praisonai.integrations.managed_agents import ManagedAgent, ManagedConfig

    managed = ManagedAgent(
        config=ManagedConfig(
            model="claude-sonnet-4-6",
            name="Standalone Test Agent",
            system="You are a concise assistant. Answer in one sentence.",
        ),
    )

    result = managed._execute_sync("What is 2 + 2? Answer in one sentence.")
    print(f"\nResult: {result}")
    print(f"Tokens: in={managed.total_input_tokens}, out={managed.total_output_tokens}")
    assert result and len(result) > 0, "Expected non-empty response"
    print("PASS: Standalone execution")
    return result


def example_2_with_agent():
    """Example 2: Use ManagedAgentIntegration as a PraisonAI Agent backend."""
    print("\n" + "=" * 60)
    print("Example 2: PraisonAI Agent with managed backend")
    print("=" * 60)

    from praisonaiagents import Agent
    from praisonai.integrations.managed_agents import ManagedAgent, ManagedConfig

    managed = ManagedAgent(
        config=ManagedConfig(
            model="claude-sonnet-4-6",
            name="PraisonAI Backend Agent",
            system="You are a helpful coding assistant. Be concise.",
        ),
    )

    agent = Agent(
        name="managed-coder",
        instructions="You are a helpful coding assistant.",
        backend=managed,
    )

    result = agent.start("Write a Python one-liner that prints the first 10 Fibonacci numbers.")
    print(f"\nResult: {result}")
    assert result and len(result) > 0, "Expected non-empty response from agent.start()"
    print("PASS: Agent backend execution")
    return result


def example_3_with_tools():
    """Example 3: Managed agent with built-in tools (bash, file ops)."""
    print("\n" + "=" * 60)
    print("Example 3: Managed agent with built-in tools")
    print("=" * 60)

    from praisonaiagents import Agent
    from praisonai.integrations.managed_agents import ManagedAgent, ManagedConfig

    managed = ManagedAgent(
        config=ManagedConfig(
            model="claude-sonnet-4-6",
            name="Tool-Using Agent",
            system="You are a coding agent with access to bash and file tools.",
            tools=[{"type": "agent_toolset_20260401"}],
        ),
    )

    agent = Agent(
        name="tool-agent",
        instructions="You are a coding agent.",
        backend=managed,
    )

    result = agent.start(
        "Use bash to run: echo 'Hello from managed agent!' && python3 -c 'print(sum(range(10)))'"
    )
    print(f"\nResult: {result}")
    assert result and len(result) > 0, "Expected non-empty response"
    print("PASS: Tool-using agent execution")
    return result


def example_4_with_packages():
    """Example 4: Managed agent with custom packages installed."""
    print("\n" + "=" * 60)
    print("Example 4: Managed agent with pip packages")
    print("=" * 60)

    from praisonaiagents import Agent
    from praisonai.integrations.managed_agents import ManagedAgent, ManagedConfig

    managed = ManagedAgent(
        config=ManagedConfig(
            model="claude-sonnet-4-6",
            name="Data Agent",
            system="You are a data analysis agent. Use pandas when helpful.",
            packages={"pip": ["pandas", "numpy"]},
        ),
    )

    agent = Agent(
        name="data-agent",
        instructions="You are a data analysis agent.",
        backend=managed,
    )

    result = agent.start(
        "Use bash to run: python3 -c \"import pandas as pd; print(pd.__version__)\""
    )
    print(f"\nResult: {result}")
    assert result and len(result) > 0, "Expected non-empty response"
    print("PASS: Package installation agent")
    return result


if __name__ == "__main__":
    print("Managed Agent Backend — Real End-to-End Tests")
    print("Using Anthropic Managed Agents API (beta)")

    examples = [
        ("standalone", example_1_standalone),
        ("agent_backend", example_2_with_agent),
        ("with_tools", example_3_with_tools),
        ("with_packages", example_4_with_packages),
    ]
    results = {}

    for name, fn in examples:
        try:
            results[name] = fn()
        except Exception as e:
            print(f"FAIL: {name}: {e}")
            results[name] = None

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    passed = sum(1 for v in results.values() if v is not None)
    total = len(results)
    for name, result in results.items():
        status = "PASS" if result else "FAIL"
        print(f"  {status}: {name}")
    print(f"\n{passed}/{total} examples passed")
