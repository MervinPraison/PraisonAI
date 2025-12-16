"""
Workflow Checkpoints Example

Demonstrates saving and resuming workflow execution using checkpoints.
Useful for long-running workflows that may be interrupted.
"""

from praisonaiagents.memory.workflows import WorkflowManager, WorkflowStep, Workflow

# Create a multi-step workflow
workflow = Workflow(
    name="Long Process",
    description="A workflow with checkpoints for resumability",
    steps=[
        WorkflowStep(
            name="step1",
            action="Initialize the process and prepare data."
        ),
        WorkflowStep(
            name="step2", 
            action="Process the first batch of data."
        ),
        WorkflowStep(
            name="step3",
            action="Process the second batch of data."
        ),
        WorkflowStep(
            name="step4",
            action="Finalize and generate report."
        )
    ]
)

if __name__ == "__main__":
    manager = WorkflowManager()
    manager.workflows["Long Process"] = workflow
    
    # Execute with checkpoint - saves after each step
    print("=== Starting workflow with checkpoint ===")
    result = manager.execute(
        "Long Process",
        default_llm="gpt-4o-mini",
        checkpoint="my-checkpoint"  # Saves progress after each step
    )
    
    print(f"Completed {len(result['results'])} steps")
    
    # List available checkpoints
    print("\n=== Available checkpoints ===")
    checkpoints = manager.list_checkpoints()
    for cp in checkpoints:
        print(f"  {cp['name']}: {cp['completed_steps']} steps completed")
    
    # Resume from checkpoint (if workflow was interrupted)
    # result = manager.execute(
    #     "Long Process",
    #     default_llm="gpt-4o-mini",
    #     resume="my-checkpoint"  # Resumes from last saved state
    # )
    
    # Clean up checkpoint
    manager.delete_checkpoint("my-checkpoint")
    print("\n✅ Checkpoint deleted")
