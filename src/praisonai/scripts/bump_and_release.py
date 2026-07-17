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
2. Optionally waits for praisonaiagents and/or praisonai-code on PyPI
3. Bumps version in all required files (agents, code, wrapper)
4. Copies root README.md to package dir
5. Runs uv lock & uv build
6. Commits changes
7. Creates git tag
8. Pushes to GitHub (with rebase if needed)
9. Creates GitHub release (latest)

Publish order: praisonaiagents → praisonai-code → praisonai-bot → praisonai-train → praisonai-browser → praisonai

One-command full release (patch by default):
    python scripts/publish_all.py
    python scripts/publish_all.py --dry-run

Wrapper-only bump (after deps already on PyPI):
    python scripts/bump_and_release.py 4.6.119 --agents 1.6.119 --code-pin 0.0.18 --bot-pin 0.0.3 \\
        --train-pin 0.0.1 --wait --wait-code --wait-bot --wait-train --no-add-all
    cd src/praisonai && uv publish

Use --code to bump code package; --code-pin to pin wrapper after code publish.
Use --bot to bump bot package; --bot-pin to pin wrapper after bot publish.
Use --train to bump train package; --train-pin to pin wrapper after train publish.
Use --wait for agents PyPI propagation; --wait-code for praisonai-code; --wait-bot for praisonai-bot; --wait-train for praisonai-train.
Use --wait-all to wait for agents, code, bot, and train (when pins are set).
"""

import re
import sys
import time
import json
import argparse
import subprocess
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional


def get_project_root() -> Path:
    """Get the project root directory (praisonai-package)."""
    return Path(__file__).parent.parent.parent.parent


def get_praisonai_dir() -> Path:
    """Get the praisonai package directory."""
    return get_project_root() / "src/praisonai"


def get_praisonai_code_dir() -> Path:
    """Get the praisonai-code package directory."""
    return get_project_root() / "src/praisonai-code"


def get_praisonai_bot_dir() -> Path:
    """Get the praisonai-bot package directory."""
    return get_project_root() / "src/praisonai-bot"


def get_praisonai_train_dir() -> Path:
    """Get the praisonai-train package directory."""
    return get_project_root() / "src/praisonai-train"


def get_praisonai_browser_dir() -> Path:
    """Get the praisonai-browser package directory."""
    return get_project_root() / "src/praisonai-browser"


def get_praisonai_mcp_dir() -> Path:
    """Get the praisonai-mcp package directory."""
    return get_project_root() / "src/praisonai-mcp"


def get_praisonai_sandbox_dir() -> Path:
    """Get the praisonai-sandbox package directory."""
    return get_project_root() / "src/praisonai-sandbox"


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


def pypi_has_version(package: str, version: str) -> bool:
    """Return True if an exact version exists on PyPI (not just latest)."""
    url = f"https://pypi.org/pypi/{package}/{version}/json"
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            json.loads(response.read().decode())
        return True
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise
    except Exception:
        return False


def wait_for_pypi_version(package: str, version: str, max_wait: int = 300, interval: int = 30) -> bool:
    """Wait until a specific version is available on PyPI."""
    print(f"\n⏳ Waiting for {package}=={version} to be available on PyPI...")
    if pypi_has_version(package, version):
        print(f"  ✅ {package}=={version} is already on PyPI")
        return True

    start = time.time()
    while time.time() - start < max_wait:
        if pypi_has_version(package, version):
            print(f"  ✅ {package}=={version} is now available on PyPI")
            return True

        elapsed = int(time.time() - start)
        remaining = max_wait - elapsed
        latest = get_pypi_version(package)
        print(
            f"  ⏳ Latest on PyPI: {latest}, waiting for exact {version} "
            f"({remaining}s remaining...)"
        )
        time.sleep(interval)

    if pypi_has_version(package, version):
        print(f"  ✅ {package}=={version} is now available on PyPI")
        return True

    print(f"  ❌ Timeout waiting for {package}=={version} on PyPI")
    latest = get_pypi_version(package)
    if latest and latest != version:
        print(
            f"  💡 PyPI latest is {latest}. If {version} was never published, "
            f"drop --wait or use --agents {latest}."
        )
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


def bump_version(
    new_version: str,
    agents_version: Optional[str] = None,
    code_version: Optional[str] = None,
    code_pin_only: bool = False,
    bot_version: Optional[str] = None,
    bot_pin_only: bool = False,
    train_version: Optional[str] = None,
    train_pin_only: bool = False,
    browser_version: Optional[str] = None,
    browser_pin_only: bool = False,
    mcp_version: Optional[str] = None,
    mcp_pin_only: bool = False,
    sandbox_version: Optional[str] = None,
    sandbox_pin_only: bool = False,
):
    """Bump version in all required files."""
    root = get_project_root()
    praisonai_dir = get_praisonai_dir()
    code_dir = get_praisonai_code_dir()
    bot_dir = get_praisonai_bot_dir()
    train_dir = get_praisonai_train_dir()
    browser_dir = get_praisonai_browser_dir()
    mcp_dir = get_praisonai_mcp_dir()
    sandbox_dir = get_praisonai_sandbox_dir()
    print(f"\n🚀 Bumping PraisonAI version to {new_version}\n")
    
    # 1. Update version.py (single source of truth)
    print("📦 Python Package:")
    update_file(
        praisonai_dir / "praisonai/version.py",
        [(r'__version__ = "[^"]+"', f'__version__ = "{new_version}"')],
        root
    )
    
    # 2. Update deploy/docker.py (Docker deployment scripts)
    print("\n🐳 Deploy Scripts:")
    docker_deploy_file = praisonai_dir / "praisonai/deploy/docker.py"
    if docker_deploy_file.exists():
        update_file(
            docker_deploy_file,
            [(r'praisonai==[0-9.]+', f'praisonai=={new_version}')],
            root
        )
    else:
        print(f"  ⏭️  Docker deploy script not found: {docker_deploy_file.relative_to(root)}")
    
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

    if code_version:
        if code_pin_only:
            print(f"\n📦 Pinning praisonai-code dependency to >={code_version}:")
        else:
            print(f"\n📦 Bumping praisonai-code to {code_version}:")
            update_file(
                code_dir / "pyproject.toml",
                [(r'(?m)^version = "[^"]+"', f'version = "{code_version}"')],
                root
            )
            update_file(
                code_dir / "praisonai_code/__init__.py",
                [(r'__version__ = "[^"]+"', f'__version__ = "{code_version}"')],
                root
            )
        update_file(
            praisonai_dir / "pyproject.toml",
            [
                (
                    r'"praisonai-code(?:>=[0-9.]+)?"',
                    f'"praisonai-code>={code_version}"',
                )
            ],
            root
        )

    if bot_version:
        if bot_pin_only:
            print(f"\n📦 Pinning praisonai-bot dependency to >={bot_version}:")
        else:
            print(f"\n📦 Bumping praisonai-bot to {bot_version}:")
            update_file(
                bot_dir / "pyproject.toml",
                [(r'(?m)^version = "[^"]+"', f'version = "{bot_version}"')],
                root,
            )
            update_file(
                bot_dir / "praisonai_bot/_version.py",
                [(r'__version__ = "[^"]+"', f'__version__ = "{bot_version}"')],
                root,
            )
        update_file(
            praisonai_dir / "pyproject.toml",
            [
                (
                    r'"praisonai-bot(?:>=[0-9.]+)?"',
                    f'"praisonai-bot>={bot_version}"',
                )
            ],
            root,
        )

    if train_version:
        if train_pin_only:
            print(f"\n📦 Pinning praisonai-train dependency to >={train_version}:")
        else:
            print(f"\n📦 Bumping praisonai-train to {train_version}:")
            update_file(
                train_dir / "pyproject.toml",
                [(r'(?m)^version = "[^"]+"', f'version = "{train_version}"')],
                root,
            )
            update_file(
                train_dir / "praisonai_train/_version.py",
                [(r'__version__ = "[^"]+"', f'__version__ = "{train_version}"')],
                root,
            )
        update_file(
            praisonai_dir / "pyproject.toml",
            [
                (
                    r'"praisonai-train(?:>=[0-9.]+)?"',
                    f'"praisonai-train>={train_version}"',
                )
            ],
            root,
        )

    if browser_version:
        if browser_pin_only:
            print(f"\n📦 Pinning praisonai-browser dependency to >={browser_version}:")
        else:
            print(f"\n📦 Bumping praisonai-browser to {browser_version}:")
            update_file(
                browser_dir / "pyproject.toml",
                [(r'(?m)^version = "[^"]+"', f'version = "{browser_version}"')],
                root,
            )
            update_file(
                browser_dir / "praisonai_browser/_version.py",
                [(r'__version__ = "[^"]+"', f'__version__ = "{browser_version}"')],
                root,
            )
        update_file(
            praisonai_dir / "pyproject.toml",
            [
                (
                    r'"praisonai-browser(?:>=[0-9.]+)?"',
                    f'"praisonai-browser>={browser_version}"',
                )
            ],
            root,
        )

    if mcp_version:
        if mcp_pin_only:
            print(f"\n📦 Pinning praisonai-mcp dependency to >={mcp_version}:")
        else:
            print(f"\n📦 Bumping praisonai-mcp to {mcp_version}:")
            update_file(
                mcp_dir / "pyproject.toml",
                [(r'(?m)^version = "[^"]+"', f'version = "{mcp_version}"')],
                root,
            )
            update_file(
                mcp_dir / "praisonai_mcp/_version.py",
                [(r'__version__ = "[^"]+"', f'__version__ = "{mcp_version}"')],
                root,
            )
        update_file(
            praisonai_dir / "pyproject.toml",
            [
                (
                    r'"praisonai-mcp(?:>=[0-9.]+)?"',
                    f'"praisonai-mcp>={mcp_version}"',
                )
            ],
            root,
        )

    if sandbox_version:
        if sandbox_pin_only:
            print(f"\n📦 Pinning praisonai-sandbox dependency to >={sandbox_version}:")
        else:
            print(f"\n📦 Bumping praisonai-sandbox to {sandbox_version}:")
            update_file(
                sandbox_dir / "pyproject.toml",
                [(r'(?m)^version = "[^"]+"', f'version = "{sandbox_version}"')],
                root,
            )
            update_file(
                sandbox_dir / "praisonai_sandbox/_version.py",
                [(r'__version__ = "[^"]+"', f'__version__ = "{sandbox_version}"')],
                root,
            )
        update_file(
            praisonai_dir / "pyproject.toml",
            [
                (
                    r'"praisonai-sandbox(?:>=[0-9.]+)?"',
                    f'"praisonai-sandbox>={sandbox_version}"',
                )
            ],
            root,
        )

    print("\n✨ Version bump complete!")


def validate_dependencies(
    max_retries: int = 3,
    retry_interval: int = 60,
    use_frozen: bool = False,
    agents_version: Optional[str] = None,
    code_version: Optional[str] = None,
    bot_version: Optional[str] = None,
    train_version: Optional[str] = None,
    browser_version: Optional[str] = None,
    mcp_version: Optional[str] = None,
    sandbox_version: Optional[str] = None,
) -> bool:
    """Validate release dependency resolution, with retry logic for PyPI propagation."""
    praisonai_dir = get_praisonai_dir()

    if agents_version or code_version or bot_version or train_version or browser_version or mcp_version or sandbox_version:
        lock_cmd = ["uv", "lock", "--frozen"]
        if agents_version:
            lock_cmd.extend(["--upgrade-package", f"praisonaiagents=={agents_version}"])
        if code_version:
            lock_cmd.extend(["--upgrade-package", f"praisonai-code=={code_version}"])
        if bot_version:
            lock_cmd.extend(["--upgrade-package", f"praisonai-bot=={bot_version}"])
        if train_version:
            lock_cmd.extend(["--upgrade-package", f"praisonai-train=={train_version}"])
        if browser_version:
            lock_cmd.extend(["--upgrade-package", f"praisonai-browser=={browser_version}"])
        if mcp_version:
            lock_cmd.extend(["--upgrade-package", f"praisonai-mcp=={mcp_version}"])
        if sandbox_version:
            lock_cmd.extend(["--upgrade-package", f"praisonai-sandbox=={sandbox_version}"])
    elif use_frozen:
        lock_cmd = ["uv", "lock", "--frozen"]
    else:
        lock_cmd = ["uv", "lock", "--dry-run"]

    for attempt in range(max_retries):
        print(f"\n🔍 Validating dependencies (attempt {attempt + 1}/{max_retries})...")

        if not use_frozen and not agents_version:
            run(["uv", "cache", "clean"], cwd=praisonai_dir, silent=True)

        result = run(lock_cmd, cwd=praisonai_dir, check=False)
        if result.returncode != 0:
            if attempt < max_retries - 1:
                print(f"\n⏳ Waiting {retry_interval}s for PyPI propagation before retry...")
                time.sleep(retry_interval)
            continue

        base = run(["uv", "pip", "install", "--system", "--dry-run", "-e", "."], cwd=praisonai_dir, check=False)
        if base.returncode == 0:
            print("  ✅ Dependencies validated successfully")
            return True

        if attempt < max_retries - 1:
            print(f"\n⏳ Waiting {retry_interval}s for PyPI propagation before retry...")
            time.sleep(retry_interval)

    print("\n❌ Dependency validation failed after all retries.")
    return False


def release(version: str, use_frozen_lock: bool = False, no_add_all: bool = False):
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
    if use_frozen_lock:
        run(["uv", "lock", "--frozen", "--upgrade-package", "praisonaiagents"], cwd=praisonai_dir)
    else:
        # Targeted upgrade must WRITE uv.lock so the refreshed resolution can be committed
        # and published. Do not pass --frozen here — it would block the lockfile update.
        run(["uv", "lock", "--upgrade-package", "praisonaiagents"], cwd=praisonai_dir)
    
    # 3. uv build
    print("\n🔨 Running uv build...")
    run(["uv", "build"], cwd=praisonai_dir)
    
    # 4. Git add and commit
    print("\n📝 Committing changes...")
    
    release_files = [
        "src/praisonai/praisonai/version.py",
        "src/praisonai/praisonai/deploy/docker.py",
        "docker/Dockerfile", 
        "docker/Dockerfile.chat",
        "docker/Dockerfile.dev", 
        "docker/Dockerfile.ui",
        "src/praisonai/praisonai.rb",
        "src/praisonai/pyproject.toml",
        "src/praisonai/uv.lock",
        "src/praisonai/README.md",
        "src/praisonai-agents/pyproject.toml",
        "src/praisonai-agents/uv.lock",
        "src/praisonai-code/pyproject.toml",
        "src/praisonai-code/praisonai_code/__init__.py",
        "src/praisonai-code/uv.lock",
        "src/praisonai-bot/pyproject.toml",
        "src/praisonai-bot/praisonai_bot/_version.py",
        "src/praisonai-bot/uv.lock",
        "src/praisonai-train/pyproject.toml",
        "src/praisonai-train/praisonai_train/_version.py",
        "src/praisonai-train/uv.lock",
        "src/praisonai-browser/pyproject.toml",
        "src/praisonai-browser/praisonai_browser/_version.py",
        "src/praisonai-browser/uv.lock",
        "src/praisonai-mcp/pyproject.toml",
        "src/praisonai-mcp/praisonai_mcp/_version.py",
        "src/praisonai-mcp/uv.lock",
        "src/praisonai-sandbox/pyproject.toml",
        "src/praisonai-sandbox/praisonai_sandbox/_version.py",
        "src/praisonai-sandbox/uv.lock",
    ]
    
    # Filter to only existing files to avoid git errors
    files_to_add = []
    for f in release_files:
        if (root / f).exists():
            files_to_add.append(f)
            
    if no_add_all:
        print("  ℹ️  --no-add-all flag detected: Only explicitly modified release files will be staged.")
        run(["git", "add"] + files_to_add, cwd=root)
    else:
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
  # One-command patch release (all 4 packages):
  python scripts/publish_all.py

  # Wrapper only (deps already published):
  python scripts/bump_and_release.py --agents 1.6.119 --code-pin 0.0.18 --bot-pin 0.0.3 \\
      --train-pin 0.0.1 --wait-all --no-add-all 4.6.119

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
        "--wait-code",
        action="store_true",
        help="Wait for the specified praisonai-code version to be available on PyPI"
    )
    parser.add_argument(
        "--max-wait",
        type=int,
        default=600,
        help="Maximum seconds to wait for PyPI propagation (default: 600)"
    )
    parser.add_argument(
        "--retries", "-r",
        type=int,
        default=3,
        help="Number of retries for dependency validation (default: 3)"
    )
    parser.add_argument(
        "--code", "-c",
        help="Bump praisonai-code version (pyproject + __init__) and pin wrapper dep",
        default=None
    )
    parser.add_argument(
        "--code-pin",
        help="Pin praisonai-code>= in wrapper pyproject only (after CI code publish)",
        default=None
    )
    parser.add_argument(
        "--bot", "-b",
        help="Bump praisonai-bot version (pyproject + _version.py) and pin wrapper dep",
        default=None
    )
    parser.add_argument(
        "--bot-pin",
        help="Pin praisonai-bot>= in wrapper pyproject only (after CI bot publish)",
        default=None
    )
    parser.add_argument(
        "--wait-bot",
        action="store_true",
        help="Wait for the specified praisonai-bot version to be available on PyPI"
    )
    parser.add_argument(
        "--train", "-t",
        help="Bump praisonai-train version (pyproject + _version.py) and pin wrapper dep",
        default=None
    )
    parser.add_argument(
        "--train-pin",
        help="Pin praisonai-train>= in wrapper pyproject only (after CI train publish)",
        default=None
    )
    parser.add_argument(
        "--wait-train",
        action="store_true",
        help="Wait for the specified praisonai-train version to be available on PyPI"
    )
    parser.add_argument(
        "--browser-pin",
        help="Pin praisonai-browser>= in wrapper pyproject only (after CI browser publish)",
        default=None
    )
    parser.add_argument(
        "--wait-browser",
        action="store_true",
        help="Wait for the specified praisonai-browser version to be available on PyPI"
    )
    parser.add_argument(
        "--mcp-pin",
        help="Pin praisonai-mcp>= in wrapper pyproject only (after CI mcp publish)",
        default=None
    )
    parser.add_argument(
        "--wait-mcp",
        action="store_true",
        help="Wait for the specified praisonai-mcp version to be available on PyPI"
    )
    parser.add_argument(
        "--sandbox-pin",
        help="Pin praisonai-sandbox>= in wrapper pyproject only (after CI sandbox publish)",
        default=None
    )
    parser.add_argument(
        "--wait-sandbox",
        action="store_true",
        help="Wait for the specified praisonai-sandbox version to be available on PyPI"
    )
    parser.add_argument(
        "--wait-all",
        action="store_true",
        help="Wait for agents, code, bot, train, browser, mcp, and sandbox versions on PyPI (needs --agents and pins)",
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Skip pre-flight checks (use with caution)"
    )
    parser.add_argument(
        "--no-add-all",
        action="store_true",
        help="Do NOT run 'git add -A'. Instead, only stage explicitly updated release files."
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
    
    if args.code and args.code_pin:
        print("❌ Use only one of --code or --code-pin")
        sys.exit(1)

    if args.bot and args.bot_pin:
        print("❌ Use only one of --bot or --bot-pin")
        sys.exit(1)

    if args.train and args.train_pin:
        print("❌ Use only one of --train or --train-pin")
        sys.exit(1)

    code_version = args.code or args.code_pin
    bot_version = args.bot or args.bot_pin
    train_version = args.train or args.train_pin
    browser_version = args.browser_pin
    mcp_version = args.mcp_pin
    sandbox_version = args.sandbox_pin
    if code_version and not re.match(r'^\d+\.\d+\.\d+$', code_version):
        print(f"❌ Invalid code version format: {code_version}")
        print("   Expected format: X.Y.Z (e.g., 0.0.3)")
        sys.exit(1)

    if bot_version and not re.match(r'^\d+\.\d+\.\d+$', bot_version):
        print(f"❌ Invalid bot version format: {bot_version}")
        print("   Expected format: X.Y.Z (e.g., 0.0.2)")
        sys.exit(1)

    if train_version and not re.match(r'^\d+\.\d+\.\d+$', train_version):
        print(f"❌ Invalid train version format: {train_version}")
        print("   Expected format: X.Y.Z (e.g., 0.0.1)")
        sys.exit(1)

    if browser_version and not re.match(r'^\d+\.\d+\.\d+$', browser_version):
        print(f"❌ Invalid browser version format: {browser_version}")
        print("   Expected format: X.Y.Z (e.g., 0.0.1)")
        sys.exit(1)

    if mcp_version and not re.match(r'^\d+\.\d+\.\d+$', mcp_version):
        print(f"❌ Invalid mcp version format: {mcp_version}")
        print("   Expected format: X.Y.Z (e.g., 0.0.1)")
        sys.exit(1)

    if sandbox_version and not re.match(r'^\d+\.\d+\.\d+$', sandbox_version):
        print(f"❌ Invalid sandbox version format: {sandbox_version}")
        print("   Expected format: X.Y.Z (e.g., 0.0.1)")
        sys.exit(1)
    
    # Pre-flight checks
    print("\n🔍 Pre-flight checks...")
    
    if check_git_status():
        if args.no_add_all and not args.force:
            print("  ❌ Error: Working directory has uncommitted changes.")
            print("  💡 Stash or commit your feature changes before releasing, or use --force.")
            sys.exit(1)
        else:
            print("  ⚠️  Warning: You have uncommitted changes. These WILL be included in the release commit by default.")
            print("  💡 Use --no-add-all to prevent this.")
    else:
        print("  ✅ Git working directory is clean")
    
    # Wait for PyPI propagation if requested
    wait_agents = args.wait or args.wait_all
    wait_code = args.wait_code or args.wait_all
    wait_bot = args.wait_bot or args.wait_all
    wait_train = args.wait_train or args.wait_all
    wait_browser = args.wait_browser or args.wait_all
    wait_mcp = args.wait_mcp or args.wait_all
    wait_sandbox = args.wait_sandbox or args.wait_all

    if wait_agents and args.agents:
        if not wait_for_pypi_version("praisonaiagents", args.agents, max_wait=args.max_wait):
            print("\n💡 Tip: Check if the package was published successfully")
            print("💡 Tip: You can retry without --wait if the package is confirmed published")
            sys.exit(1)

    if wait_code and code_version:
        if not wait_for_pypi_version("praisonai-code", code_version, max_wait=args.max_wait):
            print("\n💡 Tip: Check if praisonai-code was published successfully")
            sys.exit(1)

    if wait_bot and bot_version:
        if not wait_for_pypi_version("praisonai-bot", bot_version, max_wait=args.max_wait):
            print("\n💡 Tip: Check if praisonai-bot was published successfully")
            sys.exit(1)

    if wait_train and train_version:
        if not wait_for_pypi_version("praisonai-train", train_version, max_wait=args.max_wait):
            print("\n💡 Tip: Check if praisonai-train was published successfully")
            sys.exit(1)

    if wait_browser and browser_version:
        if not wait_for_pypi_version("praisonai-browser", browser_version, max_wait=args.max_wait):
            print("\n💡 Tip: Check if praisonai-browser was published successfully")
            sys.exit(1)

    if wait_mcp and mcp_version:
        if not wait_for_pypi_version("praisonai-mcp", mcp_version, max_wait=args.max_wait):
            print("\n💡 Tip: Check if praisonai-mcp was published successfully")
            sys.exit(1)

    if wait_sandbox and sandbox_version:
        if not wait_for_pypi_version("praisonai-sandbox", sandbox_version, max_wait=args.max_wait):
            print("\n💡 Tip: Check if praisonai-sandbox was published successfully")
            sys.exit(1)
    
    # Run bump version
    bump_version(
        args.version,
        args.agents,
        code_version=code_version,
        code_pin_only=bool(args.code_pin and not args.code),
        bot_version=bot_version,
        bot_pin_only=bool(args.bot_pin and not args.bot),
        train_version=train_version,
        train_pin_only=bool(args.train_pin and not args.train),
        browser_version=browser_version,
        browser_pin_only=bool(args.browser_pin),
        mcp_version=mcp_version,
        mcp_pin_only=bool(args.mcp_pin),
        sandbox_version=sandbox_version,
        sandbox_pin_only=bool(args.sandbox_pin),
    )
    
    # Patch releases (--agents set): frozen targeted upgrade only.
    # Full releases: regenerate lock from scratch.
    patch_release = args.agents is not None
    if not validate_dependencies(
        max_retries=args.retries,
        use_frozen=patch_release,
        agents_version=args.agents,
        code_version=code_version,
        bot_version=bot_version,
        train_version=train_version,
        browser_version=browser_version,
        mcp_version=mcp_version,
        sandbox_version=sandbox_version,
    ):
        print("\n💡 Tip: Revert changes with 'git checkout .' if needed")
        print("💡 Tip: The package may need more time to propagate to PyPI")
        sys.exit(1)
    
    # Run release
    release(args.version, use_frozen_lock=patch_release, no_add_all=args.no_add_all)


if __name__ == "__main__":
    main()
