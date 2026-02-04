#!/usr/bin/env python3
"""
Generate feature parity tracker for PraisonAI SDKs.

This script generates JSON files tracking feature parity between
Python SDK (source of truth) and other implementations (TypeScript, Rust).

Usage:
    ./scripts/generate_parity_tracker.py           # Generate all trackers
    ./scripts/generate_parity_tracker.py --check   # Check if trackers are up to date
    ./scripts/generate_parity_tracker.py --stdout  # Print to stdout
    ./scripts/generate_parity_tracker.py -t ts     # Generate TypeScript tracker only
"""

import sys
from pathlib import Path

# Add the praisonai package to path
# Script is in src/praisonai/scripts/, so go up 3 levels to repo root
repo_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(repo_root / "src" / "praisonai"))

from praisonai._dev.parity.generator import generate_parity_tracker

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Generate feature parity tracker for PraisonAI SDKs"
    )
    parser.add_argument(
        '--target', '-t',
        choices=['typescript', 'ts', 'rust', 'rs', 'all'],
        default='all',
        help='Target SDK to generate tracker for (default: all)'
    )
    parser.add_argument(
        '--check', action='store_true',
        help='Check if tracker is up to date (exit 1 if not)'
    )
    parser.add_argument(
        '--stdout', action='store_true',
        help='Print to stdout instead of writing files'
    )
    
    args = parser.parse_args()
    
    exit_code = generate_parity_tracker(
        repo_root=repo_root,
        target=args.target,
        check=args.check,
        stdout=args.stdout
    )
    sys.exit(exit_code)
