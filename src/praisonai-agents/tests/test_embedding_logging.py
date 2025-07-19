#!/usr/bin/env python3
"""
Test script to verify that embedding logging is working correctly with TRACE level.
This test verifies that the TRACE logging level works as expected for embedding operations.
"""

import logging
import sys
import os
import unittest
from io import StringIO

# Add the praisonaiagents module to the path using relative path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

# Import the memory module to test the logger setup
try:
    from praisonaiagents.memory.memory import logger, TRACE_LEVEL
except ImportError as e:
    print(f"Failed to import memory module: {e}")
    sys.exit(1)


class TestTraceLogging(unittest.TestCase):
    """Test cases for TRACE logging functionality."""
    
    def setUp(self):
        """Set up test environment before each test."""
        # Store original logger level
        self.original_level = logger.level
        # Create a string stream to capture log output
        self.log_capture = StringIO()
        self.handler = logging.StreamHandler(self.log_capture)
        self.handler.setLevel(TRACE_LEVEL)
        self.handler.setFormatter(logging.Formatter('%(levelname)s:%(name)s:%(message)s'))
        logger.addHandler(self.handler)
    
    def tearDown(self):
        """Clean up after each test."""
        # Restore original logger level
        logger.setLevel(self.original_level)
        # Remove the test handler
        logger.removeHandler(self.handler)
        self.handler.close()
    
    def test_trace_level_value(self):
        """Test that TRACE level is set to correct value (5, below DEBUG)."""
        self.assertEqual(TRACE_LEVEL, 5)
        self.assertLess(TRACE_LEVEL, logging.DEBUG)  # TRACE should be below DEBUG (10)
    
    def test_trace_method_exists(self):
        """Test that trace method exists on logger."""
        self.assertTrue(hasattr(logger, 'trace'))
        self.assertTrue(callable(getattr(logger, 'trace')))
    
    def test_trace_logging_at_trace_level(self):
        """Test that TRACE messages are logged when level is set to TRACE."""
        logger.setLevel(TRACE_LEVEL)
        test_message = "Test trace message for embedding data"
        
        logger.trace(test_message)
        
        log_output = self.log_capture.getvalue()
        self.assertIn("TRACE", log_output)
        self.assertIn(test_message, log_output)
    
    def test_trace_hidden_at_debug_level(self):
        """Test that TRACE messages are not logged when level is set to DEBUG."""
        logger.setLevel(logging.DEBUG)
        test_message = "Test trace message should be hidden"
        
        # Clear any previous output
        self.log_capture.truncate(0)
        self.log_capture.seek(0)
        
        logger.trace(test_message)
        
        log_output = self.log_capture.getvalue()
        self.assertNotIn(test_message, log_output)
    
    def test_trace_hidden_at_info_level(self):
        """Test that TRACE messages are not logged when level is set to INFO."""
        logger.setLevel(logging.INFO)
        test_message = "Test trace message should be hidden at INFO"
        
        # Clear any previous output
        self.log_capture.truncate(0)
        self.log_capture.seek(0)
        
        logger.trace(test_message)
        
        log_output = self.log_capture.getvalue()
        self.assertNotIn(test_message, log_output)
    
    def test_debug_still_works_at_debug_level(self):
        """Test that DEBUG messages still work when level is set to DEBUG."""
        logger.setLevel(logging.DEBUG)
        test_message = "Test debug message should be visible"
        
        # Clear any previous output
        self.log_capture.truncate(0)
        self.log_capture.seek(0)
        
        logger.debug(test_message)
        
        log_output = self.log_capture.getvalue()
        self.assertIn("DEBUG", log_output)
        self.assertIn(test_message, log_output)
    
    def test_info_still_works_at_info_level(self):
        """Test that INFO messages still work when level is set to INFO."""
        logger.setLevel(logging.INFO)
        test_message = "Test info message should be visible"
        
        # Clear any previous output
        self.log_capture.truncate(0)
        self.log_capture.seek(0)
        
        logger.info(test_message)
        
        log_output = self.log_capture.getvalue()
        self.assertIn("INFO", log_output)
        self.assertIn(test_message, log_output)
    
    def test_mixed_logging_levels(self):
        """Test multiple log levels working together at TRACE level."""
        logger.setLevel(TRACE_LEVEL)
        
        # Clear any previous output
        self.log_capture.truncate(0)
        self.log_capture.seek(0)
        
        logger.info("Info message")
        logger.debug("Debug message")
        logger.trace("Trace message")
        
        log_output = self.log_capture.getvalue()
        self.assertIn("INFO", log_output)
        self.assertIn("DEBUG", log_output)
        self.assertIn("TRACE", log_output)
        self.assertIn("Info message", log_output)
        self.assertIn("Debug message", log_output)
        self.assertIn("Trace message", log_output)


def run_manual_verification():
    """Run manual verification for visual inspection (can be run standalone)."""
    print("=== Manual Verification of TRACE Logging ===")
    print(f"TRACE_LEVEL = {TRACE_LEVEL}")
    print(f"DEBUG level = {logging.DEBUG}")
    print()
    
    # Configure logging for manual testing
    logging.basicConfig(
        level=TRACE_LEVEL,
        format='%(levelname)s:%(name)s:%(message)s',
        force=True  # Override any existing configuration
    )
    
    print("--- Testing with TRACE level (all messages should show) ---")
    logger.setLevel(TRACE_LEVEL)
    logger.info("This is an INFO message")
    logger.debug("This is a DEBUG message")
    logger.trace("This is a TRACE message (embedding data would be here)")
    
    print("\n--- Testing with DEBUG level (TRACE should be hidden) ---")
    logger.setLevel(logging.DEBUG)
    logger.info("INFO with DEBUG level")
    logger.debug("DEBUG with DEBUG level")
    logger.trace("TRACE with DEBUG level (should be hidden)")
    
    print("\n--- Testing with INFO level (DEBUG and TRACE should be hidden) ---")
    logger.setLevel(logging.INFO)
    logger.info("INFO with INFO level")
    logger.debug("DEBUG with INFO level (should be hidden)")
    logger.trace("TRACE with INFO level (should be hidden)")
    
    print("\n✅ Manual verification completed!")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test embedding TRACE logging implementation")
    parser.add_argument("--manual", action="store_true", help="Run manual verification with visual output")
    args = parser.parse_args()
    
    if args.manual:
        print("Running manual verification...")
        run_manual_verification()
    else:
        print("Running automated tests...")
        # Run the automated tests
        unittest.main(verbosity=2)