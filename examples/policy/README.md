# Policy Packs Example

This example demonstrates how to use PraisonAI policy packs for managing tool permissions, data policies, and execution modes.

## Features Demonstrated

- Creating and loading policy packs
- Tool permission checking (allow/deny)
- Policy modes (dev/prod)
- Merging policies
- Data and PII policies

## Quick Start

```bash
python policy_example.py
```

## CLI Commands

```bash
# Show default policy
praisonai recipe policy show

# Show policy from file
praisonai recipe policy show my-policy.yaml

# Create policy template
praisonai recipe policy init -o my-policy.yaml

# Validate policy file
praisonai recipe policy validate my-policy.yaml
```

## Policy File Format

```yaml
name: my-org-policy
version: "1.0"

tools:
  allow:
    - web.search
    - db.query
  deny:
    - shell.exec
    - file.write

network:
  allow_domains:
    - api.openai.com
  deny_domains:
    - localhost

pii:
  mode: redact  # allow, deny, redact
  fields:
    - email
    - phone

data:
  retention_days: 30
  export_allowed: true

modes:
  dev:
    allow_interactive_prompts: true
    strict_tool_enforcement: false
  prod:
    allow_interactive_prompts: false
    strict_tool_enforcement: true
    require_auth: true
```

## Using Policy with Recipe Run

```bash
# Run with policy file
praisonai recipe run my-recipe --policy my-policy.yaml --mode prod
```
