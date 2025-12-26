#!/usr/bin/env python3
"""Run all examples and collect PASS/SKIP/FAIL results."""
import subprocess
import sys
import os
from pathlib import Path

EXAMPLES_DIR = Path(__file__).parent
RESULTS = []

def run_example(path: Path) -> tuple:
    """Run an example and return (name, status, reason)."""
    name = f"{path.parent.name}/{path.name}"
    try:
        result = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "PYTHONPATH": str(EXAMPLES_DIR.parent / "src")}
        )
        output = result.stdout + result.stderr
        if "PASSED" in output:
            return (name, "PASS", "")
        elif "SKIPPED" in output:
            return (name, "SKIP", output.split("SKIPPED:")[-1].strip()[:50])
        elif result.returncode != 0:
            error = output.strip().split("\n")[-1][:80]
            return (name, "FAIL", error)
        else:
            return (name, "PASS", "")
    except subprocess.TimeoutExpired:
        return (name, "FAIL", "Timeout")
    except Exception as e:
        return (name, "FAIL", str(e)[:50])

def main():
    print("=" * 70)
    print("EXAMPLE RUNNER - PASS/SKIP/FAIL SUMMARY")
    print("=" * 70)
    
    # Find all example files
    examples = []
    for subdir in ["db", "vector", "observability", "multi_agent", "workflows"]:
        subpath = EXAMPLES_DIR / subdir
        if subpath.exists():
            examples.extend(sorted(subpath.glob("*_wow.py")))
    
    print(f"\nFound {len(examples)} examples to run\n")
    
    for ex in examples:
        name, status, reason = run_example(ex)
        RESULTS.append((name, status, reason))
        icon = {"PASS": "✅", "SKIP": "⏭️", "FAIL": "❌"}.get(status, "?")
        reason_str = f" ({reason})" if reason else ""
        print(f"{icon} {status:4} | {name:45} {reason_str}")
    
    # Summary
    print("\n" + "=" * 70)
    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    skipped = sum(1 for _, s, _ in RESULTS if s == "SKIP")
    failed = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    print(f"SUMMARY: {passed} PASS | {skipped} SKIP | {failed} FAIL | {len(RESULTS)} TOTAL")
    print("=" * 70)
    
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
