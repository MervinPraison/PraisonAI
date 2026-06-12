#!/usr/bin/env python3
"""Debug script to understand session isolation issue."""

import sys
import os
sys.path.insert(0, 'src/praisonai')

def test_session_isolation():
    print("=== Testing Session Isolation Debug ===")
    
    # Import required modules
    try:
        from praisonai.integration import host_app
        print("✓ host_app imported")
    except ImportError as e:
        print(f"✗ Failed to import host_app: {e}")
        return
    
    try:
        # Reset configuration
        host_app.reset_configuration()
        print("✓ reset_configuration() called")
        
        # Check if configured
        is_configured_before = host_app.is_configured()
        print(f"✓ is_configured before build_host_app: {is_configured_before}")
        
        # Try to build host app  
        app = host_app.build_host_app(pages=["chat"])
        print("✓ build_host_app() succeeded")
        
        # Check if configured after
        is_configured_after = host_app.is_configured()
        print(f"✓ is_configured after build_host_app: {is_configured_after}")
        
    except Exception as e:
        print(f"✗ Error during host app setup: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_session_isolation()