#!/usr/bin/env python3
"""
Test registry initialization.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

print("Testing registry initialization...")

# Test direct import
from praisonaiagents.tools.registry import get_registry
print(f"Registry from direct import: {get_registry()}")

# Test import from __init__
try:
    from praisonaiagents.tools import get_registry as get_registry_from_init
    print(f"Registry from __init__ import: {get_registry_from_init()}")
except ImportError as e:
    print(f"Could not import from __init__: {e}")

# Test global instance
from praisonaiagents.tools.registry import _global_registry
print(f"Global registry variable: {_global_registry}")

# Initialize manually
registry = get_registry()
print(f"After manual call: {registry}")
print(f"Registry type: {type(registry)}")
print(f"Registry tools: {registry.list_tools()}")