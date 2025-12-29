#!/usr/bin/env python3
"""
Run all catalog examples and report pass/fail status.

Usage:
    python run_all_catalog_examples.py
    
Environment variables:
    OPENAI_API_KEY or PRAISONAI_OPENAI_API_KEY - Required for agent example
    PRAISONAI_RUN_INTEGRATION - Set to "1" to run integration tests
"""

import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent


def run_example(name: str, script: str, requires_api_key: bool = False) -> bool:
    """Run an example script and return success status."""
    print(f"\n{'='*60}")
    print(f"Running: {name}")
    print(f"Script: {script}")
    print("="*60)
    
    # Check API key requirement
    if requires_api_key:
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("PRAISONAI_OPENAI_API_KEY")
        run_integration = os.environ.get("PRAISONAI_RUN_INTEGRATION") == "1"
        
        if not api_key:
            print(f"⏭️  SKIPPED: {name} (no API key)")
            print("   Set OPENAI_API_KEY to run this example")
            return True  # Not a failure, just skipped
        
        if not run_integration:
            print(f"⏭️  SKIPPED: {name} (integration tests disabled)")
            print("   Set PRAISONAI_RUN_INTEGRATION=1 to run")
            return True
    
    script_path = SCRIPT_DIR / script
    if not script_path.exists():
        print(f"❌ FAILED: Script not found: {script_path}")
        return False
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(SCRIPT_DIR)
        )
        
        print(result.stdout)
        if result.stderr:
            print(f"STDERR: {result.stderr}")
        
        if result.returncode == 0:
            print(f"✅ PASSED: {name}")
            return True
        else:
            print(f"❌ FAILED: {name} (exit code {result.returncode})")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"❌ FAILED: {name} (timeout)")
        return False
    except Exception as e:
        print(f"❌ FAILED: {name} ({e})")
        return False


def main():
    print("PraisonAI Template Catalog - Example Runner")
    print("=" * 50)
    
    # Check environment
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("PRAISONAI_OPENAI_API_KEY")
    if api_key:
        print(f"API key: present (...{api_key[-4:]})")
    else:
        print("API key: not set")
    
    run_integration = os.environ.get("PRAISONAI_RUN_INTEGRATION") == "1"
    print(f"Integration tests: {'enabled' if run_integration else 'disabled'}")
    
    # Define examples
    examples = [
        ("Fetch Templates (Python)", "fetch_templates.py", False),
        ("Template Finder Agent", "template_finder_agent.py", True),
    ]
    
    # Run examples
    results = []
    for name, script, requires_key in examples:
        success = run_example(name, script, requires_key)
        results.append((name, success))
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, s in results if s)
    failed = sum(1 for _, s in results if not s)
    
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\nTotal: {passed} passed, {failed} failed")
    
    # Exit with appropriate code
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
