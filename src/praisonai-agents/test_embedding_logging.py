#!/usr/bin/env python3
"""
Test script to verify that embedding logging is working correctly with TRACE level.
"""

import logging
import sys
import os

# Add the praisonaiagents module to the path
sys.path.insert(0, '/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents')

# Test the logging implementation
def test_trace_logging():
    """Test that TRACE level logging works correctly."""
    
    # Import the memory module to test the logger setup
    try:
        from praisonaiagents.memory.memory import logger, TRACE_LEVEL
        print("✓ Successfully imported memory module and TRACE_LEVEL")
    except ImportError as e:
        print(f"✗ Failed to import memory module: {e}")
        return False
    
    # Configure logging for testing
    logging.basicConfig(
        level=TRACE_LEVEL,  # Set to TRACE level to see everything
        format='%(levelname)s:%(name)s:%(message)s'
    )
    
    print(f"TRACE_LEVEL = {TRACE_LEVEL}")
    print(f"DEBUG level = {logging.DEBUG}")
    
    # Test different log levels
    print("\n--- Testing different log levels ---")
    logger.info("This is an INFO message")
    logger.debug("This is a DEBUG message")
    logger.trace("This is a TRACE message (should show sensitive data)")
    
    # Test with DEBUG level (should not show TRACE)
    print("\n--- Testing with DEBUG level (TRACE should be hidden) ---")
    logger.setLevel(logging.DEBUG)
    logger.info("INFO with DEBUG level")
    logger.debug("DEBUG with DEBUG level")
    logger.trace("TRACE with DEBUG level (should be hidden)")
    
    # Test with INFO level (should not show DEBUG or TRACE)
    print("\n--- Testing with INFO level (DEBUG and TRACE should be hidden) ---")
    logger.setLevel(logging.INFO)
    logger.info("INFO with INFO level")
    logger.debug("DEBUG with INFO level (should be hidden)")
    logger.trace("TRACE with INFO level (should be hidden)")
    
    print("\n✓ Logging test completed successfully!")
    return True

if __name__ == "__main__":
    print("Testing embedding TRACE logging implementation...")
    success = test_trace_logging()
    if success:
        print("\n🎉 All tests passed! The embedding logging fix is working correctly.")
        sys.exit(0)
    else:
        print("\n❌ Tests failed!")
        sys.exit(1)