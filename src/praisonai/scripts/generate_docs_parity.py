#!/usr/bin/env python3
"""
Generate documentation parity tracker files.

Usage:
    python generate_docs_parity.py                  # Generate all
    python generate_docs_parity.py -t ts            # TypeScript only
    python generate_docs_parity.py -t rust          # Rust only
    python generate_docs_parity.py --check          # Check mode for CI
"""

import sys
from pathlib import Path

# Add praisonai package to path
pkg_root = Path(__file__).resolve().parent.parent / "praisonai"
if pkg_root.exists():
    sys.path.insert(0, str(pkg_root.parent))

from praisonai._dev.parity.docs_generator import main

if __name__ == '__main__':
    main()
