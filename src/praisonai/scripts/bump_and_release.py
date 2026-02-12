#!/usr/bin/env python3
"""
Combined bump version and release script for PraisonAI package.

Usage:
    # Basic: bump praisonai to 3.8.2 with agents 0.11.8
    python scripts/bump_and_release.py --agents 0.11.8 3.8.2
    
    # Wait for agents version to propagate to PyPI (recommended after publishing agents)
    python scripts/bump_and_release.py --agents 0.11.8 --wait 3.8.2
    
    # Auto-detect latest agents version from PyPI
    python scripts/bump_and_release.py --auto 3.8.2

This script:
1. Validates pre-flight conditions (clean git state, versions)
2. Optionally waits for praisonaiagents to be available on PyPI
3. Bumps version in all required files
4. Copies root README.md to package dir
5. Runs uv lock & uv build
6. Commits changes
7. Creates git tag
8. Pushes to GitHub (with rebase if needed)
9. Creates GitHub release (latest)
"""

import re
import sys
import time
import json
import argparse
import subprocess
import shutil
import urllib.request
from pathlib import Path
from typing import Optional


def get_project_root() -> Path:
    """Get the project root directory (praisonai-package)."""
    return Path(__file__).parent.parent.parent.parent


def get_praisonai_dir() -> Path:
    """Get the praisonai package directory."""
    return get_project_root() / "src/praisonai"


def run(cmd: list[str], cwd: Optional[Path] = None, check: bool = True, silent: bool = False) -> subprocess.CompletedProcess:
    """Run a command and print it."""
    if not silent:
        print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if not silent:
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
    if check and result.returncode != 0:
        print(f"❌ Command failed with exit code {result.returncode}")
        sys.exit(1)
    return result


def get_pypi_version(package: str) -> Optional[str]:
    """Get the latest version of a package from PyPI."""
    try:
        url = f"https://pypi.org/pypi/{package}/json"
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
            return data["info"]["version"]
    except Exception as e:
        print(f"  ⚠️  Failed to fetch PyPI version: {e}")
        return None


def wait_for_pypi_version(package: str, version: str, max_wait: int = 300, interval: int = 30) -> bool:
    """Wait for a specific version to be available on PyPI."""
    print(f"\n⏳ Waiting for {package}=={version} to be available on PyPI...")
    start = time.time()
    
    while time.time() - start < max_wait:
        current = get_pypi_version(package)
        if current == version:
            print(f"  ✅ {package}=={version} is now available on PyPI")
            return True
        
        elapsed = int(time.time() - start)
        remaining = max_wait - elapsed
        print(f"  ⏳ Current: {current}, waiting for: {version} ({remaining}s remaining...)")
        time.sleep(interval)
    
    print(f"  ❌ Timeout waiting for {package}=={version} on PyPI")
    return False


def check_git_status() -> bool:
    """Check if there are uncommitted changes."""
    root = get_project_root()
    result = run(["git", "status", "--porcelain"], cwd=root, check=False, silent=True)
    if result.stdout.strip():
        return True  # Has uncommitted changes
    return False


def update_file(filepath: Path, patterns: list[tuple[str, str]], root: Path) -> bool:
    """Update a file with the given regex patterns and replacements."""
    if not filepath.exists():
        print(f"  ⚠️  File not found: {filepath}")
        return False
    
    content = filepath.read_text()
    original = content
    
    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content)
    
    if content != original:
        filepath.write_text(content)
        print(f"  ✅ Updated: {filepath.relative_to(root)}")
        return True
    else:
        print(f"  ⏭️  No changes: {filepath.relative_to(root)}")
        return False


def bump_version(new_version: str, agents_version: Optional[str] = None):
    """Bump version in all required files."""
    root = get_project_root()
    praisonai_dir = get_praisonai_dir()
    
    print(f"\n🚀 Bumping PraisonAI version to {new_version}\n")
    
    # 1. Update version.py (single source of truth)
    print("📦 Python Package:")
    update_file(
        praisonai_dir / "praisonai/version.py",
        [(r'__version__ = "[^"]+"', f'__version__ = "{new_version}"')],
        root
    )
    
    # 2. Update deploy.py (Dockerfile template)
    print("\n🐳 Deploy Script:")
    update_file(
        praisonai_dir / "praisonai/deploy.py",
        [(r'praisonai==[0-9.]+', f'praisonai=={new_version}')],
        root
    )
    
    # 3. Update Dockerfiles
    print("\n🐳 Dockerfiles:")
    dockerfiles = [
        "docker/Dockerfile",
        "docker/Dockerfile.chat",
        "docker/Dockerfile.dev",
        "docker/Dockerfile.ui",
    ]
    for dockerfile in dockerfiles:
        update_file(
            root / dockerfile,
            [(r'"praisonai>=[0-9.]+"', f'"praisonai>={new_version}"')],
            root
        )
    
    # 4. Update Homebrew formula
    print("\n🍺 Homebrew Formula:")
    update_file(
        praisonai_dir / "praisonai.rb",
        [(r'v[0-9]+\.[0-9]+\.[0-9]+', f'v{new_version}')],
        root
    )
    
    # 5. Update praisonaiagents dependency if specified
    if agents_version:
        print(f"\n📦 Updating praisonaiagents dependency to {agents_version}:")
        update_file(
            praisonai_dir / "pyproject.toml",
            [(r'praisonaiagents>=[0-9.]+', f'praisonaiagents>={agents_version}')],
            root
        )
    
    print("\n✨ Version bump complete!")


def validate_dependencies(max_retries: int = 3, retry_interval: int = 60, use_frozen: bool = False) -> bool:
    """Validate that uv lock will succeed, with retry logic for PyPI propagation."""
    praisonai_dir = get_praisonai_dir()
    
    lock_cmd = ["uv", "lock", "--frozen"] if use_frozen else ["uv", "lock", "--dry-run"]
    
    for attempt in range(max_retries):
        print(f"\n🔍 Validating dependencies (attempt {attempt + 1}/{max_retries})...")
        
        if not use_frozen:
            run(["uv", "cache", "clean"], cwd=praisonai_dir, silent=True)
        
        result = run(lock_cmd, cwd=praisonai_dir, check=False)
        if result.returncode == 0:
            print("  ✅ Dependencies validated successfully")
            return True
        
        if attempt < max_retries - 1:
            print(f"\n⏳ Waiting {retry_interval}s for PyPI propagation before retry...")
            time.sleep(retry_interval)
    
    print("\n❌ Dependency validation failed after all retries.")
    return False


def release(version: str, use_frozen_lock: bool = False):
    """Run the release process."""
    root = get_project_root()
    praisonai_dir = get_praisonai_dir()
    tag = f"v{version}"
    
    print(f"\n🚀 Releasing PraisonAI {tag}\n")
    
    # 1. Copy root README.md to package dir for PyPI
    print("📄 Copying README.md...")
    root_readme = root / "README.md"
    pkg_readme = praisonai_dir / "README.md"
    if root_readme.exists():
        shutil.copy(root_readme, pkg_readme)
        print(f"  ✅ Copied {root_readme} -> {pkg_readme}")
    
    # 2. Clear uv cache and run uv lock
    if not use_frozen_lock:
        print("\n🧹 Clearing uv cache...")
        run(["uv", "cache", "clean"], cwd=praisonai_dir)
    
    print("\n📦 Running uv lock...")
    run(["uv", "lock", "--frozen"] if use_frozen_lock else ["uv", "lock"], cwd=praisonai_dir)
    
    # 3. uv build
    print("\n🔨 Running uv build...")
    run(["uv", "build"], cwd=praisonai_dir)
    
    # 4. Git add and commit
    print("\n📝 Committing changes...")
    run(["git", "add", "-A"], cwd=root)
    run(["git", "commit", "-m", f"Release {tag}"], cwd=root, check=False)
    
    # 5. Create git tag
    print(f"\n🏷️  Creating tag {tag}...")
    run(["git", "tag", "-f", tag], cwd=root)
    
    # 6. Pull rebase and push to GitHub
    print("\n⬆️  Pushing to GitHub...")
    # First fetch and rebase to handle any remote changes (e.g., auto-generated api.md)
    result = run(["git", "pull", "--rebase", "origin", "main"], cwd=root, check=False)
    if result.returncode != 0:
        print("  ⚠️  Rebase failed, trying to continue...")
    
    # Recreate tag after rebase (commit hash may have changed)
    run(["git", "tag", "-f", tag], cwd=root)
    
    # Push changes
    run(["git", "push"], cwd=root)
    run(["git", "push", "--tags", "-f"], cwd=root)
    
    # 7. Create GitHub release
    print(f"\n🎉 Creating GitHub release {tag}...")
    run([
        "gh", "release", "create", tag,
        "--title", f"PraisonAI {tag}",
        "--notes", f"Release {tag}",
        "--latest"
    ], cwd=root)
    
    print(f"\n✅ Released PraisonAI {tag}")
    print("\nNext step:")
    print("  cd src/praisonai && uv publish")


def main():
    parser = argparse.ArgumentParser(
        description="Bump version and release PraisonAI package",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Bump to 3.8.2 with agents 0.11.8
  python scripts/bump_and_release.py --agents 0.11.8 3.8.2
  
  # Wait for agents to propagate to PyPI first (recommended)
  python scripts/bump_and_release.py --agents 0.11.8 --wait 3.8.2
  
  # Auto-detect latest agents version from PyPI
  python scripts/bump_and_release.py --auto 3.8.2
"""
    )
    parser.add_argument(
        "version",
        help="New version number (e.g., 3.8.2)"
    )
    parser.add_argument(
        "--agents", "-a",
        help="Update praisonaiagents dependency version (e.g., 0.11.8)",
        default=None
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Auto-detect latest praisonaiagents version from PyPI"
    )
    parser.add_argument(
        "--wait", "-w",
        action="store_true",
        help="Wait for the specified agents version to be available on PyPI"
    )
    parser.add_argument(
        "--max-wait",
        type=int,
        default=300,
        help="Maximum seconds to wait for PyPI propagation (default: 300)"
    )
    parser.add_argument(
        "--retries", "-r",
        type=int,
        default=3,
        help="Number of retries for dependency validation (default: 3)"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Skip pre-flight checks (use with caution)"
    )
    
    args = parser.parse_args()
    
    # Validate version format
    if not re.match(r'^\d+\.\d+\.\d+$', args.version):
        print(f"❌ Invalid version format: {args.version}")
        print("   Expected format: X.Y.Z (e.g., 3.8.2)")
        sys.exit(1)
    
    # Handle --auto flag
    if args.auto:
        print("\n🔍 Auto-detecting latest praisonaiagents version from PyPI...")
        agents_version = get_pypi_version("praisonaiagents")
        if not agents_version:
            print("❌ Failed to auto-detect praisonaiagents version")
            sys.exit(1)
        print(f"  ✅ Latest version: {agents_version}")
        args.agents = agents_version
    
    # Validate agents version format if provided
    if args.agents and not re.match(r'^\d+\.\d+\.\d+$', args.agents):
        print(f"❌ Invalid agents version format: {args.agents}")
        print("   Expected format: X.Y.Z (e.g., 0.11.8)")
        sys.exit(1)
    
    # Pre-flight checks
    if not args.force:
        print("\n🔍 Pre-flight checks...")
        
        # Check for uncommitted changes (warning only)
        if check_git_status():
            print("  ⚠️  Warning: You have uncommitted changes")
        else:
            print("  ✅ Git working directory is clean")
    
    # Wait for PyPI propagation if requested
    if args.wait and args.agents:
        if not wait_for_pypi_version("praisonaiagents", args.agents, max_wait=args.max_wait):
            print("\n💡 Tip: Check if the package was published successfully")
            print("💡 Tip: You can retry without --wait if the package is confirmed published")
            sys.exit(1)
    
    # Run bump version
    bump_version(args.version, args.agents)
    
    # Validate dependencies after version bump (with retries)
    use_frozen = args.agents is None
    if not validate_dependencies(max_retries=args.retries, use_frozen=use_frozen):
        print("\n💡 Tip: Revert changes with 'git checkout .' if needed")
        print("💡 Tip: The package may need more time to propagate to PyPI")
        sys.exit(1)
    
    # Run release
    release(args.version, use_frozen_lock=use_frozen)


if __name__ == "__main__":
    main()
