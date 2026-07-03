"""Console entry for ``python -m praisonai_code`` and ``praisonai-code`` script."""

from __future__ import annotations

import os
import sys


def main() -> None:
    """Run the Typer CLI (agentic terminal product)."""
    from praisonai_code._logging import configure_cli_logging
    from praisonai_code._wrapper_bridge import wrapper_available
    from praisonai_code.cli.app import app, register_commands

    configure_cli_logging(os.environ.get("LOGLEVEL", "WARNING") or "WARNING")
    register_commands()
    if not wrapper_available() and len(sys.argv) == 1:
        from praisonai_code.cli.legacy.prompt_dispatch import run_standalone_help
        run_standalone_help()
        return
    app()


if __name__ == "__main__":
    main()
