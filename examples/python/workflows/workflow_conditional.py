"""
Agentic Conditional Workflow Example

Demonstrates using should_run to conditionally execute agent steps
based on input or previous results.
"""

from praisonaiagents import Agent, Workflow, WorkflowStep

# Condition functions
def is_technical(ctx) -> bool:
    """Only run technical review for technical content."""
    keywords = ["code", "programming", "algorithm", "database", "api"]
    return any(keyword in ctx.input.lower() for keyword in keywords)

def needs_creative(ctx) -> bool:
    """Only run creative enhancement for creative content."""
    keywords = ["story", "poem", "creative", "write", "narrative"]
    return any(keyword in ctx.input.lower() for keyword in keywords)

# Create agents
analyzer = Agent(
    name="Analyzer",
    role="Content Analyzer",
    goal="Analyze and process content",
    instructions="Analyze the given content and provide insights."
)

tech_reviewer = Agent(
    name="TechReviewer",
    role="Technical Reviewer",
    goal="Review technical content",
    instructions="Review the technical aspects and provide technical feedback."
)

creative_enhancer = Agent(
    name="CreativeEnhancer",
    role="Creative Enhancer",
    goal="Enhance creative content",
    instructions="Enhance the creative aspects and make it more engaging."
)

finalizer = Agent(
    name="Finalizer",
    role="Content Finalizer",
    goal="Finalize the content",
    instructions="Provide the final polished version of the content."
)

# Create workflow with conditional steps
workflow = Workflow(
    name="Conditional Agentic Pipeline",
    steps=[
        analyzer,  # Always runs
        WorkflowStep(
            name="tech_review",
            agent=tech_reviewer,
            should_run=is_technical  # Only runs for technical content
        ),
        WorkflowStep(
            name="creative_enhance",
            agent=creative_enhancer,
            should_run=needs_creative  # Only runs for creative content
        ),
        finalizer  # Always runs
    ]
)

if __name__ == "__main__":
    # Test 1: Technical content
    print("=== Test 1: Technical Content ===")
    result = workflow.start("Review this Python code for best practices", verbose=True)
    print(f"Output: {result['output'][:200]}...\n")
    
    # Test 2: Creative content
    print("=== Test 2: Creative Content ===")
    result = workflow.start("Write a short story about a robot", verbose=True)
    print(f"Output: {result['output'][:200]}...\n")
    
    # Test 3: General content (neither technical nor creative)
    print("=== Test 3: General Content ===")
    result = workflow.start("What is the weather like today?", verbose=True)
    print(f"Output: {result['output'][:200]}...")
