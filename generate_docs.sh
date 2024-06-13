#!/bin/sh
set -e  # Exit if any command fails

# Install necessary packages
pip install pdoc3 mkdocs mkdocs-material

# Set openai_api_key so that importing doesn't throw
export OPENAI_API_KEY=""

# Generate HTML documentation with pdoc
pdoc --html --skip-errors --template-dir docs/pdoc_template -o docs/api praisonai --force

# Build the MkDocs site
mkdocs build

# Handle Jupyter deprecation warning
export JUPYTER_PLATFORM_DIRS=1
