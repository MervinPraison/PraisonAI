# C6 Integration Gate Verification (#2519)

Run on `main` after C0–C5 merge. Date: 2026-07-01.

## Smoke commands

| Command | Result |
|---------|--------|
| `praisonai --help` | PASS |
| `praisonai run/chat/code/daemon/attach/gateway/bot/doctor --help` | PASS |
| `praisonai "Say hello in one word"` (real LLM) | PASS (~3s) |

## Test shards

| Shard | Result |
|-------|--------|
| `pytest tests/unit/cli/` | 1634 passed |
| `pytest tests/unit/test_c5_backward_compat.py` | PASS |
| `pytest tests/unit/test_warm_runtime.py` | 21 passed |
| `pytest tests/unit/doctor/` | PASS (in CLI shard) |
| `pytest tests/unit/test_wrapper_layer_regression.py` | PASS |
| `pytest tests/unit/test_performance_benchmarks.py` | 11 passed |
| `pytest tests/unit/gateway/` | unchanged (bot layer) |

## Real agentic / API key

| Test | Result |
|------|--------|
| `test_real_key_smoke.py` (9 tests, gated) | 9/9 PASS |

Env: `RUN_REAL_KEY_TESTS=1 PRAISONAI_ALLOW_NETWORK=1 PRAISONAI_TEST_PROVIDERS=all`

## Import graph (#2519 grep assertions)

| Assertion | Result |
|-----------|--------|
| No `from praisonai.gateway` in `praisonai_code/cli/commands/run.py` | 0 matches |
| No `from praisonai.gateway` in `praisonai_code/cli/interactive/` | 0 matches |
| `praisonai-code/pyproject.toml` has no `praisonai` wrapper dep | PASS (only `praisonaiagents`) |

## Import performance

| Metric | Result |
|--------|--------|
| `import praisonai` | ~2ms (well under 500ms gate) |

## Legacy unit tests (re-enabled post-C6)

Removed blanket `@pytest.mark.skip("Legacy unit test pending Core Tests gate update")` from 27 files.

| Metric | Result |
|--------|--------|
| Tests in re-enabled files | 431 collected |
| Passed | 376 |
| Failed | 55 (API drift — CLI backend resolver, bot session asyncio, training mocks) |
| Critical #2519 shards | warm_runtime, gateway_gaps, profiler: green |

Follow-up: fix or rewrite remaining 55 tests in a post-C6 maintenance pass.

## Release

| Item | Result |
|------|--------|
| Cherry-pick `81b954571` (code bump regex + standalone wrapper cmd gate) | Applied on `chore/c6-sign-off` |
| Three-package PyPI workflow | Merged (#2543) |

## Sign-off

- [x] Smoke commands pass
- [x] CLI + doctor + warm runtime shards pass
- [x] `import praisonai` < 500ms
- [x] Real agentic LLM E2E passes
- [x] Zero gateway imports on agentic hot path
- [x] Wrapper-required install documented (C7 defers standalone `praisonai-code`)

Closes #2519, Closes #2512.
