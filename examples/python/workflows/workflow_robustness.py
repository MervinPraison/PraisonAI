"""
Workflow Robustness Example

Demonstrates graceful degradation and debugging features:
- skip_on_failure: Allow workflow to continue if a task fails
- retry_delay: Configure delay between retries (supports exponential backoff)
- history: Enable execution trace for debugging
- when(): Conditional branching based on results

Run: python workflow_robustness.py
"""

from praisonaiagents import Agent, Task
from praisonaiagents import AgentFlow, when


def main():
    # Create agents for the workflow
    researcher = Agent(
        name="researcher",
        role="Research Expert",
        goal="Find accurate information",
        instructions="Research topics thoroughly and provide accurate information.",
        llm="gpt-4o-mini"
    )
    
    enricher = Agent(
        name="enricher",
        role="Data Enricher",
        goal="Add additional context to research",
        instructions="Enrich research with additional context and examples.",
        llm="gpt-4o-mini"
    )
    
    writer = Agent(
        name="writer",
        role="Content Writer",
        goal="Create engaging content",
        instructions="Write clear, engaging content based on research.",
        llm="gpt-4o-mini"
    )
    
    # Create tasks with robustness features
    research_task = Task(
        description="Research the latest trends in AI agents for 2025",
        expected_output="A summary of key AI agent trends",
        agent=researcher,
        max_retries=3,
        retry_delay=1.0,  # 1 second between retries
    )
    
    # Optional enrichment step - workflow continues even if this fails
    enrich_task = Task(
        description="Enrich the research with real-world examples",
        expected_output="Research with added examples",
        agent=enricher,
        skip_on_failure=True,  # Workflow continues if enrichment fails
        max_retries=2,
        retry_delay=0.5,
    )
    
    write_task = Task(
        description="Write a brief summary based on the research",
        expected_output="A well-written summary paragraph",
        agent=writer,
        max_retries=3,
        retry_delay=1.0,
    )
    
    # Create workflow with history tracking enabled
    workflow = AgentFlow(
        name="Robust Research Workflow",
        steps=[research_task, enrich_task, write_task],
        history=True,  # Enable execution trace for debugging
    )
    
    # Run the workflow
    print("Starting robust workflow...")
    print("-" * 50)
    
    result = workflow.start("AI agents and autonomous systems")
    
    print("-" * 50)
    print(f"Workflow completed!")
    print(f"Result: {result[:200]}..." if len(str(result)) > 200 else f"Result: {result}")
    
    # Get execution history for debugging
    history = workflow.get_history()
    if history:
        print("\n" + "=" * 50)
        print("EXECUTION HISTORY (for debugging)")
        print("=" * 50)
        for entry in history:
            status = "✓" if entry.get("success") else "✗"
            print(f"{status} Step: {entry.get('step', 'unknown')}")
            print(f"  Timestamp: {entry.get('timestamp', 'N/A')}")
            if entry.get("error"):
                print(f"  Error: {entry.get('error')}")
            print()


def example_with_conditional():
    """Example showing conditional branching with when()."""
    
    scorer = Agent(
        name="scorer",
        role="Quality Scorer",
        goal="Score content quality",
        instructions="Analyze content and return a quality score from 0-100.",
        llm="gpt-4o-mini"
    )
    
    approver = Agent(
        name="approver",
        role="Content Approver",
        goal="Approve high-quality content",
        instructions="Approve the content for publication.",
        llm="gpt-4o-mini"
    )
    
    improver = Agent(
        name="improver",
        role="Content Improver",
        goal="Improve low-quality content",
        instructions="Suggest improvements for the content.",
        llm="gpt-4o-mini"
    )
    
    # Workflow with conditional branching
    workflow = AgentFlow(
        name="Quality Control Workflow",
        steps=[
            scorer,
            when(
                condition="{{score}} > 80",
                then_steps=[approver],
                else_steps=[improver]
            )
        ],
        history=True,
    )
    
    print("\nConditional workflow example created.")
    print("This workflow scores content and routes to approval or improvement.")


if __name__ == "__main__":
    main()
    # Uncomment to see conditional example structure:
    # example_with_conditional()
