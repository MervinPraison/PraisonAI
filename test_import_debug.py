#!/usr/bin/env python3
"""
Debug import issues.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

# Simulate the context inside decorator.py
import logging
logging.basicConfig(level=logging.DEBUG)

# Change to the tools directory context
original_path = sys.path[:]
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents', 'praisonaiagents', 'tools'))

print("Testing imports from decorator context...")

try:
    print("1. Testing relative import...")
    # This simulates what happens in decorator.py
    from registry import get_registry
    registry = get_registry()
    print(f"Relative import successful: {registry}")
except Exception as e:
    print(f"Relative import failed: {e}")

try:
    print("2. Testing absolute import...")
    from praisonaiagents.tools.registry import get_registry
    registry = get_registry()
    print(f"Absolute import successful: {registry}")
except Exception as e:
    print(f"Absolute import failed: {e}")

# Restore path
sys.path[:] = original_path