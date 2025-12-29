# Recipe Registry Example

This example demonstrates how to use the PraisonAI recipe registry for publishing and pulling recipes via both local filesystem and HTTP server.

## Features Demonstrated

- Creating a local registry
- Starting an HTTP registry server
- Publishing recipes with token authentication
- Listing and searching recipes
- Pulling recipes from HTTP registry

## Quick Start

```bash
# Run the HTTP registry example
python http_registry_example.py
```

## HTTP Registry Server

```bash
# Start HTTP registry server
praisonai registry serve --port 7777

# Start with authentication
praisonai registry serve --port 7777 --token mysecret

# Check server status
praisonai registry status --registry http://localhost:7777
```

## CLI Commands with HTTP Registry

```bash
# Publish to HTTP registry
praisonai recipe publish ./my-recipe --registry http://localhost:7777 --json

# Publish with token
praisonai recipe publish ./my-recipe --registry http://localhost:7777 --token mysecret

# Pull from HTTP registry
praisonai recipe pull my-recipe@1.0.0 --registry http://localhost:7777 -o ./recipes

# List recipes from HTTP registry
praisonai recipe list --registry http://localhost:7777 --json

# Search HTTP registry
praisonai recipe search "hello" --registry http://localhost:7777
```

## Local Registry Commands

```bash
# Publish to local registry (default)
praisonai recipe publish ./my-recipe --json

# Pull from local registry
praisonai recipe pull my-recipe@1.0.0 -o ./recipes

# Use custom local path
praisonai recipe publish ./my-recipe --registry /path/to/registry
```

## Environment Variables

- `PRAISONAI_REGISTRY_TOKEN` - Default token for HTTP registry authentication

## Default Registry Location

By default, the local registry is stored at `~/.praison/registry`.
