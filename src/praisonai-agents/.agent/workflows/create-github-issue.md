---
description: Research a topic in-depth, analyze both external and local codebases, and create a comprehensive GitHub issue — ready for another agent/developer to act on immediately
---

# Create GitHub Issue Workflow

Research → Clone & Analyze → PraisonAI Analysis → Draft → Create Issue.

> **When to use this:** You need to create a detailed, implementation-ready GitHub issue for a new integration, feature, or benchmark. The issue must contain enough context that another agent or developer can implement it without asking further questions.
> **When NOT to use this:** Use `@[/local-fix]` if you are implementing the change yourself, not just filing an issue.

---

## Phase 1 — Online Research

### 1a. Read official sources

Research the topic from all primary sources: official site, GitHub repo, documentation, blog posts.

```bash
# Example searches (adapt to your topic)
# - Official site / announcement pages
# - GitHub README and docs
# - Third-party write-ups (e.g. Snorkel AI, Epoch AI)
# - Framework documentation (core concepts, agents, running)
```

URLs to read for each source (use `read_url_content` tool):
- Official announcement / news page
- GitHub repository README (multiple chunks if large)
- Framework/integration documentation pages
- Any relevant blog posts or analysis

**Capture for the issue:**
- What is it? Purpose and design goals
- Key terminology and concepts (with definitions)
- Architecture overview
- Current leaderboard / ecosystem state
- References list (all URLs)

### 1b. Read paginated content

For large pages, read additional chunks:

```
view_content_chunk(document_id=<url>, position=2)
view_content_chunk(document_id=<url>, position=3)
view_content_chunk(document_id=<url>, position=4)
```

Continue until all relevant sections are read (core concepts, agent types, running instructions, integration API).

---

## Phase 2 — Clone & Analyze External Codebase

### 2a. Clone the repository

```bash
git clone <repo-url> ~/<repo-name> --depth=1
```

### 2b. Explore structure

```bash
ls -la ~/<repo-name>/
ls -la ~/<repo-name>/src/
```

Key files to read (adapt paths to repo):
- `AGENTS.md` / `CLAUDE.md` / `README.md` — architecture overview
- Base class files (e.g. `base.py` for agents, environments)
- Factory / registry files (how things are registered)
- Model/config files (data structures agents must populate)
- Enum files (valid names, types)
- Example agent implementations (minimal + full-featured)
- `pyproject.toml` — Python version, dependencies

**Capture for the issue:**
- Repository structure diagram
- Key file paths with line counts
- Base class interface (all abstract methods with signatures)
- How to register a new agent (enum + factory pattern)
- Data models the agent must populate (`AgentContext`, etc.)
- Example agent implementations (minimal and production)
- CLI commands to run the integration
- Environment variables required

### 2c. Read base classes end-to-end

Read every relevant base class completely. For agent integrations:

```
read_file(base.py)              # BaseAgent / BaseInstalledAgent
read_file(factory.py)           # AgentFactory registration
read_file(models/agent/name.py) # AgentName enum
read_file(models/agent/context.py) # AgentContext fields
read_file(examples/agents/minimal_agent.py) # Minimal example
read_file(agents/installed/reference_agent.py) # Full example
```

### 2d. Read a reference implementation

Pick the most complete existing agent implementation (e.g. `codex.py`, `gemini_cli.py`) and read it fully. This reveals:
- Install pattern (system packages → user packages)
- Version detection (`get_version_command` / `parse_version`)
- `@with_prompt_template` decorator usage
- `populate_context_post_run` for token tracking
- ATIF trajectory support (`SUPPORTS_ATIF`)
- `CliFlag` / `EnvVar` declarative config
- `exec_as_root` vs `exec_as_agent` usage

---

## Phase 3 — Analyze PraisonAI Codebase

### 3a. Identify relevant components

```bash
ls /Users/praison/praisonai-package/src/praisonai-agents/praisonaiagents/
ls /Users/praison/praisonai-package/src/praisonai-agents/praisonaiagents/tools/
ls /Users/praison/praisonai-package/src/praisonai-agents/praisonaiagents/agent/
```

Key files to read for agent integration issues:

| File | What to look for |
|------|-----------------|
| `praisonaiagents/tools/shell_tools.py` | `execute_command`, approval decorators |
| `praisonaiagents/agent/agent.py` | `Agent.start()`, `Agent.chat()`, token tracking |
| `praisonaiagents/approval/` | `@require_approval`, auto-approval backend |
| `praisonaiagents/eval/` | Evaluation framework hooks |
| `praisonaiagents/agents/agents.py` | `AgentTeam` multi-agent |
| `pyproject.toml` | Current version, optional dependencies |

### 3b. Map integration points

For each PraisonAI component, document:
- What it does
- How it maps to the external system's interface
- What needs bridging (e.g. wrapping `environment.exec()` as a tool)
- Known gotchas (e.g. `@require_approval` must be bypassed in containers)

---

## Phase 4 — Draft the Issue

The issue body must be self-contained. Another agent must be able to implement the feature by reading only the issue — no follow-up questions.

### Required sections:

```markdown
## Overview
One paragraph: what, why, and the end goal.

## Background: What is <X>?
- Purpose and design goals
- Key statistics (task count, solve rates, etc.)
- Why <X> + PraisonAI is valuable
- Current ecosystem / leaderboard state

## <X> Architecture (Codebase Analysis)
> Repo analyzed locally: `~/<repo-name>` (cloned at `~/<repo-name>`)

### Core Concepts
Table: Concept | Description

### Two (or N) Integration Types
Code examples for each type with full signatures.

### Key File Locations in <X> Codebase
Directory tree with annotations for each important file.

### Data Models
Full class definitions the agent must populate.

### How to Run (CLI)
All relevant CLI commands with flags and examples.

## PraisonAI Architecture (Relevant to This Integration)
Table: Component | Location | Relevance

### PraisonAI Execution Model
How PraisonAI currently handles the relevant operations, and what must be adapted.

## Proposed Implementation Plan
### Approach: <Recommended> (with justification)

### Phase 1: Minimal Proof-of-Concept
Full working code example.

### Phase 2: Production Implementation
Full working code example.

### Phase N: Advanced Features
(ATIF, multi-agent, etc.)

## Files to Create / Modify
### New files (praisonai-package)
Table: File | Purpose

### Modifications to <External Repo> (PR upstream)
Table: File | Change

## Technical Considerations
Subsections for:
- Container/environment dependencies
- API key forwarding
- Safety/approval bypass
- Token tracking
- Parallel execution safety

## Job / Config Example
Working YAML config + CLI invocation.

## Use Cases Unlocked
Table: Use Case | How

## Acceptance Criteria
- [ ] Checkbox list of verifiable outcomes

## Implementation Notes for the Assigned Agent/Developer
### Key <X> Files to Read First
Numbered list with file paths and line counts.

### Key PraisonAI Files to Read
Numbered list with file paths.

### Critical Integration Points
Numbered list of the exact code-level bridges needed.

### Architecture Decision
Why the chosen approach (installed vs external, etc.) with trade-offs.

### Installation & Testing Commands
Copy-pastable commands to install, verify, and run.

### Upstream PR
What to submit upstream and where.

## References
Bullet list of all URLs used.
```

---

## Phase 5 — Create the Issue

### 5a. Create via `gh` CLI

```bash
gh issue create \
  --repo <org>/<repo> \
  --title "Feature: <Descriptive Title>" \
  --label "enhancement" \
  --body "<issue body>"
```

**Title format:** `Feature: <What> with <Integration> (<Framework/Version>)`

Example:
```bash
gh issue create \
  --repo MervinPraison/PraisonAI \
  --title "Feature: Integrate PraisonAI Agents with Terminal-Bench 2.0 (Harbor Framework)" \
  --label "enhancement" \
  --body "..."
```

### 5b. Verify the issue was created

```bash
gh issue view <issue-number> --repo <org>/<repo> | head -20
```

The output URL confirms success: `https://github.com/<org>/<repo>/issues/<number>`

---

## Checklist — Before Creating the Issue

- [ ] All primary documentation URLs read (including paginated chunks)
- [ ] External repo cloned locally and analyzed
- [ ] Base classes read end-to-end (not just skimmed)
- [ ] At least one reference implementation read fully
- [ ] PraisonAI codebase analyzed for integration points
- [ ] Issue body has working code examples (not pseudocode)
- [ ] All file paths are absolute and verified to exist
- [ ] CLI commands are copy-pastable and complete
- [ ] Acceptance criteria are verifiable (not vague)
- [ ] References section includes all URLs used
- [ ] Issue is self-contained — no "see docs for details" without the details

---

## Quick Reference — Common Mistakes

| Mistake | Fix |
|---------|-----|
| Pseudocode in examples | Use real, runnable code with imports |
| Vague file paths like `agents/` | Use absolute paths like `~/harbor/src/harbor/agents/base.py` |
| Missing `--depth=1` on clone | Large repos take forever; always use shallow clone |
| Only reading chunk 0 of a URL | Read chunks 1–4+ for paginated content |
| Skipping the factory/registry file | This is where registration happens; always read it |
| Not reading a reference agent | Pattern is not obvious from base class alone |
| Forgetting API key forwarding section | Always document how secrets are passed to containers |
| Skipping `populate_context_post_run` | Harbor uses this for token tracking and leaderboard data |
| Missing upstream PR instructions | Specify exact files to modify upstream for first-class support |
