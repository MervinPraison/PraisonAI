#!/usr/bin/env python3
"""
AutoGen v0.4 Test Runner

This script runs all AutoGen v0.4 related tests and provides a comprehensive
test report for the new AutoGen v0.4 functionality.
"""

import pytest
import sys
import os
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))

def run_autogen_v4_tests():
    """Run all AutoGen v0.4 tests"""
    
    # Test files to run
    test_files = [
        "tests/unit/test_autogen_v4_integration.py",
        "tests/unit/test_autogen_version_selection.py", 
        "tests/unit/test_autogen_v4_utils.py",
        "tests/unit/test_autogen_backward_compatibility.py",
        "tests/unit/test_autogen_v4_edge_cases.py"
    ]
    
    print("🧪 Running AutoGen v0.4 Test Suite")
    print("=" * 50)
    
    # Run each test file
    for test_file in test_files:
        print(f"\n📋 Running {test_file}...")
        
        # Check if file exists
        if not Path(test_file).exists():
            print(f"❌ Test file {test_file} not found")
            continue
        
        # Run the test
        result = pytest.main([
            test_file,
            "-v",
            "--tb=short",
            "-x"  # Stop on first failure
        ])
        
        if result == 0:
            print(f"✅ {test_file} - PASSED")
        else:
            print(f"❌ {test_file} - FAILED")
            return result
    
    print("\n🎉 All AutoGen v0.4 tests completed successfully!")
    return 0

def run_specific_test_category(category):
    """Run a specific category of tests"""
    category_mapping = {
        "integration": "tests/unit/test_autogen_v4_integration.py",
        "version": "tests/unit/test_autogen_version_selection.py",
        "utils": "tests/unit/test_autogen_v4_utils.py",
        "compatibility": "tests/unit/test_autogen_backward_compatibility.py",
        "edge_cases": "tests/unit/test_autogen_v4_edge_cases.py"
    }
    
    if category not in category_mapping:
        print(f"❌ Unknown category: {category}")
        print(f"Available categories: {', '.join(category_mapping.keys())}")
        return 1
    
    test_file = category_mapping[category]
    print(f"🧪 Running {category} tests from {test_file}")
    
    result = pytest.main([
        test_file,
        "-v",
        "--tb=short"
    ])
    
    return result

def main():
    """Main entry point"""
    if len(sys.argv) > 1:
        category = sys.argv[1]
        return run_specific_test_category(category)
    else:
        return run_autogen_v4_tests()

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)