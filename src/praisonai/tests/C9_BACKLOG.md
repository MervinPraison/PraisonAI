# C9 — praisonai-bot package separation backlog

Epic branch: `feat/c9-praisonai-bot`

## Phases

| Phase | Status | Scope |
|-------|--------|-------|
| C9.0 | done | Package shell, gates, bootstrap |
| C9.1 | done | `bots/` move + shims + tests |
| C9.2 | done | `gateway/` move + shims + tests |
| C9.3 | done | `daemon/`, `integration/` partial |
| C9.4 | done | CLI commands/features, `_BOT_RESIDENT_COMMANDS` |
| C9.5 | done | pyproject extras, wrapper dep |
| C9.5b | partial | kanban/claw/tools/audio moved; scheduler via bridge |
| C9.6 | done | `_bot_bridge`, SDK lazy re-export, doctor/approval |
| C9.6b | partial | approval via bot bridge; serve split deferred |
| C9.7 | done | test_c9_backward_compat, install action |
| C9.7b | pending | pypi-release 4th package |
| C9.8 | done | entry-points praisonai.channels |
| C9.9 | partial | ARCHITECTURE note in boundaries doc |
| C9.10 | partial | sign-off pending CI green |

## Gates

```bash
bash scripts/check_c9_bot_imports.sh
bash scripts/audit_bot_wrapper_imports.sh
pytest src/praisonai/tests/unit/test_c9_backward_compat.py -q
```
