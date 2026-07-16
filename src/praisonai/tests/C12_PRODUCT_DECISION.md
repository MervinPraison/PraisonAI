# C12 product decision

**Date:** 2026-07-15  
**Decision:** C12 = `praisonai-mcp` (MCP server hosting product)

## Rationale

- Named standalone goal: `pip install praisonai-mcp` → expose PraisonAI to Cursor/Claude Desktop
- Follows C11 browser extraction playbook (`_MCP_RESIDENT_COMMANDS`, shims, import gates)
- Capability/recipe adapters stay wrapper-backed via lazy `_wrapper_bridge` (three-layer MCP model)

## Alternatives considered

| Candidate | Score | Outcome |
|-----------|-------|---------|
| praisonai-sandbox | 4 | C13 candidate |
| praisonai-deploy | 4 | C13 candidate |
| Stay wrapper only | 2 | Rejected — user chose package division |

## Sign-off

Product target confirmed per Post-C11 extraction roadmap plan.
