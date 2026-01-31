"""
Example 3: Save Agent Output Using Workflow output_file

Workflow step output is automatically saved with variable substitution.
"""

from praisonaiagents import AgentFlow

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

# Run workflow
workflow = AgentFlow(config=workflow_config)
result = workflow.run()

print("✅ Workflow completed!")
print("Output saved to: generated/tutorial.md")
