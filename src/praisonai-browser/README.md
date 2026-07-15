# PraisonAI Browser

Browser automation for [PraisonAI](https://github.com/mervinpraison/PraisonAI) — Chrome extension bridge, CDP/hybrid agents, and Playwright automation as a standalone package or part of the full `praisonai` stack.

## Install

```bash
pip install "praisonai-browser[all]"

# Or via the umbrella product
pip install "praisonai[browser]"
```

## Quickstart

```bash
praisonai-browser start --port 8765
praisonai-browser run "Search for AI news on Google"
praisonai-browser doctor
```

With the full stack: `praisonai browser start`, `praisonai browser run "..."`.

## Stack

```
praisonaiagents  (browser protocols)
   └── praisonai-browser  (this package)
        └── praisonai     (wrapper shims: praisonai.browser.*)
```

Old import paths (`praisonai.browser`, `python -m praisonai.browser.server`) keep working via wrapper shims.

Boundary details: `src/praisonai/tests/PRAISONAI_BROWSER_MANIFEST.md`.
