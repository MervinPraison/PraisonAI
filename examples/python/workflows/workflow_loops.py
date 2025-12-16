"""
Workflow Loops Example

Demonstrates iterating over a list of items in a workflow step.
Each item is processed individually with the loop variable.
"""

from praisonaiagents.memory.workflows import WorkflowManager, WorkflowStep, Workflow

# Create a workflow with loop
workflow = Workflow(
    name="Process Items",
    description="Process a list of items using loop",
    variables={
        "items": ["apple", "banana", "cherry"]  # List to iterate over
    },
    steps=[
        WorkflowStep(
            name="process_each",
            action="Describe the fruit: {{item}}",
            loop_over="items",  # Variable name containing the list
            loop_var="item"     # Variable name for current item
        ),
        WorkflowStep(
            name="summarize",
            action="Summarize all the fruits that were processed."
        )
    ]
)

if __name__ == "__main__":
    # Create manager and register workflow
    manager = WorkflowManager()
    manager.workflows["Process Items"] = workflow
    
    # Execute - will process each fruit in the list
    result = manager.execute(
        "Process Items",
        default_llm="gpt-4o-mini"
    )
    
    print("Workflow completed!")
    for step_result in result["results"]:
        print(f"  {step_result['step']}: {step_result['status']}")
        if isinstance(step_result.get("output"), list):
            print(f"    Loop processed {len(step_result['output'])} items")
