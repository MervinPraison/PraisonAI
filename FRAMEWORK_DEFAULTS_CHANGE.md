# Framework Default Change Notice

## Breaking Change: Default Framework Changed from `crewai` to `praisonai`

**Effective**: v1.0.0+

### What Changed

When no explicit `--framework` flag is provided and no `framework` key is specified in your YAML configuration file, PraisonAI now defaults to using the `praisonai` framework instead of `crewai`.

### Migration Required

**Before (v0.x):**
```bash
praisonai agents.yaml  # Used crewai framework by default
```

**After (v1.0.0+):**
```bash
praisonai agents.yaml  # Now uses praisonai framework by default
```

### How to Maintain Previous Behavior

If you need to continue using `crewai` as the default:

1. **Option 1**: Specify framework in YAML file
```yaml
framework: crewai
input: Your task description
roles:
  # ... your agents
```

2. **Option 2**: Use CLI flag
```bash
praisonai --framework crewai agents.yaml
```

### Rationale

This change improves the onboarding experience for new users by:
- Providing a more consistent default framework aligned with PraisonAI's core capabilities
- Reducing confusion for users following the README quickstart guide
- Enabling better OpenAI integration out of the box

### Technical Details

- **Issue**: #1877 - Fixed YAML framework initialization bug
- **PR**: #1881 - Defer framework adapter creation until YAML is loaded
- **Files Changed**: `src/praisonai/praisonai/agents_generator.py`

This change affects both synchronous (`generate_crew_and_kickoff()`) and asynchronous (`agenerate_crew_and_kickoff()`) execution paths.