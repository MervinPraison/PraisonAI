#!/usr/bin/env python3
"""Simple test script for runtime system."""

import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(__file__))

def test_runtime_system():
    """Test basic runtime system functionality."""
    try:
        from praisonaiagents.runtime import resolve_runtime, list_runtimes
        
        # Test listing runtimes
        runtimes = list_runtimes()
        print(f"Available runtimes: {runtimes}")
        
        # Test runtime resolution  
        runtime = resolve_runtime('praisonai')
        print(f"Built-in runtime resolved: {type(runtime).__name__}")
        print(f"Runtime supports test: {runtime.supports()}")
        print(f"Runtime supports gpt-4: {runtime.supports('gpt-4')}")
        
        # Test protocol compliance
        assert hasattr(runtime, 'supports')
        assert hasattr(runtime, 'run_turn')
        assert hasattr(runtime, 'stream_turn')
        
        print("✅ Basic runtime system test passed!")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Runtime system error: {e}")
        return False


if __name__ == "__main__":
    success = test_runtime_system()
    sys.exit(0 if success else 1)