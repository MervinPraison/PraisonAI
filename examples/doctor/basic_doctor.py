#!/usr/bin/env python3
"""
Basic Doctor Example - Programmatic health checks for PraisonAI

This example demonstrates how to use the Doctor module programmatically
to run health checks and diagnostics.
"""

import json
import sys

# Add the praisonai path for development
sys.path.insert(0, '/Users/praison/praisonai-package/src/praisonai')

from praisonai.cli.features.doctor import DoctorEngine
from praisonai.cli.features.doctor.models import DoctorConfig, CheckCategory
from praisonai.cli.features.doctor.registry import get_registry
from praisonai.cli.features.doctor.checks import register_all_checks
from praisonai.cli.features.doctor.formatters import get_formatter


def run_basic_checks():
    """Run basic health checks."""
    print("=" * 60)
    print("Running Basic Health Checks")
    print("=" * 60)
    
    # Register all checks
    register_all_checks()
    
    # Create config for fast checks only
    config = DoctorConfig(
        deep=False,
        timeout=10.0,
        strict=False,
        quiet=False,
    )
    
    # Create and run engine
    engine = DoctorEngine(config)
    report = engine.run()
    
    # Format and print results
    formatter = get_formatter("text", no_color=True)
    print(formatter.format_report(report))
    
    return report.exit_code


def run_environment_checks():
    """Run only environment checks."""
    print("\n" + "=" * 60)
    print("Running Environment Checks Only")
    print("=" * 60)
    
    # Register all checks
    register_all_checks()
    
    config = DoctorConfig(deep=False)
    engine = DoctorEngine(config)
    
    # Run only environment category
    engine.run_checks(categories=[CheckCategory.ENVIRONMENT])
    report = engine.generate_report()
    
    formatter = get_formatter("text", no_color=True)
    print(formatter.format_report(report))
    
    return report.exit_code


def run_specific_checks():
    """Run specific checks by ID."""
    print("\n" + "=" * 60)
    print("Running Specific Checks")
    print("=" * 60)
    
    # Register all checks
    register_all_checks()
    
    # Only run these specific checks
    config = DoctorConfig(
        only=["python_version", "openai_api_key", "os_info"]
    )
    
    engine = DoctorEngine(config)
    report = engine.run()
    
    formatter = get_formatter("text", no_color=True)
    print(formatter.format_report(report))
    
    return report.exit_code


def run_json_output():
    """Run checks and get JSON output."""
    print("\n" + "=" * 60)
    print("Running Checks with JSON Output")
    print("=" * 60)
    
    # Register all checks
    register_all_checks()
    
    config = DoctorConfig(
        only=["python_version", "os_info"],
        format="json"
    )
    
    engine = DoctorEngine(config)
    report = engine.run()
    
    # Get JSON output
    formatter = get_formatter("json")
    json_output = formatter.format_report(report)
    
    # Parse and pretty print
    data = json.loads(json_output)
    print(json.dumps(data, indent=2))
    
    return report.exit_code


def list_available_checks():
    """List all available checks."""
    print("\n" + "=" * 60)
    print("Available Checks")
    print("=" * 60)
    
    # Register all checks
    register_all_checks()
    
    registry = get_registry()
    checks = registry.get_all_checks()
    
    # Sort by category
    checks.sort(key=lambda c: c.category.value)
    
    current_category = None
    for check in checks:
        if check.category != current_category:
            current_category = check.category
            print(f"\n  {current_category.value.upper()}:")
        
        deep_marker = " [deep]" if check.requires_deep else ""
        print(f"    {check.id:30} {check.description}{deep_marker}")


if __name__ == "__main__":
    print("PraisonAI Doctor - Programmatic Usage Examples\n")
    
    # List available checks
    list_available_checks()
    
    # Run basic checks
    exit_code = run_basic_checks()
    print(f"\nBasic checks exit code: {exit_code}")
    
    # Run environment checks only
    exit_code = run_environment_checks()
    print(f"\nEnvironment checks exit code: {exit_code}")
    
    # Run specific checks
    exit_code = run_specific_checks()
    print(f"\nSpecific checks exit code: {exit_code}")
    
    # Run with JSON output
    exit_code = run_json_output()
    print(f"\nJSON output exit code: {exit_code}")
