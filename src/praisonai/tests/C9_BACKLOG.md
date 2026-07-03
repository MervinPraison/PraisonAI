# C9 — praisonai-bot package separation backlog

Epic branch: `feat/c9-praisonai-bot`

## Phases

| Phase | Status | Scope |
|-------|--------|-------|
| C9.0 | done | Package shell, gates, bootstrap |
| C9.0b | done | 4-package CI install, standalone smoke, Windows bot help |
| C9.1 | done | `bots/` move + shims + tests |
| C9.2 | done | `gateway/` move + shims + tests |
| C9.3 | done | `daemon/`, `integration/` partial |
| C9.4 | done | CLI commands/features, `_BOT_RESIDENT_COMMANDS` |
| C9.5 | done | pyproject extras, wrapper dep |
| C9.5b | partial | kanban/claw/tools/audio moved; scheduler via `_wrapper_bridge` |
| C9.6 | done | `_bot_bridge`, SDK lazy re-export, doctor/approval |
| C9.6b | partial | serve gateway/recipe retarget done; HTTP serve stays in wrapper |
| C9.7 | done | test_c9_backward_compat, install action, boundary tests |
| C9.7b | done | pypi-release 4th package, `publish_all.py`, wrapper pin |
| C9.8 | done | entry-points `praisonai.channels` |
| C9.9 | partial | ARCHITECTURE/AGENTS updated; Mintlify standalone install TBD |
| C9.10 | done | registry standalone fix, backlog/manifest reconciliation |

## Post-C9 gap fixes (2026-07-03)

- [x] `_registry.py` builtin loaders → `praisonai_bot.bots.*` (standalone without wrapper)
- [x] `entry_point_group` → `praisonai.channels`
- [x] `praisonai_bot.__init__.__version__` synced from `_version.py`
- [x] SDK docstrings → canonical `praisonai-bot` home
- [x] Standalone CI smoke + `test_bot_registry_resolves_without_wrapper`

## Deferred (optional follow-on)

- [ ] Move gateway scheduler subset out of wrapper bridge (`praisonai.scheduler.executor`)
- [ ] Mintlify + examples: first-class `pip install praisonai-bot[gateway,bot]`
- [ ] C9.11 gateway `server.py` thinning (optional)

## Gates

```bash
bash scripts/check_c9_bot_imports.sh
bash scripts/audit_bot_wrapper_imports.sh
pytest src/praisonai/tests/unit/test_c9_backward_compat.py -q
pytest src/praisonai/tests/unit/test_c9_1_boundaries.py -q
```
