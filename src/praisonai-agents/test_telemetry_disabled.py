#!/usr/bin/env python3
"""Test to verify litellm telemetry is properly disabled"""

import sys
import os

print("Testing litellm telemetry is disabled...")

# Test 1: Check environment variable is set
print(f"\n1. Environment variable LITELLM_TELEMETRY: {os.environ.get('LITELLM_TELEMETRY', 'NOT SET')}")

# Test 2: Import praisonaiagents and check if telemetry is disabled
try:
    from praisonaiagents.llm import LLM
    print("2. Successfully imported LLM from praisonaiagents")
    
    # Check if litellm was imported and telemetry is disabled
    import litellm
    print(f"3. litellm.telemetry = {litellm.telemetry}")
    
    # Test 3: Create an LLM instance
    llm = LLM(model="gpt-3.5-turbo")
    print("4. Successfully created LLM instance")
    
    # Check telemetry again after instance creation
    print(f"5. After LLM creation, litellm.telemetry = {litellm.telemetry}")
    
    # Test 4: Try a mock completion
    print("\n6. Testing mock completion...")
    response = litellm.completion(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "test"}],
        mock_response="test response"
    )
    print("   Mock completion successful")
    
    # Final check
    print(f"\n7. Final check: litellm.telemetry = {litellm.telemetry}")
    
    if litellm.telemetry == False:
        print("\n✅ SUCCESS: Telemetry is properly disabled!")
    else:
        print("\n❌ FAILURE: Telemetry is still enabled!")
        sys.exit(1)
        
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nAll tests passed! Telemetry should be disabled.")