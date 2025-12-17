"""
Workflow Routing Example

Demonstrates decision-based routing where the workflow
takes different paths based on the output of a decision step.
"""

from praisonaiagents import Workflow, WorkflowContext, StepResult
from praisonaiagents.workflows import route

# Decision maker - determines which route to take
def classify_request(ctx: WorkflowContext) -> StepResult:
    """Classify the input and decide the route."""
    input_lower = ctx.input.lower()
    
    if "urgent" in input_lower or "emergency" in input_lower:
        return StepResult(output="priority: high")
    elif "question" in input_lower or "help" in input_lower:
        return StepResult(output="priority: support")
    else:
        return StepResult(output="priority: normal")

# Route handlers
def handle_high_priority(ctx: WorkflowContext) -> StepResult:
    return StepResult(output="🚨 HIGH PRIORITY: Escalating to senior team immediately!")

def handle_support(ctx: WorkflowContext) -> StepResult:
    return StepResult(output="💬 SUPPORT: Routing to help desk for assistance.")

def handle_normal(ctx: WorkflowContext) -> StepResult:
    return StepResult(output="📋 NORMAL: Added to standard processing queue.")

# Create workflow with routing
workflow = Workflow(
    name="Request Router",
    steps=[
        classify_request,
        route({
            "high": [handle_high_priority],
            "support": [handle_support],
            "normal": [handle_normal],
            "default": [handle_normal]
        })
    ]
)

if __name__ == "__main__":
    # Test different inputs
    print("=== Testing Routing Workflow ===\n")
    
    # Test 1: Urgent request
    result = workflow.start("This is an URGENT matter!", verbose=True)
    print(f"Result: {result['output']}\n")
    
    # Test 2: Support request
    result = workflow.start("I have a question about my account", verbose=True)
    print(f"Result: {result['output']}\n")
    
    # Test 3: Normal request
    result = workflow.start("Please process my order", verbose=True)
    print(f"Result: {result['output']}")
