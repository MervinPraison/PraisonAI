#!/usr/bin/env python3
"""Mechanical migration: praisonai wrapper bot/gateway tree → praisonai_bot package."""

from __future__ import annotations

import re
import shutil
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WRAPPER = REPO / "src" / "praisonai" / "praisonai"
BOT_PKG = REPO / "src" / "praisonai-bot" / "praisonai_bot"
TESTS_SRC = REPO / "src" / "praisonai" / "tests"
TESTS_DST = REPO / "src" / "praisonai-bot" / "tests"

# (source relative to WRAPPER, dest relative to BOT_PKG)
DIR_COPIES = [
    "bots",
    "gateway",
    "daemon",
    "kanban",
    "claw",
]

INTEGRATION_FILES = [
    "integration/gateway_host.py",
    "integration/host_app.py",
    "integration/context_files.py",
    "integration/pages/bot_health.py",
    "integration/bridges/kanban_bridge.py",
]

CLI_COMMANDS = [
    "cli/commands/bot.py",
    "cli/commands/gateway.py",
    "cli/commands/pairing.py",
    "cli/commands/identity.py",
    "cli/commands/onboard.py",
    "cli/commands/kanban.py",
    "cli/commands/claw.py",
    "cli/commands/mint_link.py",
]

CLI_FEATURES = [
    "cli/features/gateway.py",
    "cli/features/bots_cli.py",
    "cli/features/onboard.py",
    "cli/features/approval.py",
]

CLI_LEGACY = [
    "cli/legacy/dispatch/legacy_dispatch.py",
    "cli/legacy/dispatch/argparse_builder.py",
]

TOOLS_FILES = ["tools/audio.py"]

TEST_DIRS = [
    "unit/bots",
    "unit/gateway",
    "integration/bots",
    "integration/gateway",
]

IMPORT_REPLACEMENTS = [
    (re.compile(r"\bfrom praisonai\.bots\b"), "from praisonai_bot.bots"),
    (re.compile(r"\bimport praisonai\.bots\b"), "import praisonai_bot.bots"),
    (re.compile(r"\bfrom praisonai\.gateway\b"), "from praisonai_bot.gateway"),
    (re.compile(r"\bimport praisonai\.gateway\b"), "import praisonai_bot.gateway"),
    (re.compile(r"\bfrom praisonai\.daemon\b"), "from praisonai_bot.daemon"),
    (re.compile(r"\bimport praisonai\.daemon\b"), "import praisonai_bot.daemon"),
    (re.compile(r"\bfrom praisonai\.kanban\b"), "from praisonai_bot.kanban"),
    (re.compile(r"\bimport praisonai\.kanban\b"), "import praisonai_bot.kanban"),
    (re.compile(r"\bfrom praisonai\.claw\b"), "from praisonai_bot.claw"),
    (re.compile(r"\bimport praisonai\.claw\b"), "import praisonai_bot.claw"),
    (re.compile(r"\bfrom praisonai\.integration\b"), "from praisonai_bot.integration"),
    (re.compile(r"\bimport praisonai\.integration\b"), "import praisonai_bot.integration"),
    (re.compile(r"\bfrom praisonai\.tools\.audio\b"), "from praisonai_bot.tools.audio"),
    (re.compile(r"\bfrom praisonai\.tool_resolver\b"), "from praisonai_code.tool_resolver"),
    (re.compile(r"\bfrom praisonai\.llm\.env\b"), "from praisonai_code.llm.env"),
    (re.compile(r"\bfrom praisonai\.cli\.features\.gateway\b"), "from praisonai_bot.cli.features.gateway"),
    (re.compile(r"\bfrom praisonai\.cli\.features\.bots_cli\b"), "from praisonai_bot.cli.features.bots_cli"),
    (re.compile(r"\bfrom praisonai\.cli\.features\.onboard\b"), "from praisonai_bot.cli.features.onboard"),
    (re.compile(r"\bfrom praisonai\.cli\.features\.approval\b"), "from praisonai_bot.cli.features.approval"),
    (re.compile(r"\bfrom praisonai\.cli\.commands\.bot\b"), "from praisonai_bot.cli.commands.bot"),
    (re.compile(r"\bfrom praisonai\.cli\.commands\.gateway\b"), "from praisonai_bot.cli.commands.gateway"),
    (re.compile(r"\bfrom praisonai\.cli\.legacy\.dispatch\b"), "from praisonai_bot.cli.legacy.dispatch"),
]

SHIM_PACKAGES = [
    ("praisonai.bots", "praisonai_bot.bots", WRAPPER / "bots"),
    ("praisonai.gateway", "praisonai_bot.gateway", WRAPPER / "gateway"),
    ("praisonai.daemon", "praisonai_bot.daemon", WRAPPER / "daemon"),
    ("praisonai.kanban", "praisonai_bot.kanban", WRAPPER / "kanban"),
    ("praisonai.claw", "praisonai_bot.claw", WRAPPER / "claw"),
]

SHIM_SINGLE_FILES = [
    ("praisonai.cli.commands.bot", "praisonai_bot.cli.commands.bot", WRAPPER / "cli/commands/bot.py"),
    ("praisonai.cli.commands.gateway", "praisonai_bot.cli.commands.gateway", WRAPPER / "cli/commands/gateway.py"),
    ("praisonai.cli.commands.pairing", "praisonai_bot.cli.commands.pairing", WRAPPER / "cli/commands/pairing.py"),
    ("praisonai.cli.commands.identity", "praisonai_bot.cli.commands.identity", WRAPPER / "cli/commands/identity.py"),
    ("praisonai.cli.commands.onboard", "praisonai_bot.cli.commands.onboard", WRAPPER / "cli/commands/onboard.py"),
    ("praisonai.cli.commands.kanban", "praisonai_bot.cli.commands.kanban", WRAPPER / "cli/commands/kanban.py"),
    ("praisonai.cli.commands.claw", "praisonai_bot.cli.commands.claw", WRAPPER / "cli/commands/claw.py"),
    ("praisonai.cli.commands.mint_link", "praisonai_bot.cli.commands.mint_link", WRAPPER / "cli/commands/mint_link.py"),
]


def rewrite_imports(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    original = text
    for pattern, repl in IMPORT_REPLACEMENTS:
        text = pattern.sub(repl, text)
    if text != original:
        path.write_text(text, encoding="utf-8")


def copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    for py in dst.rglob("*.py"):
        rewrite_imports(py)


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    rewrite_imports(dst)


def write_shim_package(old_name: str, new_name: str, shim_dir: Path) -> None:
    shim_dir.mkdir(parents=True, exist_ok=True)
    init = shim_dir / "__init__.py"
    init.write_text(
        textwrap.dedent(
            f'''\
            """Backward-compatibility shim for :mod:`{old_name}`."""
            from praisonai._bootstrap import ensure_praisonai_bot

            ensure_praisonai_bot()
            from praisonai.cli._shim import alias_package

            alias_package("{old_name}", "{new_name}")
            '''
        ),
        encoding="utf-8",
    )
    for child in list(shim_dir.glob("*.py")):
        if child.name != "__init__.py":
            child.unlink()
    for child in list(shim_dir.iterdir()):
        if child.is_dir() and child.name != "__pycache__":
            shutil.rmtree(child)


def write_shim_module(old_mod: str, new_mod: str, shim_path: Path) -> None:
    shim_path.parent.mkdir(parents=True, exist_ok=True)
    shim_path.write_text(
        textwrap.dedent(
            f'''\
            """Backward-compatibility shim for :mod:`{old_mod}`."""
            import sys as _sys

            from praisonai._bootstrap import ensure_praisonai_bot

            ensure_praisonai_bot()
            import {new_mod} as _impl

            _sys.modules[__name__] = _impl
            '''
        ),
        encoding="utf-8",
    )


def main() -> None:
    BOT_PKG.mkdir(parents=True, exist_ok=True)

    for name in DIR_COPIES:
        src = WRAPPER / name
        if src.is_dir():
            copy_tree(src, BOT_PKG / name)

    for rel in INTEGRATION_FILES:
        copy_file(WRAPPER / rel, BOT_PKG / rel)

    for rel in TOOLS_FILES:
        copy_file(WRAPPER / rel, BOT_PKG / rel)

    for rel in CLI_COMMANDS:
        copy_file(WRAPPER / rel, BOT_PKG / rel)

    for rel in CLI_FEATURES:
        copy_file(WRAPPER / rel, BOT_PKG / rel)

    for rel in CLI_LEGACY:
        copy_file(WRAPPER / rel, BOT_PKG / rel)

    # Fix relative imports in botos (..gateway -> praisonai_bot.gateway stays relative)
    for py in BOT_PKG.rglob("*.py"):
        rewrite_imports(py)

    for old_name, new_name, shim_dir in SHIM_PACKAGES:
        write_shim_package(old_name, new_name, shim_dir)

    for old_mod, new_mod, shim_path in SHIM_SINGLE_FILES:
        write_shim_module(old_mod, new_mod, shim_path)

    # Feature shims (single files in hybrid package)
    for feat in ("gateway", "bots_cli", "onboard", "approval"):
        write_shim_module(
            f"praisonai.cli.features.{feat}",
            f"praisonai_bot.cli.features.{feat}",
            WRAPPER / "cli/features" / f"{feat}.py",
        )

    # Tests
    for rel in TEST_DIRS:
        src = TESTS_SRC / rel
        dst = TESTS_DST / rel
        if src.is_dir():
            copy_tree(src, dst)

    for pattern in (
        "test_bot*.py",
        "test_gateway*.py",
        "test_bots_cli.py",
        "test_botos*.py",
    ):
        for src in TESTS_SRC.glob(f"unit/{pattern}"):
            dst = TESTS_DST / "unit" / src.name
            copy_file(src, dst)

    for src in (TESTS_SRC / "unit/cli").glob("test_gateway*.py"):
        copy_file(src, TESTS_DST / "unit/cli" / src.name)
    for src in (TESTS_SRC / "unit/cli").glob("test_onboard*.py"):
        copy_file(src, TESTS_DST / "unit/cli" / src.name)
    for src in (TESTS_SRC / "unit/cli").glob("test_legacy_parse_args.py"):
        copy_file(src, TESTS_DST / "unit/cli" / src.name)
    if (TESTS_SRC / "unit/daemon/test_daemon_dispatch.py").exists():
        copy_file(
            TESTS_SRC / "unit/daemon/test_daemon_dispatch.py",
            TESTS_DST / "unit/daemon/test_daemon_dispatch.py",
        )

    print("C9 migration copy complete:", BOT_PKG)


if __name__ == "__main__":
    main()
