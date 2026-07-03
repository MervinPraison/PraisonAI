# Agent Instructions

You are working on the PraisonAI project.

## Project Guidelines
- Follow the existing code style and conventions
- Be concise and helpful in responses  
- Test implementation thoroughly
- Ensure backward compatibility with existing APIs
- Follow protocol-driven design: core protocols in `praisonaiagents/`, agentic terminal CLI in `praisonai-code/`, bot/channel and heavy implementations in `praisonai/`
- Preserve old `praisonai.cli.*` import paths via shims when changing moved CLI code (see §2.3 in `src/praisonai-agents/AGENTS.md`)

## Cursor Cloud specific instructions

Scope: the core Python product (three-package monorepo `praisonaiagents` → `praisonai-code` → `praisonai`). The TypeScript (`src/praisonai-ts`) and Rust (`src/praisonai-rust`) SDKs are separate optional products and are not part of this setup.

Environment (the update script installs all three packages editable, plus test tooling):
- Use `python3` — there is no `python` on PATH. No conda is available; packages are system pip user installs.
- The `praisonai` console script lives in `~/.local/bin`; if it is not on PATH, run `python3 -m praisonai …` instead.
- Set `PYTHONPATH=src/praisonai-agents` for CLI/tests (mirrors CI's `.github/workflows/test-core.yml`).

Running/testing:
- Run the CLI: `praisonai version`, `praisonai --help`, `praisonai doctor` (doctor "failures" for unset API keys / bot tokens are expected). CLI `run` takes options *before* the prompt, e.g. `praisonai run --model gpt-4o-mini "Say hello"`.
- Unit tests (from `src/praisonai-agents` or `src/praisonai`): `OPENAI_API_KEY=sk-test OPENAI_MODEL_NAME=gpt-4o-mini PRAISONAI_ALLOW_NETWORK=0 python3 -m pytest tests/unit -m "not network and not slow"`. A fake key is fine for unit tests.
- No Python linter (ruff/flake8/black) is configured; there is no lint command.
- Some unit tests in the current snapshot are pre-existing failures from test/source drift (e.g. `tests/unit/config/test_precedence_ladder.py`, `tests/unit/sandbox/test_security.py`, `tests/unit/test_error_classification.py`) — not environment problems. The full wrapper suite additionally expects heavy extras (`crewai`, `autogen`, etc.) that the minimal setup omits.

Running an agent without a paid key: point `OPENAI_API_BASE` and `OPENAI_BASE_URL` at a local OpenAI-compatible mock. Note the core SDK `Agent` uses the Chat Completions API (`/v1/chat/completions`), while the terminal CLI `praisonai run` uses the OpenAI **Responses API** (`/v1/responses`) — a mock must implement both to satisfy both paths.