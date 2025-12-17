"""
Workflow Parallel Execution Example

Demonstrates running multiple steps concurrently and
combining their results.
"""

from praisonaiagents import Workflow, WorkflowContext, StepResult
from praisonaiagents.workflows import parallel
import time

# Parallel workers - each does independent work
def research_market(ctx: WorkflowContext) -> StepResult:
    """Research market trends."""
    time.sleep(0.1)  # Simulate work
    return StepResult(output="📊 Market: Growth expected 15% YoY")

def research_competitors(ctx: WorkflowContext) -> StepResult:
    """Research competitor analysis."""
    time.sleep(0.1)  # Simulate work
    return StepResult(output="🏢 Competitors: 3 major players identified")

def research_customers(ctx: WorkflowContext) -> StepResult:
    """Research customer feedback."""
    time.sleep(0.1)  # Simulate work
    return StepResult(output="👥 Customers: 85% satisfaction rate")

# Aggregator - combines parallel results
def summarize_research(ctx: WorkflowContext) -> StepResult:
    """Summarize all research findings."""
    outputs = ctx.variables.get("parallel_outputs", [])
    summary = "📋 RESEARCH SUMMARY:\n" + "\n".join(f"  • {o}" for o in outputs)
    return StepResult(output=summary)

# Create workflow with parallel execution
workflow = Workflow(
    name="Parallel Research",
    steps=[
        parallel([research_market, research_competitors, research_customers]),
        summarize_research
    ]
)

if __name__ == "__main__":
    print("=== Testing Parallel Workflow ===\n")
    
    start_time = time.time()
    result = workflow.start("Analyze the business landscape", verbose=True)
    elapsed = time.time() - start_time
    
    print(f"\nFinal Output:\n{result['output']}")
    print(f"\nCompleted in {elapsed:.2f}s (parallel execution)")
    print(f"Individual outputs: {len(result['variables']['parallel_outputs'])}")
