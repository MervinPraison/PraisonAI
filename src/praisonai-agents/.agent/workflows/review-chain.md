---
description: PR review chain — how automated reviews flow for every PR
---

## Review Chain (Sequential)

> **KEY PHILOSOPHY: We act as the Manager, GitHub Actions execute the Workflow.**
> As the local agent, our job is to analyze, supervise, and coordinate the cloud bots. If we identify a gap in the review chain or code (e.g., missing tests), provide detailed relevant information and trigger the agents (like `@claude`) again.
```
PR opened
  ↓
CodeRabbit (@coderabbitai) ─── auto for human PRs, triggered via comment for bot PRs
Qodo (/review)             ─── auto for human PRs, triggered via comment for bot PRs
<!-- Gemini (@gemini)           ─── triggered via comment for bot PRs/Issues
  ↓ (~3-5 min)                  ↓ (auto triggers Claude on completion) -->
PraisonAI (@praisonai)     ─── triggered via comment
  ↓ (~3-5 min)                  ↓ (auto triggers Claude on completion)
Copilot (@copilot)         ─── triggered ONLY after CodeRabbit or Qodo post their review
  ↓
Claude (@claude)           ─── triggered ONLY after Copilot OR Gemini OR PraisonAI finishes (final reviewer)
```

## Workflow Files

| File | Trigger | Does what |
|------|---------|-----------|
| `auto-pr-comment.yml` | `issue_comment`, `pull_request_review`, `pull_request:opened` | Triggers Copilot after CodeRabbit/Qodo finish. For bot PRs: triggers CodeRabbit+Qodo+Gemini first. |
| `praisonai-pr-review.yml` | `issue_comment`, `workflow_dispatch` | PraisonAI multi-agent PR review triggered by @praisonai mentions. |
| `chain-claude-after-copilot.yml` | `pull_request_review:submitted`, `issue_comment` | Triggers Claude after Copilot reviews, AND automatically after Gemini Code Assist finishes fixing issues/PRs. |
| `claude.yml` | `issue_comment`, `pull_request_review_comment`, `issues:assigned/labeled` | Claude responds to @claude mentions. |

## Bot PR fix

CodeRabbit and Qodo skip `github-actions[bot]` authored PRs by default. The `bot-pr-trigger-reviews` job in `auto-pr-comment.yml` explicitly triggers them via comments.

## PraisonAI Integration

PraisonAI provides multi-agent PR review capabilities through the native PraisonAI agent framework. When triggered with `@praisonai`, it deploys a team of specialized agents:

- **Security Reviewer**: Analyzes for vulnerabilities, authentication issues, and unsafe code practices
- **Performance Reviewer**: Identifies bottlenecks, inefficient algorithms, and resource usage issues  
- **Maintainability Reviewer**: Evaluates code quality, documentation, and adherence to best practices
- **Lead Reviewer**: Synthesizes feedback and posts comprehensive review comments

The workflow uses the agent configuration at `.github/praisonai-reviewer.yaml` and leverages the `praisonai` CLI for execution.

## Key rules

- **Copilot ignores bot comments.** All `@copilot` mentions MUST use `GH_TOKEN` (not `GITHUB_TOKEN`) so comments post as `MervinPraison`.
- Copilot NEVER triggers before CodeRabbit/Qodo complete.
- Claude NEVER triggers before Copilot completes.
- Duplicate `@copilot` comments are prevented by checking existing comments.
- PraisonAI PRs: NEVER merge automatically — user merges manually.

## Security & Credentials

- **OIDC Configuration (`id-token: write`)**: Any workflow utilizing the `anthropics/claude-code-action@beta` (or similar actions requiring JWTs for AWS Bedrock/GCP Vertex) MUST define `id-token: write` under the job's `permissions` block. Missing this causes deep, opaque failures like "Could not fetch an OIDC token" paired with `Bad credentials` execution limits.
- **Valid `github_token` Payload**: Always pass `secrets.GH_TOKEN` into `github_token` inputs rather than `secrets.PAT_TOKEN`, as the latter has historically proven invalid and caused silent 401 exceptions on curl requests behind the scenes.
