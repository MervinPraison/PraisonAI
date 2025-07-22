#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, 'src/praisonai-agents')

print("Testing DEBUG mode functionality...")

def clear_praisonai_modules():
    """Clear all praisonai modules from sys.modules"""
    to_remove = []
    for mod in sys.modules.keys():
        if mod.startswith('praisonaiagents'):
            to_remove.append(mod)
    
    for mod in to_remove:
        del sys.modules[mod]

def test_normal_mode():
    """Test that warnings are suppressed in normal mode"""
    print("\n=== Testing NORMAL mode (LOGLEVEL=INFO) ===")
    os.environ['LOGLEVEL'] = 'INFO'
    
    # Clear modules
    clear_praisonai_modules()
    
    import warnings
    warnings.simplefilter('always')
    
    try:
        import praisonaiagents
        print("✅ Import successful in normal mode")
        
        # Check if warning suppression is active
        should_suppress = praisonaiagents._should_suppress_warnings()
        print(f"✅ Warning suppression active: {should_suppress}")
        
        return should_suppress  # Should be True in normal mode
        
    except Exception as e:
        print(f"❌ Error in normal mode: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_debug_mode():
    """Test that warnings are shown in DEBUG mode"""
    print("\n=== Testing DEBUG mode (LOGLEVEL=DEBUG) ===")
    os.environ['LOGLEVEL'] = 'DEBUG'
    
    # Clear modules
    clear_praisonai_modules()
    
    import warnings
    warnings.simplefilter('always')
    
    try:
        import praisonaiagents
        print("✅ Import successful in debug mode")
        
        # Check if warning suppression is inactive
        should_suppress = praisonaiagents._should_suppress_warnings()
        print(f"✅ Warning suppression active: {should_suppress} (should be False)")
        
        return not should_suppress  # Should be False in debug mode (so we return True if it's correct)
        
    except Exception as e:
        print(f"❌ Error in debug mode: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🧪 Testing DEBUG mode implementation")
    
    # Clean up environment first
    if 'LOGLEVEL' in os.environ:
        del os.environ['LOGLEVEL']
    
    normal_success = test_normal_mode()
    debug_success = test_debug_mode()
    
    print("\n" + "="*50)
    if normal_success and debug_success:
        print("🎉 ALL TESTS PASSED: DEBUG mode functionality works correctly!")
        print("✅ Warnings suppressed in normal mode")
        print("✅ Warnings enabled in DEBUG mode")
    else:
        print("💥 TESTS FAILED: Issues with DEBUG mode implementation")
        print(f"   Normal mode success: {normal_success}")
        print(f"   Debug mode success: {debug_success}")
    
    # Restore normal mode
    os.environ['LOGLEVEL'] = 'INFO'
    
    sys.exit(0 if (normal_success and debug_success) else 1)