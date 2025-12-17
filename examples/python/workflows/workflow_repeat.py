"""
Agentic Evaluator-Optimizer (Repeat) Workflow Example

Demonstrates the evaluator-optimizer pattern where an agent
generates content and another evaluates it, repeating until approved.
"""

from praisonaiagents import Agent, Workflow
from praisonaiagents.workflows import repeat

# Create generator agent
generator = Agent(
    name="Generator",
    role="Content Generator",
    goal="Generate high-quality content",
    instructions="Generate content based on the topic. Improve based on feedback if provided."
)

# Create evaluator agent  
evaluator = Agent(
    name="Evaluator",
    role="Content Evaluator",
    goal="Evaluate and provide feedback on content",
    instructions="Evaluate the content quality. If good, respond with 'APPROVED'. Otherwise provide specific feedback for improvement."
)

# Evaluation function to check if content is approved
def is_approved(ctx) -> bool:
    return "approved" in ctx.previous_result.lower()

# Create workflow with evaluator-optimizer pattern
workflow = Workflow(
    name="Evaluator-Optimizer Pipeline",
    steps=[
        generator,  # First, generate content
        repeat(
            evaluator,  # Evaluate and provide feedback
            until=is_approved,
            max_iterations=3
        )
    ]
)

if __name__ == "__main__":
    print("=== Testing Agentic Evaluator-Optimizer Workflow ===\n")
    
    # Run optimization workflow
    result = workflow.start(
        "Write a compelling product description for an AI assistant",
        verbose=True
    )
    
    print(f"\nFinal Result:\n{result['output']}")
