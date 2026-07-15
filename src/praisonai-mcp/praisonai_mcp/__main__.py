"""Console entry: ``praisonai-mcp``."""

from __future__ import annotations

import sys

# Heavy MCP host commands (MCPServerCLI) — not Typer config subcommands.
_HOST_COMMANDS = frozenset({
    "serve",
    "serve-recipe",
    "list-tools",
    "list-resources",
    "list-prompts",
    "list-recipes",
    "validate-recipe",
    "inspect-recipe",
    "config-generate",
    "config-generate-recipe",
    "tasks",
    "doctor",
})


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        args = ["--help"]
    if args[0] in _HOST_COMMANDS:
        from praisonai_mcp.mcp_server.cli import handle_mcp_command

        raise SystemExit(handle_mcp_command(args))
    from praisonai_mcp.cli.app import app

    app(args=args, prog_name="praisonai-mcp")


if __name__ == "__main__":
    main()
