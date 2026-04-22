#!/usr/bin/env python3
"""Run basic CLI backend test with proper import setup."""

import sys
import os

# Set up paths
current_dir = os.path.dirname(os.path.abspath(__file__))
agents_path = os.path.join(current_dir, 'src', 'praisonai-agents')
praisonai_path = os.path.join(current_dir, 'src', 'praisonai')

sys.path.insert(0, agents_path)
sys.path.insert(0, praisonai_path)

# Set environment variables
os.environ['PYTHONPATH'] = f"{agents_path}:{praisonai_path}"

# Now run our test
from test_cli_backend_basic import main

if __name__ == "__main__":
    exit(main())