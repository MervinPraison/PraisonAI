"""
Workflow Loop with CSV Example

Demonstrates iterating over a CSV file, processing each row.
"""

from praisonaiagents import Workflow, WorkflowContext, StepResult
from praisonaiagents.workflows import loop
import tempfile
import os

# Create sample CSV file
csv_content = """name,email,task
Alice,alice@example.com,Write documentation
Bob,bob@example.com,Review pull requests
Charlie,charlie@example.com,Fix critical bug
Diana,diana@example.com,Deploy to production"""

# Processor for each CSV row
def process_task(ctx: WorkflowContext) -> StepResult:
    """Process a single task from CSV."""
    item = ctx.variables.get("item", {})
    name = item.get("name", "Unknown")
    task = item.get("task", "No task")
    index = ctx.variables.get("loop_index", 0)
    
    return StepResult(
        output=f"[{index+1}] {name}: {task} ✅",
        variables={"last_processed": name}
    )

if __name__ == "__main__":
    # Create temp CSV file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write(csv_content)
        csv_path = f.name
    
    try:
        print("=== Testing Loop with CSV ===\n")
        print(f"CSV file: {csv_path}\n")
        
        # Create workflow
        workflow = Workflow(
            name="CSV Task Processor",
            steps=[loop(process_task, from_csv=csv_path)]
        )
        
        result = workflow.start("Process all tasks", verbose=True)
        
        print(f"\nAll outputs:\n{result['output']}")
        print(f"\nProcessed {len(result['variables']['loop_outputs'])} items")
        print(f"Last processed: {result['variables'].get('last_processed')}")
        
    finally:
        os.unlink(csv_path)
