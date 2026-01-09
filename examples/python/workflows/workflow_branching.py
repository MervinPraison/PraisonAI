"""
Workflow Branching Example

Demonstrates conditional branching in workflows where steps can route
to different next steps based on output content.
"""

from praisonaiagents import Workflow, WorkflowStep
from praisonaiagents.workflows import WorkflowManager

# Create a workflow with branching
workflow = Workflow(
    name="Decision Workflow",
    description="A workflow that branches based on validation result",
    steps=[
        WorkflowStep(
            name="validate",
            action="Check if the number 42 is positive. Reply with 'valid' or 'invalid'.",
            routing={
                "next_steps": ["success_handler", "error_handler"],
                "branches": {
                    "valid": ["success_handler"],
                    "invalid": ["error_handler"]
                }
            }
        ),
        WorkflowStep(
            name="success_handler",
            action="The validation passed! Generate a success message."
        ),
        WorkflowStep(
            name="error_handler",
            action="The validation failed. Generate an error message."
        )
    ]
)

if __name__ == "__main__":
    # Create manager and register workflow
    manager = WorkflowManager()
    manager.workflows["Decision Workflow"] = workflow
    
    # Execute - will branch to success_handler since 42 is positive
    result = manager.execute(
        "Decision Workflow",
        default_llm="gpt-4o-mini"
    )
    
    print("Workflow completed!")
    for step_result in result["results"]:
        print(f"  {step_result['step']}: {step_result['status']}")
