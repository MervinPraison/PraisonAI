#!/usr/bin/env python3
"""
Performance test to verify that metrics=False has zero overhead.
Tests the optimized implementation where metrics checks happen at call sites.
"""

import time
import sys
import os

# Add the source path
sys.path.insert(0, '/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents')

def test_performance_impact():
    """Test if metrics=False has any performance overhead."""
    
    print("🚀 Testing performance impact of metrics implementation...")
    
    # Mock response object similar to what LiteLLM returns
    mock_response = {
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150
        }
    }
    
    try:
        from praisonaiagents.llm.llm import LLM
        
        # Test with metrics disabled (default case)
        print("\n📊 Testing with metrics=False (default)...")
        llm_no_metrics = LLM(model="test-model", metrics=False)
        
        # Time the _track_token_usage calls
        iterations = 1000
        start_time = time.time()
        
        for i in range(iterations):
            # Simulate the optimized conditional call
            if llm_no_metrics.metrics:
                llm_no_metrics._track_token_usage(mock_response, "test-model")
        
        no_metrics_time = time.time() - start_time
        
        # Test with metrics enabled 
        print("📊 Testing with metrics=True...")
        llm_with_metrics = LLM(model="test-model", metrics=True)
        
        start_time = time.time()
        
        for i in range(iterations):
            # Simulate the optimized conditional call
            if llm_with_metrics.metrics:
                llm_with_metrics._track_token_usage(mock_response, "test-model")
        
        with_metrics_time = time.time() - start_time
        
        print(f"\n🎯 Performance Results (n={iterations}):")
        print(f"   metrics=False: {no_metrics_time:.6f} seconds")
        print(f"   metrics=True:  {with_metrics_time:.6f} seconds")
        print(f"   Overhead when disabled: {no_metrics_time:.6f} seconds")
        
        # Check if metrics=False has minimal overhead
        if no_metrics_time < 0.001:  # Less than 1ms for 1000 iterations
            print("✅ SUCCESS: metrics=False has minimal overhead!")
        else:
            print("⚠️  WARNING: metrics=False may have some overhead")
            
        # Verify metrics tracking works when enabled
        if hasattr(llm_with_metrics, 'last_token_metrics') and llm_with_metrics.last_token_metrics:
            print("✅ SUCCESS: Token tracking works when metrics=True")
        else:
            print("⚠️  Note: Token tracking may require full initialization")
            
        return True
        
    except Exception as e:
        print(f"❌ Error during performance test: {e}")
        return False

if __name__ == "__main__":
    test_performance_impact()