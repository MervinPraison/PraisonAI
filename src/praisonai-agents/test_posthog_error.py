#!/usr/bin/env python3
"""
Test PostHog initialization error.
"""

from posthog import Posthog

print("Testing PostHog initialization with telemetry parameters...")
try:
    posthog_client = Posthog(
        project_api_key='phc_skZpl3eFLQJ4iYjsERNMbCO6jfeSJi2vyZlPahKgxZ7',
        host='https://eu.i.posthog.com',
        disable_geoip=True,
        events_to_ignore=['test-event']
    )
    print(f"✅ PostHog client created: {posthog_client}")
except Exception as e:
    print(f"❌ PostHog initialization failed: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()