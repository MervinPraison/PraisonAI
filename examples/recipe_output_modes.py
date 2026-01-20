"""
Recipe Output Modes Example

Demonstrates how to use different output modes when running recipes.
Output modes control the verbosity and format of execution feedback.

Available modes:
- silent: No output (default, best performance)
- status: Shows tool calls inline
- trace: Timestamped execution trace
- verbose: Full interactive output with panels
- debug: Trace + metrics (tokens, cost, model)
- json: Machine-readable JSONL events

CLI Usage:
    praisonai recipe run my-recipe --output status
    praisonai recipe run my-recipe --output trace
    praisonai recipe run my-recipe -v  # alias for --output verbose
"""

from praisonai.recipe import run


def example_silent_mode():
    """Silent mode - no output, best performance."""
    print("=== Silent Mode (default) ===")
    result = run(
        "my-recipe",
        input={"query": "Hello"},
        options={"output": "silent"}
    )
    print(f"Result: {result}")


def example_status_mode():
    """Status mode - shows tool calls inline."""
    print("\n=== Status Mode ===")
    print("Shows: ▸ tool → result ✓")
    result = run(
        "my-recipe",
        input={"query": "Hello"},
        options={"output": "status"}
    )
    print(f"Result: {result}")


def example_trace_mode():
    """Trace mode - timestamped execution trace."""
    print("\n=== Trace Mode ===")
    print("Shows: [HH:MM:SS] ▸ tool → result [0.2s] ✓")
    result = run(
        "my-recipe",
        input={"query": "Hello"},
        options={"output": "trace"}
    )
    print(f"Result: {result}")


def example_verbose_mode():
    """Verbose mode - full interactive output with panels."""
    print("\n=== Verbose Mode ===")
    result = run(
        "my-recipe",
        input={"query": "Hello"},
        options={"output": "verbose"}
    )
    print(f"Result: {result}")


def example_backward_compat():
    """Backward compatibility - verbose flag maps to output='verbose'."""
    print("\n=== Backward Compatibility ===")
    print("Using verbose=True (deprecated, use output='verbose' instead)")
    result = run(
        "my-recipe",
        input={"query": "Hello"},
        options={"verbose": True}  # Maps to output="verbose"
    )
    print(f"Result: {result}")


if __name__ == "__main__":
    print(__doc__)
    print("Note: These examples require a recipe named 'my-recipe' to be available.")
    print("Create one with: praisonai recipe init my-recipe")
    print()
    
    # Uncomment to run examples:
    # example_silent_mode()
    # example_status_mode()
    # example_trace_mode()
    # example_verbose_mode()
    # example_backward_compat()
