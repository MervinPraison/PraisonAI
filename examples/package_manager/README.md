# Package Manager Example

This example demonstrates how to use the PraisonAI package manager for installing and managing Python packages with security defaults.

## Features Demonstrated

- Installing packages with version constraints
- Listing installed packages
- Searching for packages on PyPI
- Managing package index configuration
- Security features (dependency confusion prevention)

## Quick Start

```bash
# Run the example
python package_manager_example.py
```

## CLI Commands

### Install Packages

```bash
# Install a package
praisonai install requests

# Install with version constraint
praisonai install "requests>=2.28"

# Install multiple packages
praisonai install requests httpx aiohttp

# Upgrade existing package
praisonai install requests --upgrade

# JSON output
praisonai install requests --json
```

### Uninstall Packages

```bash
# Uninstall a package
praisonai uninstall requests

# Uninstall without confirmation
praisonai uninstall requests --yes
```

### List Packages

```bash
# List all installed packages
praisonai package list

# JSON output
praisonai package list --json
```

### Search Packages

```bash
# Search PyPI
praisonai package search langchain

# JSON output
praisonai package search langchain --json
```

### Index Configuration

```bash
# Show current index settings
praisonai package index show --json

# Set custom index
praisonai package index set https://pypi.mycompany.com/simple

# Reset to PyPI default
praisonai package index set https://pypi.org/simple
```

## Security Features

By default, only the primary index (PyPI) is used. Extra indexes are blocked to prevent dependency confusion attacks.

```bash
# This will FAIL (extra index not allowed by default)
praisonai install mypackage --extra-index-url https://other.index.com/simple

# Explicitly allow extra index (shows security warning)
praisonai install mypackage \
  --extra-index-url https://other.index.com/simple \
  --allow-extra-index
```

## Environment Variables

- `PRAISONAI_PACKAGE_INDEX_URL` - Override primary index URL
- `PIP_INDEX_URL` - Fallback to pip's index URL
