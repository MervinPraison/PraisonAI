#!/usr/bin/env python3
"""
Runner for all performance examples.

Usage:
    # Run without real API (mock only)
    python run_all_examples.py
    
    # Run with real API
    RUN_REAL_KEY_TESTS=1 OPENAI_API_KEY=your-key python run_all_examples.py
"""
import os
import sys
import subprocess


def run_example(name, script_path):
    """Run an example script and report results."""
    print(f"\n{'=' * 60}")
    print(f"Running: {name}")
    print("=" * 60)
    
    result = subprocess.run(
        [sys.executable, script_path],
        capture_output=True,
        text=True,
        env=os.environ.copy()
    )
    
    print(result.stdout)
    if result.stderr:
        print(f"STDERR: {result.stderr}")
    
    return result.returncode == 0


def main():
    """Run all performance examples."""
    print("PraisonAI Agents - Performance Examples Runner")
    print("=" * 60)
    
    # Check environment
    real_tests = os.environ.get("RUN_REAL_KEY_TESTS")
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))
    
    print(f"RUN_REAL_KEY_TESTS: {real_tests or 'not set'}")
    print(f"OPENAI_API_KEY: {'set' if has_openai else 'not set'}")
    
    # Get script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Define examples
    examples = [
        ("Lazy Imports", os.path.join(script_dir, "lazy_imports_example.py")),
        ("Lite Agent", os.path.join(script_dir, "lite_agent_example.py")),
        ("Thread Safety", os.path.join(script_dir, "thread_safety_example.py")),
    ]
    
    # Run examples
    results = []
    for name, path in examples:
        if os.path.exists(path):
            success = run_example(name, path)
            results.append((name, success))
        else:
            print(f"Skipping {name}: {path} not found")
            results.append((name, None))
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    passed = 0
    failed = 0
    skipped = 0
    
    for name, success in results:
        if success is None:
            status = "SKIPPED"
            skipped += 1
        elif success:
            status = "PASS"
            passed += 1
        else:
            status = "FAIL"
            failed += 1
        print(f"  {name}: {status}")
    
    print(f"\nTotal: {passed} passed, {failed} failed, {skipped} skipped")
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
