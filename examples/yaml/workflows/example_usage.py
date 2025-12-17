"""
Example usage of YAML Workflow Parser.

This script demonstrates how to load and execute YAML workflow files.
"""

import os
from pathlib import Path

# Ensure OPENAI_API_KEY is set
if not os.getenv("OPENAI_API_KEY"):
    print("Please set OPENAI_API_KEY environment variable")
    print("export OPENAI_API_KEY='your-api-key'")
    exit(1)

from praisonaiagents.workflows import YAMLWorkflowParser, WorkflowManager


def example_1_parse_and_run():
    """Example 1: Parse YAML and run workflow directly."""
    print("=" * 60)
    print("Example 1: Parse YAML and run workflow")
    print("=" * 60)
    
    yaml_content = """
name: Quick Research
description: A quick research workflow

agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    instructions: "Provide brief, factual information."

steps:
  - agent: researcher
    action: "Research: {{input}}"
"""
    
    parser = YAMLWorkflowParser()
    workflow = parser.parse_string(yaml_content)
    
    print(f"Workflow Name: {workflow.name}")
    print(f"Steps: {len(workflow.steps)}")
    
    # Run the workflow
    result = workflow.start("What is Python?")
    print(f"Result: {result['output'][:200]}...")
    print()


def example_2_load_yaml_file():
    """Example 2: Load workflow from YAML file using WorkflowManager."""
    print("=" * 60)
    print("Example 2: Load YAML file with WorkflowManager")
    print("=" * 60)
    
    # Get the directory of this script
    script_dir = Path(__file__).parent
    yaml_file = script_dir / "simple_workflow.yaml"
    
    if not yaml_file.exists():
        print(f"YAML file not found: {yaml_file}")
        return
    
    manager = WorkflowManager()
    workflow = manager.load_yaml(yaml_file)
    
    print(f"Loaded workflow: {workflow.name}")
    print(f"Steps: {len(workflow.steps)}")
    
    # Run the workflow
    result = workflow.start("Benefits of renewable energy")
    print(f"Result: {result['output'][:200]}...")
    print()


def example_3_execute_yaml_directly():
    """Example 3: Execute YAML file directly with WorkflowManager."""
    print("=" * 60)
    print("Example 3: Execute YAML directly")
    print("=" * 60)
    
    script_dir = Path(__file__).parent
    yaml_file = script_dir / "simple_workflow.yaml"
    
    if not yaml_file.exists():
        print(f"YAML file not found: {yaml_file}")
        return
    
    manager = WorkflowManager()
    result = manager.execute_yaml(
        yaml_file,
        input_data="The future of AI",
        verbose=True
    )
    
    print(f"Status: {result['status']}")
    print(f"Result: {result['output'][:200]}...")
    print()


def example_4_with_variables():
    """Example 4: YAML workflow with variables."""
    print("=" * 60)
    print("Example 4: Workflow with variables")
    print("=" * 60)
    
    yaml_content = """
name: Variable Workflow
variables:
  topic: Machine Learning
  style: concise

agents:
  writer:
    name: Writer
    role: Content Writer
    goal: Write content
    instructions: "Write {{style}} content about the topic."

steps:
  - agent: writer
    action: "Write about {{topic}}"
"""
    
    parser = YAMLWorkflowParser()
    workflow = parser.parse_string(yaml_content)
    
    print(f"Variables: {workflow.variables}")
    
    # Run with default variables
    result = workflow.start("")
    print(f"Result: {result['output'][:200]}...")
    print()


if __name__ == "__main__":
    print("YAML Workflow Examples")
    print("=" * 60)
    print()
    
    # Run examples
    example_1_parse_and_run()
    example_2_load_yaml_file()
    example_3_execute_yaml_directly()
    example_4_with_variables()
    
    print("=" * 60)
    print("All examples completed!")
    print("=" * 60)
