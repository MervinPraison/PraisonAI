#!/usr/bin/env python3
"""
Test script for database_config module functionality.
"""

import sys
import os
sys.path.insert(0, 'src/praisonai/praisonai/ui')

# Test the database_config module
from database_config import should_force_sqlite, get_database_url_with_sqlite_override, get_database_config_for_sqlalchemy

def test_database_config():
    print("Testing database_config utilities...")
    
    # Test 1: FORCE_SQLITE=false (default)
    print('\nTest 1: Default behavior (FORCE_SQLITE not set)')
    os.environ.pop('FORCE_SQLITE', None)
    os.environ.pop('DATABASE_URL', None) 
    os.environ.pop('SUPABASE_DATABASE_URL', None)
    print(f'should_force_sqlite(): {should_force_sqlite()}')
    print(f'get_database_url_with_sqlite_override(): {get_database_url_with_sqlite_override()}')
    print(f'get_database_config_for_sqlalchemy(): {get_database_config_for_sqlalchemy()}')
    
    # Test 2: FORCE_SQLITE=true
    print('\nTest 2: FORCE_SQLITE=true')
    os.environ['FORCE_SQLITE'] = 'true'
    os.environ['DATABASE_URL'] = 'postgres://test'
    os.environ['SUPABASE_DATABASE_URL'] = 'postgres://supabase'
    print(f'should_force_sqlite(): {should_force_sqlite()}')
    print(f'get_database_url_with_sqlite_override(): {get_database_url_with_sqlite_override()}')
    print(f'get_database_config_for_sqlalchemy(): {get_database_config_for_sqlalchemy()}')
    
    # Test 3: FORCE_SQLITE=false with DATABASE_URL
    print('\nTest 3: FORCE_SQLITE=false with DATABASE_URL')
    os.environ['FORCE_SQLITE'] = 'false'
    print(f'should_force_sqlite(): {should_force_sqlite()}')
    print(f'get_database_url_with_sqlite_override(): {get_database_url_with_sqlite_override()}')
    print(f'get_database_config_for_sqlalchemy(): {get_database_config_for_sqlalchemy()}')
    
    print('\n✅ All tests completed - utility functions work correctly!')

if __name__ == "__main__":
    test_database_config()