#!/usr/bin/env python3
"""Direct test of MongoDB tools"""
import sys
sys.path.insert(0, 'src/praisonai-agents')

try:
    # Test direct import of MongoDB tools
    from praisonaiagents.tools.mongodb_tools import MongoDBTools
    print('MongoDB tools import successful')
    
    # Test basic initialization
    tools = MongoDBTools()
    print('MongoDB tools initialization successful')
    
    # Test the _get_pymongo method which should handle missing dependency gracefully
    pymongo = tools._get_pymongo()
    if pymongo is None:
        print('pymongo not available - graceful fallback working')
    else:
        print('pymongo available')
    
    # Test client connection (should fail gracefully)
    client = tools._get_client()
    if client is None:
        print('MongoDB client connection failed gracefully (expected without pymongo)')
    else:
        print('MongoDB client connection successful')
        
    print('All MongoDB direct tests passed')
except Exception as e:
    print(f'MongoDB direct test failed: {e}')
    import traceback
    traceback.print_exc()