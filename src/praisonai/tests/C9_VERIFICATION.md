# C9 Bot Package Verification

Run after `praisonai-bot` extraction (C9). Date: 2026-07-03.

## Standalone install smoke

```bash
python -m venv /tmp/c9-standalone
/tmp/c9-standalone/bin/pip install -e src/praisonai-agents -e src/praisonai-bot
```

| Check | Command | Expected |
|-------|---------|----------|
| Import | `python -c "from praisonai_bot.bots import Bot; print(Bot)"` | No ImportError |
| CLI help | `praisonai-bot --help` | Exit 0 |
| Gateway help | `praisonai-bot gateway --help` | Exit 0 |

## Import gates

```bash
bash scripts/check_c9_bot_imports.sh
bash scripts/audit_bot_wrapper_imports.sh
```

## Backward compatibility (wrapper install)

```bash
cd src/praisonai
PYTHONPATH="../praisonai-agents:../praisonai-code:../praisonai-bot" \
  pytest tests/unit/test_c9_backward_compat.py tests/unit/test_c9_1_boundaries.py -q
```

## Full bot test shard

```bash
cd src/praisonai-bot
PYTHONPATH="../praisonai-agents:../praisonai-code" pytest tests/unit/bots tests/unit/gateway -q
```

## PyPI publish order

1. `praisonaiagents`
2. `praisonai-code`
3. `praisonai-bot`
4. `praisonai` (wrapper pins code + bot)
