#!/usr/bin/env python3
"""
Simple test to verify thread safety fixes work correctly.
"""

import sys
import os
import contextvars

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from praisonaiagents.main import error_logs, sync_display_callbacks

def test_basic_context_isolation():
    """Test basic context isolation"""
    print("Testing basic context isolation...")
    
    # Clear any existing state
    error_logs.clear()
    sync_display_callbacks.clear()
    
    print(f"Initial error_logs length: {len(error_logs)}")
    
    # Add an error in main context
    error_logs.append("Main context error")
    print(f"After adding main error: {len(error_logs)}")
    
    # Create a new context
    ctx = contextvars.copy_context()
    
    def in_new_context():
        print(f"In new context, error_logs length: {len(error_logs)}")
        error_logs.append("New context error")
        print(f"After adding new context error: {len(error_logs)}")
        return list(error_logs)
    
    result = ctx.run(in_new_context)
    print(f"Result from new context: {result}")
    print(f"Back in main context, error_logs length: {len(error_logs)}")
    print(f"Main context errors: {list(error_logs)}")

if __name__ == "__main__":
    test_basic_context_isolation()