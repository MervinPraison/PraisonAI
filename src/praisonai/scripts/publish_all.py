#!/usr/bin/env python3
"""
One-command monorepo PyPI release (patch by default).

Publishes all six packages in order:
  praisonaiagents → praisonai-code → praisonai-bot → praisonai-train → praisonai-browser → praisonai (wrapper)

Usage (from repo root or src/praisonai):
  python scripts/publish_all.py                  # patch bump + publish all
  python scripts/publish_all.py --dry-run        # preview versions only
  python scripts/publish_all.py --bump minor
  python scripts/publish_all.py --skip-wrapper   # publish deps only

Requires: uv, git, UV_PUBLISH_TOKEN (or PYPI_TOKEN), clean working tree (or --force).
"""

from __future__ import annotations

import argparse
import os
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


def _plan_versions(bump_type: str, overrides: dict[str, str | None]) -> dict[str, str]:
    current = lib.read_current_versions()
    planned: dict[str, str] = {}
    for key in ("agents", "code", "bot", "train", "browser", "wrapper"):
        planned[key] = overrides.get(key) or lib.bump_semver(current[key], bump_type)
    return planned


def _print_plan(planned: dict[str, str], skip: dict[str, bool]) -> None:
    print("\n📋 Release plan\n")
    order = [
        ("agents", lib.PYPI_NAMES["agents"]),
        ("code", lib.PYPI_NAMES["code"]),
        ("bot", lib.PYPI_NAMES["bot"]),
        ("train", lib.PYPI_NAMES["train"]),
        ("browser", lib.PYPI_NAMES["browser"]),
        ("wrapper", lib.PYPI_NAMES["wrapper"]),
    ]
    current = lib.read_current_versions()
    for key, pypi_name in order:
        if skip.get(key):
            print(f"  SKIP  {pypi_name}")
            continue
        on_pypi = lib.pypi_has_version(pypi_name, planned[key])
        tag = " (already on PyPI)" if on_pypi else ""
        print(f"  {pypi_name}: {current[key]} → {planned[key]}{tag}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish all PraisonAI monorepo packages to PyPI in order",
    )
    parser.add_argument(
        "--bump",
        choices=("patch", "minor", "major"),
        default="patch",
        help="Semver bump for all packages (default: patch)",
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
    parser.add_argument("--skip-wrapper", action="store_true")
    parser.add_argument("--agents-version", default=None)
    parser.add_argument("--code-version", default=None)
    parser.add_argument("--bot-version", default=None)
    parser.add_argument("--train-version", default=None)
    parser.add_argument("--browser-version", default=None)
    parser.add_argument("--wrapper-version", default=None)
    args = parser.parse_args()

    skip = {
        "agents": args.skip_agents,
        "code": args.skip_code,
        "bot": args.skip_bot,
        "train": args.skip_train,
        "browser": args.skip_browser,
        "wrapper": args.skip_wrapper,
    }
    overrides = {
        "agents": args.agents_version,
        "code": args.code_version,
        "bot": args.bot_version,
        "train": args.train_version,
        "browser": args.browser_version,
        "wrapper": args.wrapper_version,
    }
    planned = _plan_versions(args.bump, overrides)
    _print_plan(planned, skip)

    if args.dry_run:
        print("Dry run — no changes made.")
        return

    token = lib.resolve_pypi_token()
    if not token:
        print("❌ Set UV_PUBLISH_TOKEN or PYPI_TOKEN before publishing.")
        sys.exit(1)
    lib.ensure_uv_publish_token()

    if bump.check_git_status() and not args.force:
        print("❌ Working tree has uncommitted changes. Commit/stash or use --force.")
        sys.exit(1)

    root = lib.project_root()

    # --- 1. praisonaiagents ---
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
            _wait(lib.PYPI_NAMES["agents"], planned["agents"], args.max_wait)
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
            _wait(lib.PYPI_NAMES["agents"], planned["agents"], args.max_wait)
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
            _wait(lib.PYPI_NAMES["bot"], planned["bot"], args.max_wait)
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
            _wait(lib.PYPI_NAMES["train"], planned["train"], args.max_wait)
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

    # --- 6. praisonai wrapper ---
    if not skip["wrapper"]:
        pkg = lib.PYPI_NAMES["wrapper"]
        ver = planned["wrapper"]
        if lib.pypi_has_version(pkg, ver):
            print(f"⏭️  {pkg}=={ver} already on PyPI")
        else:
            print(f"\n📦 Publishing {pkg} (wrapper) {ver}")
            _wait(lib.PYPI_NAMES["agents"], planned["agents"], args.max_wait)
            _wait(lib.PYPI_NAMES["code"], planned["code"], args.max_wait)
            _wait(lib.PYPI_NAMES["bot"], planned["bot"], args.max_wait)
            _wait(lib.PYPI_NAMES["train"], planned["train"], args.max_wait)
            _wait(lib.PYPI_NAMES["browser"], planned["browser"], args.max_wait)

            bump.bump_version(
                ver,
                planned["agents"],
                code_version=planned["code"],
                bot_version=planned["bot"],
                train_version=planned["train"],
                browser_version=planned["browser"],
            )
            if not bump.validate_dependencies(
                max_retries=3,
                use_frozen=True,
                agents_version=planned["agents"],
                code_version=planned["code"],
                bot_version=planned["bot"],
                train_version=planned["train"],
                browser_version=planned["browser"],
            ):
                sys.exit(1)

            if args.no_git:
                lib.publish_package(lib.wrapper_dir())
            else:
                bump.release(ver, use_frozen_lock=True, no_add_all=True)
                lib.publish_package(lib.wrapper_dir())

    print("\n✅ Monorepo publish complete.")
    print(f"   praisonaiagents {planned['agents']}")
    print(f"   praisonai-code    {planned['code']}")
    print(f"   praisonai-bot     {planned['bot']}")
    print(f"   praisonai-train   {planned['train']}")
    print(f"   praisonai-browser {planned['browser']}")
    print(f"   praisonai         {planned['wrapper']}")


if __name__ == "__main__":
    main()
