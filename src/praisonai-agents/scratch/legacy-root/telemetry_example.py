#!/usr/bin/env python3
"""
Example demonstrating the minimal telemetry implementation.
"""

import os
from praisonaiagents.telemetry import get_telemetry, disable_telemetry, enable_telemetry

# Example 1: Default telemetry (enabled unless disabled by environment)
print("=== Example 1: Default Telemetry ===")
telemetry = get_telemetry()
print(f"Telemetry enabled: {telemetry.enabled}")

# Track some events
telemetry.track_agent_execution("TestAgent", success=True)
telemetry.track_task_completion("TestTask", success=True)
telemetry.track_tool_usage("calculator", success=True)
telemetry.track_error("ValueError")
telemetry.track_feature_usage("memory")

# Get metrics
metrics = telemetry.get_metrics()
print(f"Current metrics: {metrics}")

# Example 2: Programmatically disable telemetry
print("\n=== Example 2: Disable Telemetry ===")
disable_telemetry()
telemetry = get_telemetry()
print(f"Telemetry enabled: {telemetry.enabled}")

# These won't be tracked
telemetry.track_agent_execution("TestAgent2", success=True)
metrics = telemetry.get_metrics()
print(f"Metrics after disable: {metrics}")

# Example 3: Re-enable telemetry
print("\n=== Example 3: Re-enable Telemetry ===")
enable_telemetry()
telemetry = get_telemetry()
print(f"Telemetry enabled: {telemetry.enabled}")

# Example 4: Test with environment variable
print("\n=== Example 4: Environment Variable Opt-out ===")
# Simulate environment variable being set
os.environ['PRAISONAI_TELEMETRY_DISABLED'] = 'true'

# Need to create a new instance to pick up the environment change
from importlib import reload
import praisonaiagents.telemetry.telemetry as telemetry_module
reload(telemetry_module)

from praisonaiagents.telemetry import get_telemetry as get_new_telemetry
new_telemetry = get_new_telemetry()
print(f"Telemetry enabled with env var: {new_telemetry.enabled}")

# Clean up
del os.environ['PRAISONAI_TELEMETRY_DISABLED']

# Example 5: Backward compatibility with TelemetryCollector
print("\n=== Example 5: Backward Compatibility ===")
from praisonaiagents.telemetry.telemetry import TelemetryCollector

collector = TelemetryCollector()
collector.start()

# Use context managers (backward compatible interface)
with collector.trace_agent_execution("CompatAgent"):
    print("Executing agent...")
    
with collector.trace_tool_call("web_search"):
    print("Calling tool...")

# Get metrics through collector
collector_metrics = collector.get_metrics()
print(f"Collector metrics: {collector_metrics}")

collector.stop()

print("\n=== Telemetry Example Complete ===")
print("\nPrivacy Notes:")
print("- No personal data, prompts, or responses are collected")
print("- Only anonymous usage metrics are tracked")
print("- Telemetry can be disabled via environment variables:")
print("  - PRAISONAI_TELEMETRY_DISABLED=true")
print("  - PRAISONAI_DISABLE_TELEMETRY=true")
print("  - DO_NOT_TRACK=true")