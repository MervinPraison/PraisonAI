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

All three layers ask about a symbol somebody named in `surface.yaml`, and about
one function of it. Two further checks, run by the `signatures` gate, ask the
questions that sit either side of that:

| Check | Question | Where | Run it |
|---|---|---|---|
| **Export identity** (`signatures/export_identity.py`) | Is the TypeScript symbol being validated the one `src/index.ts` exports under the Python name? | stdout of `--check` | `--identity` |
| **Method inventory** (`signatures/method_inventory.py`, `signatures/ts_members.mjs`) | Does the TypeScript class offer the public methods the Python class offers? | stdout of `--check` | `--methods` |

Neither writes into `SIGNATURE_PARITY.md`, and neither runs under `--write`:
`--write` refreshes files these checks do not touch, and main regenerates and
commits those on every push.

### Export identity

`surface.yaml` mapped `Task.__init__` to `agent/types.ts` and the gate reported
60 of 60 parameters matched. `src/index.ts` exports a *different* `Task`, from
`./workflows`. `import { Task } from 'praisonai'` hands the caller
`{ name, execute, condition }`; the checker was validating
`{ description, expectedOutput, agent }`. Five `Task`/`TaskConfig` declarations
exist in the tree, and the gate was green over a symbol no caller could obtain.

The check resolves what the barrel really leads to -- through
`export { X as Y } from`, `export *`, local export lists and re-exported
imports -- and compares the *identity* (declaring file plus declared name) with
what the surface validates. When a divergence is intended, record it on the
surface rather than re-pointing the surface at whatever is quiet:

```yaml
  - key: Task.__init__
    python: {...}
    typescript: {...}
    export_identity:
      reason: why the validated symbol is not the exported one
      owner: praisonai-ts
```

A reason without an owner is a tooling error (exit 2). A signed reason
downgrades the failure to a warning and prints the reason; it never hides it.

### Method inventory

Thirteen of the seventeen surfaces compare `__init__`, so everything else a
class does is outside the signature layer's field of view. `Session` has
`save_state`, `restore_state`, `add_memory`, `search_memory` and `chat` in
Python and none of them in TypeScript; `FunctionTool` has `run` in Python and
neither `run` nor a callable form in TypeScript. The check lists public methods
on both sides, following Python base classes through the package (`Agent` takes
its methods from twelve mixins) and matching `save_state` to `saveState`.

**It compares NAMES ONLY** -- the same measure, and the same caveat, `PARITY.md`
prints. `Agent.execute` counts as present here and still does the wrong thing:
Python `execute(task, context=None)` runs the task it is handed, TypeScript
`execute(previousResult?)` runs the agent's own instructions. Signature parity
is the layer that would see that; behaviour parity is the layer above it.

A method that will not be ported is waived on a surface, with the same two
required fields:

```yaml
    method_waivers:
      save_state:
        reason: browser sessions have no state file
        owner: praisonai-ts
```

## One number to watch

```bash
PYTHONPATH=src/praisonai python3 -m praisonai._dev.parity.behaviour
# behaviour parity: 76 options not yet acted on, across 5 surfaces; 10 partial
```

Names and signature *parameters* are at zero and are gated so they stay there.
Behaviour is the number that still moves, and `BEHAVIOUR_PARITY.md` is the work
queue: one row per option, grouped by surface.

The `signatures` gate is currently RED, and truthfully so: the two checks
described below opened with 3 surfaces validating a symbol the package does not
export under the Python name, and 162 public Python methods with no TypeScript
counterpart across 7 classes. Neither number existed before the checks did, and
neither is a regression -- both were always true and invisible. Triage them; do
not silence them by re-pointing `surface.yaml`.

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
python3 -m praisonai._dev.parity.signatures --identity             # export identity only
python3 -m praisonai._dev.parity.signatures --methods              # method inventory only

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
