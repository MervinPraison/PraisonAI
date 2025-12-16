"""
Workflow Early Stop Example

Demonstrates how to stop a workflow early using custom handler
functions that return StepResult with stop_workflow=True.
"""

from praisonaiagents.memory.workflows import (
    WorkflowManager, WorkflowStep, Workflow,
    WorkflowContext, StepResult
)

# Custom validator that can stop the workflow
def validate_data(context: WorkflowContext) -> StepResult:
    """Check if data is valid and stop workflow if not."""
    data = context.variables.get("data", {})
    
    if data.get("value", 0) < 0:
        return StepResult(
            output="❌ Validation failed: negative value detected. Stopping workflow.",
            stop_workflow=True  # This stops the entire workflow
        )
    
    return StepResult(
        output="✅ Validation passed: data is valid.",
        stop_workflow=False  # Continue to next step
    )

# Create workflow with early stop capability
workflow = Workflow(
    name="Data Processing",
    description="Process data with validation gate",
    variables={
        "data": {"value": -5}  # Invalid data - will trigger early stop
    },
    steps=[
        WorkflowStep(
            name="validate",
            handler=validate_data  # Custom function
        ),
        WorkflowStep(
            name="process",
            action="Process the validated data."  # Won't run if validation fails
        ),
        WorkflowStep(
            name="report",
            action="Generate final report."  # Won't run if validation fails
        )
    ]
)

if __name__ == "__main__":
    manager = WorkflowManager()
    manager.workflows["Data Processing"] = workflow
    
    # Test with invalid data (will stop early)
    print("=== Testing with invalid data ===")
    result = manager.execute("Data Processing", default_llm="gpt-4o-mini")
    
    for step_result in result["results"]:
        print(f"  {step_result['step']}: {step_result['output']}")
    
    # Test with valid data (will complete)
    print("\n=== Testing with valid data ===")
    workflow.variables["data"] = {"value": 42}
    result = manager.execute("Data Processing", default_llm="gpt-4o-mini")
    
    for step_result in result["results"]:
        print(f"  {step_result['step']}: {step_result['status']}")
