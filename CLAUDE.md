# CLAUDE.md — Instructions for Claude Code

## Workflow for Issues

When triggered on an issue (via label or @claude), follow this EXACT workflow:

1. **Read AGENTS.md** first for repo guidelines
2. **Analyze** the issue — classify, find root cause in the codebase
3. **Create a fix branch**: `git checkout -b claude/issue-{NUMBER}-fix`
4. **Implement** a minimal, focused fix
5. **Test** — run `pytest tests/` to verify
6. **Commit and push** your changes
7. **Create a PR automatically** using:
   ```
   gh pr create --title "fix: {description}" --body "Fixes #{ISSUE_NUMBER}" --head claude/issue-{NUMBER}-fix
   ```

> **CRITICAL**: You MUST create the PR using `gh pr create`. Do NOT just provide a link for manual PR creation. The PR must be created automatically.

## Workflow for PR Reviews

When triggered on a PR (via @claude or as final reviewer):

1. Read ALL reviewer comments (Qodo, Coderabbit, Copilot)
2. Review per AGENTS.md architecture standards
3. For valid suggestions: implement fixes and push to the PR branch
4. Approve or request changes

## Code Standards

- Follow AGENTS.md strictly
- Protocol-driven core: no heavy implementations in praisonaiagents
- Lazy imports for optional dependencies
- Backward compatible: no public API removed without deprecation
- Every change must have tests
- Async-safe and multi-agent safe
