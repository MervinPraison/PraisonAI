#!/bin/sh
set -e  # Exit if any command fails

# Install necessary packages
pip install pdoc3 mkdocs mkdocs-material 

# Generate HTML documentation with pdoc
pdoc --html --skip-errors --template-dir docs/pdoc_template -o docs/api praisonai --force

# Build the MkDocs site
mkdocs build
