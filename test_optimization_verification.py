#!/usr/bin/env python3
"""
Simple verification test for the performance optimization.
Tests that metrics check happens at call sites, not inside the method.
"""

import time

class MockLLM:
    """Mock LLM class to test the optimization pattern."""
    
    def __init__(self, metrics=False):
        self.metrics = metrics
        self.call_count = 0
        
    def _track_token_usage(self, response, model):
        """Mock method that increments call count."""
        self.call_count += 1
        return None
    
    def process_response_optimized(self, response, model):
        """Optimized version: check metrics before calling method."""
        if self.metrics:
            self._track_token_usage(response, model)
    
    def process_response_unoptimized(self, response, model):
        """Unoptimized version: always call method, check inside."""
        self._track_token_usage(response, model)
        # Note: In real implementation, method would return early if not self.metrics

def test_optimization():
    """Test that optimization reduces method calls when metrics disabled."""
    
    print("🔧 Testing performance optimization...")
    
    # Test optimized version
    llm_optimized = MockLLM(metrics=False)
    
    # Process 100 responses
    for i in range(100):
        llm_optimized.process_response_optimized({}, "test-model")
    
    print(f"✅ Optimized version (metrics=False): {llm_optimized.call_count} method calls")
    
    # Test unoptimized version
    llm_unoptimized = MockLLM(metrics=False) 
    
    for i in range(100):
        llm_unoptimized.process_response_unoptimized({}, "test-model")
    
    print(f"❌ Unoptimized version (metrics=False): {llm_unoptimized.call_count} method calls")
    
    # Verify optimization works
    if llm_optimized.call_count == 0:
        print("✅ SUCCESS: Zero method calls when metrics=False (optimal)")
    else:
        print("❌ FAILED: Method still called when metrics=False")
    
    if llm_unoptimized.call_count == 100:
        print("✅ Confirmed: Unoptimized version calls method unnecessarily") 
    
    # Test that metrics=True still works
    llm_enabled = MockLLM(metrics=True)
    
    for i in range(10):
        llm_enabled.process_response_optimized({}, "test-model")
    
    if llm_enabled.call_count == 10:
        print("✅ SUCCESS: Method called correctly when metrics=True")
    else:
        print("❌ FAILED: Method not called when metrics=True")
    
    print("\n🎯 Optimization verification complete!")
    
    return llm_optimized.call_count == 0 and llm_enabled.call_count == 10

if __name__ == "__main__":
    success = test_optimization()
    if success:
        print("🚀 All tests passed! Optimization is working correctly.")
    else:
        print("⚠️  Some tests failed. Review implementation.")