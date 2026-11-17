#!/usr/bin/env python3
"""
Detailed test of PostHog integration showing why events might not be sent.
"""

import os
import sys
import time

# Ensure telemetry is enabled
for var in ['PRAISONAI_TELEMETRY_DISABLED', 'PRAISONAI_DISABLE_TELEMETRY', 'DO_NOT_TRACK']:
    if var in os.environ:
        del os.environ[var]

print("=== Detailed PostHog Test ===")

# Test PostHog directly
print("\n1. Testing PostHog directly:")
try:
    from posthog import Posthog
    
    # Create a PostHog client directly
    posthog_client = Posthog(
        project_api_key='phc_skZpl3eFLQJ4iYjsERNMbCO6jfeSJi2vyZlPahKgxZ7',
        host='https://eu.i.posthog.com'
    )
    
    # Send a test event
    print("  Sending test event...")
    posthog_client.capture(
        distinct_id='test-user-123',
        event='direct_test_event',
        properties={
            'test': True,
            'timestamp': time.time()
        }
    )
    
    # Flush to ensure event is sent
    print("  Flushing...")
    posthog_client.flush()
    
    print("✓ Direct PostHog test completed")
    
except Exception as e:
    print(f"✗ Direct PostHog test failed: {e}")
    import traceback
    traceback.print_exc()

# Test telemetry integration
print("\n2. Testing telemetry integration:")
from praisonaiagents.telemetry.telemetry import MinimalTelemetry

# Create a new telemetry instance with debug output
class DebugTelemetry(MinimalTelemetry):
    def flush(self):
        """Override flush to add debug output."""
        if not self.enabled:
            print("  [DEBUG] Telemetry disabled, skipping flush")
            return
            
        metrics = self.get_metrics()
        print(f"  [DEBUG] Flushing metrics: {metrics}")
        
        # Check PostHog client
        if hasattr(self, '_posthog') and self._posthog:
            print("  [DEBUG] PostHog client exists")
            print(f"  [DEBUG] PostHog API key: {self._posthog.api_key[:20]}...")
            print(f"  [DEBUG] PostHog host: {self._posthog.host}")
            
            try:
                # Send events
                print("  [DEBUG] Sending sdk_used event...")
                self._posthog.capture(
                    distinct_id='anonymous',
                    event='sdk_used',
                    properties={
                        'version': self._environment['framework_version'],
                        'os': self._environment['os_type'],
                        'python_version': self._environment['python_version'],
                        'session_id': self.session_id,
                        'metrics': self._metrics,
                        '$process_person_profile': False
                    }
                )
                
                print("  [DEBUG] Sending test event...")
                self._posthog.capture('test-id', 'test-event')
                
                # Explicitly flush PostHog
                print("  [DEBUG] Flushing PostHog client...")
                self._posthog.flush()
                
                print("  [DEBUG] PostHog flush completed")
            except Exception as e:
                print(f"  [DEBUG] PostHog error: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("  [DEBUG] No PostHog client available")
        
        # Reset counters
        for key in self._metrics:
            if isinstance(self._metrics[key], int):
                self._metrics[key] = 0

# Create debug telemetry instance
telemetry = DebugTelemetry(enabled=True)

# Track some events
print("\n3. Tracking events:")
telemetry.track_agent_execution("TestAgent", success=True)
telemetry.track_task_completion("TestTask", success=True)
telemetry.track_tool_usage("calculator", success=True)
print("✓ Events tracked")

# Flush with debug output
print("\n4. Flushing telemetry:")
telemetry.flush()

# Wait a moment for async operations
print("\n5. Waiting for async operations...")
time.sleep(2)

print("\n=== Test Complete ===")

# Additional debug info
print("\n6. Debug information:")
print(f"  POSTHOG_AVAILABLE: {telemetry.logger.parent.manager.loggerDict.get('posthog', 'Not found')}")
print(f"  Telemetry module location: {MinimalTelemetry.__module__}")

# Check if PostHog is properly installed
print("\n7. PostHog installation check:")
try:
    import posthog
    print(f"  PostHog version: {posthog.VERSION}")
    print(f"  PostHog location: {posthog.__file__}")
except Exception as e:
    print(f"  PostHog check failed: {e}")