#!/usr/bin/env python3
"""
CI Integration Example - Using Doctor in CI/CD pipelines

This example demonstrates how to integrate PraisonAI Doctor
into CI/CD pipelines for automated health checks.
"""

import json
import subprocess
import sys


def run_doctor_ci():
    """Run doctor in CI mode and parse results."""
    print("Running PraisonAI Doctor in CI mode...")
    
    result = subprocess.run(
        [sys.executable, "-m", "praisonai", "doctor", "ci"],
        capture_output=True,
        text=True,
        timeout=120
    )
    
    # Parse JSON output
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("Error: Could not parse doctor output")
        print(result.stdout)
        print(result.stderr)
        return 1
    
    # Print summary
    summary = report.get("summary", {})
    print("\nDoctor CI Results:")
    print(f"  Total checks: {summary.get('total', 0)}")
    print(f"  Passed: {summary.get('passed', 0)}")
    print(f"  Warnings: {summary.get('warnings', 0)}")
    print(f"  Failed: {summary.get('failed', 0)}")
    print(f"  Skipped: {summary.get('skipped', 0)}")
    print(f"  Errors: {summary.get('errors', 0)}")
    print(f"\nExit code: {report.get('exit_code', -1)}")
    
    # Check for failures
    if summary.get('failed', 0) > 0:
        print("\nFailed checks:")
        for check in report.get("results", []):
            if check.get("status") == "fail":
                print(f"  - {check.get('title')}: {check.get('message')}")
                if check.get("remediation"):
                    print(f"    Fix: {check.get('remediation')}")
    
    return result.returncode


def run_specific_checks_ci():
    """Run specific checks for CI."""
    print("\nRunning specific checks for CI...")
    
    # Only run critical checks
    critical_checks = [
        "python_version",
        "praisonai_package",
        "openai_api_key",
    ]
    
    result = subprocess.run(
        [
            sys.executable, "-m", "praisonai", "doctor",
            "--json",
            "--only", ",".join(critical_checks)
        ],
        capture_output=True,
        text=True,
        timeout=60
    )
    
    try:
        report = json.loads(result.stdout)
        print(f"Critical checks: {report['summary']['passed']}/{report['summary']['total']} passed")
        return result.returncode
    except json.JSONDecodeError:
        print("Error parsing output")
        return 1


def save_report_to_file():
    """Save doctor report to a file for artifact upload."""
    print("\nSaving doctor report to file...")
    
    result = subprocess.run(
        [
            sys.executable, "-m", "praisonai", "doctor",
            "--json",
            "--output", "/tmp/doctor-report.json"
        ],
        capture_output=True,
        text=True,
        timeout=120
    )
    
    if result.returncode in [0, 1]:
        print("Report saved to /tmp/doctor-report.json")
        
        # Read and display summary
        with open("/tmp/doctor-report.json", "r") as f:
            report = json.load(f)
            print(f"Summary: {report['summary']}")
    
    return result.returncode


if __name__ == "__main__":
    print("PraisonAI Doctor - CI Integration Examples\n")
    print("=" * 60)
    
    # Run CI mode
    exit_code = run_doctor_ci()
    
    # Run specific checks
    run_specific_checks_ci()
    
    # Save report
    save_report_to_file()
    
    print(f"\nFinal exit code: {exit_code}")
    sys.exit(exit_code)
