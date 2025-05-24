#!/usr/bin/env python3
"""
Comprehensive test runner for PraisonAI Agents

This script runs all tests in an organized manner:
- Unit tests for core functionality
- Integration tests for complex features
- Performance tests for optimization
- Coverage reporting
"""

import pytest
import sys
import os
import subprocess
from pathlib import Path


def run_test_suite():
    """Run the complete test suite with proper organization."""
    
    # Get the project root directory
    project_root = Path(__file__).parent.parent
    tests_dir = project_root / "tests"
    
    print("🧪 Starting PraisonAI Agents Test Suite")
    print("=" * 50)
    
    # Test configuration
    pytest_args = [
        "-v",                    # Verbose output
        "--tb=short",           # Short traceback format
        "--strict-markers",     # Strict marker validation
        "--disable-warnings",   # Disable warnings for cleaner output
    ]
    
    # Add coverage if pytest-cov is available
    try:
        import pytest_cov
        pytest_args.extend([
            "--cov=praisonaiagents",
            "--cov-report=term-missing",
            "--cov-report=html:htmlcov",
            "--cov-report=xml:coverage.xml"
        ])
        print("📊 Coverage reporting enabled")
    except ImportError:
        print("⚠️  pytest-cov not available, skipping coverage")
    
    # Test categories to run
    test_categories = [
        {
            "name": "Unit Tests - Core Functionality",
            "path": str(tests_dir / "unit"),
            "markers": "-m 'not slow'",
            "description": "Fast tests for core agent, task, and LLM functionality"
        },
        {
            "name": "Integration Tests - Complex Features", 
            "path": str(tests_dir / "integration"),
            "markers": "-m 'not slow'",
            "description": "Tests for MCP, RAG, and multi-agent systems"
        },
        {
            "name": "Legacy Tests - Examples",
            "path": str(tests_dir / "test.py"),
            "markers": "",
            "description": "Original example tests"
        }
    ]
    
    # Run each test category
    all_passed = True
    results = []
    
    for category in test_categories:
        print(f"\n🔍 Running: {category['name']}")
        print(f"📝 {category['description']}")
        print("-" * 40)
        
        # Prepare pytest command
        cmd = [sys.executable, "-m", "pytest"] + pytest_args
        
        if category['markers']:
            cmd.append(category['markers'])
        
        cmd.append(category['path'])
        
        try:
            # Run the tests
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=project_root)
            
            if result.returncode == 0:
                print(f"✅ {category['name']}: PASSED")
                results.append((category['name'], "PASSED", result.stdout))
            else:
                print(f"❌ {category['name']}: FAILED")
                results.append((category['name'], "FAILED", result.stderr))
                all_passed = False
                
            # Show some output
            if result.stdout:
                print(result.stdout[-500:])  # Last 500 chars
            if result.stderr and result.returncode != 0:
                print(result.stderr[-500:])  # Last 500 chars of errors
                
        except Exception as e:
            print(f"❌ {category['name']}: ERROR - {e}")
            results.append((category['name'], "ERROR", str(e)))
            all_passed = False
    
    # Summary
    print("\n" + "=" * 50)
    print("📋 TEST SUMMARY")
    print("=" * 50)
    
    for name, status, _ in results:
        status_emoji = "✅" if status == "PASSED" else "❌"
        print(f"{status_emoji} {name}: {status}")
    
    if all_passed:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print("\n💥 Some tests failed!")
        return 1


def run_specific_tests(test_pattern=None, markers=None):
    """Run specific tests based on pattern or markers."""
    
    project_root = Path(__file__).parent.parent
    
    pytest_args = ["-v", "--tb=short"]
    
    if markers:
        pytest_args.extend(["-m", markers])
    
    if test_pattern:
        pytest_args.extend(["-k", test_pattern])
    
    # Add the tests directory
    pytest_args.append(str(project_root / "tests"))
    
    print(f"🔍 Running specific tests with args: {pytest_args}")
    return pytest.main(pytest_args)


def main():
    """Main entry point for the test runner."""
    
    import argparse
    
    parser = argparse.ArgumentParser(description="PraisonAI Agents Test Runner")
    parser.add_argument("--pattern", "-k", help="Run tests matching pattern")
    parser.add_argument("--markers", "-m", help="Run tests with specific markers")
    parser.add_argument("--unit", action="store_true", help="Run only unit tests")
    parser.add_argument("--integration", action="store_true", help="Run only integration tests")
    parser.add_argument("--fast", action="store_true", help="Run only fast tests")
    parser.add_argument("--all", action="store_true", default=True, help="Run all tests (default)")
    
    args = parser.parse_args()
    
    # Handle specific test type requests
    if args.unit:
        return run_specific_tests(markers="not integration and not slow")
    elif args.integration:
        return run_specific_tests(markers="not unit and not slow")
    elif args.fast:
        return run_specific_tests(markers="not slow")
    elif args.pattern or args.markers:
        return run_specific_tests(test_pattern=args.pattern, markers=args.markers)
    else:
        # Run the full test suite
        return run_test_suite()


if __name__ == "__main__":
    sys.exit(main()) 