"""
Unified Handoff Configuration Example.

Demonstrates the new HandoffConfig features:
- Context policies (full, summary, none, last_n)
- Cycle detection
- Max depth limiting
- Timeout configuration
- Programmatic handoff via Agent.handoff_to()
"""

from praisonaiagents import Agent, handoff, HandoffConfig, ContextPolicy

# Create specialized agents
research_agent = Agent(
    name="Research Agent",
    role="Research Specialist",
    goal="Conduct thorough research on topics",
    backstory="Expert researcher with access to comprehensive knowledge bases."
)

writer_agent = Agent(
    name="Writer Agent",
    role="Content Writer",
    goal="Create well-written content based on research",
    backstory="Professional writer skilled in creating engaging content."
)

editor_agent = Agent(
    name="Editor Agent",
    role="Content Editor",
    goal="Review and polish written content",
    backstory="Experienced editor with keen eye for quality and clarity."
)

# Create coordinator with handoffs using new config options
coordinator = Agent(
    name="Coordinator",
    role="Project Coordinator",
    goal="Coordinate tasks between specialized agents",
    backstory="Expert at understanding requirements and delegating to the right specialist.",
    instructions="""Analyze the request and delegate to the appropriate specialist:
    - For research tasks, use transfer_to_research_agent
    - For writing tasks, use transfer_to_writer_agent
    - For editing tasks, use transfer_to_editor_agent
    Always explain your delegation decision.""",
    handoffs=[
        # Handoff with summary context policy (default - safe)
        handoff(
            research_agent,
            context_policy="summary",
            timeout_seconds=120,
            max_depth=5,
        ),
        # Handoff with full context
        handoff(
            writer_agent,
            context_policy="full",
            timeout_seconds=180,
        ),
        # Handoff with custom config
        handoff(
            editor_agent,
            config=HandoffConfig(
                context_policy=ContextPolicy.LAST_N,
                max_context_messages=5,
                detect_cycles=True,
                max_depth=3,
            ),
        ),
    ]
)


def demo_llm_driven_handoff():
    """Demonstrate LLM-driven handoff via tool calls."""
    print("=" * 60)
    print("Demo 1: LLM-Driven Handoff")
    print("=" * 60)
    
    response = coordinator.chat("I need to research the latest trends in AI agents")
    print(f"\nFinal Response:\n{response}")


def demo_programmatic_handoff():
    """Demonstrate programmatic handoff via Agent.handoff_to()."""
    print("\n" + "=" * 60)
    print("Demo 2: Programmatic Handoff (Agent.handoff_to)")
    print("=" * 60)
    
    # Create a simple agent for programmatic handoff
    source_agent = Agent(
        name="Source Agent",
        role="Task Initiator",
        goal="Initiate tasks and hand them off",
    )
    
    target_agent = Agent(
        name="Target Agent",
        role="Task Executor",
        goal="Execute delegated tasks",
    )
    
    # Programmatic handoff with custom config
    config = HandoffConfig(
        context_policy=ContextPolicy.SUMMARY,
        timeout_seconds=60,
        detect_cycles=True,
    )
    
    result = source_agent.handoff_to(
        target_agent,
        prompt="Summarize the key benefits of multi-agent systems",
        config=config,
    )
    
    print(f"\nHandoff Result:")
    print(f"  Success: {result.success}")
    print(f"  Target: {result.target_agent}")
    print(f"  Duration: {result.duration_seconds:.2f}s")
    if result.response:
        print(f"  Response: {result.response[:200]}...")


def demo_handoff_chain():
    """Demonstrate a handoff chain with depth tracking."""
    print("\n" + "=" * 60)
    print("Demo 3: Handoff Chain")
    print("=" * 60)
    
    # Create a chain: Analyst -> Researcher -> Writer
    analyst = Agent(
        name="Analyst",
        role="Requirements Analyst",
        goal="Analyze requirements and delegate research",
    )
    
    researcher = Agent(
        name="Researcher",
        role="Research Specialist",
        goal="Research topics and provide findings",
    )
    
    writer = Agent(
        name="Writer",
        role="Technical Writer",
        goal="Write documentation based on research",
    )
    
    # Chain: Analyst hands off to Researcher
    result1 = analyst.handoff_to(
        researcher,
        prompt="Research best practices for agent handoffs",
        config=HandoffConfig(max_depth=5),
    )
    print(f"\nStep 1 - Analyst -> Researcher:")
    print(f"  Success: {result1.success}")
    print(f"  Depth: {result1.handoff_depth}")
    
    # Researcher hands off to Writer
    if result1.success:
        result2 = researcher.handoff_to(
            writer,
            prompt=f"Write documentation based on: {result1.response[:100] if result1.response else 'research findings'}",
            config=HandoffConfig(max_depth=5),
        )
        print(f"\nStep 2 - Researcher -> Writer:")
        print(f"  Success: {result2.success}")
        print(f"  Depth: {result2.handoff_depth}")


if __name__ == "__main__":
    print("\n🤝 Unified Handoff Configuration Demo\n")
    
    # Run demos
    demo_llm_driven_handoff()
    demo_programmatic_handoff()
    demo_handoff_chain()
    
    print("\n" + "=" * 60)
    print("All demos completed!")
    print("=" * 60)
