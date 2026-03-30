# Migration Guide

This guide documents breaking changes and deprecations in PraisonAI, with migration instructions and timelines.

## Version Strategy

PraisonAI follows [Semantic Versioning](https://semver.org/):
- **Major versions** (e.g., 2.0.0): Breaking changes, deprecated features removed
- **Minor versions** (e.g., 1.5.0): New features, deprecations introduced
- **Patch versions** (e.g., 1.5.1): Bug fixes, no API changes

**Deprecation Timeline:**
- Features are deprecated in **minor** releases
- Deprecated features are removed in the **next major** release
- Deprecation warnings include the removal version

## Current Deprecations (v1.0.0)

### Agent Parameters → Consolidated Config Objects

**Status:** Deprecated in v1.0.0, will be removed in v2.0.0

Old standalone parameters have been consolidated into config objects for better organization and type safety.

#### ❌ Old Way (Deprecated)
```python
from praisonaiagents import Agent

agent = Agent(
    name="coder",
    allow_code_execution=True,       # ❌ Deprecated
    code_execution_mode="unsafe",    # ❌ Deprecated  
    auto_save="my_session",          # ❌ Deprecated
    rate_limiter=my_limiter,         # ❌ Deprecated
    allow_delegation=True,           # ❌ Deprecated
    verification_hooks=[my_hook],    # ❌ Deprecated
    llm="gpt-4o-mini"               # ❌ Deprecated
)
```

#### ✅ New Way (Recommended)
```python
from praisonaiagents import Agent, ExecutionConfig, MemoryConfig
from praisonaiagents.agent.autonomy import AutonomyConfig

agent = Agent(
    name="coder",
    model="gpt-4o-mini",  # ✅ Use 'model' instead of 'llm'
    handoffs=[reviewer_agent],  # ✅ Use 'handoffs' instead of 'allow_delegation'
    execution=ExecutionConfig(
        code_execution=True,
        code_mode="unsafe", 
        rate_limiter=my_limiter
    ),
    memory=MemoryConfig(auto_save="my_session"),
    autonomy=AutonomyConfig(verification_hooks=[my_hook])
)
```

**Migration Steps:**
1. Replace `llm=` with `model=`
2. Replace `allow_delegation=True` with `handoffs=[agent_list]`
3. Group execution-related params into `ExecutionConfig`
4. Group memory params into `MemoryConfig`
5. Group autonomy params into `AutonomyConfig`

### Task Parameters

**Status:** Deprecated in v1.0.0, will be removed in v2.0.0

#### Task Callback → on_task_complete
```python
# ❌ Old Way
task = Task(callback=my_function)

# ✅ New Way  
task = Task(on_task_complete=my_function)
```

#### Task Guardrail → guardrails
```python
# ❌ Old Way
task = Task(guardrail=my_guardrail)

# ✅ New Way
task = Task(guardrails=my_guardrail)
```

### Class Renames

**Status:** Deprecated in v1.0.0, will be removed in v2.0.0

#### AutonomySignal → EscalationSignal
```python
# ❌ Old Way
from praisonaiagents.agent.autonomy import AutonomySignal

# ✅ New Way
from praisonaiagents.escalation.types import EscalationSignal
```

### Directory Structure Changes

**Status:** Deprecated in v1.0.0, will be removed in v2.0.0

#### Data Directory Migration
```bash
# Old location (deprecated)
~/.praisonai-data/

# New location (recommended) 
~/.praisonai/

# Migration command
praisonai migrate-data
```

### Process Workflow → Workflow Class

**Status:** Deprecated in v1.0.0, will be removed in v2.0.0

```python
# ❌ Old Way
from praisonaiagents import process
result = process='workflow'

# ✅ New Way
from praisonaiagents import Workflow
workflow = Workflow(steps=[...])
result = workflow.start()
```

### BotOS Platform Changes

**Status:** Deprecated in v1.0.0, will be removed in v2.0.0

#### BotApprovalBackend → Platform-Specific Approvals
```python
# ❌ Old Way
from praisonai.bots._approval import BotApprovalBackend

# ✅ New Way - Use platform-specific approvals
from praisonai.bots.approval import SlackApproval, TelegramApproval, DiscordApproval
```

### LLM Module Changes

**Status:** Deprecated in v1.0.0, will be removed in v2.0.0

#### Embedding Function
```python
# ❌ Old Way
from praisonai.llm import embedding
result = embedding(text)

# ✅ New Way
from praisonai import embed
# or
from praisonai.capabilities import embed
result = embed(text)  # Returns EmbeddingResult with metadata
```

## Previous Versions

### v0.9.x → v1.0.0

No breaking changes. All v0.9.x code continues to work with deprecation warnings.

## Migration Tools

### Automated Migration (Future)
We're working on automated migration tools:

```bash
# Check for deprecated usage (Future)
praisonai check-deprecations

# Auto-migrate code (Future) 
praisonai migrate --from=1.0 --to=2.0
```

### Manual Migration Checklist

Before upgrading to v2.0.0:

- [ ] Update Agent constructor parameters to use config objects
- [ ] Replace `llm=` with `model=`
- [ ] Update `allow_delegation` to `handoffs`
- [ ] Update task parameters (`callback` → `on_task_complete`, `guardrail` → `guardrails`)
- [ ] Replace `AutonomySignal` with `EscalationSignal`
- [ ] Migrate data directory with `praisonai migrate-data`
- [ ] Update workflow process to Workflow class
- [ ] Replace BotApprovalBackend with platform-specific approvals
- [ ] Update embedding imports
- [ ] Run tests to ensure functionality

### Testing Your Migration

After migrating:

```bash
# Run with deprecation warnings as errors to catch any missed items
python -W error::DeprecationWarning your_script.py

# Or use pytest
python -m pytest -W error::DeprecationWarning
```

## Getting Help

- **Documentation:** Check the updated docs for new patterns
- **Examples:** See `/examples` for updated usage patterns
- **Community:** Ask questions in GitHub Discussions
- **Issues:** Report migration problems in GitHub Issues

## Contributing

When adding new deprecations:

1. Use the `@deprecated` decorator from `praisonaiagents.utils.deprecation`
2. Specify `since` and `removal` versions
3. Provide clear `alternative` guidance
4. Update this MIGRATION.md file
5. Add deprecation to the test suite

Example:
```python
from praisonaiagents.utils.deprecation import deprecated

@deprecated(
    since="1.5.0",
    removal="2.0.0", 
    alternative="use new_function() instead",
    details="The new function provides better error handling"
)
def old_function():
    pass
```