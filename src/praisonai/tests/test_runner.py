#!/usr/bin/env python3
"""
Comprehensive test runner for PraisonAI Agents

This script runs all tests in an organized manner:
- Unit tests for core functionality
- Integration tests for complex features
- Performance tests for optimization
- Coverage reporting
"""

import sys
import os
import subprocess
from pathlib import Path
import argparse


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
    
    try:
        import pytest
        return pytest.main(pytest_args)
    except ImportError:
        print("❌ pytest not available, falling back to subprocess")
        cmd = [sys.executable, "-m", "pytest"] + pytest_args
        result = subprocess.run(cmd)
        return result.returncode


def run_tests(pattern=None, verbose=False, coverage=False):
    """
    Run tests based on the specified pattern
    
    Args:
        pattern: Test pattern to run (unit, integration, fast, all, autogen, crewai, real, etc.)
        verbose: Enable verbose output
        coverage: Enable coverage reporting
    """
    
    # Base pytest command
    cmd = ["python", "-m", "pytest"]
    
    if verbose:
        cmd.append("-v")
    
    if coverage:
        cmd.extend(["--cov=praisonaiagents", "--cov-report=term-missing"])
    
    # Check if this is a real test (requires API keys)
    is_real_test = pattern and ("real" in pattern or pattern.startswith("e2e"))
    
    if is_real_test:
        # Warn about real API calls
        print("⚠️  WARNING: Real tests make actual API calls and may incur costs!")
        
        # Check for API keys
        if not os.getenv("OPENAI_API_KEY"):
            print("❌ OPENAI_API_KEY not set - real tests will be skipped")
            print("💡 Set your API key: export OPENAI_API_KEY='your-key'")
        else:
            print("✅ API key detected - real tests will run")
        
        # Add real test marker
        cmd.extend(["-m", "real"])
    
    # Check if this is a full execution test
    is_full_test = pattern and "full" in pattern
    
    if is_full_test:
        # Add -s flag to see real-time output from praisonai.run()
        cmd.append("-s")
        print("🔥 Full execution mode: Real-time output enabled")
    
    # Add pattern-specific arguments
    if pattern == "unit":
        cmd.append("tests/unit/")
    elif pattern == "integration":
        cmd.append("tests/integration/")
    elif pattern == "autogen":
        cmd.append("tests/integration/autogen/")
    elif pattern == "crewai":
        cmd.append("tests/integration/crewai/")
    elif pattern == "mcp":
        cmd.append("tests/integration/test_mcp_integration.py")
    elif pattern == "rag":
        cmd.append("tests/integration/test_rag_integration.py")
    elif pattern == "real" or pattern == "e2e":
        # Run all real tests
        cmd.append("tests/e2e/")
    elif pattern == "real-autogen":
        # Run real AutoGen tests only
        cmd.append("tests/e2e/autogen/")
    elif pattern == "real-crewai":
        # Run real CrewAI tests only
        cmd.append("tests/e2e/crewai/")
    elif pattern == "fast":
        # Run only fast, non-integration tests
        cmd.extend(["tests/unit/", "-m", "not slow"])
    elif pattern == "all":
        cmd.extend(["tests/", "-m", "not real"])  # Exclude real tests that require API keys
        # Ignore flaky timing-sensitive tests
        cmd.extend([
            "--ignore=tests/unit/cli/test_message_queue.py",
            "--ignore=tests/unit/doctor/test_engine.py",
            "--ignore=tests/unit/mcp_server/test_auth.py",
        ])
        # Allow up to 5 failures without failing the entire run
        cmd.append("--maxfail=10")
    elif pattern == "frameworks":
        # Run both AutoGen and CrewAI integration tests (mock)
        cmd.extend(["tests/integration/autogen/", "tests/integration/crewai/"])
    elif pattern == "real-frameworks":
        # Run both AutoGen and CrewAI real tests
        cmd.extend(["tests/e2e/autogen/", "tests/e2e/crewai/"])
    elif pattern == "full-autogen":
        # Run real AutoGen tests with full execution
        cmd.append("tests/e2e/autogen/")
        os.environ["PRAISONAI_RUN_FULL_TESTS"] = "true"
    elif pattern == "full-crewai":
        # Run real CrewAI tests with full execution
        cmd.append("tests/e2e/crewai/")
        os.environ["PRAISONAI_RUN_FULL_TESTS"] = "true"
    elif pattern == "full-frameworks":
        # Run both AutoGen and CrewAI with full execution
        cmd.extend(["tests/e2e/autogen/", "tests/e2e/crewai/"])
        os.environ["PRAISONAI_RUN_FULL_TESTS"] = "true"
    else:
        # Default to all tests if no pattern specified
        cmd.append("tests/")
    
    # Add additional pytest options
    cmd.extend([
        "--tb=short",
        "--disable-warnings",
        "-x"  # Stop on first failure
    ])
    
    print(f"Running command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=False)
        return result.returncode
    except KeyboardInterrupt:
        print("\n❌ Tests interrupted by user")
        return 1
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return 1


def main():
    """Main entry point for the test runner."""
    
    parser = argparse.ArgumentParser(description="Test runner for PraisonAI")
    parser.add_argument(
        "--pattern", 
        choices=[
            "unit", "integration", "autogen", "crewai", "mcp", "rag", 
            "frameworks", "fast", "all",
            "real", "e2e", "real-autogen", "real-crewai", "real-frameworks",
            "full-autogen", "full-crewai", "full-frameworks"
        ],
        default="all",
        help="Test pattern to run (real tests make actual API calls!)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--coverage", "-c",
        action="store_true", 
        help="Enable coverage reporting"
    )
    
    args = parser.parse_args()
    
    # Show warning for real tests
    if "real" in args.pattern or args.pattern == "e2e":
        print("🚨 REAL TEST WARNING:")
        print("⚠️  You're about to run real tests that make actual API calls!")
        print("💰 This may incur charges on your API accounts")
        print("📋 Make sure you have:")
        print("   - API keys set as environment variables")  
        print("   - Understanding of potential costs")
        print("")
        
        confirm = input("Type 'yes' to continue with real tests: ").lower().strip()
        if confirm != 'yes':
            print("❌ Real tests cancelled by user")
            sys.exit(1)
    
    # Show EXTRA warning for full execution tests
    if "full" in args.pattern:
        print("🚨🚨 FULL EXECUTION TEST WARNING 🚨🚨")
        print("💰💰 These tests run praisonai.run() with ACTUAL API calls!")
        print("💸 This will consume API credits and may be expensive!")
        print("⚠️  You will see real agent execution logs and output!")
        print("")
        print("📋 Requirements:")
        print("   - Valid API keys (OPENAI_API_KEY, etc.)")
        print("   - Understanding of API costs")
        print("   - Willingness to pay for API usage")
        print("")
        
        confirm = input("Type 'EXECUTE' to run full execution tests: ").strip()
        if confirm != 'EXECUTE':
            print("❌ Full execution tests cancelled by user")
            sys.exit(1)
        
        # Enable full execution tests
        os.environ["PRAISONAI_RUN_FULL_TESTS"] = "true"
        print("🔥 Full execution tests enabled!")
    
    print(f"🧪 Running {args.pattern} tests...")
    
    # Set environment variables for testing
    os.environ["PYTEST_CURRENT_TEST"] = "true"
    
    exit_code = run_tests(
        pattern=args.pattern,
        verbose=args.verbose,
        coverage=args.coverage
    )
    
    if exit_code == 0:
        print(f"✅ {args.pattern} tests completed successfully!")
    else:
        print(f"❌ {args.pattern} tests failed!")
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main() 