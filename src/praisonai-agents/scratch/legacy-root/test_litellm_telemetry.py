#!/usr/bin/env python3
"""Test script to identify litellm telemetry behavior"""

import os
import sys

# Disable litellm telemetry before importing
os.environ["LITELLM_TELEMETRY"] = "False"
os.environ["LITELLM_LOG"] = "ERROR"

print("Environment variables set:")
print(f"LITELLM_TELEMETRY: {os.environ.get('LITELLM_TELEMETRY')}")
print(f"LITELLM_LOG: {os.environ.get('LITELLM_LOG')}")

print("\nImporting litellm...")
import litellm

print(f"\nChecking litellm telemetry status:")
print(f"Has telemetry attribute: {hasattr(litellm, 'telemetry')}")
if hasattr(litellm, 'telemetry'):
    print(f"Telemetry value: {litellm.telemetry}")

# Try to disable telemetry programmatically
if hasattr(litellm, 'telemetry'):
    litellm.telemetry = False
    print(f"\nTelemetry disabled programmatically")

# Check callbacks
print(f"\nCallbacks: {litellm.callbacks}")
print(f"Success callbacks: {litellm.success_callback}")
print(f"Async success callbacks: {litellm._async_success_callback}")

# Test a simple completion
print("\n\nTesting completion (this might trigger telemetry)...")
try:
    response = litellm.completion(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "Say hi"}],
        mock_response="Hi there!"
    )
    print("Completion successful")
except Exception as e:
    print(f"Error: {e}")

print("\nDone. Check if any network requests were made to BerriAI/litellm")