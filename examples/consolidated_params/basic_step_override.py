"""Basic example showing step-level override of workflow defaults."""
from praisonaiagents import Agent
from praisonaiagents.workflows import Workflow, WorkflowStep

# Workflow with defaults
workflow = Workflow(
    name="StepOverrideWorkflow",
    steps=[
        WorkflowStep(
            name="step1",
            action="Process with workflow defaults",
            agent=Agent(instructions="You are a processor."),
            # Uses workflow-level web=True (inherited)
        ),
        WorkflowStep(
            name="step2",
            action="Process with step override",
            agent=Agent(instructions="You are a processor."),
            # Override workflow default
            web=False,  # Disable web for this step
            reflection="thorough",  # Use thorough reflection preset
        ),
    ],
    # Workflow defaults
    web=True,
    reflection=True,
)

if __name__ == "__main__":
    print(f"Workflow web default: {workflow.web}")
    print(f"Step1 web: {workflow.steps[0].web}")  # None (uses workflow default)
    print(f"Step2 web: {workflow.steps[1].web}")  # False (overridden)
    print(f"Step2 reflection: {workflow.steps[1].reflection}")  # thorough
