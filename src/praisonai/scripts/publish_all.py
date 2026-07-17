#!/usr/bin/env python3
"""
One-command monorepo PyPI release (patch by default).

Tier-2 packages are standalone: by default only changed packages are published,
plus the wrapper when a dependency pin needs updating (agents always flows to
wrapper when agents changes).

Publish order when selected:
  praisonaiagents → praisonai-code → praisonai-bot → praisonai-train
  → praisonai-browser → praisonai-mcp → praisonai-sandbox → praisonai (wrapper)

Usage (from repo root or src/praisonai):
  python scripts/publish_all.py                  # changed packages only (default)
  python scripts/publish_all.py --all            # bump + publish all eight
  python scripts/publish_all.py --dry-run        # preview versions only
  python scripts/publish_all.py --since v4.6.149 # diff since tag/ref
  python scripts/publish_all.py --skip-wrapper   # publish changed deps only

Requires: uv, git, UV_PUBLISH_TOKEN (or PYPI_TOKEN), clean working tree (or --force).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as scripts/publish_all.py from src/praisonai
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import _release_lib as lib  # noqa: E402
import bump_and_release as bump  # noqa: E402


def _wait(package: str, version: str, max_wait: int, interval: int = 30) -> None:
    if not bump.wait_for_pypi_version(package, version, max_wait=max_wait, interval=interval):
        raise SystemExit(f"Timeout waiting for {package}=={version} on PyPI")


def _plan_versions(
    bump_type: str,
    overrides: dict[str, str | None],
    skip: dict[str, bool],
    current: dict[str, str],
) -> dict[str, str]:
    planned: dict[str, str] = {}
    for key in lib.PACKAGE_KEYS:
        if overrides.get(key):
            planned[key] = overrides[key]  # type: ignore[assignment]
        elif skip[key]:
            planned[key] = current[key]
        else:
            planned[key] = lib.bump_semver(current[key], bump_type)
    return planned


def _apply_changed_only(
    skip: dict[str, bool],
    changed: set[str],
    overrides: dict[str, str | None],
    skip_wrapper_flag: bool,
) -> None:
    """Auto-skip unchanged tier packages; always refresh wrapper when deps ship."""
    if overrides.get("agents"):
        changed.add("agents")
    for key in ("code", "bot", "train", "browser", "mcp", "sandbox"):
        if overrides.get(key):
            changed.add(key)
    if overrides.get("wrapper"):
        changed.add("wrapper")

    for key in ("agents", "code", "bot", "train", "browser", "mcp", "sandbox"):
        if key not in changed:
            skip[key] = True

    dep_publish = any(not skip[k] for k in ("agents", "code", "bot", "train", "browser", "mcp", "sandbox"))
    if dep_publish and not skip_wrapper_flag:
        skip["wrapper"] = False
    elif "wrapper" not in changed:
        skip["wrapper"] = True


def _print_plan(
    planned: dict[str, str],
    skip: dict[str, bool],
    current: dict[str, str],
    *,
    changed_only: bool,
    since_ref: str | None,
    changed: set[str] | None,
) -> None:
    print("\n📋 Release plan\n")
    if changed_only and since_ref:
        print(f"  Mode: changed-only (git diff {since_ref}..HEAD)")
        if changed:
            names = ", ".join(lib.PYPI_NAMES[k] for k in lib.PACKAGE_KEYS if k in changed)
            print(f"  Changed: {names or '(none)'}")
        print()
    order = [
        ("agents", lib.PYPI_NAMES["agents"]),
        ("code", lib.PYPI_NAMES["code"]),
        ("bot", lib.PYPI_NAMES["bot"]),
        ("train", lib.PYPI_NAMES["train"]),
        ("browser", lib.PYPI_NAMES["browser"]),
        ("mcp", lib.PYPI_NAMES["mcp"]),
        ("sandbox", lib.PYPI_NAMES["sandbox"]),
        ("wrapper", lib.PYPI_NAMES["wrapper"]),
    ]
    for key, pypi_name in order:
        if skip.get(key):
            reason = "unchanged" if changed_only and changed and key not in changed else "skip"
            print(f"  SKIP  {pypi_name} ({reason})")
            continue
        on_pypi = lib.pypi_has_version(pypi_name, planned[key])
        tag = " (already on PyPI)" if on_pypi else ""
        bump_tag = "" if planned[key] != current[key] else " (pin only)"
        print(f"  {pypi_name}: {current[key]} → {planned[key]}{tag}{bump_tag}")
    print()


def _wrapper_bump_kwargs(
    planned: dict[str, str],
    current: dict[str, str],
    skip: dict[str, bool],
) -> dict:
    """Pin-only for unchanged tier packages; full pin for published ones."""
    return {
        "agents_version": planned["agents"],
        "code_version": planned["code"] if not skip["code"] else current["code"],
        "code_pin_only": skip["code"],
        "bot_version": planned["bot"] if not skip["bot"] else current["bot"],
        "bot_pin_only": skip["bot"],
        "train_version": planned["train"] if not skip["train"] else current["train"],
        "train_pin_only": skip["train"],
        "browser_version": planned["browser"] if not skip["browser"] else current["browser"],
        "browser_pin_only": skip["browser"],
        "mcp_version": planned["mcp"] if not skip["mcp"] else current["mcp"],
        "mcp_pin_only": skip["mcp"],
        "sandbox_version": planned["sandbox"] if not skip["sandbox"] else current["sandbox"],
        "sandbox_pin_only": skip["sandbox"],
    }


def _validate_kwargs(planned: dict[str, str], skip: dict[str, bool]) -> dict:
    return {
        "agents_version": None if skip["agents"] else planned["agents"],
        "code_version": None if skip["code"] else planned["code"],
        "bot_version": None if skip["bot"] else planned["bot"],
        "train_version": None if skip["train"] else planned["train"],
        "browser_version": None if skip["browser"] else planned["browser"],
        "mcp_version": None if skip["mcp"] else planned["mcp"],
        "sandbox_version": None if skip["sandbox"] else planned["sandbox"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish PraisonAI monorepo packages to PyPI in dependency order",
    )
    parser.add_argument(
        "--bump",
        choices=("patch", "minor", "major"),
        default="patch",
        help="Semver bump for packages selected to publish (default: patch)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Publish all eight packages (default: only changed packages since --since)",
    )
    parser.add_argument(
        "--since",
        default=None,
        metavar="REF",
        help="Git ref for change detection (default: latest v* tag, else origin/main)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show plan only; no publish")
    parser.add_argument("--force", "-f", action="store_true", help="Allow dirty git tree")
    parser.add_argument("--no-git", action="store_true", help="Publish only; skip git commit/push/tag")
    parser.add_argument("--max-wait", type=int, default=600, help="PyPI propagation wait (seconds)")
    parser.add_argument("--skip-agents", action="store_true")
    parser.add_argument("--skip-code", action="store_true")
    parser.add_argument("--skip-bot", action="store_true")
    parser.add_argument("--skip-train", action="store_true")
    parser.add_argument("--skip-browser", action="store_true")
    parser.add_argument("--skip-mcp", action="store_true")
    parser.add_argument("--skip-sandbox", action="store_true")
    parser.add_argument("--skip-wrapper", action="store_true")
    parser.add_argument("--agents-version", default=None)
    parser.add_argument("--code-version", default=None)
    parser.add_argument("--bot-version", default=None)
    parser.add_argument("--train-version", default=None)
    parser.add_argument("--browser-version", default=None)
    parser.add_argument("--mcp-version", default=None)
    parser.add_argument("--sandbox-version", default=None)
    parser.add_argument("--wrapper-version", default=None)
    args = parser.parse_args()

    root = lib.project_root()
    current = lib.read_current_versions()
    changed_only = not args.all
    since_ref = args.since or (lib.resolve_since_ref(root) if changed_only else None)
    changed: set[str] | None = None

    skip = {
        "agents": args.skip_agents,
        "code": args.skip_code,
        "bot": args.skip_bot,
        "train": args.skip_train,
        "browser": args.skip_browser,
        "mcp": args.skip_mcp,
        "sandbox": args.skip_sandbox,
        "wrapper": args.skip_wrapper,
    }
    overrides = {
        "agents": args.agents_version,
        "code": args.code_version,
        "bot": args.bot_version,
        "train": args.train_version,
        "browser": args.browser_version,
        "mcp": args.mcp_version,
        "sandbox": args.sandbox_version,
        "wrapper": args.wrapper_version,
    }

    if changed_only:
        changed = lib.detect_changed_packages(since_ref, root)
        _apply_changed_only(skip, changed, overrides, args.skip_wrapper)
        if not any(not skip[k] for k in lib.PACKAGE_KEYS):
            print(f"❌ No package changes detected since {since_ref}. Use --all to publish everything.")
            sys.exit(1)

    planned = _plan_versions(args.bump, overrides, skip, current)
    _print_plan(planned, skip, current, changed_only=changed_only, since_ref=since_ref, changed=changed)

    if args.dry_run:
        print("Dry run — no changes made.")
        return

    token = lib.resolve_pypi_token()
    if not token:
        print("❌ Set UV_PUBLISH_TOKEN or PYPI_TOKEN before publishing.")
        sys.exit(1)
    lib.ensure_uv_publish_token()

    if bump.check_git_status() and not args.force:
        print("❌ Working directory has uncommitted changes. Commit/stash or use --force.")
        sys.exit(1)

    def wait_published(key: str) -> None:
        if not skip[key]:
            _wait(lib.PYPI_NAMES[key], planned[key], args.max_wait)

    # --- 1. praisonaiagents (core) ---
    if not skip["agents"]:
        pkg = lib.PYPI_NAMES["agents"]
        ver = planned["agents"]
        if lib.pypi_has_version(pkg, ver):
            print(f"⏭️  {pkg}=={ver} already on PyPI")
        else:
            print(f"\n📦 Publishing {pkg} {ver}")
            lib.bump_agents_files(ver)
            lib.publish_package(lib.agents_dir())
            _wait(pkg, ver, args.max_wait)
            if not args.no_git:
                lib.git_commit_files(
                    f"Bump praisonaiagents to {ver}",
                    ["src/praisonai-agents/pyproject.toml", "src/praisonai-agents/uv.lock"],
                    root,
                )

    # --- 2. praisonai-code ---
    if not skip["code"]:
        pkg = lib.PYPI_NAMES["code"]
        ver = planned["code"]
        if lib.pypi_has_version(pkg, ver):
            print(f"⏭️  {pkg}=={ver} already on PyPI")
        else:
            print(f"\n📦 Publishing {pkg} {ver}")
            wait_published("agents")
            lib.bump_code_files(ver)
            lib.publish_package(lib.code_dir())
            _wait(pkg, ver, args.max_wait)
            if not args.no_git:
                lib.git_commit_files(
                    f"Bump praisonai-code to {ver}",
                    [
                        "src/praisonai-code/pyproject.toml",
                        "src/praisonai-code/praisonai_code/__init__.py",
                        "src/praisonai-code/uv.lock",
                    ],
                    root,
                )

    # --- 3. praisonai-bot ---
    if not skip["bot"]:
        pkg = lib.PYPI_NAMES["bot"]
        ver = planned["bot"]
        if lib.pypi_has_version(pkg, ver):
            print(f"⏭️  {pkg}=={ver} already on PyPI")
        else:
            print(f"\n📦 Publishing {pkg} {ver}")
            wait_published("agents")
            lib.bump_bot_files(ver)
            lib.publish_package(lib.bot_dir())
            _wait(pkg, ver, args.max_wait)
            if not args.no_git:
                lib.git_commit_files(
                    f"Bump praisonai-bot to {ver}",
                    [
                        "src/praisonai-bot/pyproject.toml",
                        "src/praisonai-bot/praisonai_bot/_version.py",
                        "src/praisonai-bot/uv.lock",
                    ],
                    root,
                )

    # --- 4. praisonai-train ---
    if not skip["train"]:
        pkg = lib.PYPI_NAMES["train"]
        ver = planned["train"]
        if lib.pypi_has_version(pkg, ver):
            print(f"⏭️  {pkg}=={ver} already on PyPI")
        else:
            print(f"\n📦 Publishing {pkg} {ver}")
            wait_published("agents")
            lib.bump_train_files(ver)
            lib.publish_package(lib.train_dir())
            _wait(pkg, ver, args.max_wait)
            if not args.no_git:
                lib.git_commit_files(
                    f"Bump praisonai-train to {ver}",
                    [
                        "src/praisonai-train/pyproject.toml",
                        "src/praisonai-train/praisonai_train/_version.py",
                        "src/praisonai-train/uv.lock",
                    ],
                    root,
                )

    # --- 5. praisonai-browser ---
    if not skip["browser"]:
        pkg = lib.PYPI_NAMES["browser"]
        ver = planned["browser"]
        if lib.pypi_has_version(pkg, ver):
            print(f"⏭️  {pkg}=={ver} already on PyPI")
        else:
            print(f"\n📦 Publishing {pkg} {ver}")
            wait_published("agents")
            lib.bump_browser_files(ver)
            lib.publish_package(lib.browser_dir())
            _wait(pkg, ver, args.max_wait)
            if not args.no_git:
                lib.git_commit_files(
                    f"Bump praisonai-browser to {ver}",
                    [
                        "src/praisonai-browser/pyproject.toml",
                        "src/praisonai-browser/praisonai_browser/_version.py",
                    ],
                    root,
                )

    # --- 6. praisonai-mcp ---
    if not skip["mcp"]:
        pkg = lib.PYPI_NAMES["mcp"]
        ver = planned["mcp"]
        if lib.pypi_has_version(pkg, ver):
            print(f"⏭️  {pkg}=={ver} already on PyPI")
        else:
            print(f"\n📦 Publishing {pkg} {ver}")
            wait_published("agents")
            lib.bump_mcp_files(ver)
            lib.publish_package(lib.mcp_dir())
            _wait(pkg, ver, args.max_wait)
            if not args.no_git:
                lib.git_commit_files(
                    f"Bump praisonai-mcp to {ver}",
                    [
                        "src/praisonai-mcp/pyproject.toml",
                        "src/praisonai-mcp/uv.lock",
                        "src/praisonai-mcp/praisonai_mcp/_version.py",
                    ],
                    root,
                )

    # --- 7. praisonai-sandbox ---
    if not skip["sandbox"]:
        pkg = lib.PYPI_NAMES["sandbox"]
        ver = planned["sandbox"]
        if lib.pypi_has_version(pkg, ver):
            print(f"⏭️  {pkg}=={ver} already on PyPI")
        else:
            print(f"\n📦 Publishing {pkg} {ver}")
            wait_published("agents")
            lib.bump_sandbox_files(ver)
            lib.publish_package(lib.sandbox_dir())
            _wait(pkg, ver, args.max_wait)
            if not args.no_git:
                lib.git_commit_files(
                    f"Bump praisonai-sandbox to {ver}",
                    [
                        "src/praisonai-sandbox/pyproject.toml",
                        "src/praisonai-sandbox/uv.lock",
                        "src/praisonai-sandbox/praisonai_sandbox/_version.py",
                    ],
                    root,
                )

    # --- 8. praisonai wrapper ---
    if not skip["wrapper"]:
        pkg = lib.PYPI_NAMES["wrapper"]
        ver = planned["wrapper"]
        if lib.pypi_has_version(pkg, ver):
            print(f"⏭️  {pkg}=={ver} already on PyPI")
        else:
            print(f"\n📦 Publishing {pkg} (wrapper) {ver}")
            for key in ("agents", "code", "bot", "train", "browser", "mcp", "sandbox"):
                wait_published(key)

            bump.bump_version(ver, **_wrapper_bump_kwargs(planned, current, skip))
            if not bump.validate_dependencies(max_retries=3, use_frozen=True, **_validate_kwargs(planned, skip)):
                sys.exit(1)

            if args.no_git:
                lib.publish_package(lib.wrapper_dir())
            else:
                bump.release(ver, use_frozen_lock=True, no_add_all=True)
                lib.publish_package(lib.wrapper_dir())

    print("\n✅ Monorepo publish complete.")
    for key in lib.PACKAGE_KEYS:
        label = lib.PYPI_NAMES[key].ljust(17)
        status = "published" if not skip[key] else "skipped"
        print(f"   {label} {planned[key]} ({status})")


if __name__ == "__main__":
    main()
