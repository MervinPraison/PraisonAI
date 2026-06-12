# HandoffToolPolicy Security Documentation

## Overview

HandoffToolPolicy enforces tool security boundaries during agent handoffs to prevent privilege escalation in multi-agent deployments.

## Default Security Mode: `intersect`

**Default behavior is now secure by default.** When one agent hands off to another:

- Target agent gets **intersection** of source and target tools only
- No privilege escalation possible
- Empty intersection = no tools (secure boundary)

### Example

```python
from praisonaiagents import Agent, handoff

# Gatekeeper agent has limited tools
gatekeeper = Agent(name="Gatekeeper", tools=[search_tool])

# Automation agent has powerful tools  
automation = Agent(name="Automation", tools=[search_tool, execute_code, file_access])

# Handoff with default intersect mode (SECURE)
secure_handoff = handoff(automation)

# When gatekeeper hands off to automation:
# automation only gets: [search_tool]  <- intersection only!
# automation does NOT get: execute_code, file_access
```

## Legacy Mode: `passthrough` 

Opt-in to legacy behavior where target keeps full toolset:

```python
# Legacy behavior (explicit opt-in)
legacy_handoff = handoff(
    automation, 
    tool_policy_mode="passthrough",
    blocked_tools=["execute_code"]  # Can still block specific tools
)

# When gatekeeper hands off:
# automation gets: [search_tool, file_access]  <- full toolset minus blocked
```

## Security Boundary Implementation

### Critical Fix: `tools=[]` vs `tools=None`

The security boundary is enforced by distinguishing:

- `tools=None` → Inherit agent's configured tools
- `tools=[]` → Explicit deny all tools (security boundary)

**Before Fix:**
```python
# Both fell back to self.tools (SECURITY VULNERABILITY!)
if tools is None or (isinstance(tools, list) and len(tools) == 0):
    tool_param = self.tools  # ❌ Privilege escalation possible
```

**After Fix:**
```python
# Distinguish None vs empty list (SECURE)
if tools is None:
    tool_param = self.tools        # Inherit agent tools
elif isinstance(tools, list) and len(tools) == 0:
    tool_param = []               # ✅ Explicit security boundary
```

## Backward Compatibility

- **✅ Existing code works unchanged**
- **✅ Default is secure** (intersect mode)
- **✅ Legacy behavior available** via `tool_policy_mode="passthrough"`
- **✅ No breaking API changes**

## Configuration Options

### Via `handoff()` function:

```python
# Secure by default
handoff(agent)

# Explicit modes
handoff(agent, tool_policy_mode="intersect")  # Default
handoff(agent, tool_policy_mode="passthrough")  # Legacy

# With blocked tools
handoff(agent, blocked_tools=["dangerous_tool"])
```

### Via `HandoffConfig`:

```python
from praisonaiagents import HandoffConfig, HandoffToolPolicy

config = HandoffConfig(
    tool_policy=HandoffToolPolicy(
        mode="intersect",  # or "passthrough"
        blocked_tools=["execute_code", "shell_access"]
    )
)

handoff_instance = Handoff(agent=target, config=config)
```

## Security Best Practices

1. **Use default intersect mode** unless you specifically need legacy behavior
2. **Always block dangerous tools** like `execute_code`, `shell_access` 
3. **Principle of least privilege** - only grant necessary tools to each agent
4. **Test handoff boundaries** in your security tests

## Migration Guide

No migration required! Default behavior is now secure:

```python
# Before: This could escalate privileges
handoff_to_automation = handoff(powerful_agent)

# After: Same code, but now secure by default
handoff_to_automation = handoff(powerful_agent)  # ✅ Only shared tools
```

To restore legacy behavior (not recommended):

```python
# Explicit legacy mode
handoff_to_automation = handoff(powerful_agent, tool_policy_mode="passthrough")
```

## Implementation Details

The security boundary is enforced in three places:

1. **`Handoff._compute_effective_tools()`** - Computes safe tool intersection
2. **`Agent.chat(tools=effective_tools)`** - Passes computed tools explicitly  
3. **`ChatMixin._format_tools_for_completion()`** - Respects `tools=[]` boundary

This prevents privilege escalation at multiple layers for defense in depth.