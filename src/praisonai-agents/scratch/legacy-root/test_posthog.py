#!/usr/bin/env python3
"""
Test PostHog integration in telemetry.
"""

import os
import sys

# Ensure telemetry is enabled
if 'PRAISONAI_TELEMETRY_DISABLED' in os.environ:
    del os.environ['PRAISONAI_TELEMETRY_DISABLED']
if 'PRAISONAI_DISABLE_TELEMETRY' in os.environ:
    del os.environ['PRAISONAI_DISABLE_TELEMETRY']
if 'DO_NOT_TRACK' in os.environ:
    del os.environ['DO_NOT_TRACK']

# Test PostHog availability
print("=== Testing PostHog Integration ===")
print("\n1. Checking PostHog import:")
try:
    from posthog import Posthog
    print("✓ PostHog is available")
except ImportError as e:
    print("✗ PostHog is NOT available")
    print(f"  Error: {e}")
    print("\n  To fix: pip install posthog")
    sys.exit(1)

# Test telemetry initialization
print("\n2. Testing telemetry initialization:")
from praisonaiagents.telemetry import get_telemetry

telemetry = get_telemetry()
print(f"✓ Telemetry enabled: {telemetry.enabled}")
print(f"✓ Session ID: {telemetry.session_id}")

# Check PostHog client
print("\n3. Checking PostHog client:")
if hasattr(telemetry, '_posthog') and telemetry._posthog:
    print("✓ PostHog client is initialized")
    print(f"  API Key: {telemetry._posthog.api_key[:10]}...")
    print(f"  Host: {telemetry._posthog.host}")
else:
    print("✗ PostHog client is NOT initialized")

# Test tracking
print("\n4. Testing event tracking:")
telemetry.track_agent_execution("TestAgent", success=True)
telemetry.track_task_completion("TestTask", success=True)
telemetry.track_tool_usage("test_tool", success=True)
print("✓ Events tracked locally")

# Test flush (which should send to PostHog)
print("\n5. Testing flush (should send to PostHog):")
telemetry.flush()
print("✓ Flush completed")

# Check metrics
print("\n6. Current metrics:")
metrics = telemetry.get_metrics()
for key, value in metrics.items():
    print(f"  {key}: {value}")

print("\n=== PostHog Test Complete ===")