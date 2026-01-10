#!/usr/bin/env python3
"""
Generate api.md for PraisonAI.

This script generates a comprehensive API reference document
covering all public exports from praisonaiagents, praisonai, CLI, and TypeScript.

Usage:
    ./scripts/generate_api_md.py           # Generate api.md
    ./scripts/generate_api_md.py --check   # Check if api.md is up to date
    ./scripts/generate_api_md.py --stdout  # Print to stdout
"""

import sys
from pathlib import Path

# Add the praisonai package to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root / "src" / "praisonai"))

from praisonai._dev.api_md import generate_api_md

if __name__ == '__main__':
    # Parse simple args
    check = '--check' in sys.argv
    stdout = '--stdout' in sys.argv
    
    exit_code = generate_api_md(
        repo_root=repo_root,
        check=check,
        stdout=stdout
    )
    sys.exit(exit_code)
