"""
Entrypoint so ``python -m praisonai.runtime`` boots a warm runtime.

Used by ``praisonai daemon start --background`` to spawn a detached process.
"""

from __future__ import annotations

import argparse
import signal
import sys

from .server import serve_runtime

# Restart-intent exit-code protocol (Issue #2437). Shared with the gateway
# CLI; source of truth lives in core. Fall back to the sysexits.h values and
# a minimal classifier if running against an older core.
try:
    from praisonaiagents.gateway import (
        GATEWAY_OK_EXIT_CODE,
        GATEWAY_RESTART_EXIT_CODE,
        GATEWAY_FATAL_CONFIG_EXIT_CODE,
        FatalConfigError,
        classify_exit_reason,
    )
except ImportError:  # pragma: no cover - older core without the protocol
    GATEWAY_OK_EXIT_CODE = 0
    GATEWAY_RESTART_EXIT_CODE = 75
    GATEWAY_FATAL_CONFIG_EXIT_CODE = 78

    class FatalConfigError(Exception):
        """Fallback fatal-config error when core lacks the protocol."""

    def classify_exit_reason(exc):  # type: ignore[no-redef]
        if exc is None or isinstance(exc, KeyboardInterrupt):
            return GATEWAY_OK_EXIT_CODE
        if isinstance(exc, FatalConfigError):
            return GATEWAY_FATAL_CONFIG_EXIT_CODE
        return GATEWAY_RESTART_EXIT_CODE


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="praisonai.runtime")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--model", default=None)
    parser.add_argument("--idle-timeout", type=float, default=1800.0)
    args = parser.parse_args(argv)

    # Terminate cleanly on SIGTERM so the lockfile is removed.
    def _handle_term(signum, frame):  # noqa: ANN001
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _handle_term)

    try:
        serve_runtime(
            host=args.host,
            port=args.port,
            model=args.model,
            idle_timeout=args.idle_timeout,
        )
    except KeyboardInterrupt:
        # Clean stop (SIGTERM/Ctrl+C) — lockfile removed, do not restart-loop.
        return GATEWAY_OK_EXIT_CODE
    except FatalConfigError as exc:
        # Unrecoverable config — tell the supervisor to stop restarting (#2437).
        print(f"Fatal config error: {exc}")
        return GATEWAY_FATAL_CONFIG_EXIT_CODE
    except Exception as exc:  # noqa: BLE001
        # Transient failure — ask the supervisor to restart us (#2437).
        print(f"Runtime exited with a transient error: {exc}")
        return classify_exit_reason(exc)
    return GATEWAY_OK_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
