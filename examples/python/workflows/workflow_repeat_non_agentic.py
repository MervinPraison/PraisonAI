"""
Workflow Repeat (Evaluator-Optimizer) Example

Demonstrates repeating a step until a condition is met.
This is useful for iterative improvement patterns.
"""

from praisonaiagents import Workflow, WorkflowContext, StepResult
from praisonaiagents.workflows import repeat

# Simulated content generator that improves each iteration
class ContentGenerator:
    def __init__(self):
        self.iteration = 0
        self.content = []
    
    def generate(self, ctx: WorkflowContext) -> StepResult:
        """Generate content, adding more each iteration."""
        self.iteration += 1
        
        # Add new content each iteration
        new_items = [
            f"Point {self.iteration}.1: Key insight about the topic",
            f"Point {self.iteration}.2: Supporting evidence"
        ]
        self.content.extend(new_items)
        
        output = f"Iteration {self.iteration}: Generated {len(self.content)} points total"
        
        return StepResult(
            output=output,
            variables={
                "total_points": len(self.content),
                "content": self.content.copy()
            }
        )

# Condition: stop when we have enough content
def has_enough_content(ctx: WorkflowContext) -> bool:
    """Check if we have generated enough content."""
    total = ctx.variables.get("total_points", 0)
    return total >= 6  # Stop when we have 6+ points

# Create generator instance
generator = ContentGenerator()

# Create workflow with repeat pattern
workflow = Workflow(
    name="Content Generator",
    steps=[
        repeat(
            generator.generate,
            until=has_enough_content,
            max_iterations=10
        )
    ]
)

if __name__ == "__main__":
    print("=== Testing Repeat (Evaluator-Optimizer) Pattern ===\n")
    
    result = workflow.start("Generate comprehensive content", verbose=True)
    
    print(f"\nFinal output: {result['output']}")
    print(f"Total iterations: {result['variables']['repeat_iterations']}")
    print(f"Total points generated: {result['variables']['total_points']}")
    print("\nGenerated content:")
    for point in result['variables']['content']:
        print(f"  • {point}")
