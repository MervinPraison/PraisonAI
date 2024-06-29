#!/bin/sh
set -e  # Exit if any command fails

# Install necessary packages
pip install pdoc3 mkdocs mkdocs-material duckduckgo_search

# Generate HTML documentation with pdoc
pdoc --html --skip-errors -o docs/api praisonai --force

# Build the MkDocs site
mkdocs build
