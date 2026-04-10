---
description: Audit existing docs against live code, then create a comprehensive GitHub issue in PraisonAIDocs with correct, tested information ready for a writer/agent to implement immediately
---

# Create PraisonAIDocs Issue Workflow

Audit code → Compare with existing docs → Draft correct content → Create issue.

> **When to use this:** A feature is already implemented in PraisonAI but the docs are missing, outdated, or wrong. You need to file a self-contained docs issue in `MervinPraison/PraisonAIDocs` that a writer or agent can act on without asking follow-up questions.
> **When NOT to use this:** Use `@[/create-github-issue]` for new integrations that need external research. Use `@[/local-fix]` if you are writing the docs yourself.

---

## Phase 1 — Identify the Feature & Existing Docs

### 1a. Find the relevant doc file

```bash
ls /Users/praison/PraisonAIDocs/docs/<section>/
cat /Users/praison/PraisonAIDocs/docs/<section>/<feature>.mdx
```

Key doc sections:
- `docs/observability/` — tracing providers (Langfuse, LangSmith, etc.)
- `docs/tools/` — tool integrations
- `docs/features/` — agent features
- `docs/cli/` — CLI commands
- `docs/guides/` — how-to guides

### 1b. Read the existing doc fully

Note every claim that needs verification:
- Install commands
- Import statements
- API method names and signatures
- Environment variable names
- CLI commands

---

## Phase 2 — Audit the Live Code

### 2a. Find the source implementation

```bash
# Search praisonaiagents core SDK
grep -rn "<feature>" /Users/praison/praisonai-package/src/praisonai-agents/praisonaiagents/ 2>&1 | grep -v ".pyc"

# Search praisonai wrapper (CLI, integrations)
grep -rn "<feature>" /Users/praison/praisonai-package/src/praisonai/praisonai/ 2>&1 | grep -v ".pyc"

# Search praisonai-tools
grep -rn "<feature>" /Users/praison/PraisonAI-tools/ 2>&1 | grep -v ".pyc"
```

### 2b. Read all relevant source files end-to-end

Read every file that implements the feature. For each file capture:
- Actual class/function names and signatures
- Required vs optional parameters
- Environment variables read (exact names)
- What gets called internally (trace the call chain)
- Any version-specific behavior

Key files to always check:
| File pattern | What to look for |
|---|---|
| `praisonaiagents/obs/__init__.py` | `_LazyObsModule`, factory methods, `auto()` |
| `praisonai_tools/observability/providers/<name>_provider.py` | `init()`, `is_available()`, `shutdown()`, `flush()` |
| `praisonai/observability/<name>.py` | CLI sink adapter, event handling |
| `praisonai/cli/commands/<name>.py` | All CLI sub-commands and options |
| `praisonai/__init__.py` | Global env var overrides that may interfere |

### 2c. Test the feature live

Run minimal test scripts to verify the actual behavior:

```bash
# Test the import works
python3 -c "from praisonaiagents.obs import obs; provider = obs.<name>(); print(type(provider).__name__, provider._initialized)"

# Test CLI commands
praisonai <feature> --help
praisonai <feature> <subcommand>

# Verify traces/output appear
timeout 30 praisonai <feature> <subcommand> --limit 5
```

### 2d. Build a "What's Wrong" table

For each doc claim that is incorrect, record:

| Current Doc (Wrong) | Correct |
|---|---|
| wrong install command | correct install |
| wrong import | correct import |
| non-existent method | actual method |
| wrong env var name | actual env var |

---

## Phase 3 — Draft the Issue

The issue body must be **self-contained and implementation-ready**. A writer should be able to update the doc by reading only the issue — no follow-up questions.

### Required sections:

```markdown
## Overview
One paragraph: what doc file needs updating, why it's wrong, and the end goal.
State explicitly: "All code in this issue has been tested and verified working."

## What's Wrong With the Current Docs
Table: Current (Wrong) | Correct
Cover: install commands, imports, API methods, env vars, missing sections.

## Correct Architecture (How It Actually Works)
Explain the actual internal call chain so the writer understands context.
Include a text diagram if helpful.

## Required Install
Exact pip commands, nothing more.

## Environment Variables
Table: Variable | Required | Description
Show bash export examples for both cloud and self-hosted.

## Python Usage

### Quickstart (Recommended)
Full working code with correct imports, init, agent run, and flush.

### Auto-Detection
Document obs.auto() or equivalent if applicable.

### Additional Patterns
Any other valid usage patterns (explicit provider, multi-agent, etc.).

## CLI Usage (if applicable)
All sub-commands with flags and examples.
Include an end-to-end CLI session example.

## Configuration File (if applicable)
Document any config files that are auto-created or auto-read.

## What Output Looks Like
Show what traces/output actually look like after a successful run.

## Version Compatibility Notes
Document any breaking changes between SDK versions that affect usage.

## Files to Update
Table: File | Change

## Acceptance Criteria
- [ ] Checkbox list — each item must be specific and verifiable

## References
List all source files read (with absolute paths).
```

---

## Phase 4 — Create the Issue

### 4a. Write body to a temp file

```bash
cat > /tmp/docs_issue_<feature>.md << 'EOF'
<issue body>
EOF
```

### 4b. Create via `gh` CLI

```bash
gh issue create \
  --repo MervinPraison/PraisonAIDocs \
  --title "Docs: <action verb> <feature> page — <one-line summary of what's wrong>" \
  --label "documentation" \
  --body-file /tmp/docs_issue_<feature>.md
```

**Title format:** `Docs: Rewrite/Update/Add <Feature> page — <what's wrong or missing>`

Examples:
- `Docs: Rewrite Langfuse integration page with correct Langfuse v4 API and CLI commands`
- `Docs: Add obs.auto() documentation to observability overview`
- `Docs: Fix LangSmith install command and update import paths`

### 4c. Verify

```bash
gh issue view <number> --repo MervinPraison/PraisonAIDocs | head -30
```

Confirm the URL: `https://github.com/MervinPraison/PraisonAIDocs/issues/<number>`

---

## Checklist — Before Creating the Issue

- [ ] Existing doc file read completely
- [ ] All source files implementing the feature read end-to-end (not skimmed)
- [ ] Feature tested live — not just code-read
- [ ] "What's Wrong" table is complete and specific
- [ ] All code examples in the issue are copy-pastable and tested
- [ ] All env var names are verified against source (not guessed)
- [ ] All CLI commands verified with `--help` and live run
- [ ] Acceptance criteria are specific and verifiable (not vague)
- [ ] References list includes all source file paths read
- [ ] Issue is self-contained — writer needs no follow-up

---

## Quick Reference — Common Mistakes

| Mistake | Fix |
|---|---|
| Documenting what the code *should* do, not what it *does* | Run it. Test it. Document the actual behavior. |
| Copying import paths from docs being replaced | Always verify imports against source files |
| Missing the "What's Wrong" table | This is the most important section — be explicit |
| Vague acceptance criteria like "docs are updated" | Write specific, testable criteria: "install command is `pip install langfuse`" |
| Not checking for interfering globals (e.g. `OTEL_SDK_DISABLED`) | Always grep `__init__.py` files for env var overrides |
| Forgetting `provider.flush()` in examples | Async buffers need explicit flush before process exit |
| Not testing with a real API key | Code-reading alone misses runtime errors |
| Using `timeout` too short for first-run (downloads, auth) | Use `timeout 120` for agent runs, `timeout 30` for CLI |
