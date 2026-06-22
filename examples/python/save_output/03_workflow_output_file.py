"""
Example 3: Save Agent Output Using Workflow output_file

Workflow step output is automatically saved with variable substitution.
"""

from praisonaiagents import Agent, AgentFlow, Task

# Define workflow with output_file
workflow_config = {
    "metadata": {
        "name": "content-generator",
        "version": "1.0"
    },
    "variables": {
        "output_dir": "generated",
        "topic": "Python programming"
    },
    "agents": {
        "writer": {
            "role": "Content Writer",
            "goal": "Create engaging content",
            "llm": "gpt-4o-mini"
        }
    },
    "steps": [
        {
            "agent": "writer",
            "action": "Write a short tutorial about Python basics",
            "expected_output": "A beginner-friendly tutorial",
            "output_file": "{{output_dir}}/tutorial.md"
        }
    ]
}

# Build agent and workflow from config dict
writer_cfg = workflow_config["agents"]["writer"]
writer = Agent(
    name="writer",
    role=writer_cfg["role"],
    goal=writer_cfg["goal"],
    llm=writer_cfg["llm"],
)

step_cfg = workflow_config["steps"][0]
workflow = AgentFlow(
    name=workflow_config["metadata"]["name"],
    variables=workflow_config["variables"],
    steps=[
        Task(
            name="write_tutorial",
            description=step_cfg["action"],
            expected_output=step_cfg["expected_output"],
            output_file=step_cfg["output_file"],
            agent=writer,
        )
    ],
)
result = workflow.start()

print("✅ Workflow completed!")
print("Output saved to: generated/tutorial.md")
