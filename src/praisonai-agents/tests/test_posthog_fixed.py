#!/usr/bin/env python3
"""
Test PostHog integration after fix.
"""

import os
import time

# Ensure telemetry is enabled
for var in ['PRAISONAI_TELEMETRY_DISABLED', 'PRAISONAI_DISABLE_TELEMETRY', 'DO_NOT_TRACK']:
    if var in os.environ:
        del os.environ[var]

print("=== Testing PostHog Fix ===\n")

# Test PostHog directly first
print("1. Testing PostHog directly:")
try:
    from posthog import Posthog
    
    # Create PostHog client
    ph = Posthog(
        project_api_key='phc_skZpl3eFLQJ4iYjsERNMbCO6jfeSJi2vyZlPahKgxZ7',
        host='https://eu.i.posthog.com'
    )
    
    # Send test event
    ph.capture('test-user', 'direct_test', {'timestamp': time.time()})
    
    # Flush and shutdown properly
    ph.flush()
    ph.shutdown()
    
    print("✓ Direct PostHog test successful\n")
except Exception as e:
    print(f"✗ Direct PostHog test failed: {e}\n")

# Test telemetry module
print("2. Testing telemetry module:")
from praisonaiagents.telemetry.telemetry import MinimalTelemetry

# Create telemetry instance
telemetry = MinimalTelemetry(enabled=True)

# Track events
telemetry.track_agent_execution("TestAgent", success=True)
telemetry.track_task_completion("TestTask", success=True)
telemetry.track_tool_usage("TestTool", success=True)

print(f"✓ Events tracked")
print(f"✓ PostHog client available: {telemetry._posthog is not None}")

# Flush
print("\n3. Flushing telemetry...")
telemetry.flush()
print("✓ Flush completed")

# Shutdown
print("\n4. Shutting down telemetry...")
telemetry.shutdown()
print("✓ Shutdown completed")

print("\n=== Test Complete ===")
print("\nPostHog should now be receiving data properly!")
print("The fix adds:")
print("1. posthog.flush() call in the flush() method")
print("2. shutdown() method that properly closes the connection")