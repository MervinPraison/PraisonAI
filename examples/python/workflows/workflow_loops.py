"""
Workflow Loops Example

Demonstrates iterating over a list of items in a workflow step.
Each item is processed individually with the loop variable.
"""

from praisonaiagents import AgentFlow, Task

# Create a workflow with loop
workflow = AgentFlow(
    name="Process Items",
    description="Process a list of items using loop",
    variables={
        "items": ["apple", "banana", "cherry"]  # List to iterate over
    },
    steps=[
        Task(
            name="process_each",
            action="Describe the fruit: {{item}}",
            loop_over="items",  # Variable name containing the list
            loop_var="item"     # Variable name for current item
        ),
        Task(
            name="summarize",
            action="Summarize all the fruits that were processed."
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
        out = step.get("output")
        if isinstance(out, list):
            print(f"    Loop processed {len(out)} items")
