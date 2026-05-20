# Skill Capability Gates

This document describes the capability gates enforcement system for PraisonAI Agent Skills, implementing support for Hermes/OpenClaw skill metadata validation.

## Overview

Skill capability gates ensure that required tools, servers, and environment variables are available before allowing skill activation. This prevents confusing behavior where skills try to use unavailable capabilities and fail halfway through execution.

## Features

- **Declarative Requirements**: Skills specify `requires_*` metadata in frontmatter
- **Layered Enforcement**: From telemetry-only to hard blocking  
- **Backward Compatible**: Existing skills continue to work unchanged
- **CLI Diagnostics**: `praisonai doctor skills` shows missing dependencies
- **Feature Flag Control**: Environment variable configures enforcement level

## Skill Frontmatter

Skills can specify capability requirements in their SKILL.md frontmatter:

```yaml
---
name: web-research
description: Research topics using web search and save results
requires_tools:
  - web_search
  - file_write
requires_servers:
  - mcp:filesystem  
requires_env:
  - API_KEY
openclaw:
  version: "1.0"
  compatibility: "hermes"
---
```

### Supported Fields

| Field | Type | Description |
|-------|------|-------------|
| `requires_tools` | list/string | Required tool names from registry |
| `requires_servers` | list/string | Required MCP servers or endpoints |
| `requires_env` | list/string | Required environment variables |
| `openclaw` | object | OpenClaw-specific hints (passthrough) |

### Backward Compatibility

- Existing `allowed-tools` is automatically converted to `requires_tools`
- Skills without requirements are always considered available
- All enforcement is opt-in via environment variables

## Enforcement Levels

Set the enforcement level with the `SKILL_CAPABILITY_ENFORCEMENT` environment variable:

| Level | Behavior |
|-------|----------|
| `disabled` | No enforcement (existing behavior) |
| `telemetry` | Log missing dependencies only |
| `warn` | Show warnings but allow activation (default) |
| `strict` | Block skill activation until dependencies satisfied |

### Examples

```bash
# Default: warnings only
export SKILL_CAPABILITY_ENFORCEMENT=warn

# Strict enforcement
export SKILL_CAPABILITY_ENFORCEMENT=strict

# Disable enforcement entirely  
export SKILL_CAPABILITY_ENFORCEMENT=disabled
```

## Skill States

Skills are classified into states based on requirement validation:

| State | Description |
|-------|-------------|
| `ACTIVE` | All requirements satisfied |
| `DEGRADED` | Some requirements missing (warnings) |
| `UNAVAILABLE` | Critical requirements missing (strict mode only) |
| `UNKNOWN` | Requirements not yet validated |

## CLI Diagnostics

Check skill capabilities with the doctor command:

```bash
# Check all skills
praisonai doctor skills

# Detailed requirements view
praisonai doctor skills --requirements

# JSON output for scripting
praisonai doctor skills --json
```

## Programmatic Usage

### SkillManager

The `SkillManager` automatically validates capabilities:

```python
from praisonaiagents.skills import SkillManager, EnforcementLevel

# Initialize with enforcement level
manager = SkillManager(EnforcementLevel.STRICT)

# Get skills by state
active_skills = manager.get_available_skills_by_state(SkillState.ACTIVE)
degraded_skills = manager.get_available_skills_by_state(SkillState.DEGRADED)

# Get full diagnostics
diagnostics = manager.get_skills_diagnostics()
for skill_name, result in diagnostics.items():
    print(f"{skill_name}: {result.state.value}")
    if result.missing_tools:
        print(f"  Missing tools: {result.missing_tools}")
```

### Capability Validator

For lower-level validation:

```python
from praisonaiagents.skills import CapabilityValidator, EnforcementLevel

validator = CapabilityValidator(EnforcementLevel.WARN)
result = validator.validate_skill(skill_properties)

if result.state == SkillState.DEGRADED:
    print(f"Warnings: {result.warnings}")
elif result.state == SkillState.UNAVAILABLE:
    print(f"Errors: {result.errors}")
```

## Implementation Details

### Data Models

- `SkillRequirements`: Parsed and normalized requirements
- `SkillState`: Enum of possible skill states
- `ValidationResult`: Complete validation outcome with details

### Pipeline Integration

The capability validator integrates into the existing skill pipeline:

```
discover_skills() → parse_skill_md() → validate_schema() → resolve_requirements()
                                                               ↓
                 SkillState.ACTIVE ← satisfied ← compare against AgentContext
                 SkillState.DEGRADED ← partial
                 SkillState.UNAVAILABLE ← blocked
```

### Tool Registry Integration

The validator automatically queries the global tool registry for available tools:

```python
from praisonaiagents.tools.registry import get_registry

available_tools = set(get_registry().list_tools())
```

## Migration Guide

### For Skill Authors

1. Add `requires_*` fields to skill frontmatter for dependencies
2. Test with `SKILL_CAPABILITY_ENFORCEMENT=strict` to verify
3. Consider providing fallback instructions for missing tools

### For Users

1. Install required tools before enabling strict enforcement
2. Use `praisonai doctor skills` to check current status
3. Set `SKILL_CAPABILITY_ENFORCEMENT=disabled` for legacy behavior

### For Framework Developers

1. Use `SkillManager.get_available_skills()` - it already respects enforcement
2. Check `ValidationResult.state` when implementing custom skill loaders
3. Extend `CapabilityValidator._get_available_servers()` for MCP integration

## Risks and Limitations

### Known Limitations

- **False negatives**: Tool name changes between versions may cause validation failures
- **MCP server detection**: Currently returns empty set (TODO: implement discovery)
- **Dynamic tool loading**: Some tools loaded at runtime may not be detected

### Mitigation Strategies

- Use aliases table in tool registry for rename migrations
- Default to `warn` mode to avoid blocking legitimate use cases
- Provide clear error messages with actionable fix suggestions

## References

- [Agent Skills Standard](https://agentskills.io) - Open standard for skill metadata
- [Hermes/OpenClaw Conventions](https://github.com/hermesagents) - Naming conventions
- [PraisonAI Skills Documentation](https://docs.praison.ai/skills) - Usage guides