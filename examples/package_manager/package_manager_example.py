#!/usr/bin/env python3
"""
Package Manager Example

This example demonstrates:
1. Checking package index configuration
2. Searching for packages on PyPI
3. Listing installed packages
4. Security features (safe defaults)

Requirements:
- praisonai installed
- No external API keys required

Note: This example does NOT actually install/uninstall packages
to avoid modifying your environment. It demonstrates read-only
operations and shows the commands for install/uninstall.
"""

import sys
import json
import subprocess


def run_command(args, description):
    """Run a praisonai command and display results."""
    print(f"\n[{description}]")
    print(f"Command: praisonai {' '.join(args)}")
    print("-" * 40)
    
    result = subprocess.run(
        ["python3", "-m", "praisonai"] + args,
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        try:
            data = json.loads(result.stdout)
            print(json.dumps(data, indent=2))
            return data
        except json.JSONDecodeError:
            print(result.stdout)
            return None
    else:
        print(f"Error (exit code {result.returncode}):")
        print(result.stderr or result.stdout)
        return None


def main():
    print("=" * 60)
    print("PraisonAI Package Manager Example")
    print("=" * 60)
    print("\nThis example demonstrates package manager features.")
    print("No packages will be installed or uninstalled.")
    
    # 1. Show index configuration
    print("\n" + "=" * 60)
    print("1. PACKAGE INDEX CONFIGURATION")
    print("=" * 60)
    
    data = run_command(
        ["package", "index", "show", "--json"],
        "Show current index settings"
    )
    
    if data:
        print(f"\n✓ Primary index: {data.get('index_url', 'N/A')}")
        print(f"✓ Extra indexes allowed: {data.get('allow_extra_index', False)}")
    
    # 2. Search for packages
    print("\n" + "=" * 60)
    print("2. SEARCH PACKAGES")
    print("=" * 60)
    
    data = run_command(
        ["package", "search", "requests", "--json"],
        "Search for 'requests' package"
    )
    
    if data and data.get("results"):
        pkg = data["results"][0]
        print(f"\n✓ Found: {pkg.get('name')} v{pkg.get('version')}")
        print(f"  Summary: {pkg.get('summary', 'N/A')}")
    
    # 3. List installed packages (sample)
    print("\n" + "=" * 60)
    print("3. LIST INSTALLED PACKAGES")
    print("=" * 60)
    
    data = run_command(
        ["package", "list", "--json"],
        "List installed packages"
    )
    
    if data and data.get("packages"):
        print(f"\n✓ Total packages: {len(data['packages'])}")
        print("  Sample (first 5):")
        for pkg in data["packages"][:5]:
            print(f"    - {pkg['name']}=={pkg['version']}")
    
    # 4. Show install/uninstall commands (without executing)
    print("\n" + "=" * 60)
    print("4. INSTALL/UNINSTALL COMMANDS (NOT EXECUTED)")
    print("=" * 60)
    
    print("\nTo install packages, use:")
    print("  praisonai install requests")
    print("  praisonai install 'requests>=2.28'")
    print("  praisonai install requests httpx --upgrade")
    
    print("\nTo uninstall packages, use:")
    print("  praisonai uninstall requests")
    print("  praisonai uninstall requests --yes")
    
    # 5. Security features
    print("\n" + "=" * 60)
    print("5. SECURITY FEATURES")
    print("=" * 60)
    
    print("\nDependency Confusion Prevention:")
    print("  - By default, only PyPI is used as package source")
    print("  - Extra index URLs are blocked unless explicitly allowed")
    print("  - Use --allow-extra-index to enable (shows warning)")
    
    print("\nExample (blocked by default):")
    print("  praisonai install pkg --extra-index-url https://other.index.com/simple")
    print("  → Error: Extra index URLs not allowed")
    
    print("\nExample (explicitly allowed):")
    print("  praisonai install pkg --extra-index-url https://other.index.com/simple --allow-extra-index")
    print("  → Warning shown, then proceeds")
    
    print("\n" + "=" * 60)
    print("Example completed!")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
