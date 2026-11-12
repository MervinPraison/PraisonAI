# Terminal-Bench 2.1 Results — PraisonAI

Pass-rates from the Harbor smoke workflow
(`.github/workflows/terminal-bench-smoke.yml`, manual dispatch). The full 2.1
dataset (89 tasks) can be scored by dropping the `task_names` filter in
`job.yaml`.

| Date | Agent | Model | Tasks | Pass rate | Harbor artifact |
|------|-------|-------|-------|-----------|-----------------|
| 2026-11-09 | `praisonai-code` | `openai/gpt-4o-mini` | smoke (3) | **0/3** | `jobs/2026-11-09__13-06-10` (2 tasks) + `jobs/2026-11-09__13-22-32` (`bn-fit-modify`) |
| 2026-11-09 | `praisonai-code` | `openai/gpt-4o-mini` | `build-pmars` (1) | **0/1** | `jobs/2026-11-09__12-37-08` |

## How scores are produced

```bash
# Harbor 0.22+ CLI (registry id terminal-bench/terminal-bench-2-1)
export PYTHONPATH=.
harbor run -d terminal-bench/terminal-bench-2-1 \
  --agent "examples.terminal_bench.praisonai_code_agent:PraisonAICodeAgent" \
  -m openai/gpt-4o-mini \
  --ae OPENAI_API_KEY=$OPENAI_API_KEY \
  --agent-setup-timeout-multiplier 4 \
  -n 1 \
  -i terminal-bench/build-pmars \
  -i terminal-bench/bn-fit-modify \
  -i terminal-bench/break-filter-js-from-html
```

The job YAML (`job_code_smoke.yaml`) uses the same registry id and task slugs:
`PYTHONPATH=. harbor run -c examples/terminal_bench/job_code_smoke.yaml`.

The workflow uploads the Harbor results directory as a CI artifact and appends
the pass-rate row above.
