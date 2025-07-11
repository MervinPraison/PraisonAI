#!/usr/bin/env python3
"""Simple test to demonstrate PraisonAI debug logging"""

import os
import logging

# IMPORTANT: Set LOGLEVEL before importing PraisonAI
os.environ['LOGLEVEL'] = 'DEBUG'

# Now import PraisonAI
from praisonai import PraisonAI
from praisonai.agents_generator import AgentsGenerator

# Configure logging format for better visibility
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True  # Force reconfiguration
)

# Test 1: Direct logger test
print("=" * 60)
print("TEST 1: Testing Python logging directly")
print("=" * 60)

test_logger = logging.getLogger('test')
test_logger.debug("✓ This DEBUG message should be visible")
test_logger.info("✓ This INFO message should be visible")

# Test 2: Test AgentsGenerator logging
print("\n" + "=" * 60)
print("TEST 2: Testing AgentsGenerator logging")
print("=" * 60)

# Create a minimal config
config_yaml = """
framework: praisonai
topic: Test
roles:
  tester:
    role: Tester
    goal: Test logging
    backstory: Test agent
"""

try:
    # This will trigger logging in AgentsGenerator.__init__
    generator = AgentsGenerator(
        agent_yaml=config_yaml,
        framework='praisonai',
        log_level='DEBUG'
    )
    print("✓ AgentsGenerator created - check for debug messages above")
except Exception as e:
    print(f"Note: {e}")
    print("This is expected if praisonai framework is not installed")

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print("\nTo enable debug logging in PraisonAI:")
print("1. Set environment variable: export LOGLEVEL=DEBUG")
print("2. Run your script: python your_script.py")
print("\nThe fix ensures that:")
print("- Logging is configured early in cli.py")
print("- AgentsGenerator doesn't override existing logging config")
print("- Debug messages from all modules are visible")