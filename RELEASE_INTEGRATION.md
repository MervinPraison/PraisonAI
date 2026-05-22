# Cross-Repo Release Integration Guide

This document describes the release order and version compatibility for the integrated PraisonAI ecosystem.

## Release Order

When releasing integrated features, follow this exact order to maintain compatibility:

1. **praisonaiagents** (Core SDK)
2. **praisonai** (Wrapper)
3. **PraisonAIUI** (UI Framework)

## Current Integration Versions

| Component | Version | Integration Status |
|-----------|---------|-------------------|
| praisonaiagents | 1.6.46+ | Pattern B compatible |
| praisonai | 4.6.46+ | Pattern B compatible |
| PraisonAIUI | 0.3.121+ | Pattern B integrated |

## Release Checklist

### Before Release

- [ ] Verify version dependencies in pyproject.toml files
- [ ] Run integration tests across all repos
- [ ] Test `praisonai claw` command functionality
- [ ] Verify cross-repo CI passes

### Release Process

1. **praisonaiagents Release**
   ```bash
   cd src/praisonai-agents
   # Update version and release
   ```

2. **praisonai Release**
   ```bash
   cd src/praisonai
   # Update praisonaiagents dependency
   # Update version and release
   ```

3. **PraisonAIUI Release**
   ```bash
   # External repo - coordinate with PraisonAIUI team
   # Ensure backend compatibility
   ```

### Version Dependencies

The wrapper (praisonai) must specify compatible versions:

```toml
# src/praisonai/pyproject.toml
dependencies = [
    "praisonaiagents>=1.6.46",
]

[project.optional-dependencies]
ui = [
    "aiui>=0.3.121,<0.4",
]
```

## Integration Test Matrix

| Test Type | Location | Purpose |
|-----------|----------|---------|
| Backend injection | `tests/integration/test_aiui_backends_injection.py` | Verify bridges work |
| Host isolation | `tests/integration/test_aiui_host_isolation.py` | Test session separation |
| SSE events | `tests/integration/test_aiui_host_sse.py` | Test real-time communication |
| Gateway parity | `tests/integration/test_aiui_gateway_parity.py` | Pattern B/C compatibility |
| Agentic flow | `tests/integration/test_aiui_host_agentic.py` | End-to-end agent execution |

## Troubleshooting

### Common Issues

1. **Version Mismatch**
   - Check pyproject.toml dependencies
   - Verify pip resolves compatible versions
   - Use `pip install praisonai[ui] --dry-run` to test

2. **Backend Injection Failures**
   - Check bridge import paths
   - Verify PraisonAIUI version >= 0.3.121
   - Review logs for missing modules

3. **Integration Test Failures**
   - Ensure OPENAI_API_KEY is set for agentic tests
   - Check that both repos are checked out at compatible versions
   - Verify no conflicting environment variables

## Contact

For integration issues, coordinate between:
- PraisonAI core team
- PraisonAIUI team
- Integration test maintainers