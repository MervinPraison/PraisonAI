#!/usr/bin/env python3
"""
CI script to check version sync between praisonai-agents and praisonai packages.

This script ensures that shared dependencies have compatible version ranges
across both packages to prevent dependency conflicts during installation.

Usage:
    python scripts/check_version_sync.py

Exit codes:
    0 - All versions are in sync
    1 - Version conflicts detected
"""

import sys
import tomllib
from pathlib import Path
from typing import Dict, List, Tuple


def parse_version_spec(spec: str) -> Tuple[str, str]:
    """
    Parse a version specification into (package_name, version_constraint).
    
    Examples:
        "pydantic>=2.10.0" -> ("pydantic", ">=2.10.0")
        "rich" -> ("rich", "")
    """
    # Handle extras like "mem0ai[graph]>=0.1.0"
    spec = spec.split("[")[0] if "[" in spec else spec
    
    for op in [">=", "<=", "==", "~=", "!=", ">", "<"]:
        if op in spec:
            parts = spec.split(op, 1)
            return (parts[0].strip().lower(), op + parts[1].strip())
    
    return (spec.strip().lower(), "")


def load_dependencies(pyproject_path: Path) -> Dict[str, str]:
    """Load all dependencies from a pyproject.toml file."""
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
    
    deps = {}
    
    # Core dependencies
    for dep in data.get("project", {}).get("dependencies", []):
        name, version = parse_version_spec(dep)
        deps[name] = version
    
    # Optional dependencies
    for extra, extra_deps in data.get("project", {}).get("optional-dependencies", {}).items():
        for dep in extra_deps:
            if not dep.startswith("praisonai"):  # Skip self-references
                name, version = parse_version_spec(dep)
                if name not in deps:
                    deps[name] = version
    
    return deps


def check_version_compatibility(v1: str, v2: str) -> bool:
    """
    Check if two version constraints are compatible.
    
    This is a simplified check - it mainly catches obvious conflicts like:
    - >=2.0.0 vs <=1.9.0
    - >=2.0.0 vs <2.0.0
    """
    if not v1 or not v2:
        return True  # No constraint means compatible
    
    if v1 == v2:
        return True
    
    # Extract version numbers for comparison
    def extract_version(v: str) -> Tuple[str, List[int]]:
        for op in [">=", "<=", "==", "~=", "!=", ">", "<"]:
            if v.startswith(op):
                version_str = v[len(op):]
                try:
                    parts = [int(x) for x in version_str.split(".")[:3]]
                    while len(parts) < 3:
                        parts.append(0)
                    return (op, parts)
                except ValueError:
                    return (op, [0, 0, 0])
        return ("", [0, 0, 0])
    
    op1, ver1 = extract_version(v1)
    op2, ver2 = extract_version(v2)
    
    # Check for obvious conflicts
    if op1 in [">=", ">"] and op2 in ["<=", "<"]:
        # v1 requires >= X, v2 requires <= Y
        # Conflict if X > Y
        if ver1 > ver2:
            return False
    
    if op1 in ["<=", "<"] and op2 in [">=", ">"]:
        # v1 requires <= X, v2 requires >= Y
        # Conflict if X < Y
        if ver1 < ver2:
            return False
    
    return True


def main():
    """Main function to check version sync."""
    repo_root = Path(__file__).parent.parent
    
    agents_pyproject = repo_root / "src" / "praisonai-agents" / "pyproject.toml"
    wrapper_pyproject = repo_root / "src" / "praisonai" / "pyproject.toml"
    
    if not agents_pyproject.exists():
        print(f"ERROR: {agents_pyproject} not found")
        return 1
    
    if not wrapper_pyproject.exists():
        print(f"ERROR: {wrapper_pyproject} not found")
        return 1
    
    print("Loading dependencies...")
    agents_deps = load_dependencies(agents_pyproject)
    wrapper_deps = load_dependencies(wrapper_pyproject)
    
    print(f"  praisonai-agents: {len(agents_deps)} dependencies")
    print(f"  praisonai: {len(wrapper_deps)} dependencies")
    
    # Find shared dependencies
    shared = set(agents_deps.keys()) & set(wrapper_deps.keys())
    print(f"\nShared dependencies: {len(shared)}")
    
    conflicts: List[Tuple[str, str, str]] = []
    synced: List[Tuple[str, str, str]] = []
    
    for dep in sorted(shared):
        v1 = agents_deps[dep]
        v2 = wrapper_deps[dep]
        
        if not check_version_compatibility(v1, v2):
            conflicts.append((dep, v1, v2))
        else:
            synced.append((dep, v1, v2))
    
    # Report results
    if synced:
        print("\n✅ Synced dependencies:")
        for dep, v1, v2 in synced:
            if v1 == v2:
                print(f"   {dep}: {v1 or '(no constraint)'}")
            else:
                print(f"   {dep}: agents={v1 or '(none)'}, wrapper={v2 or '(none)'}")
    
    if conflicts:
        print("\n❌ Version conflicts detected:")
        for dep, v1, v2 in conflicts:
            print(f"   {dep}:")
            print(f"      praisonai-agents: {v1}")
            print(f"      praisonai: {v2}")
        print("\nPlease update the pyproject.toml files to resolve these conflicts.")
        return 1
    
    print("\n✅ All shared dependencies are in sync!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
