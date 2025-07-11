#!/usr/bin/env python3
"""
Minimal test script to verify logging functionality.
"""

import os
import sys
import logging

# Set environment variable for DEBUG logging
os.environ['LOGLEVEL'] = 'DEBUG'

# Check which package is available
try:
    # Try praisonai-agents first (newer package)
    from praisonaiagents.main import LOGLEVEL
    print(f"Using praisonaiagents package, LOGLEVEL is set to: {LOGLEVEL}")
    
    # Test logging in the main module
    logger = logging.getLogger('praisonaiagents')
    logger.debug("DEBUG message from praisonaiagents")
    logger.info("INFO message from praisonaiagents")
    logger.warning("WARNING message from praisonaiagents")
    logger.error("ERROR message from praisonaiagents")
    
except ImportError:
    try:
        # Try the older praisonai package
        from praisonai.cli import PraisonAI
        print("Using praisonai package")
        
        # Test logging
        logger = logging.getLogger('praisonai')
        logger.debug("DEBUG message from praisonai")
        logger.info("INFO message from praisonai")
        logger.warning("WARNING message from praisonai")
        logger.error("ERROR message from praisonai")
        
    except ImportError:
        print("Neither praisonaiagents nor praisonai packages are installed.")
        print("Please install with: pip install praisonaiagents")
        sys.exit(1)

# Test root logger
root_logger = logging.getLogger()
print(f"\nRoot logger level: {logging.getLevelName(root_logger.level)}")
print(f"Root logger handlers: {root_logger.handlers}")

# Test if logging is working
print("\n--- Testing logging output ---")
logging.debug("This is a DEBUG message")
logging.info("This is an INFO message")
logging.warning("This is a WARNING message")
logging.error("This is an ERROR message")