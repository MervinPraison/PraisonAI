"""
Workflow Loop with List Example

Demonstrates iterating over a list of items, processing each one.
"""

from praisonaiagents import Workflow, WorkflowContext, StepResult
from praisonaiagents.workflows import loop

# Sample data
fruits = ["apple", "banana", "cherry", "date", "elderberry"]

# Processor for each item
def process_fruit(ctx: WorkflowContext) -> StepResult:
    """Process a single fruit from the list."""
    fruit = ctx.variables.get("item", "unknown")
    index = ctx.variables.get("loop_index", 0)
    
    # Simulate processing
    result = f"🍎 [{index + 1}] {fruit.upper()} - processed successfully"
    
    return StepResult(
        output=result,
        variables={"last_fruit": fruit}
    )

# Aggregator to summarize results
def summarize(ctx: WorkflowContext) -> StepResult:
    """Summarize all processed fruits."""
    outputs = ctx.variables.get("loop_outputs", [])
    summary = f"📊 Processed {len(outputs)} fruits:\n"
    summary += "\n".join(f"  {o}" for o in outputs)
    return StepResult(output=summary)

# Create workflow
workflow = Workflow(
    name="Fruit Processor",
    steps=[
        loop(process_fruit, over="fruits"),
        summarize
    ],
    variables={"fruits": fruits}
)

if __name__ == "__main__":
    print("=== Testing Loop with List ===\n")
    
    result = workflow.start("Process all fruits", verbose=True)
    
    print(f"\nFinal Output:\n{result['output']}")
    print(f"\nLoop outputs count: {len(result['variables']['loop_outputs'])}")
    print(f"Last processed: {result['variables'].get('last_fruit')}")
