"""Shared helpers for monorepo PyPI release scripts."""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")

PYPI_NAMES = {
    "agents": "praisonaiagents",
    "code": "praisonai-code",
    "bot": "praisonai-bot",
    "train": "praisonai-train",
    "browser": "praisonai-browser",
    "mcp": "praisonai-mcp",
    "sandbox": "praisonai-sandbox",
    "wrapper": "praisonai",
}

PACKAGE_KEYS = ("agents", "code", "bot", "train", "browser", "mcp", "sandbox", "wrapper")

# Path prefixes used to detect which packages changed in git (longest match wins).
PACKAGE_PATH_PREFIXES: dict[str, tuple[str, ...]] = {
    "agents": ("src/praisonai-agents/",),
    "code": ("src/praisonai-code/",),
    "bot": ("src/praisonai-bot/",),
    "train": ("src/praisonai-train/",),
    "browser": ("src/praisonai-browser/",),
    "mcp": ("src/praisonai-mcp/",),
    "sandbox": ("src/praisonai-sandbox/",),
    "wrapper": ("src/praisonai/", "docker/"),
}


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent


def agents_dir() -> Path:
    return project_root() / "src/praisonai-agents"


def code_dir() -> Path:
    return project_root() / "src/praisonai-code"


def bot_dir() -> Path:
    return project_root() / "src/praisonai-bot"


def train_dir() -> Path:
    return project_root() / "src/praisonai-train"


def browser_dir() -> Path:
    return project_root() / "src/praisonai-browser"


def mcp_dir() -> Path:
    return project_root() / "src/praisonai-mcp"


def sandbox_dir() -> Path:
    return project_root() / "src/praisonai-sandbox"


def wrapper_dir() -> Path:
    return project_root() / "src/praisonai"


def run(cmd: list[str], cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=__import__("sys").stderr)
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(cmd)}")
    return result


def bump_semver(version: str, bump: str) -> str:
    if not SEMVER.match(version):
        raise ValueError(f"Invalid semver: {version!r}")
    major, minor, patch = (int(x) for x in version.split("."))
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"Unknown bump type: {bump!r}")


def read_pyproject_version(path: Path) -> str:
    content = path.read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if not match:
        raise ValueError(f"No version in {path}")
    return match.group(1)


def write_pyproject_version(path: Path, current: str, new: str) -> None:
    content = path.read_text()
    updated = content.replace(f'version = "{current}"', f'version = "{new}"', 1)
    if updated == content:
        raise ValueError(f"Could not bump version in {path} ({current!r} -> {new!r})")
    path.write_text(updated)


def read_wrapper_version() -> str:
    version_py = wrapper_dir() / "praisonai/version.py"
    match = re.search(r'__version__ = "([^"]+)"', version_py.read_text())
    if not match:
        raise ValueError("Could not read wrapper version")
    return match.group(1)


def read_current_versions() -> dict[str, str]:
    return {
        "agents": read_pyproject_version(agents_dir() / "pyproject.toml"),
        "code": read_pyproject_version(code_dir() / "pyproject.toml"),
        "bot": read_pyproject_version(bot_dir() / "pyproject.toml"),
        "train": read_pyproject_version(train_dir() / "pyproject.toml"),
        "browser": read_pyproject_version(browser_dir() / "pyproject.toml"),
        "mcp": read_pyproject_version(mcp_dir() / "pyproject.toml"),
        "sandbox": read_pyproject_version(sandbox_dir() / "pyproject.toml"),
        "wrapper": read_wrapper_version(),
    }


def resolve_since_ref(root: Optional[Path] = None) -> str:
    """Git ref to diff against for change detection (last release tag, else main)."""
    root = root or project_root()
    for cmd in (
        ["git", "describe", "--tags", "--match", "v*", "--abbrev=0"],
        ["git", "rev-parse", "origin/main"],
        ["git", "rev-parse", "HEAD~1"],
    ):
        result = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    return "HEAD~1"


def _package_for_path(path: str) -> Optional[str]:
    matches = [
        (pkg, prefix)
        for pkg, prefixes in PACKAGE_PATH_PREFIXES.items()
        for prefix in prefixes
        if path.startswith(prefix)
    ]
    if not matches:
        return None
    # Prefer the longest prefix (e.g. praisonai-mcp over praisonai wrapper).
    matches.sort(key=lambda item: len(item[1]), reverse=True)
    return matches[0][0]


def detect_changed_packages(since_ref: str, root: Optional[Path] = None) -> set[str]:
    """Return package keys with file changes between since_ref and HEAD."""
    root = root or project_root()
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{since_ref}..HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git diff failed ({since_ref}..HEAD): {result.stderr.strip() or result.stdout}"
        )
    changed: set[str] = set()
    for line in result.stdout.splitlines():
        path = line.strip()
        if not path:
            continue
        pkg = _package_for_path(path)
        if pkg:
            changed.add(pkg)
    return changed


def pypi_has_version(package: str, version: str) -> bool:
    url = f"https://pypi.org/pypi/{package}/{version}/json"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            json.loads(resp.read().decode())
        return True
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise


def get_pypi_latest(package: str) -> Optional[str]:
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{package}/json", timeout=15) as resp:
            data = json.loads(resp.read().decode())
        return data["info"]["version"]
    except Exception:
        return None


def bump_agents_files(new_version: str) -> None:
    path = agents_dir() / "pyproject.toml"
    current = read_pyproject_version(path)
    write_pyproject_version(path, current, new_version)


def bump_code_files(new_version: str) -> None:
    path = code_dir() / "pyproject.toml"
    current = read_pyproject_version(path)
    write_pyproject_version(path, current, new_version)
    init_py = code_dir() / "praisonai_code/__init__.py"
    init_py.write_text(
        re.sub(r'__version__ = "[^"]+"', f'__version__ = "{new_version}"', init_py.read_text(), count=1)
    )


def bump_bot_files(new_version: str) -> None:
    path = bot_dir() / "pyproject.toml"
    current = read_pyproject_version(path)
    write_pyproject_version(path, current, new_version)
    version_py = bot_dir() / "praisonai_bot/_version.py"
    version_py.write_text(
        re.sub(r'__version__ = "[^"]+"', f'__version__ = "{new_version}"', version_py.read_text(), count=1)
    )


def bump_train_files(new_version: str) -> None:
    path = train_dir() / "pyproject.toml"
    current = read_pyproject_version(path)
    write_pyproject_version(path, current, new_version)
    version_py = train_dir() / "praisonai_train/_version.py"
    version_py.write_text(
        re.sub(r'__version__ = "[^"]+"', f'__version__ = "{new_version}"', version_py.read_text(), count=1)
    )


def bump_browser_files(new_version: str) -> None:
    path = browser_dir() / "pyproject.toml"
    current = read_pyproject_version(path)
    write_pyproject_version(path, current, new_version)
    version_py = browser_dir() / "praisonai_browser/_version.py"
    version_py.write_text(
        re.sub(r'__version__ = "[^"]+"', f'__version__ = "{new_version}"', version_py.read_text(), count=1)
    )


def bump_mcp_files(new_version: str) -> None:
    path = mcp_dir() / "pyproject.toml"
    current = read_pyproject_version(path)
    write_pyproject_version(path, current, new_version)
    version_py = mcp_dir() / "praisonai_mcp/_version.py"
    version_py.write_text(
        re.sub(r'__version__ = "[^"]+"', f'__version__ = "{new_version}"', version_py.read_text(), count=1)
    )


def bump_sandbox_files(new_version: str) -> None:
    path = sandbox_dir() / "pyproject.toml"
    current = read_pyproject_version(path)
    write_pyproject_version(path, current, new_version)
    version_py = sandbox_dir() / "praisonai_sandbox/_version.py"
    version_py.write_text(
        re.sub(r'__version__ = "[^"]+"', f'__version__ = "{new_version}"', version_py.read_text(), count=1)
    )


def resolve_pypi_token() -> str | None:
    """Return PyPI token from env (UV_PUBLISH_TOKEN, PYPI_TOKEN, or PYPI_API_TOKEN)."""
    return (
        os.environ.get("UV_PUBLISH_TOKEN")
        or os.environ.get("PYPI_TOKEN")
        or os.environ.get("PYPI_API_TOKEN")
    )


def ensure_uv_publish_token() -> None:
    """Map PYPI_TOKEN / PYPI_API_TOKEN into UV_PUBLISH_TOKEN for uv publish."""
    if os.environ.get("UV_PUBLISH_TOKEN"):
        return
    token = os.environ.get("PYPI_TOKEN") or os.environ.get("PYPI_API_TOKEN")
    if token:
        os.environ["UV_PUBLISH_TOKEN"] = token


def publish_package(package_dir: Path) -> None:
    token = resolve_pypi_token()
    if not token:
        raise RuntimeError("Missing PyPI credentials. Set UV_PUBLISH_TOKEN or PYPI_TOKEN.")
    ensure_uv_publish_token()
    dist = package_dir / "dist"
    if dist.exists():
        import shutil
        shutil.rmtree(dist)
    # Regenerate the lockfile so it matches the current pyproject. `--frozen` fails
    # when a package has no committed lockfile or when dependencies changed; a plain
    # `uv lock` creates/updates it, keeping publish resilient to dependency edits.
    run(["uv", "lock"], cwd=package_dir)
    run(["uv", "build"], cwd=package_dir)
    run(["uv", "publish", "--trusted-publishing", "never"], cwd=package_dir)


def git_commit_files(message: str, rel_paths: list[str], root: Optional[Path] = None) -> bool:
    root = root or project_root()
    existing = [p for p in rel_paths if (root / p).exists()]
    if not existing:
        return False
    run(["git", "add"] + existing, cwd=root)
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=root,
        capture_output=True,
    )
    if result.returncode == 0:
        print(f"  ⏭️  Nothing to commit for: {message}")
        return False
    run(["git", "commit", "-m", message], cwd=root)
    run(["git", "pull", "--rebase", "origin", "main"], cwd=root, check=False)
    run(["git", "push", "origin", "main"], cwd=root, check=False)
    return True
