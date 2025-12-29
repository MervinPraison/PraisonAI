# Recipe Server Example

This example demonstrates how to configure and run the PraisonAI recipe server with authentication.

## Files

- `serve.yaml` - Server configuration file
- `serve_example.py` - Python client example with authentication

## Quick Start

### 1. Install Dependencies

```bash
pip install praisonai[serve]
```

### 2. Set Environment Variables

```bash
export OPENAI_API_KEY=your-openai-key
export PRAISONAI_API_KEY=your-secret-api-key
```

### 3. Start the Server

```bash
# Using config file
praisonai recipe serve --config serve.yaml

# Or with CLI flags
praisonai recipe serve --port 8765 --auth api-key
```

### 4. Test with the Example

```bash
python serve_example.py
```

## Configuration Options

See `serve.yaml` for all available options:

| Option | Description | Default |
|--------|-------------|---------|
| `host` | Server bind address | 127.0.0.1 |
| `port` | Server port | 8765 |
| `auth` | Auth type (none, api-key, jwt) | none |
| `api_key` | API key for auth | - |
| `preload` | Preload recipes on startup | false |
| `recipes` | List of recipes to serve | all |
| `cors_origins` | CORS allowed origins | - |

## CLI Commands

```bash
# Health check
praisonai endpoints health

# List recipes (with auth)
praisonai endpoints list --api-key your-key

# Invoke recipe
praisonai endpoints invoke my-recipe \
  --input-json '{"query": "Hello"}' \
  --api-key your-key \
  --json
```

## Security Notes

- Always use `--auth api-key` when binding to `0.0.0.0`
- Store API keys in environment variables, not config files
- Use HTTPS in production (via reverse proxy)
