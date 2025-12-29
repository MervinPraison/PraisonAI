# PraisonAI Doctor Examples

Examples demonstrating the PraisonAI Doctor health check and diagnostics system.

## CLI Examples

| Command | Description |
|---------|-------------|
| `praisonai doctor` | Run all fast health checks |
| `praisonai doctor --version` | Show doctor version |
| `praisonai doctor --list-checks` | List all available checks |
| `praisonai doctor env` | Check environment configuration |
| `praisonai doctor config` | Validate configuration files |
| `praisonai doctor tools` | Check tool availability |
| `praisonai doctor db` | Check database drivers |
| `praisonai doctor mcp` | Check MCP configuration |
| `praisonai doctor obs` | Check observability providers |
| `praisonai doctor skills` | Check agent skills |
| `praisonai doctor memory` | Check memory storage |
| `praisonai doctor permissions` | Check filesystem permissions |
| `praisonai doctor network` | Check network connectivity |
| `praisonai doctor performance` | Check import times |
| `praisonai doctor ci` | CI mode with JSON output |
| `praisonai doctor selftest` | Test agent functionality |

## Global Flags

| Flag | Description |
|------|-------------|
| `--json` | Output in JSON format |
| `--format text\|json` | Output format |
| `--output PATH` | Write report to file |
| `--deep` | Enable deeper probes |
| `--timeout SEC` | Per-check timeout |
| `--strict` | Treat warnings as failures |
| `--quiet` | Minimal output |
| `--no-color` | Disable colors |
| `--only IDS` | Only run these checks |
| `--skip IDS` | Skip these checks |

## Python Examples

| File | Description |
|------|-------------|
| [basic_doctor.py](basic_doctor.py) | Programmatic health checks |
| [ci_integration.py](ci_integration.py) | CI/CD pipeline integration |

## Quick Start

```bash
# Run basic health checks
praisonai doctor

# Run with JSON output
praisonai doctor --json

# Run specific checks
praisonai doctor --only python_version,openai_api_key

# CI mode
praisonai doctor ci

# Save report to file
praisonai doctor --output report.json
```
