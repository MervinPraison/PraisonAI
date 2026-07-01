#!/usr/bin/env python3
"""
Version bump script for PraisonAI package.

This script updates the version number in all required locations:
- praisonai/version.py (single source of truth for Python package)
- praisonai/deploy/docker.py (Docker deployment scripts)
- ../../docker/Dockerfile, Dockerfile.chat, Dockerfile.dev, Dockerfile.ui
- praisonai.rb (Homebrew formula)

Usage:
    python src/praisonai/scripts/bump_version.py 2.2.96
    
Or with optional praisonaiagents version:
    python src/praisonai/scripts/bump_version.py 2.2.96 --agents 0.0.167
"""

import re
import sys
import argparse
from pathlib import Path


def get_project_root() -> Path:
    """Get the project root directory (praisonai-package)."""
    # scripts/ -> src/praisonai/ -> src/ -> praisonai-package/
    return Path(__file__).parent.parent.parent.parent


def update_file(filepath: Path, patterns: list[tuple[str, str]]) -> bool:
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
        print(f"  ✅ Updated: {filepath.relative_to(get_project_root())}")
        return True
    else:
        print(f"  ⏭️  No changes: {filepath.relative_to(get_project_root())}")
        return False


def bump_version(new_version: str, agents_version: str | None = None, code_version: str | None = None, code_pin_only: bool = False):
    """Bump version in all required files."""
    root = get_project_root()
    
    print(f"\n🚀 Bumping PraisonAI version to {new_version}\n")
    
    praisonai_dir = root / "src/praisonai"
    
    # 1. Update version.py (single source of truth)
    print("📦 Python Package:")
    update_file(
        praisonai_dir / "praisonai/version.py",
        [(r'__version__ = "[^"]+"', f'__version__ = "{new_version}"')]
    )
    
    # 2. Update deploy/docker.py (Docker deployment scripts)
    print("\n🐳 Deploy Scripts:")
    docker_deploy_file = praisonai_dir / "praisonai/deploy/docker.py"
    if docker_deploy_file.exists():
        update_file(
            docker_deploy_file,
            [(r'praisonai==[0-9.]+', f'praisonai=={new_version}')]
        )
    else:
        print(f"  ⏭️  Docker deploy script not found: {docker_deploy_file.relative_to(get_project_root())}")
    
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
            [(r'"praisonai>=[0-9.]+"', f'"praisonai>={new_version}"')]
        )
    
    # 4. Update Homebrew formula
    print("\n🍺 Homebrew Formula:")
    update_file(
        praisonai_dir / "praisonai.rb",
        [(r'v[0-9]+\.[0-9]+\.[0-9]+', f'v{new_version}')]
    )
    
    # 5. Update praisonaiagents dependency if specified
    if agents_version:
        print(f"\n📦 Updating praisonaiagents dependency to {agents_version}:")
        update_file(
            praisonai_dir / "pyproject.toml",
            [(r'praisonaiagents>=[0-9.]+', f'praisonaiagents>={agents_version}')]
        )

    if code_version:
        code_dir = root / "src/praisonai-code"
        if code_pin_only:
            print(f"\n📦 Pinning praisonai-code dependency to >={code_version}:")
        else:
            print(f"\n📦 Bumping praisonai-code to {code_version}:")
            update_file(
                code_dir / "pyproject.toml",
                [(r'(?m)^version = "[^"]+"', f'version = "{code_version}"')]
            )
            update_file(
                code_dir / "praisonai_code/__init__.py",
                [(r'__version__ = "[^"]+"', f'__version__ = "{code_version}"')]
            )
        update_file(
            praisonai_dir / "pyproject.toml",
            [
                (
                    r'"praisonai-code(?:>=[0-9.]+)?"',
                    f'"praisonai-code>={code_version}"',
                )
            ],
        )
    
    print("\n✨ Version bump complete!")
    print("\nNext steps:")
    print("  1. Run: cd src/praisonai && uv lock")
    print("  2. Run: cd src/praisonai && uv build")
    print(f"  3. Commit changes: git add -A && git commit -m 'Bump version to {new_version}'")
    print(f"  4. Tag release: git tag v{new_version}")
    print("  5. Publish: cd src/praisonai && uv publish")


def main():
    parser = argparse.ArgumentParser(
        description="Bump PraisonAI version in all required files"
    )
    parser.add_argument(
        "version",
        help="New version number (e.g., 2.2.96)"
    )
    parser.add_argument(
        "--agents", "-a",
        help="Optional: Update praisonaiagents dependency version (e.g., 0.0.167)",
        default=None
    )
    
    parser.add_argument(
        "--code", "-c",
        help="Bump praisonai-code version and pin wrapper dependency",
        default=None
    )
    parser.add_argument(
        "--code-pin",
        help="Pin praisonai-code>= in wrapper pyproject only",
        default=None
    )
    
    args = parser.parse_args()
    
    # Validate version format
    if not re.match(r'^\d+\.\d+\.\d+$', args.version):
        print(f"❌ Invalid version format: {args.version}")
        print("   Expected format: X.Y.Z (e.g., 2.2.96)")
        sys.exit(1)
    
    if args.agents and not re.match(r'^\d+\.\d+\.\d+$', args.agents):
        print(f"❌ Invalid agents version format: {args.agents}")
        print("   Expected format: X.Y.Z (e.g., 0.0.167)")
        sys.exit(1)
    
    if args.code and args.code_pin:
        print("❌ Use only one of --code or --code-pin")
        sys.exit(1)

    code_version = args.code or args.code_pin
    if code_version and not re.match(r'^\d+\.\d+\.\d+$', code_version):
        print(f"❌ Invalid code version format: {code_version}")
        sys.exit(1)
    
    bump_version(
        args.version,
        args.agents,
        code_version=code_version,
        code_pin_only=bool(args.code_pin and not args.code),
    )


if __name__ == "__main__":
    main()
