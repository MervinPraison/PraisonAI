#!/usr/bin/env python3
"""
Debug script to check PostHog availability and configuration.
"""

def check_posthog_availability():
    """Check if PostHog is available and can be imported."""
    print("=== PostHog Availability Test ===")
    
    try:
        import posthog
        print(f"✅ PostHog successfully imported")
        print(f"   Version: {posthog.__version__}")
        print(f"   Location: {posthog.__file__}")
        return True
    except ImportError as e:
        print(f"❌ PostHog import failed: {e}")
        print("   This means PostHog is not installed in your environment")
        return False

def check_telemetry_posthog_init():
    """Check if telemetry can initialize PostHog."""
    print("\n=== Telemetry PostHog Initialization Test ===")
    
    try:
        from praisonaiagents.telemetry.telemetry import MinimalTelemetry
        
        # Create telemetry instance
        telemetry = MinimalTelemetry()
        
        if hasattr(telemetry, '_posthog') and telemetry._posthog:
            print("✅ PostHog client successfully initialized in telemetry")
            return True
        else:
            print("❌ PostHog client is None in telemetry")
            print("   This could be due to:")
            print("   1. PostHog not installed")
            print("   2. PostHog import error")
            print("   3. PostHog initialization error")
            return False
            
    except Exception as e:
        print(f"❌ Error testing telemetry PostHog init: {e}")
        return False

def test_posthog_connection():
    """Test actual PostHog connection."""
    print("\n=== PostHog Connection Test ===")
    
    try:
        from posthog import Posthog
        
        # Initialize PostHog client with same config as telemetry
        posthog_client = Posthog(
            project_api_key='phc_skZpl3eFLQJ4iYjsERNMbCO6jfeSJi2vyZlPahKgxZ7',
            host='https://eu.i.posthog.com',
            disable_geoip=True
        )
        
        # Try to capture a test event
        posthog_client.capture(
            distinct_id='test-user',
            event='debug_test',
            properties={
                'test': True,
                '$process_person_profile': False,
                '$geoip_disable': True
            }
        )
        
        print("✅ PostHog test event sent successfully")
        print("   (Note: This doesn't guarantee delivery, just that the API call succeeded)")
        return True
        
    except Exception as e:
        print(f"❌ PostHog connection test failed: {e}")
        return False

def main():
    """Run all diagnostic tests."""
    print("PostHog Telemetry Diagnostic Tool")
    print("=" * 40)
    
    posthog_available = check_posthog_availability()
    telemetry_posthog_ok = check_telemetry_posthog_init()
    connection_ok = test_posthog_connection() if posthog_available else False
    
    print("\n=== Summary ===")
    print(f"PostHog Available: {'✅' if posthog_available else '❌'}")
    print(f"Telemetry PostHog Init: {'✅' if telemetry_posthog_ok else '❌'}")
    print(f"PostHog Connection: {'✅' if connection_ok else '❌'}")
    
    if not posthog_available:
        print("\n🔧 Solution: Install PostHog")
        print("   pip install posthog>=3.0.0")
        print("   or")
        print("   pip install praisonaiagents[telemetry]")
    elif not telemetry_posthog_ok:
        print("\n🔧 Check telemetry initialization code")
    elif not connection_ok:
        print("\n🔧 Check network connectivity and PostHog configuration")
    else:
        print("\n🎉 Everything looks good! PostHog should be working.")

if __name__ == "__main__":
    main()