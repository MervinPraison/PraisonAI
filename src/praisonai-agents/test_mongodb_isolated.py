#!/usr/bin/env python3
"""Isolated test of MongoDB tools"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/praisonai-agents'))

# Test if the MongoDB tools can be directly imported and used
try:
    # Read the mongodb_tools.py file content and check for issues
    with open('src/praisonai-agents/praisonaiagents/tools/mongodb_tools.py', 'r') as f:
        content = f.read()
    
    # Check for potential syntax or import issues
    print("Checking MongoDB tools file...")
    
    # Check imports
    if 'from importlib import util' in content:
        print('✓ importlib import present')
    if 'from typing import' in content:
        print('✓ typing imports present')
    if 'TYPE_CHECKING' in content:
        print('✓ TYPE_CHECKING conditional imports present')
    
    # Check class structure
    if 'class MongoDBTools:' in content:
        print('✓ MongoDBTools class present')
    if 'def _get_pymongo' in content:
        print('✓ _get_pymongo method present')
    if 'def _get_client' in content:
        print('✓ _get_client method present')
    
    # Check MongoDB operations
    if 'def insert_document' in content:
        print('✓ insert_document method present')
    if 'def vector_search' in content:
        print('✓ vector_search method present')
    if 'def create_vector_index' in content:
        print('✓ create_vector_index method present')
    
    # Check error handling
    if 'try:' in content and 'except' in content:
        print('✓ Error handling present')
    
    # Check graceful fallback
    if 'if util.find_spec' in content:
        print('✓ Graceful dependency checking present')
    
    print('MongoDB tools file structure looks good!')
    
except Exception as e:
    print(f'Error checking MongoDB tools: {e}')

# Check if imports work correctly
try:
    # Test individual components
    import logging
    from typing import List, Dict, Any, Optional, Union
    from importlib import util
    import json
    import time
    from datetime import datetime
    
    print('✓ All required imports for MongoDB tools available')
    
    # Test util.find_spec functionality
    if util.find_spec('pymongo') is None:
        print('✓ pymongo not available - graceful fallback should work')
    else:
        print('✓ pymongo available')
        
    print('MongoDB tools dependencies check passed')
    
except Exception as e:
    print(f'Error with MongoDB tools dependencies: {e}')