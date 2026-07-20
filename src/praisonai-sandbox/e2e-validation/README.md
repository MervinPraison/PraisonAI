# praisonai-sandbox E2E validation

Single-command end-to-end smoke suite for the sandbox backends.

## Quick start

```bash
cd src/praisonai-sandbox
python e2e-validation/run_e2e.py
```

The runner exits `0` when all required checks pass and `1` on any failure.
No API keys are required for the subprocess path. Docker is optional and is
skipped gracefully when the daemon or base image is unavailable.

### What it checks

| Check | Required | Notes |
|-------|----------|-------|
| Subprocess execute | ✅ | No dependencies |
| SandboxManager subprocess | ✅ | Via `praisonaiagents.sandbox` |
| Backward-compat shim | ✅ | `praisonai.sandbox` → `praisonai_sandbox` |
| Docker execute | ⬜ (optional) | Skipped if Docker unavailable |
| CLI backends smoke | ✅ | `praisonai-sandbox backends` |

## Pytest alternative

The same live paths are covered by pytest:

```bash
python -m pytest tests/test_live_sandbox.py -v --tb=short
```

See [`MANUAL-E2E-GUIDE.md`](./MANUAL-E2E-GUIDE.md) for step-by-step validation.
