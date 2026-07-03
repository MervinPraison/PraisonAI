"""Plain dispatch helpers for legacy parse_args (C8.4).

Not a formal registry — a thin routing layer that returns exit codes
so parse_args can exit once at the top level.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from argparse import Namespace

HandlerFn = Callable[["PraisonAI", "Namespace", list[str]], Optional[int]]


def dispatch_gateway(praison, args: "Namespace", unknown_args: list[str]) -> int:
    """Route gateway to wrapper feature handler via bridge."""
    from praisonai_code._wrapper_bridge import import_wrapper_module, wrapper_available

    if not wrapper_available():
        print("Gateway requires the full PraisonAI wrapper. Install with: pip install praisonai")
        print("Or use: praisonai gateway ...")
        return 1
    mod = import_wrapper_module("praisonai.cli.features.gateway")
    return mod.handle_gateway_command(unknown_args)


def dispatch_bot(praison, args: "Namespace", unknown_args: list[str]) -> int:
    """Route bot to wrapper feature handler via bridge."""
    from praisonai_code._wrapper_bridge import import_wrapper_module, wrapper_available

    if not wrapper_available():
        print("Bot commands require the full PraisonAI wrapper. Install with: pip install praisonai")
        print("Or use: praisonai bot ...")
        return 1
    bot_args = list(unknown_args)
    if getattr(args, "model", None) and "--model" not in bot_args and "-m" not in bot_args:
        bot_args.extend(["--model", args.model])
    mod = import_wrapper_module("praisonai.cli.features.bots_cli")
    return mod.handle_bot_command(bot_args)


# Commands redirected through bridge (Typer is canonical; legacy path uses bridge)
WRAPPER_FEATURE_DISPATCH: dict[str, HandlerFn] = {
    "gateway": dispatch_gateway,
    "bot": dispatch_bot,
}


def run_wrapper_feature(command: str, praison, args: "Namespace", unknown_args: list[str]) -> Optional[int]:
    """Run a wrapper-resident legacy handler. Returns exit code or None if unhandled."""
    handler = WRAPPER_FEATURE_DISPATCH.get(command)
    if handler is None:
        return None
    return handler(praison, args, unknown_args)
