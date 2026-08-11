# Terminal-Bench 2.1 Results — PraisonAI

Pass-rates from the Harbor smoke workflow
(`.github/workflows/terminal-bench-smoke.yml`, manual dispatch). The full 2.1
dataset (89 tasks) can be scored by dropping the `task_names` filter in
`job.yaml`.

| Date | Agent | Model | Tasks | Pass rate | Harbor artifact |
|------|-------|-------|-------|-----------|-----------------|
| _pending first run_ | `praisonai code` | `openai/gpt-4o-mini` | smoke (3) | — | — |

## How scores are produced

```bash
PYTHONPATH=. harbor run -c examples/terminal_bench/job_code_smoke.yaml
```

The workflow uploads the Harbor results directory as a CI artifact and appends
the pass-rate row above.
