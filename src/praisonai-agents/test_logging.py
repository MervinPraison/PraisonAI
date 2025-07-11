#!/usr/bin/env python3
"""Test script to verify logging is working correctly with LOGLEVEL environment variable"""

import os
import sys
import logging

# Test 1: Show current environment variable
print(f"Current LOGLEVEL environment variable: {os.environ.get('LOGLEVEL', 'Not set')}")

# Test 2: Import praisonaiagents and check logging level
print("\nImporting praisonaiagents...")
import praisonaiagents

print(f"Root logger level after import: {logging.getLevelName(logging.getLogger().getEffectiveLevel())}")

# Test 3: Create a test agent and check its logging
print("\nCreating test agent...")
from praisonaiagents import Agent

agent = Agent(
    name="TestAgent",
    role="Logger Tester",
    goal="Test if logging works",
    backstory="I am a test agent created to verify logging functionality"
)

# Test 4: Test different log levels
print("\nTesting different log levels:")
test_logger = logging.getLogger(__name__)

test_logger.debug("This is a DEBUG message - should show only when LOGLEVEL=DEBUG")
test_logger.info("This is an INFO message - should show when LOGLEVEL=INFO or DEBUG")
test_logger.warning("This is a WARNING message - should always show")
test_logger.error("This is an ERROR message - should always show")

print("\nTest complete! Check above for log messages based on your LOGLEVEL setting.")
print("\nTo test different levels, run:")
print("  export LOGLEVEL=DEBUG && python test_logging.py")
print("  export LOGLEVEL=INFO && python test_logging.py")
print("  export LOGLEVEL=WARNING && python test_logging.py")