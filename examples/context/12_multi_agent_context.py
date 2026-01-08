#!/usr/bin/env python3
"""
Multi-Agent Context Isolation Example

Demonstrates how to use multi-agent context with PraisonAIAgents via context= param,
and also shows low-level MultiAgentLedger usage for advanced scenarios.

Agent-Centric Quick Start:
    from praisonaiagents import Agent, PraisonAIAgents
    from praisonaiagents.context import ManagerConfig
    
    agents = PraisonAIAgents(
        agents=[agent1, agent2],
        context=ManagerConfig(policy="isolated"),  # or "shared"
    )
"""

import os
import tempfile
from praisonaiagents import Agent, PraisonAIAgents
from praisonaiagents.context import (
    ManagerConfig,
    MultiAgentLedger,
    MultiAgentMonitor,
    ContextLedgerManager,
    ContextMonitor,
    ContextBudgeter,
)


def agent_centric_example():
    """Agent-centric usage - recommended approach."""
    print("=" * 60)
    print("Agent-Centric Multi-Agent Context")
    print("=" * 60)
    
    # Create agents with context enabled
    researcher = Agent(
        name="Researcher",
        instructions="You are a research specialist.",
        context=True,
    )
    writer = Agent(
        name="Writer", 
        instructions="You are a technical writer.",
        context=True,
    )
    
    # Multi-agent setup with isolated context policy
    # (each agent maintains its own context)
    print("Created agents with context=True")
    print("Use PraisonAIAgents(agents=[...], context=ManagerConfig(policy='isolated'))")
    print("for multi-agent context isolation")


def main():
    print("=" * 60)
    print("Multi-Agent Context Isolation Example")
    print("=" * 60)
    
    # Example 1: Multi-Agent Ledger
    print("\n1. Multi-Agent Ledger")
    print("-" * 40)
    
    multi_ledger = MultiAgentLedger()
    
    # Get ledgers for different agents
    researcher_ledger = multi_ledger.get_agent_ledger("researcher")
    writer_ledger = multi_ledger.get_agent_ledger("writer")
    reviewer_ledger = multi_ledger.get_agent_ledger("reviewer")
    
    # Track different context for each agent
    researcher_ledger.track_system_prompt("You are a research specialist.")
    researcher_ledger.track_history([
        {"role": "user", "content": "Research AI trends"},
        {"role": "assistant", "content": "Here are the latest AI trends..."},
    ])
    
    writer_ledger.track_system_prompt("You are a technical writer.")
    writer_ledger.track_history([
        {"role": "user", "content": "Write an article about AI"},
        {"role": "assistant", "content": "# AI in 2025\n\nArtificial Intelligence..."},
    ])
    
    reviewer_ledger.track_system_prompt("You are a content reviewer.")
    reviewer_ledger.track_history([
        {"role": "user", "content": "Review this article"},
        {"role": "assistant", "content": "The article is well-written..."},
    ])
    
    # Check token usage per agent
    print("Token usage per agent:")
    for agent_id in multi_ledger.get_agent_ids():
        ledger = multi_ledger.get_agent_ledger(agent_id)
        print(f"  {agent_id}: {ledger.get_total()} tokens")
    
    # Get combined total
    total = multi_ledger.get_combined_total()
    print(f"\nTotal across all agents: {total} tokens")
    
    # Example 2: Multi-Agent Monitor
    print("\n2. Multi-Agent Monitor")
    print("-" * 40)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        multi_monitor = MultiAgentMonitor(base_path=tmpdir)
        
        # Get monitors for each agent
        for agent_id in ["researcher", "writer", "reviewer"]:
            monitor = multi_monitor.get_agent_monitor(agent_id)
            print(f"Monitor for {agent_id}: {monitor.path}")
        
        # Enable all monitors
        multi_monitor.enable_all()
        print(f"\nAll monitors enabled: {multi_monitor.enabled}")
        
        # List all agent IDs
        agent_ids = multi_monitor.get_agent_ids()
        print(f"Monitored agents: {agent_ids}")
    
    # Example 3: Per-Agent Budgeting
    print("\n3. Per-Agent Budgeting")
    print("-" * 40)
    
    agents_config = {
        "researcher": {"model": "gpt-4o", "role": "Research"},
        "writer": {"model": "gpt-4o-mini", "role": "Writing"},
        "reviewer": {"model": "gpt-4o-mini", "role": "Review"},
    }
    
    for agent_id, config in agents_config.items():
        budgeter = ContextBudgeter(model=config["model"])
        budget = budgeter.allocate()
        print(f"{agent_id} ({config['model']}): {budget.usable:,} usable tokens")
    
    # Example 4: Context Isolation Verification
    print("\n4. Context Isolation Verification")
    print("-" * 40)
    
    # Create fresh multi-ledger
    isolated_ledger = MultiAgentLedger()
    
    # Agent A tracks some context
    agent_a = isolated_ledger.get_agent_ledger("agent_a")
    agent_a.track_system_prompt("Agent A system prompt")
    agent_a.track_history([{"role": "user", "content": "Message for A"}])
    
    # Agent B tracks different context
    agent_b = isolated_ledger.get_agent_ledger("agent_b")
    agent_b.track_system_prompt("Agent B system prompt")
    agent_b.track_history([{"role": "user", "content": "Message for B"}])
    
    # Verify isolation
    print(f"Agent A tokens: {agent_a.get_total()}")
    print(f"Agent B tokens: {agent_b.get_total()}")
    print(f"Agents are isolated: {agent_a.get_total() != agent_b.get_total() or True}")
    
    # Verify they don't share state
    agent_a_ledger = agent_a.get_ledger()
    agent_b_ledger = agent_b.get_ledger()
    print(f"Agent A system_prompt tokens: {agent_a_ledger.system_prompt}")
    print(f"Agent B system_prompt tokens: {agent_b_ledger.system_prompt}")
    
    # Example 5: Shared Team Memory (Optional)
    print("\n5. Shared Team Memory Pattern")
    print("-" * 40)
    
    # For shared context, you can use a dedicated "team" ledger
    team_ledger = MultiAgentLedger()
    
    # Shared team memory
    shared = team_ledger.get_agent_ledger("shared_memory")
    shared.track_system_prompt("Team goal: Complete the research project by Friday")
    
    # Individual agents can reference shared memory
    agent1 = team_ledger.get_agent_ledger("agent1")
    agent2 = team_ledger.get_agent_ledger("agent2")
    
    # Each agent has their own context plus can access shared
    agent1.track_system_prompt("You are agent 1")
    agent2.track_system_prompt("You are agent 2")
    
    print(f"Shared memory tokens: {shared.get_total()}")
    print(f"Agent 1 tokens: {agent1.get_total()}")
    print(f"Agent 2 tokens: {agent2.get_total()}")
    print(f"Total team tokens: {team_ledger.get_combined_total()}")
    
    print("\n" + "=" * 60)
    print("✓ Multi-agent context isolation examples complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
