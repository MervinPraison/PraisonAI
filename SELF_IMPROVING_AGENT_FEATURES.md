# Self-Improving Agent Features

This document describes the self-improving agent capabilities added to PraisonAI to achieve parity with Hermes Agent's learning loop.

## Overview

PraisonAI now includes a **self-improving agent loop** that enables agents to:
1. Learn from conversations automatically
2. Get periodic nudges to persist knowledge  
3. Create and manage their own skills
4. Build up reusable knowledge across sessions

This is achieved through a combination of existing infrastructure and new protocols.

## Architecture

### Core SDK (praisonaiagents) - Protocol Layer
- **`SkillMutatorProtocol`**: Protocol for agent-managed skill CRUD operations
- **`LearnConfig` extensions**: Added `nudge_interval`, `nudge_min_tool_iters`, `propose_skills` fields
- **Memory mixin**: Added `_maybe_emit_nudge()` method for periodic knowledge persistence prompts
- **LearnManager**: Fixed auto-extraction to include improvements alongside persona/insights/patterns

### Wrapper (praisonai) - Implementation Layer  
- **`skill_manage` tool**: Agent-facing tool for creating, editing, and managing skills
- **`BasicSkillMutator`**: Safe-by-default implementation with propose/approve workflow
- **Integration test**: Demonstrates end-to-end self-improving loop

## Usage

### Basic Self-Improving Agent

```python
from praisonaiagents import Agent
from praisonaiagents.config.feature_configs import LearnConfig
from praisonai.tools.skill_manage import skill_manage

agent = Agent(
    name="learner",
    instructions="You are a helpful assistant that learns and improves over time.",
    learn=LearnConfig(
        mode="agentic",           # Auto-extract learnings
        improvements=True,        # Enable improvement proposals
        nudge_interval=5,         # Nudge every 5 turns
        propose_skills=True,      # Enable skill creation
    ),
    tools=[skill_manage],        # Provide skill management capability
)

# Agent will now:
# 1. Learn from each conversation
# 2. Get nudged every 5 turns to persist knowledge
# 3. Can create skills when discovering useful procedures
```

### Skill Management Workflow

```python
# Agent can create skills (defaults to propose mode)
response = agent.chat(
    "I just showed you how to set up a Python project. "
    "Can you create a skill to remember this procedure?"
)

# Check pending skills
from praisonai.tools.skill_manage import skill_manage
pending = skill_manage("list", "")
print(pending)

# Approve skills manually
result = skill_manage("approve", "python-project-setup") 
print(result)
```

### Nudge Mechanism

When `nudge_interval > 0`, agents receive periodic system prompts:

> [System nudge] Review the recent conversation. If you discovered a non-trivial procedure or pattern, consider using available tools to persist this knowledge for future use. Skip if nothing noteworthy.

This encourages knowledge persistence without being intrusive.

## Implementation Details

### SkillMutatorProtocol

The core protocol defines the interface for skill mutations:

```python
from praisonaiagents.skills import SkillMutatorProtocol

class SkillMutatorProtocol(Protocol):
    def create(self, name: str, content: str, category: Optional[str] = None,
               propose: bool = True) -> str: ...
    def patch(self, name: str, old_string: str, new_string: str, ...) -> str: ...
    def edit(self, name: str, content: str, propose: bool = True) -> str: ...
    def delete(self, name: str, propose: bool = True) -> str: ...
    # ... more methods
```

### Safety Features

1. **Propose by Default**: All mutations go to `~/.praisonai/skills/pending/` first
2. **Human Approval**: Manual approval moves skills to `~/.praisonai/skills/`  
3. **Audit Log**: All actions logged to `.skill_log` with timestamps
4. **Validation**: Skill names must be alphanumeric with hyphens/underscores

### Integration with Existing Systems

- **Reuses existing `LearnManager`** for auto-extraction
- **Extends `LearnConfig`** without breaking changes
- **Compatible with existing skills system** (read-only → read-write)
- **Uses existing approval patterns** from `ApprovalRegistry` concept

## Testing

Run the integration test to verify the self-improving loop:

```bash
cd src/praisonai
python tests/integration/test_self_improving_loop.py
```

This test demonstrates:
- Agent learning from complex conversations
- Nudge mechanism triggering  
- Skill creation and approval workflow
- Protocol compliance verification

## Limitations

This is a **proof-of-concept** implementation that provides the foundation for self-improving agents. Future enhancements could include:

1. **Session Search Tool**: Cross-session FTS5 search capability
2. **Trajectory Export**: JSONL format for fine-tuning data  
3. **Skills Hub**: Marketplace for sharing skills
4. **Advanced Nudging**: Context-aware nudge timing
5. **Automatic Approval**: Trust-based auto-approval for reliable agents

## Files Modified/Created

### Core SDK Changes
- `src/praisonai-agents/praisonaiagents/skills/protocols.py` - Added SkillMutatorProtocol
- `src/praisonai-agents/praisonaiagents/skills/__init__.py` - Export new protocol
- `src/praisonai-agents/praisonaiagents/config/feature_configs.py` - Extended LearnConfig
- `src/praisonai-agents/praisonaiagents/agent/memory_mixin.py` - Added nudge method
- `src/praisonai-agents/praisonaiagents/memory/learn/manager.py` - Fixed improvements extraction

### Wrapper Implementation  
- `src/praisonai/praisonai/tools/skill_manage.py` - Agent tool + BasicSkillMutator
- `src/praisonai/tests/integration/test_self_improving_loop.py` - Integration test
- `SELF_IMPROVING_AGENT_FEATURES.md` - This documentation

## Summary

PraisonAI now provides the **foundation for self-improving agents** with:

✅ **Skill Mutation**: Agents can create/edit/delete their own skills  
✅ **Nudge Mechanism**: Periodic prompts encourage knowledge persistence  
✅ **Safe Workflow**: Propose/approve pattern prevents accidental changes  
✅ **Integration**: Works with existing learning and skills systems  
✅ **Protocol-Driven**: Extensible via SkillMutatorProtocol

This enables the core **self-improving claim**: agents can learn procedures and persist them as skills for reuse across sessions.