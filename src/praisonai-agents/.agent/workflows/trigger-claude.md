---
description: Trigger Claude to fix an issue using the full architectural prompt
---

Use this workflow when you want to manually trigger Claude on an issue (especially for external users) using the complete, strict set of architectural rules. 

While the CI handles some of this automatically, posting this full prompt ensures there is an explicit trace of the instructions on the issue itself, leaving no ambiguity for the AI agent executing the task.

### 1. View Recent External Issues

```bash
// turbo
gh issue list --state open --limit 10
```

### 2. Post the Full @claude Trigger Prompt

Replace `<ISSUE_NUMBER>` with the target issue and run:

```bash
ISSUE_NUMBER="<ISSUE_NUMBER>"

PROMPT=$(cat << 'EOF'
@claude
You are working on the PraisonAI SDK. Follow AGENTS.md strictly.

STEP 0 — SETUP GIT IDENTITY:
git config user.name "MervinPraison"
git config user.email "454862+MervinPraison@users.noreply.github.com"

STEP 1 — READ GUIDELINES:
Read AGENTS.md to understand the architecture rules.

STEP 2 — ARCHITECTURE VALIDATION & ROUTING (MANDATORY before writing code):
Before implementing anything, answer these questions:
- CORE vs WRAPPER vs TOOLS ROUTING:
  1. Core SDK (praisonaiagents/): Only core protocols, base classes, decorators. No heavy implementations.
  2. Wrapper (praisonai/): CLI, heavy implementations, optional dependencies.
  3. Tools (PraisonAI-Tools): Specific integrations, external tools (e.g. SurrealDB, Slack), and community extensions MUST go to the `MervinPraison/PraisonAI-Tools` repository. If the feature is a tool, clone `https://github.com/MervinPraison/PraisonAI-Tools`, implement it there, and create the PR using `gh pr create -R MervinPraison/PraisonAI-Tools`.
- Does it duplicate existing functionality? Check if Agent already supports this via existing params (reflection, planning, tools, hooks, memory).
- Does it inherit from Agent properly? New agent types MUST inherit Agent, not wrap it with composition.
- Does it add new dependencies? Only optional deps allowed, must be lazy-imported.
- Will agent.py grow larger? If the change adds >50 lines to agent.py, find a way to extract instead.
- Is there a name collision with existing exports in `__init__.py`?
If ANY of these conceptual checks fail (excluding routing), add a comment to the issue explaining why and close it. Do NOT create a PR.

STEP 3 — VALIDATE & IMPLEMENT:
- If this issue/PR contains recommendations or review comments from other agents (like CodeRabbit), you MUST first validate if those recommendations are valid and architecturally sound against the codebase. Explain your findings.
- Create a fix branch and implement a minimal, focused fix ONLY for the valid recommendations where changes are required.
- Follow protocol-driven design: protocols in core SDK, heavy implementations in wrapper
- Keep changes small and backward-compatible

STEP 4 — TEST:
- Run: `cd src/praisonai-agents && PYTHONPATH=. python -m pytest tests/ -x -q --timeout=30`
- Ensure no regressions

STEP 5 — CREATE PR:
- Commit with descriptive message, push, and create PR using `gh pr create`
CRITICAL: You MUST create the PR automatically using `gh pr create`. Do NOT just provide a link.
EOF
)

gh issue comment $ISSUE_NUMBER -b "$PROMPT"
```
