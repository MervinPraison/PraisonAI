#!/usr/bin/env python3
"""
Auto-generate CLI reference documentation from --help output.

Usage:
    python scripts/generate_cli_docs.py > docs/cli/reference.mdx
    python scripts/generate_cli_docs.py --output docs/cli/reference.mdx

This script runs `praisonai <cmd> --help` for key commands and generates
deterministic markdown documentation.
"""

import subprocess
import sys
import argparse
from datetime import datetime
from pathlib import Path


# Commands to document
COMMANDS = [
    # Top-level
    ("praisonai", "--help"),
    # Knowledge
    ("praisonai knowledge", "--help"),
    ("praisonai knowledge index", "--help"),
    ("praisonai knowledge search", "--help"),
    ("praisonai knowledge add", "--help"),
    ("praisonai knowledge list", "--help"),
    # RAG
    ("praisonai rag", "--help"),
    ("praisonai rag index", "--help"),
    ("praisonai rag query", "--help"),
    ("praisonai rag chat", "--help"),
    ("praisonai rag eval", "--help"),
    ("praisonai rag serve", "--help"),
    # Run
    ("praisonai run", "--help"),
    # Chat
    ("praisonai chat", "--help"),
]


def run_help(cmd: str, flag: str = "--help") -> str:
    """Run a command with --help and capture output."""
    full_cmd = f"{cmd} {flag}"
    try:
        result = subprocess.run(
            full_cmd.split(),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout or result.stderr or "(no output)"
    except subprocess.TimeoutExpired:
        return "(timeout)"
    except FileNotFoundError:
        return "(command not found)"
    except Exception as e:
        return f"(error: {e})"


def generate_markdown() -> str:
    """Generate markdown documentation."""
    lines = [
        "---",
        "title: CLI Reference",
        "description: Auto-generated CLI command reference",
        "---",
        "",
        "# PraisonAI CLI Reference",
        "",
        "This page is auto-generated from `--help` output.",
        "",
        f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        "",
    ]
    
    for cmd, flag in COMMANDS:
        # Section header
        cmd_name = cmd.replace("praisonai ", "").replace(" ", "-") or "main"
        lines.append(f"## `{cmd}`")
        lines.append("")
        lines.append("```")
        
        # Get help output
        output = run_help(cmd, flag)
        lines.append(output.strip())
        
        lines.append("```")
        lines.append("")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate CLI docs from --help")
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if output matches existing file (for CI)",
    )
    args = parser.parse_args()
    
    content = generate_markdown()
    
    if args.check and args.output:
        if args.output.exists():
            existing = args.output.read_text()
            # Compare ignoring timestamp line
            existing_lines = [l for l in existing.split("\n") if not l.startswith("Generated:")]
            new_lines = [l for l in content.split("\n") if not l.startswith("Generated:")]
            if existing_lines != new_lines:
                print(f"ERROR: {args.output} is out of date. Run: python scripts/generate_cli_docs.py -o {args.output}", file=sys.stderr)
                sys.exit(1)
            print(f"OK: {args.output} is up to date")
            sys.exit(0)
        else:
            print(f"ERROR: {args.output} does not exist", file=sys.stderr)
            sys.exit(1)
    
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content)
        print(f"Written to {args.output}")
    else:
        print(content)


if __name__ == "__main__":
    main()
