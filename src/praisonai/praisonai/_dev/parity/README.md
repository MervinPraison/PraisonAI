# Python ↔ TypeScript parity tooling

Two layers, both with Python (`src/praisonai-agents/praisonaiagents`) as the source of truth.

| Layer | Question it answers | Generated files | Config |
|---|---|---|---|
| **Names** (`generator.py`) | Is a Python export name present in the TS barrel? | `src/praisonai-ts/PARITY.md`, `FEATURE_PARITY_TRACKER.json` (+ Rust pair) | `python_extractor.py` / `typescript_extractor.py` mapping tables |
| **Signatures** (`signatures/`) | Do the parameters of a curated surface match, after naming rules? | `src/praisonai-ts/SIGNATURE_PARITY.md`, `signature-parity.json` | `signatures/surface.yaml`, `rules.yaml`, `waivers.yaml` |

A name row marked `⚠️ stub exported` means the only TS provider is `src/praisonai-ts/src/parity/index.ts`,
the shim written to satisfy name matching. Treat it as missing.

## Commands

```bash
# Names layer
python3 src/praisonai/scripts/generate_parity_tracker.py          # regenerate
python3 src/praisonai/scripts/generate_parity_tracker.py --check  # exit 1 on drift

# Signatures layer (needs node + the `typescript` package; point at any node_modules that has it)
export PARITY_TS_NODE_MODULES=src/praisonai-ts/node_modules
export PYTHONPATH=src/praisonai
python3 -m praisonai._dev.parity.signatures --write               # regenerate report
python3 -m praisonai._dev.parity.signatures --check               # exit 1 on drift or un-waived gap, 2 on tooling failure
python3 -m praisonai._dev.parity.signatures --diff Agent.__init__ # one surface, side by side
python3 -m praisonai._dev.parity.signatures --baseline            # add waivers for every current un-waived gap
python3 -m praisonai._dev.parity.signatures --prune               # delete waivers whose gap has been closed
```

## Keeping the SDKs in sync

1. Add or change a parameter on the Python side.
2. Run `--diff <surface>`. The row shows the canonical TS name the convention expects
   (snake_case → camelCase unless `rules.yaml` names an alias or a flattening) and the default to carry over.
3. Port it in `src/praisonai-ts`, or add a waiver with a `reason` and `owner` to `waivers.yaml`.
   A method that takes an options object (`chat(prompt, options?: AgentChatOptions)`) counts the
   interface's members as parameters, so Python keyword arguments map onto it one to one.
4. Run `--write` and commit the regenerated report with the change.

CI (`.github/workflows/parity-gate.yml`) runs both `--check` modes on pull requests and fails on:
un-waived drift, a waiver that has expired, a waiver whose gap no longer exists, or a run that compared nothing.
`update-parity-tracker.yml` still regenerates the names layer on push to main.

## Adding a surface

Append an entry to `signatures/surface.yaml` with the Python `file`/`class`/`function` and the TS
`file`/`kind` (`interface` or `method`)/`name`, run `--baseline` to waive its current gaps, then `--write`.
