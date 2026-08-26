# praisonai-js hub intake — file reference

## PraisonAI monorepo (`MervinPraison/PraisonAI`)

| File | Role |
|------|------|
| `.github/workflows/claude.yml` | Issue triage labels; STEP 3-ALT to praisonai-js; npm test in external flow |
| `.github/scripts/merge-gate.js` | `tsMirrorPathReasons()` blocks non-sync edits to `src/praisonai-ts/` |
| `.github/workflows/claude-merge-gate.yml` | Assess checklist: TS → praisonai-js |
| `.github/scripts/ci-failure-claude.js` | CI fix guardrails include TS routing |
| `.github/actions/claude-code-action/action.yml` | Shared Claude routing (TS → praisonai-js) |
| `.github/praisonai-issue-triage.yaml` | `@praisonai` triage: TS-external routing |
| `.github/workflows/auto-issue-comment.yml` | Auto-triage comment mentions praisonai-js |
| `.github/ISSUE_TEMPLATE/bug_report.md` | Python / TS / cross-language selector |
| `CONTRIBUTING.md` | Hub intake table |
| `SECURITY.md` | npm canonical source = praisonai-js |
| `src/praisonai-ts/` | **Mirror only** — do not implement features here |
| `.cursor/skills/praisonai-js-hub-intake/` | This skill (agent reference) |

### Commits (Option B rollout)

- `4ab1ed280` — Implement Option B hub intake for praisonai-js TypeScript issues

## praisonai-js (`MervinPraison/praisonai-js`)

| File | Role |
|------|------|
| `.github/workflows/sync-to-praisonai.yml` | Rsync to `src/praisonai-ts/`; optional `upstream_issue` input |
| `.github/pull_request_template.md` | `Fixes MervinPraison/PraisonAI#N` + sync checklist |
| `.github/ISSUE_TEMPLATE/bug_report.md` | TS bug template; link to PraisonAI for cross-stack |
| `.github/ISSUE_TEMPLATE/config.yml` | Contact links → PraisonAI for Python/cross-stack |
| `.github/scripts/gate-config.js` | Scope + `externalRepos` hub-intake config |
| `.github/workflows/claude.yml` | Hub caller (Claude automation) |
| `AGENTS.md` §2.1.1 | Hub intake for agents |
| `README.md` | Reporting issues table |
| `.cursor/skills/praisonai-js-hub-intake/` | This skill (agent reference) |

### Commits

- `0c8cc3f` — Complete Option B reciprocal hub intake
- `bfc5e34` — Add praisonai-js-hub-intake Cursor skill

## github-automation-template

| Item | Role |
|------|------|
| `install.sh --mode hub` | Thin callers on consumer repos |
| `stacks/claude/profiles/sdk/gate-config.js.tmpl` | Base gate config (customise per repo) |
| `AGENTS.md` | Install / rollout guide |

praisonai-js uses hub mode `@v1.1.0`.

## Decision tree for agents

```
Is the issue about npm / TypeScript / praisonai-js / src/praisonai-ts?
├─ YES → Fix in MervinPraison/praisonai-js (STEP 3-ALT)
│         PR: Fixes MervinPraison/PraisonAI#N
│         After merge: Sync to PraisonAI Monorepo
└─ NO  → Is it Python praisonaiagents / praisonai CLI?
          ├─ YES → Fix in this monorepo
          └─ NO  → Tools / Plugins / Docs external repos (see claude.yml STEP 2)
```

## Anti-patterns

| Wrong | Right |
|-------|-------|
| Edit `src/praisonai-ts/` for a new TS feature | Edit praisonai-js, then sync |
| Tell user to re-file on praisonai-js only | Accept on PraisonAI; route fix externally |
| Merge gate approves direct TS mirror PR without sync metadata | Title `sync:` or body references praisonai-js |
| Skip `Fixes MervinPraison/PraisonAI#N` on external PR | Always cross-link hub issues |
