# PraisonAI Open Products

Focused, open-source developer products built directly on PraisonAI. Every product lives inside [`MervinPraison/PraisonAI`](https://github.com/MervinPraison/PraisonAI) with **zero duplicated runtime code** — each directory packages documentation, architecture visuals, starter workflows, examples, and (where useful) a thin meta-package pointing straight to the canonical PraisonAI packages.

| Product | What it does | Install / Entry | Directory |
|---|---|---|---|
| **OpenShip** | Open-source Claude Ship alternative: self-review, PR Steward with 3-try circuit breaker, and declarative `.praisonai/approvals.yml` on any LLM or local Ollama — draft PRs only, never merges | `pip install praisonai-code` (`praisonai ship`, `praisonai steward`) or `pip install praisonai-ship` | [`./openship/`](./openship/) |

## Why Inside the Monorepo?

- **One source of truth:** Core logic, safety guards, and tests stay in `src/praisonai-*` — no fork drift or copy-pasted code.
- **Same 3-way ergonomics:** Every product works from the CLI, Python API, and YAML / CI workflows, including fully offline on Ollama.
- **MIT open source:** Star [`MervinPraison/PraisonAI`](https://github.com/MervinPraison/PraisonAI) to follow new `Open<X>` releases.
