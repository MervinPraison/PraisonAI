"""
Workflow Branching Example

Demonstrates conditional branching in workflows where steps can route
to different next steps based on output content.
"""

from praisonaiagents import AgentFlow, Task

# Create a workflow with branching
workflow = AgentFlow(
    name="Decision Workflow",
    description="A workflow that branches based on validation result",
    steps=[
        Task(
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
        Task(
            name="success_handler",
            action="The validation passed! Generate a success message."
        ),
        Task(
            name="error_handler",
            action="The validation failed. Generate an error message."
        )
    ]
)

if __name__ == "__main__":
    result = workflow.run("", llm="gpt-4o-mini", verbose=True)
    print("Workflow completed!")
    for step in result.get("steps", []):
        name = step.get("step", step.get("name", "unknown"))
        status = step.get("status", "completed")
        print(f"  {name}: {status}")
