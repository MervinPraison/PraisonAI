#!/usr/bin/env python3
"""
Simple test runner for PraisonAI Agents
Works without pytest dependency at import time
"""

import sys
import subprocess
from pathlib import Path


def run_tests_with_subprocess():
    """Run tests using subprocess to avoid import issues."""
    
    project_root = Path(__file__).parent.parent
    
    print("🧪 PraisonAI Agents - Simple Test Runner")
    print("=" * 50)
    
    # Test commands to run
    test_commands = [
        {
            "name": "Unit Tests",
            "cmd": [sys.executable, "-m", "pytest", "tests/unit/", "-v", "--tb=short"],
            "description": "Core functionality tests"
        },
        {
            "name": "Integration Tests", 
            "cmd": [sys.executable, "-m", "pytest", "tests/integration/", "-v", "--tb=short"],
            "description": "Complex feature integration tests"
        },
        {
            "name": "Legacy Tests",
            "cmd": [sys.executable, "-m", "pytest", "tests/test.py", "-v", "--tb=short"],
            "description": "Original example tests"
        }
    ]
    
    all_passed = True
    results = []
    
    for test_config in test_commands:
        print(f"\n🔍 Running: {test_config['name']}")
        print(f"📝 {test_config['description']}")
        print("-" * 40)
        
        try:
            result = subprocess.run(
                test_config['cmd'], 
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                print(f"✅ {test_config['name']}: PASSED")
                results.append((test_config['name'], "PASSED"))
                # Show some successful output
                if result.stdout:
                    lines = result.stdout.strip().split('\n')
                    if len(lines) > 0:
                        print(f"📄 {lines[-1]}")  # Show last line
            else:
                print(f"❌ {test_config['name']}: FAILED")
                results.append((test_config['name'], "FAILED"))
                all_passed = False
                
                # Show error details
                if result.stderr:
                    print("Error output:")
                    print(result.stderr[-500:])  # Last 500 chars
                if result.stdout:
                    print("Standard output:")
                    print(result.stdout[-500:])  # Last 500 chars
                    
        except subprocess.TimeoutExpired:
            print(f"⏱️  {test_config['name']}: TIMEOUT")
            results.append((test_config['name'], "TIMEOUT"))
            all_passed = False
        except Exception as e:
            print(f"💥 {test_config['name']}: ERROR - {e}")
            results.append((test_config['name'], "ERROR"))
            all_passed = False
    
    # Summary
    print("\n" + "=" * 50)
    print("📋 TEST SUMMARY")
    print("=" * 50)
    
    for name, status in results:
        if status == "PASSED":
            print(f"✅ {name}: {status}")
        else:
            print(f"❌ {name}: {status}")
    
    if all_passed:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print("\n💥 Some tests failed!")
        return 1


def run_fast_tests():
    """Run only the fastest tests."""
    
    project_root = Path(__file__).parent.parent
    
    print("🏃 Running Fast Tests Only")
    print("=" * 30)
    
    # Try to run a simple Python import test first
    try:
        result = subprocess.run([
            sys.executable, "-c", 
            "import sys; sys.path.insert(0, 'src'); import praisonaiagents; print('✅ Import successful')"
        ], cwd=project_root, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            print("✅ Basic import test: PASSED")
            print(result.stdout.strip())
        else:
            print("❌ Basic import test: FAILED")
            if result.stderr:
                print(result.stderr)
            return 1
            
    except Exception as e:
        print(f"❌ Basic import test: ERROR - {e}")
        return 1
    
    # Run a subset of legacy tests
    try:
        result = subprocess.run([
            sys.executable, "-c",
            """
import sys
sys.path.insert(0, 'src')
sys.path.insert(0, 'tests')

# Try to run basic_example
try:
    from basic_example import basic_agent_example
    result = basic_agent_example()
    print(f'✅ basic_example: {result}')
except Exception as e:
    print(f'❌ basic_example failed: {e}')

# Try to run advanced_example
try:
    from advanced_example import advanced_agent_example  
    result = advanced_agent_example()
    print(f'✅ advanced_example: {result}')
except Exception as e:
    print(f'❌ advanced_example failed: {e}')
            """
        ], cwd=project_root, capture_output=True, text=True, timeout=60)
        
        print("🔍 Fast Example Tests:")
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print("Errors:", result.stderr)
            
        return 0 if result.returncode == 0 else 1
        
    except Exception as e:
        print(f"❌ Fast tests failed: {e}")
        return 1


def main():
    """Main entry point."""
    
    import argparse
    
    parser = argparse.ArgumentParser(description="Simple PraisonAI Test Runner")
    parser.add_argument("--fast", action="store_true", help="Run only fast tests")
    parser.add_argument("--unit", action="store_true", help="Run unit tests via subprocess")
    
    args = parser.parse_args()
    
    if args.fast:
        return run_fast_tests()
    elif args.unit:
        # Run only unit tests
        try:
            result = subprocess.run([
                sys.executable, "-m", "pytest", "tests/unit/", "-v", "--tb=short"
            ], cwd=Path(__file__).parent.parent)
            return result.returncode
        except Exception as e:
            print(f"Failed to run unit tests: {e}")
            return 1
    else:
        return run_tests_with_subprocess()


if __name__ == "__main__":
    sys.exit(main()) 