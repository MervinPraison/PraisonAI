#!/usr/bin/env python3
"""
Test import order to debug telemetry availability.
"""

import sys

print("1. Importing telemetry module directly...")
try:
    import praisonaiagents.telemetry
    print("   ✅ Telemetry module imported successfully")
except Exception as e:
    print(f"   ❌ Failed: {type(e).__name__}: {e}")

print("\n2. Importing main praisonaiagents...")
try:
    import praisonaiagents
    print("   ✅ Main module imported successfully")
    print(f"   _telemetry_available: {praisonaiagents._telemetry_available}")
except Exception as e:
    print(f"   ❌ Failed: {type(e).__name__}: {e}")

print("\n3. Checking what prevented telemetry import...")
# The main __init__.py tries to import from .telemetry
# Let's see if we can import the functions directly
try:
    from praisonaiagents.telemetry import (
        get_telemetry,
        enable_telemetry,
        disable_telemetry,
        MinimalTelemetry,
        TelemetryCollector
    )
    print("   ✅ All telemetry functions imported successfully")
except Exception as e:
    print(f"   ❌ Failed to import telemetry functions: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()