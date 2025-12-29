# Recipe Registry Example

This example demonstrates how to use the PraisonAI recipe registry for publishing and pulling recipes.

## Features Demonstrated

- Creating a local registry
- Packing recipes into bundles
- Publishing recipes to the registry
- Listing and searching recipes
- Pulling recipes from the registry

## Quick Start

```bash
# Run the example
python registry_example.py
```

## CLI Commands

```bash
# Publish a recipe
praisonai recipe publish ./my-recipe --json

# Pull a recipe
praisonai recipe pull my-recipe@1.0.0 -o ./recipes

# List recipes in registry
praisonai recipe list --json

# Search recipes
praisonai recipe search "hello"
```

## Using a Custom Registry Path

```bash
# Publish to custom registry
praisonai recipe publish ./my-recipe --registry /path/to/registry

# Pull from custom registry
praisonai recipe pull my-recipe@1.0.0 --registry /path/to/registry
```

## Default Registry Location

By default, the registry is stored at `~/.praison/registry`.
