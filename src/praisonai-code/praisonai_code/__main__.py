"""Console entry for ``python -m praisonai_code`` and ``praisonai-code`` script."""

from __future__ import annotations

import os


def main() -> None:
    """Run the Typer CLI (agentic terminal product)."""
    from praisonai_code._logging import configure_cli_logging
    from praisonai_code.cli.app import app, register_commands

    configure_cli_logging(os.environ.get("LOGLEVEL", "WARNING") or "WARNING")
    register_commands()
    app()


if __name__ == "__main__":
    main()
