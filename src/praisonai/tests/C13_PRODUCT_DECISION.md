# C13 product decision

**Date:** 2026-07-17  
**Decision:** C13 = `praisonai-sandbox` (isolated agent code execution product)

## Rationale

- Named standalone goal: `pip install praisonai-sandbox[docker]` → run untrusted agent code in Docker/E2B/Modal/Sandlock/SSH without the full umbrella
- Follows C11/C12 extraction playbook (shims, import gates, eight-package publish order)
- Protocol/config/manager stay in `praisonaiagents`; heavy backends move to tier-2 package

## Alternatives considered

| Candidate | Score | Outcome |
|-----------|-------|---------|
| praisonai-deploy | 4 | C14 candidate (DevOps-only deploy story) |
| Stay wrapper only | 2 | Rejected — user chose package division |

## Out of scope

- Container-mgmt Typer CLI (`praisonai-code sandbox status/explain/list/recreate`) — stays in code
- CLI `--sandbox` flag executor — stays in code
- serve/recipe/jobs, persist, in-tree frameworks

## Sign-off

Product target confirmed per Post-C12 extraction roadmap plan.
