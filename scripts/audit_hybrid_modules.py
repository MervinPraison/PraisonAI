#!/usr/bin/env python3
"""Assert critical C8 hybrid import paths resolve (wrapper + code tiers)."""

from __future__ import annotations

import importlib
import sys


def _check(label: str, import_fn) -> None:
    try:
        import_fn()
    except Exception as exc:
        print(f"FAIL {label}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(f"OK   {label}")


def main() -> None:
    _check(
        "praisonai.cli.features.tui.app.TUIApp",
        lambda: importlib.import_module("praisonai.cli.features.tui.app").TUIApp,
    )
    _check(
        "praisonai.cli.features.tools.ToolsHandler",
        lambda: importlib.import_module("praisonai.cli.features.tools").ToolsHandler,
    )
    _check(
        "praisonai.cli.features.workflow.WorkflowHandler",
        lambda: importlib.import_module("praisonai.cli.features.workflow").WorkflowHandler,
    )
    _check(
        "praisonai.cli.interactive.core.InteractiveCore",
        lambda: importlib.import_module("praisonai.cli.interactive.core").InteractiveCore,
    )
    _check(
        "praisonai_code.cli.interactive.async_tui.AsyncTUI",
        lambda: importlib.import_module("praisonai_code.cli.interactive.async_tui").AsyncTUI,
    )
    _check(
        "praisonai_code.cli.features.workflow.WorkflowHandler",
        lambda: importlib.import_module("praisonai_code.cli.features.workflow").WorkflowHandler,
    )
    print("All hybrid module paths importable.")


if __name__ == "__main__":
    main()
