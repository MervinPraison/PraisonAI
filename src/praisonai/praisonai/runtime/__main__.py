"""
Entrypoint so ``python -m praisonai.runtime`` boots a warm runtime.

Used by ``praisonai daemon start --background`` to spawn a detached process.
"""

from __future__ import annotations

import argparse
import signal
import sys

from .server import serve_runtime


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
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
