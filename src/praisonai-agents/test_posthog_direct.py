#!/usr/bin/env python3
"""
Test PostHog integration directly to verify it's working.
"""

import os
from praisonaiagents.telemetry import get_telemetry
from praisonaiagents.telemetry.integration import auto_instrument_all

# Enable automatic telemetry instrumentation
auto_instrument_all()

telemetry = get_telemetry()
print(f"Telemetry enabled: {telemetry.enabled}")
print(f"PostHog available: {telemetry._posthog is not None}")

if telemetry.enabled and telemetry._posthog:
    # Manually track some events
    telemetry.track_agent_execution("TestAgent", success=True)
    telemetry.track_task_completion("TestTask", success=True)
    telemetry.track_tool_usage("TestTool")
    
    # Get metrics before flush
    metrics = telemetry.get_metrics()
    print(f"\nMetrics before flush:")
    print(f"- Agent executions: {metrics['metrics']['agent_executions']}")
    print(f"- Task completions: {metrics['metrics']['task_completions']}")
    print(f"- Tool calls: {metrics['metrics']['tool_calls']}")
    
    # Manually flush to send to PostHog
    print("\nFlushing telemetry to PostHog...")
    telemetry.flush()
    
    # Get metrics after flush (should be reset)
    metrics = telemetry.get_metrics()
    print(f"\nMetrics after flush (should be reset):")
    print(f"- Agent executions: {metrics['metrics']['agent_executions']}")
    print(f"- Task completions: {metrics['metrics']['task_completions']}")
    print(f"- Tool calls: {metrics['metrics']['tool_calls']}")
    
    print("\n✅ If no errors above, PostHog integration is working!")
else:
    print("\n❌ Telemetry or PostHog is not available")