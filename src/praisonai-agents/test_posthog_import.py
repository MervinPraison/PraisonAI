#!/usr/bin/env python3
"""
Test PostHog import and initialization.
"""

print("1. Testing PostHog import...")
try:
    from posthog import Posthog
    print("✅ PostHog imported successfully")
except ImportError as e:
    print(f"❌ PostHog import failed: {e}")
    exit(1)

print("\n2. Testing PostHog initialization...")
try:
    posthog_client = Posthog(
        project_api_key='phc_skZpl3eFLQJ4iYjsERNMbCO6jfeSJi2vyZlPahKgxZ7',
        host='https://eu.i.posthog.com'
    )
    print("✅ PostHog client created successfully")
except Exception as e:
    print(f"❌ PostHog initialization failed: {e}")
    exit(1)

print("\n3. Testing PostHog capture...")
try:
    posthog_client.capture(
        distinct_id='test-user',
        event='test-event',
        properties={'test': True}
    )
    print("✅ PostHog capture successful")
except Exception as e:
    print(f"❌ PostHog capture failed: {e}")

print("\n4. Testing telemetry module...")
from praisonaiagents.telemetry.telemetry import MinimalTelemetry, POSTHOG_AVAILABLE
print(f"POSTHOG_AVAILABLE in telemetry module: {POSTHOG_AVAILABLE}")

print("\n5. Creating MinimalTelemetry instance...")
telemetry = MinimalTelemetry(enabled=True)
print(f"Telemetry enabled: {telemetry.enabled}")
print(f"Telemetry _posthog: {telemetry._posthog}")

print("\n6. Checking get_telemetry()...")
from praisonaiagents.telemetry import get_telemetry
global_telemetry = get_telemetry()
print(f"Global telemetry enabled: {global_telemetry.enabled}")
print(f"Global telemetry _posthog: {global_telemetry._posthog}")
print(f"Global telemetry session_id: {global_telemetry.session_id}")