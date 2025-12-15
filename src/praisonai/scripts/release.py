#!/usr/bin/env python3
"""
Release script for PraisonAI package.

Usage:
    python src/praisonai/scripts/release.py

This script:
1. Reads version from praisonai/version.py
2. Runs uv lock
3. Runs uv build
4. Commits changes
5. Creates git tag
6. Pushes to GitHub
7. Creates GitHub release (latest)
"""

import subprocess
import sys
from pathlib import Path


def get_project_root() -> Path:
    """Get the project root directory (praisonai-package)."""
    return Path(__file__).parent.parent.parent.parent


def get_praisonai_dir() -> Path:
    """Get the praisonai package directory."""
    return get_project_root() / "src/praisonai"


def get_version() -> str:
    """Read version from version.py."""
    version_file = get_praisonai_dir() / "praisonai/version.py"
    content = version_file.read_text()
    for line in content.splitlines():
        if line.startswith("__version__"):
            return line.split('"')[1]
    raise ValueError("Could not find version in version.py")


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and print it."""
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if check and result.returncode != 0:
        print(f"❌ Command failed with exit code {result.returncode}")
        sys.exit(1)
    return result


def main():
    root = get_project_root()
    praisonai_dir = get_praisonai_dir()
    version = get_version()
    tag = f"v{version}"
    
    print(f"\n🚀 Releasing PraisonAI {tag}\n")
    
    # 1. uv lock
    print("📦 Running uv lock...")
    run(["uv", "lock"], cwd=praisonai_dir)
    
    # 2. uv build
    print("\n🔨 Running uv build...")
    run(["uv", "build"], cwd=praisonai_dir)
    
    # 3. Git add and commit
    print("\n📝 Committing changes...")
    run(["git", "add", "-A"], cwd=root)
    run(["git", "commit", "-m", f"Release {tag}"], cwd=root, check=False)
    
    # 4. Create git tag
    print(f"\n🏷️  Creating tag {tag}...")
    run(["git", "tag", "-f", tag], cwd=root)
    
    # 5. Push to GitHub
    print("\n⬆️  Pushing to GitHub...")
    run(["git", "push"], cwd=root)
    run(["git", "push", "--tags", "-f"], cwd=root)
    
    # 6. Create GitHub release
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


if __name__ == "__main__":
    main()
