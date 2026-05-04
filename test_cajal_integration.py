#!/usr/bin/env python3
"""Simple test script for CAJAL integration."""

import sys
import os

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

def test_import():
    """Test importing ScientificWriterAgent."""
    try:
        from praisonaiagents import ScientificWriterAgent, PaperSection, ScientificPaper
        print("✅ Successfully imported all ScientificWriter classes")
        return True
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return False

def test_instantiation():
    """Test creating a ScientificWriterAgent instance."""
    try:
        from praisonaiagents import ScientificWriterAgent
        
        agent = ScientificWriterAgent(
            name="Test Writer",
            model="gpt-4o-mini"
        )
        
        print("✅ Successfully created ScientificWriterAgent")
        print(f"   Name: {agent.agent.name}")
        print(f"   Is CAJAL: {agent.is_cajal_model}")
        print(f"   Model: {agent.model_name}")
        return True
    except Exception as e:
        print(f"❌ Instantiation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_cajal_model_detection():
    """Test CAJAL model detection."""
    try:
        from praisonaiagents import ScientificWriterAgent
        
        # Test with CAJAL model
        cajal_agent = ScientificWriterAgent(model="cajal-4b")
        assert cajal_agent.is_cajal_model == True
        print("✅ CAJAL model correctly detected")
        
        # Test with non-CAJAL model
        regular_agent = ScientificWriterAgent(model="gpt-4o-mini")
        assert regular_agent.is_cajal_model == False
        print("✅ Non-CAJAL model correctly detected")
        
        return True
    except Exception as e:
        print(f"❌ Model detection test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("Testing CAJAL Scientific Writer Integration")
    print("=" * 50)
    
    success = True
    
    # Test 1: Import
    print("\n1. Testing imports...")
    success &= test_import()
    
    # Test 2: Instantiation
    print("\n2. Testing instantiation...")
    success &= test_instantiation()
    
    # Test 3: Model detection
    print("\n3. Testing model detection...")
    success &= test_cajal_model_detection()
    
    print("\n" + "=" * 50)
    if success:
        print("✅ All tests passed! CAJAL integration is working.")
    else:
        print("❌ Some tests failed.")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)