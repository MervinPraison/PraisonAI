# Delegation and HITL: Current Limitations

This document describes the current behavior of delegated sub-agent runs and the known limitations around human-in-the-loop (HITL) approval pauses.

## Current behavior

`delegate_task` is wired to real sub-agent creation, but delegated children still execute as synchronous, blocking, in-memory runs.

That means:

- A parent tool call can block while the delegated child runs.
- A delegated child is not guaranteed to survive a process restart.
- If a child reaches an approval pause, the parent has no durable way to resume that child in place.
- There is no stable child-run result contract for `pending`, `completed`, and `halted` states.

## Supported workaround

For long-running or potentially blocking sub-agent work, use the background sub-agent path instead of synchronous delegation:

```python
job = spawn_subagent(..., background=True)
result = subagent_result(job['job_id'])
```

This avoids blocking the parent turn, but it is not a full HITL resume flow. Background polling does not yet provide durable approval routing or continuation of a paused child.

## Missing pieces for resumable delegation

The following pieces are required before delegated children can be considered resumable:

1. Durable child session persistence through the session store.
2. A child-run result-state contract, for example `pending`, `completed`, and `halted`.
3. HITL bubble-up from child to parent, so an approval pause creates a durable pending handle.
4. A `drive_child` or equivalent continuation seam to resume the paused child.
5. Ownership and lifecycle rules for cancellation, timeouts, and result collection.

## Recommended next step

Prefer a core-first increment: introduce an internal `v0` child-run pause/resume contract before designing the full gateway UX. The first contract should be explicitly internal and anti-freeze: the resume handle should remain opaque so later metadata such as approval IDs, gateway routing, or cancellation state can be added without changing the parent-facing shape.

A possible `v0` state shape is:

```python
from typing import Literal, TypedDict

class ChildRunStateV0(TypedDict):
    schema_version: Literal['v0']
    child_run_id: str
    parent_run_id: str
    status: Literal['pending', 'completed', 'halted']
    pause_reason: Literal['approval_required'] | None
    resume_token: str | None
```

Semantics:

- `pending`: the child reached a HITL approval pause; the parent should receive a durable handle rather than block indefinitely.
- `completed`: the child reached a terminal success or failure state; the parent can collect the result.
- `halted`: the child was cancelled or failed in a non-resumable way.

Until this work lands, do not assume delegated sub-agent runs are durable, restart-safe, or resumable after HITL pauses.
