"""
Basic Workflow Example - Agent-Centric API

Demonstrates minimal workflow with consolidated params.
"""

from praisonaiagents import Agent
from praisonaiagents.workflows import Workflow, WorkflowStep

# Create a simple workflow
workflow = Workflow(
    name="simple_workflow",
    output="verbose",  # Workflow-level output preset
)

# Add a step
step = WorkflowStep(
    name="writer",
    action="Write a haiku about programming",
    agent=Agent(instructions="You are a creative poet."),
    output="result.txt",  # Save output to file
)

# Note: This is a structural example - actual execution requires workflow.run()
print("Workflow created with output preset:", workflow.output)
print("Step output file:", step.output_file)
