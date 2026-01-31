"""
Workflow Output Modes Example

Demonstrates how to use different output modes with Workflow.
Workflows use the same output presets as Agent for consistency (DRY approach).

Available presets:
- silent: No output (default, fastest)
- status: Tool calls + final output inline
- trace: Timestamped execution trace
- verbose: Full Rich panels
- debug: Trace + metrics
- json: JSONL output for piping
"""

from praisonaiagents import Agent, Workflow


def main():
    # Create a simple agent
    researcher = Agent(
        name="Researcher",
        role="Research Analyst",
        goal="Research and provide information",
        instructions="You are a research analyst. Provide concise, factual information."
    )
    
    # Example 1: Status output (recommended for CLI)
    print("=" * 50)
    print("Example 1: Status Output (output='status')")
    print("=" * 50)
    
    workflow_status = AgentFlow(
        name="Status Example",
        steps=[researcher],
        output="status"  # Shows: ▸ tool → result ✓
    )
    # result = workflow_status.start("What is Python?")
    print("Workflow created with output='status'")
    print(f"  actions_trace: {getattr(workflow_status._output_config, 'actions_trace', False)}")
    print()
    
    # Example 2: Trace output (with timestamps)
    print("=" * 50)
    print("Example 2: Trace Output (output='trace')")
    print("=" * 50)
    
    workflow_trace = AgentFlow(
        name="Trace Example",
        steps=[researcher],
        output="trace"  # Shows: [HH:MM:SS] ▸ tool → result [0.2s] ✓
    )
    print("Workflow created with output='trace'")
    print(f"  status_trace: {getattr(workflow_trace._output_config, 'status_trace', False)}")
    print()
    
    # Example 3: Verbose output (Rich panels)
    print("=" * 50)
    print("Example 3: Verbose Output (output='verbose')")
    print("=" * 50)
    
    workflow_verbose = AgentFlow(
        name="Verbose Example",
        steps=[researcher],
        output="verbose"  # Full interactive display
    )
    print("Workflow created with output='verbose'")
    print(f"  verbose: {getattr(workflow_verbose._output_config, 'verbose', False)}")
    print()
    
    # Example 4: Silent output (default, fastest)
    print("=" * 50)
    print("Example 4: Silent Output (output='silent' or default)")
    print("=" * 50)
    
    workflow_silent = AgentFlow(
        name="Silent Example",
        steps=[researcher],
        output="silent"  # No output - zero overhead
    )
    print("Workflow created with output='silent'")
    print(f"  verbose: {getattr(workflow_silent._output_config, 'verbose', False)}")
    print(f"  actions_trace: {getattr(workflow_silent._output_config, 'actions_trace', False)}")
    print()
    
    # Example 5: JSON output (for piping)
    print("=" * 50)
    print("Example 5: JSON Output (output='json')")
    print("=" * 50)
    
    workflow_json = AgentFlow(
        name="JSON Example",
        steps=[researcher],
        output="json"  # JSONL output for scripting
    )
    print("Workflow created with output='json'")
    print(f"  json_output: {getattr(workflow_json._output_config, 'json_output', False)}")
    print()
    
    print("=" * 50)
    print("All examples completed successfully!")
    print("=" * 50)


if __name__ == "__main__":
    main()
