"""
Agent-Centric API Example

Demonstrates the new consolidated feature parameters for PraisonAI Agents.
These params provide a cleaner, more intuitive API with progressive disclosure.

New Consolidated Params:
- memory: Union[bool, MemoryConfig, MemoryManager] - Memory and session management
- knowledge: Union[bool, List[str], KnowledgeConfig, KnowledgeBase] - RAG and retrieval
- planning: Union[bool, PlanningConfig] - Planning mode
- reflection: Union[bool, ReflectionConfig] - Self-reflection
- guardrails: Union[bool, Callable, GuardrailConfig] - Safety validation
- web: Union[bool, WebConfig] - Web search and fetch
- context: Union[bool, ManagerConfig, ContextManager] - Context management
"""

from praisonaiagents import (
    Agent,
    # Config classes for progressive disclosure
    MemoryConfig,
    KnowledgeConfig,
    PlanningConfig,
    ReflectionConfig,
    GuardrailConfig,
    WebConfig,
)


def example_simple_enable():
    """Example 1: Simple boolean enable (easiest)"""
    print("\n=== Example 1: Simple Boolean Enable ===")
    
    agent = Agent(
        instructions="You are a helpful assistant",
        memory=True,      # Enable memory with defaults
        reflection=True,  # Enable self-reflection
        web=True,         # Enable web search + fetch
    )
    print(f"Agent created with memory={agent._memory_instance is not None}")
    print(f"  self_reflect={agent.self_reflect}")
    print(f"  web_search={agent.web_search}")


def example_with_config():
    """Example 2: Using config objects (more control)"""
    print("\n=== Example 2: Using Config Objects ===")
    
    agent = Agent(
        instructions="You are a research assistant",
        memory=MemoryConfig(
            backend="file",
            user_id="researcher_001",
            auto_memory=True,
        ),
        reflection=ReflectionConfig(
            min_iterations=1,
            max_iterations=5,
            llm="gpt-4o-mini",
        ),
        web=WebConfig(
            search=True,
            fetch=False,  # Only search, no full page fetch
            max_results=3,
        ),
    )
    print(f"Agent created with user_id={agent.user_id}")
    print(f"  {agent.max_reflect}")
    print(f"  web_search={agent.web_search}, web_fetch={agent.web_fetch}")


def example_guardrails():
    """Example 3: Guardrails with callable or config"""
    print("\n=== Example 3: Guardrails ===")
    
    # Option A: Direct callable
    def my_validator(output):
        """Simple validator that checks response length."""
        is_valid = len(output.raw) < 1000
        return (is_valid, output if is_valid else "Response too long")
    
    agent_a = Agent(
        instructions="Be concise",
        guardrails=my_validator,  # Direct callable
    )
    print(f"Agent A: guardrail is callable = {callable(agent_a.guardrail)}")
    
    # Option B: Using GuardrailConfig
    agent_b = Agent(
        instructions="Be helpful and safe",
        guardrails=GuardrailConfig(
            llm_validator="Ensure the response is helpful, accurate, and safe",
            max_retries=3,
        ),
    )
    print(f"Agent B: guardrail = {agent_b.guardrail}")
    print(f"  max_retries = {agent_b.max_guardrail_retries}")


def example_planning():
    """Example 4: Planning mode"""
    print("\n=== Example 4: Planning Mode ===")
    
    agent = Agent(
        instructions="You are a project planner",
        planning=PlanningConfig(
            reasoning=True,
            read_only=True,  # Plan mode - only read operations
        ),
    )
    print(f"Agent created with planning={agent.planning}")
    print(f"  plan_mode={agent.plan_mode}")
    print(f"  planning_reasoning={agent.planning_reasoning}")


def example_backward_compatible():
    """Example 5: Using new consolidated params"""
    print("\n=== Example 5: Consolidated Params ===")
    
    # New consolidated params
    agent = Agent(
        instructions="Test agent",
        reflection=True,
        web=WebConfig(search=True, fetch=False),
    )
    print(f"Consolidated params work: self_reflect={agent.self_reflect}")
    print(f"  web_search={agent.web_search}, web_fetch={agent.web_fetch}")


def example_real_chat():
    """Example 6: Real chat with new API"""
    print("\n=== Example 6: Real Chat ===")
    
    agent = Agent(
        instructions="You are a helpful math tutor. Be concise.",
        reflection=False,
        web=False,
        verbose=False,
    )
    
    response = agent.start("What is the square root of 144?")
    print(f"Response: {response}")


if __name__ == "__main__":
    print("=" * 60)
    print("PraisonAI Agent-Centric API Examples")
    print("=" * 60)
    
    example_simple_enable()
    example_with_config()
    example_guardrails()
    example_planning()
    example_backward_compatible()
    example_real_chat()
    
    print("\n" + "=" * 60)
    print("All examples completed!")
    print("=" * 60)
