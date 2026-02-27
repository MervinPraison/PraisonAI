# AGENTS.md

## Cursor Cloud specific instructions

### Project overview

PraisonAI is a multi-AI agents framework. The monorepo has three main packages under `src/`:

| Package | Path | Language | Purpose |
|---------|------|----------|---------|
| **praisonai-agents** | `src/praisonai-agents/` | Python | Core SDK (agents, tools, memory, workflows) |
| **praisonai** | `src/praisonai/` | Python | CLI wrapper, integrations, UI/API |
| **praisonai-ts** | `src/praisonai-ts/` | TypeScript | TypeScript port of the framework |

### Python environment

- Python 3.12, using `uv` as package manager (installed at `~/.local/bin/uv`).
- Both Python packages are installed in editable mode via `uv pip install --system -e`.
- Ensure `$HOME/.local/bin` is on PATH for `uv`.
- `dist-packages` ownership has been changed to `ubuntu` user to avoid permission errors with `uv pip install --system`.

### Running tests

**praisonai-agents (core SDK):**
```bash
cd src/praisonai-agents
OPENAI_API_KEY="sk-test-key" python3 -m pytest tests/unit/ --timeout=60 -q
```
Note: Some test files fail to collect due to a missing `praisonaiagents.output.models` module (referenced by `task/task.py`). To skip those, add `--ignore=tests/unit/agents --ignore=tests/unit/workflows --ignore=tests/unit/test_task_execution_config.py`.

**praisonai (wrapper/CLI):**
```bash
cd src/praisonai
OPENAI_API_KEY="sk-test-key" PYTHONPATH="/workspace/src/praisonai-agents:$PYTHONPATH" python3 -m pytest tests/unit/ --timeout=60 -q
```
Same `output.models` import errors affect some test files here too.

**TypeScript SDK:**
```bash
cd src/praisonai-ts
OPENAI_API_KEY="sk-test-key" npx jest --no-cache --passWithNoTests
```
The TS build (`tsc`) has pre-existing errors from missing `db/`, `cli/output/`, and `@ai-sdk/provider-utils` modules. Tests still largely pass (446/463).

### Running the application

- **CLI:** `python3 -m praisonai --help` (version 4.5.15)
- **Agent hello world:**
  ```python
  from praisonaiagents import Agent
  agent = Agent(name="assistant", instructions="Be helpful.")
  response = agent.start("Hello!")
  ```
- Requires a valid `OPENAI_API_KEY` environment variable for any LLM calls.

### Known caveats

- No linting tools (ESLint, ruff, flake8) are configured in this repository.
- The Rust SDK (`src/praisonai-rust/`) requires Cargo 1.85+ (edition2024 support); the default system Cargo 1.83 is too old.
- `pnpm install` for the TS SDK should use `--ignore-scripts` to skip the broken `prepare` (build) step during install.
