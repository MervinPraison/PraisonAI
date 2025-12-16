"""
Mixed Steps Workflow Example

Demonstrates combining different step types in a single workflow:
- Agent instances
- Handler functions
- WorkflowStep with action strings
"""

from praisonaiagents import Workflow, WorkflowStep, WorkflowContext, StepResult, Agent

# Create an agent
analyzer = Agent(
    name="Analyzer",
    role="Data Analyst",
    goal="Analyze and summarize data",
    llm="gpt-4o-mini"
)

# Custom handler functions
def validate_input(ctx: WorkflowContext) -> StepResult:
    """Validate the input before processing."""
    if len(ctx.input) < 5:
        return StepResult(
            output="Input too short. Minimum 5 characters required.",
            stop_workflow=True
        )
    return StepResult(output=f"✅ Valid input: {ctx.input}")

def format_output(ctx: WorkflowContext) -> StepResult:
    """Format the final output."""
    return StepResult(
        output=f"📊 Report:\n{ctx.previous_result}",
        variables={"report_generated": True}
    )

# Create workflow with mixed step types
workflow = Workflow(
    name="Mixed Pipeline",
    steps=[
        # Step 1: Function - validates input
        validate_input,
        
        # Step 2: Agent - analyzes content
        analyzer,
        
        # Step 3: WorkflowStep with action string
        WorkflowStep(
            name="enhance",
            action="Add a conclusion to this analysis: {{previous_output}}"
        ),
        
        # Step 4: Function - formats output
        format_output
    ],
    default_llm="gpt-4o-mini"  # Used for action-based steps
)

if __name__ == "__main__":
    # Test with valid input
    print("=== Running mixed workflow ===")
    result = workflow.start(
        "Analyze the trends in AI adoption for 2024",
        verbose=True
    )
    
    print(f"\nFinal output:\n{result['output']}")
    print(f"\nVariables: {result['variables']}")
