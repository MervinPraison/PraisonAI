#!/usr/bin/env python3
"""Test script to verify PraisonAI logging functionality"""

import os
import logging
import yaml

# Set LOGLEVEL before importing PraisonAI modules
os.environ['LOGLEVEL'] = 'DEBUG'

# Configure logging at the script level to see debug messages
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Import after setting the env var
from praisonai import PraisonAI

# Create a logger for this test script
logger = logging.getLogger(__name__)

def test_basic_logging():
    """Test basic logging functionality"""
    print("=" * 60)
    print("LOGGING TEST - Verifying DEBUG messages are visible")
    print("=" * 60)
    
    print(f"\nEnvironment and Configuration:")
    print(f"- LOGLEVEL environment variable: {os.environ.get('LOGLEVEL', 'NOT SET')}")
    print(f"- Root logger level: {logging.getLevelName(logging.getLogger().getEffectiveLevel())}")
    print(f"- Script logger level: {logging.getLevelName(logger.getEffectiveLevel())}")
    
    print("\n--- Testing direct logging ---")
    logger.debug("✓ DEBUG message from test script is visible")
    logger.info("✓ INFO message from test script is visible")
    logger.warning("✓ WARNING message from test script is visible")
    
    print("\n--- Testing PraisonAI with debug logging ---")
    
    # Create a simple agent configuration as YAML string
    config_yaml = """
framework: praisonai
topic: Test logging functionality
roles:
  test_agent:
    role: Test Agent
    goal: Test the logging system
    backstory: You are a test agent created to verify logging works
    tasks:
      test_task:
        description: Simply output 'Hello, logging test completed successfully!'
        expected_output: A greeting message confirming the test worked
"""
    
    # Write the configuration to a temporary file
    with open('test_agents.yaml', 'w') as f:
        f.write(config_yaml)
    
    try:
        # Initialize PraisonAI with the config file
        praison = PraisonAI(agent_file='test_agents.yaml', framework='praisonai')
        print("\n✓ PraisonAI initialized successfully")
        
        # Run the task
        print("\n--- Running PraisonAI task (watch for DEBUG messages) ---")
        result = praison.run()
        
        if result:
            print(f"\n✓ Task completed with result: {result}")
        else:
            print("\n✓ Task completed")
        
    except Exception as e:
        print(f"\n✗ Error during test: {e}")
        logger.debug("Full error details:", exc_info=True)
    finally:
        # Clean up
        if os.path.exists('test_agents.yaml'):
            os.remove('test_agents.yaml')
            print("\n✓ Cleaned up test configuration file")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE - Check above for DEBUG messages")
    print("=" * 60)

if __name__ == "__main__":
    test_basic_logging()