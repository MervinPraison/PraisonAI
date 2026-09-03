# Python ↔ TypeScript parity tooling

Three layers, each answering a different question, with Python
(`src/praisonai-agents/praisonaiagents`) as the source of truth. They exist as three
because each was added after the previous one was found to pass something it should
have caught.

| Layer | Question | Generated files | Gate |
|---|---|---|---|
| **Names** (`generator.py`) | Is the Python export name present in TypeScript? | `PARITY.md`, `FEATURE_PARITY_TRACKER.json` (+ Rust) | `names` |
| **Signatures** (`signatures/`) | Does every parameter exist, with a matching default? | `SIGNATURE_PARITY.md`, `signature-parity.json` | `signatures` |
| **Behaviour** (`behaviour.py`) | Is the option actually acted on? | `BEHAVIOUR_PARITY.md`, `behaviour-parity.json` | `behaviour` |

**Read them in that order and the trap is obvious.** A name can exist while the
parameter is missing. A parameter can exist while the option is ignored. Only the
third layer sees the last case, and it was added after 76 ignored options had
accumulated without any number moving.

## One number to watch

```bash
PYTHONPATH=src/praisonai python3 -m praisonai._dev.parity.behaviour
# behaviour parity: 76 options not yet acted on, across 5 surfaces; 10 partial
```

Names and signatures are at zero and are gated so they stay there. Behaviour is the
number that still moves, and `BEHAVIOUR_PARITY.md` is the work queue: one row per
option, grouped by surface.

## Commands

```bash
# Names
python3 src/praisonai/scripts/generate_parity_tracker.py           # regenerate
python3 src/praisonai/scripts/generate_parity_tracker.py --check   # exit 1 on drift

# Signatures (needs node plus the `typescript` package)
export PARITY_TS_NODE_MODULES=src/praisonai-ts/node_modules
export PYTHONPATH=src/praisonai
python3 -m praisonai._dev.parity.signatures --write
python3 -m praisonai._dev.parity.signatures --check
python3 -m praisonai._dev.parity.signatures --diff Agent.__init__  # one surface, side by side
python3 -m praisonai._dev.parity.signatures --prune                # drop waivers whose gap is closed

# Behaviour
python3 -m praisonai._dev.parity.behaviour                         # the count, and the queue
python3 -m praisonai._dev.parity.behaviour --write
python3 -m praisonai._dev.parity.behaviour --check                 # ratchet: the total may fall, never rise
```

## Closing one option

The unit of work is a single row of `BEHAVIOUR_PARITY.md`, and the layers are designed
so two people can take two rows without colliding.

1. Pick a row. Its surface names the file that owns it: `Agent.__init__` and
   `Agent.chat` live in `agent/simple.ts`, `AgentTeam.__init__` in `agent/team.ts`,
   `Task.__init__` in `agent/types.ts`, `Handoff` in `agent/handoff.ts`.
2. Implement the behaviour, preferably in its own module under `agent/features/`, so the
   large files gain a call rather than a block and two people editing two options do not
   meet in the same hunk.
3. Delete the option from `UNHONOURED_OPTIONS` in `src/praisonai-ts/src/utils/parity-notice.ts`.
   That is the only list; the surfaces iterate it, so nothing else needs touching.
4. Add a test proving the option changes what the code does, with a control showing the
   behaviour is absent when the option is not passed.
5. `python3 -m praisonai._dev.parity.behaviour --write` and commit the report with the change.

## Waivers

A signature difference that is deliberate goes in `signatures/waivers.yaml` with a
`reason` and an `owner`. Treat every waiver as a claim, not a decision: of the 21 that
were written in one sitting, four were hiding real gaps and four more described Python
behaviour that did not exist. `--prune` deletes waivers whose gap has closed.

## Notes that cost time to learn

- `--check` on the signature report ignores source line numbers. Comparing them byte for
  byte reddened the branch whenever an unrelated commit shifted a line, which is the
  noise this tooling exists to remove.
- `npm install` in `src/praisonai-ts` needs `--legacy-peer-deps`; the tree does not
  otherwise resolve.
- The signature extractor needs only the `typescript` package, not praisonai-ts's full
  dependency tree.
