"""
Simple Workflow Example

The easiest way to create and run workflows in PraisonAI.
Just pass functions or agents as steps - no complex configuration needed!
"""

from praisonaiagents import Workflow, WorkflowContext, StepResult

# Define simple handler functions
def validate(ctx: WorkflowContext) -> StepResult:
    """Validate the input data."""
    if not ctx.input:
        return StepResult(output="No input provided", stop_workflow=True)
    return StepResult(output=f"Validated: {ctx.input}")

def process(ctx: WorkflowContext) -> StepResult:
    """Process the validated data."""
    return StepResult(output=f"Processed: {ctx.previous_result}")

def format_output(ctx: WorkflowContext) -> StepResult:
    """Format the final output."""
    return StepResult(output=f"✅ Final: {ctx.previous_result}")

# Create workflow - just list your functions!
workflow = Workflow(
    name="Simple Pipeline",
    steps=[validate, process, format_output]
)

if __name__ == "__main__":
    # Run the workflow - PraisonAI style uses .start()
    result = workflow.start("Hello, World!", verbose=True)
    
    print(f"\nFinal output: {result['output']}")
    print(f"Steps completed: {len(result['steps'])}")
