# C14 product decision

**Date:** 2026-07-31  
**Decision:** C14 = `praisonai-deploy` (DevOps deployment product)

## Rationale

- Named standalone goal: `pip install praisonai-deploy` → deploy agents to API, Docker, or AWS/Azure/GCP without the full umbrella
- Follows C10–C13 extraction playbook (shims, import gates, nine-package publish order)
- Deployment logic is self-contained; scheduler integration stays accessible via wrapper shims

## Alternatives considered

| Candidate | Score | Outcome |
|-----------|-------|---------|
| Stay wrapper only | 2 | Rejected — user chose package division |
| Merge into praisonai-code | 3 | Rejected — deploy is a distinct product surface |

## Out of scope

- Agent runtime / serve stack — stays in wrapper and code tier
- MCP validate/status tools — keep calling `praisonai.deploy` shim paths (unchanged surface)

## Sign-off

Product target confirmed per Post-C13 extraction roadmap plan.
