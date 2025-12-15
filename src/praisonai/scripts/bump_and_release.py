#!/usr/bin/env python3
"""
Combined bump version and release script for PraisonAI package.

Usage:
    python src/praisonai/scripts/bump_and_release.py 2.2.99
    
Or with optional praisonaiagents version:
    python src/praisonai/scripts/bump_and_release.py 2.2.99 --agents 0.0.169

This script:
1. Bumps version in all required files
2. Copies root README.md to package dir
3. Runs uv lock & uv build
4. Commits changes
5. Creates git tag
6. Pushes to GitHub
7. Creates GitHub release (latest)
"""

import re
import sys
import argparse
import subprocess
import shutil
from pathlib import Path


def get_project_root() -> Path:
    """Get the project root directory (praisonai-package)."""
    return Path(__file__).parent.parent.parent.parent


def get_praisonai_dir() -> Path:
    """Get the praisonai package directory."""
    return get_project_root() / "src/praisonai"


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


def bump_version(new_version: str, agents_version: str | None = None):
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


def release(version: str):
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
    
    # 2. uv lock
    print("\n📦 Running uv lock...")
    run(["uv", "lock"], cwd=praisonai_dir)
    
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
    
    # 6. Push to GitHub
    print("\n⬆️  Pushing to GitHub...")
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
        description="Bump version and release PraisonAI package"
    )
    parser.add_argument(
        "version",
        help="New version number (e.g., 2.2.99)"
    )
    parser.add_argument(
        "--agents", "-a",
        help="Optional: Update praisonaiagents dependency version (e.g., 0.0.169)",
        default=None
    )
    
    args = parser.parse_args()
    
    # Validate version format
    if not re.match(r'^\d+\.\d+\.\d+$', args.version):
        print(f"❌ Invalid version format: {args.version}")
        print("   Expected format: X.Y.Z (e.g., 2.2.99)")
        sys.exit(1)
    
    if args.agents and not re.match(r'^\d+\.\d+\.\d+$', args.agents):
        print(f"❌ Invalid agents version format: {args.agents}")
        print("   Expected format: X.Y.Z (e.g., 0.0.169)")
        sys.exit(1)
    
    # Run bump version
    bump_version(args.version, args.agents)
    
    # Run release
    release(args.version)


if __name__ == "__main__":
    main()
