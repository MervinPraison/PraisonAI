"""
Isolated Registry Example - Multi-Agent Safety

This example demonstrates how to use isolated registries to prevent
provider registration collisions in multi-agent scenarios.

Key concepts:
- Each agent/context can have its own registry
- No global state mutation
- Safe for concurrent/parallel runs
- Different agents can use different provider implementations

Requirements:
- pip install praisonai
"""

import sys
sys.path.insert(0, '../../src/praisonai')

from praisonai.llm import (
    LLMProviderRegistry,
    create_llm_provider,
    register_llm_provider,
    get_default_llm_registry,
    _reset_default_registry
)


# Define two different provider implementations with the same name
class Agent1Provider:
    """Provider implementation for Agent 1."""
    provider_id = "custom"
    
    def __init__(self, model_id, config=None):
        self.model_id = model_id
        self.config = config or {}
        self.agent_name = "Agent1"
    
    def generate(self, prompt):
        return f"[{self.agent_name}] Response to: {prompt}"


class Agent2Provider:
    """Provider implementation for Agent 2 - different behavior."""
    provider_id = "custom"
    
    def __init__(self, model_id, config=None):
        self.model_id = model_id
        self.config = config or {}
        self.agent_name = "Agent2"
    
    def generate(self, prompt):
        return f"[{self.agent_name}] Different response to: {prompt}"


def demonstrate_collision_problem():
    """Show what happens with global registry collisions."""
    print("=== Problem: Global Registry Collision ===\n")
    
    # Reset to clean state
    _reset_default_registry()
    
    # Agent 1 registers "custom" provider
    register_llm_provider("custom", Agent1Provider)
    print("Agent 1 registered 'custom' provider")
    
    # Agent 2 tries to register same name - ERROR!
    try:
        register_llm_provider("custom", Agent2Provider)
        print("Agent 2 registered 'custom' provider")
    except ValueError as e:
        print(f"Agent 2 FAILED: {e}")
    
    print()
    print("Problem: Both agents want to use 'custom' but with different implementations.")
    print("Solution: Use isolated registries.\n")


def demonstrate_isolated_solution():
    """Show how isolated registries solve the collision problem."""
    print("=== Solution: Isolated Registries ===\n")
    
    # Create isolated registries for each agent
    agent1_registry = LLMProviderRegistry()
    agent2_registry = LLMProviderRegistry()
    
    # Each agent registers its own "custom" provider
    agent1_registry.register("custom", Agent1Provider)
    agent2_registry.register("custom", Agent2Provider)
    
    print("Agent 1 registry providers:", agent1_registry.list())
    print("Agent 2 registry providers:", agent2_registry.list())
    print()
    
    # Create providers from each registry
    provider1 = create_llm_provider("custom/model-v1", registry=agent1_registry)
    provider2 = create_llm_provider("custom/model-v1", registry=agent2_registry)
    
    # They have different implementations!
    print("Provider 1 response:", provider1.generate("Hello"))
    print("Provider 2 response:", provider2.generate("Hello"))
    print()
    
    # Verify isolation
    print("Verification:")
    print(f"  provider1.agent_name = {provider1.agent_name}")
    print(f"  provider2.agent_name = {provider2.agent_name}")
    print(f"  Same class? {type(provider1) == type(provider2)}")
    print()


def demonstrate_parallel_agents():
    """Simulate parallel agent execution with isolated registries."""
    print("=== Parallel Agent Simulation ===\n")
    
    def run_agent(agent_id, registry):
        """Simulate an agent run with its own registry."""
        provider = create_llm_provider("custom/model", registry=registry)
        result = provider.generate(f"Query from agent {agent_id}")
        return result
    
    # Setup registries
    registries = {}
    for i in range(3):
        reg = LLMProviderRegistry()
        # Each agent gets a slightly different provider
        class DynamicProvider:
            provider_id = "custom"
            def __init__(self, model_id, config=None):
                self.model_id = model_id
                self.agent_id = i  # Capture agent ID
            def generate(self, prompt):
                return f"Agent-{self.agent_id} processed: {prompt}"
        
        reg.register("custom", DynamicProvider)
        registries[i] = reg
    
    # Simulate parallel execution
    print("Simulating parallel agent runs:")
    for agent_id, registry in registries.items():
        result = run_agent(agent_id, registry)
        print(f"  {result}")
    
    print()
    print("Each agent used its own isolated registry - no collisions!")
    print()


def demonstrate_shared_vs_isolated():
    """Compare shared (global) vs isolated registry patterns."""
    print("=== Shared vs Isolated Patterns ===\n")
    
    # Reset global registry
    _reset_default_registry()
    
    # Pattern 1: Shared (global) registry
    print("Pattern 1: Shared Registry (use for app-wide providers)")
    register_llm_provider("shared-provider", Agent1Provider)
    
    # All code sees the same provider
    global_reg = get_default_llm_registry()
    print(f"  Global registry has 'shared-provider': {global_reg.has('shared-provider')}")
    
    # Pattern 2: Isolated registry
    print("\nPattern 2: Isolated Registry (use for per-agent/per-run providers)")
    isolated = LLMProviderRegistry()
    isolated.register("isolated-provider", Agent2Provider)
    
    # Only code with reference to this registry sees it
    print(f"  Isolated registry has 'isolated-provider': {isolated.has('isolated-provider')}")
    print(f"  Global registry has 'isolated-provider': {global_reg.has('isolated-provider')}")
    
    print()
    print("Recommendation:")
    print("  - Use global registry for app-wide, stable providers")
    print("  - Use isolated registries for per-agent or per-run customization")
    print()


def main():
    print("=" * 60)
    print("Isolated Registry Example - Multi-Agent Safety")
    print("=" * 60)
    print()
    
    demonstrate_collision_problem()
    demonstrate_isolated_solution()
    demonstrate_parallel_agents()
    demonstrate_shared_vs_isolated()
    
    print("=" * 60)
    print("Example Complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
