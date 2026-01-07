#!/usr/bin/env python3
"""
Context Monitoring Example

Demonstrates how to use the ContextMonitor to write runtime context
snapshots to disk for debugging and analysis.
"""

import os
import tempfile
from praisonaiagents.context import (
    ContextMonitor,
    ContextLedger,
    BudgetAllocation,
    format_human_snapshot,
    format_json_snapshot,
    redact_sensitive,
    ContextSnapshot,
)


def main():
    print("=" * 60)
    print("Context Monitoring Example")
    print("=" * 60)
    
    # Sample conversation for demonstration
    messages = [
        {"role": "system", "content": "You are a helpful AI assistant."},
        {"role": "user", "content": "What is the weather like today?"},
        {"role": "assistant", "content": "I don't have access to real-time weather data."},
        {"role": "user", "content": "Can you help me write Python code?"},
        {"role": "assistant", "content": "Of course! I'd be happy to help with Python."},
    ]
    
    # Example 1: Basic monitoring setup
    print("\n1. Basic Monitor Setup")
    print("-" * 40)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        context_path = os.path.join(tmpdir, "context.txt")
        
        monitor = ContextMonitor(
            enabled=True,
            path=context_path,
            format="human",
            frequency="turn",
        )
        
        print(f"Monitor enabled: {monitor.enabled}")
        print(f"Output path: {context_path}")
        print(f"Format: {monitor.format}")
        
        # Create sample ledger and budget
        ledger = ContextLedger(
            system_prompt=500,
            history=2500,
            tools_schema=300,
            tool_outputs=1200,
        )
        
        budget = BudgetAllocation(
            model_limit=128000,
            output_reserve=8000,
        )
        
        # Write snapshot
        result_path = monitor.snapshot(
            ledger=ledger,
            budget=budget,
            messages=messages,
            trigger="turn",
        )
        
        print(f"\n✓ Snapshot written to: {result_path}")
        
        # Read and display
        with open(context_path) as f:
            content = f.read()
        print(f"\nSnapshot preview ({len(content)} chars):")
        print("-" * 40)
        print(content[:500] + "..." if len(content) > 500 else content)
    
    # Example 2: JSON format
    print("\n\n2. JSON Format Output")
    print("-" * 40)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        json_path = os.path.join(tmpdir, "context.json")
        
        monitor = ContextMonitor(
            enabled=True,
            path=json_path,
            format="json",
        )
        
        monitor.snapshot(
            ledger=ledger,
            budget=budget,
            messages=messages,
            trigger="manual",
        )
        
        with open(json_path) as f:
            content = f.read()
        
        print(f"JSON snapshot ({len(content)} chars):")
        print(content[:300] + "..." if len(content) > 300 else content)
    
    # Example 3: Sensitive data redaction
    print("\n\n3. Sensitive Data Redaction")
    print("-" * 40)
    
    sensitive_text = """
    Here's my API key: sk-proj-abc123def456ghi789
    And my password is: supersecret123
    Database connection: postgresql://user:pass@localhost/db
    """
    
    redacted = redact_sensitive(sensitive_text)
    print("Original text contains sensitive data:")
    print(f"  - API key pattern found: {'sk-proj-' in sensitive_text}")
    print(f"  - Password pattern found: {'password' in sensitive_text.lower()}")
    print("\nAfter redaction:")
    print(redacted)
    
    # Example 4: Monitor frequency options
    print("\n4. Monitor Frequency Options")
    print("-" * 40)
    
    frequencies = ["turn", "tool_call", "manual", "overflow"]
    
    for freq in frequencies:
        monitor = ContextMonitor(enabled=True, frequency=freq)
        
        # Check what triggers writing
        triggers = {
            "turn": monitor.should_write("turn"),
            "tool_call": monitor.should_write("tool_call"),
            "manual": monitor.should_write("manual"),
            "overflow": monitor.should_write("overflow"),
        }
        
        active = [k for k, v in triggers.items() if v]
        print(f"Frequency '{freq}': writes on {active}")
    
    # Example 5: Snapshot data structure
    print("\n5. Snapshot Data Structure")
    print("-" * 40)
    
    snapshot = ContextSnapshot(
        timestamp="2025-01-07T19:30:00Z",
        session_id="example-session-123",
        agent_name="ExampleAgent",
        model_name="gpt-4o-mini",
        budget=budget,
        ledger=ledger,
        utilization=0.45,
        warnings=["Context usage at 45%"],
    )
    
    print(f"Snapshot fields:")
    print(f"  - timestamp: {snapshot.timestamp}")
    print(f"  - session_id: {snapshot.session_id}")
    print(f"  - agent_name: {snapshot.agent_name}")
    print(f"  - model_name: {snapshot.model_name}")
    print(f"  - utilization: {snapshot.utilization:.1%}")
    print(f"  - warnings: {snapshot.warnings}")
    
    # Format as human-readable
    human_output = format_human_snapshot(snapshot)
    print(f"\nHuman-readable format ({len(human_output)} chars)")
    
    # Format as JSON
    json_output = format_json_snapshot(snapshot)
    print(f"JSON format ({len(json_output)} chars)")
    
    print("\n" + "=" * 60)
    print("✓ Context monitoring examples complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
