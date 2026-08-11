"""
Kanban protocols for PraisonAI Agents.

Defines the protocol contracts that the wrapper (praisonai) and PraisonAIUI
can use to implement kanban functionality with a stable interface.

This follows AGENTS.md §3.2 Protocol-First Design:
- Protocols define WHAT (interface contract)
- Implementations define HOW (concrete behavior)
- Core SDK has protocols only, wrapper has heavy implementations
"""

from typing import Protocol, TypedDict, runtime_checkable


# Valid kanban statuses matching PraisonAIUI columns + archived
VALID_KANBAN_STATUSES: frozenset[str] = frozenset([
    "triage",
    "todo", 
    "ready",
    "running",
    "blocked",
    "review",
    "done",
    "archived"
])


class KanbanTaskProtocol(TypedDict, total=False):
    """Typed dict shape for kanban task fields.
    
    Defines the expected structure of task objects returned by
    KanbanStoreProtocol implementations.
    """
    id: str
    title: str
    body: str
    status: str
    assignee: str | None
    priority: str | None
    tenant: str | None
    board: str
    created_at: float
    updated_at: float
    # Workspace isolation (optional; default "default" = shared cwd).
    # "worktree" opts a task into a dedicated per-task git worktree/branch.
    workspace_kind: str
    branch: str | None
    worktree_path: str | None
    # Claim lease / reclamation fields (optional; populated while running).
    # Timestamps are serialized as ISO 8601 strings by Task.to_dict().
    claim_lock: str | None
    claim_expires: str | None
    worker_pid: int | None
    last_heartbeat_at: str | None
    # Retry / run-history fields (optional).
    max_retries: int | None
    consecutive_failures: int
    current_run_id: int | None


class KanbanRunProtocol(TypedDict, total=False):
    """Typed dict shape for a single task attempt (run).

    One row per attempt: outcome plus a structured summary/metadata handoff and
    any error. Surfaced to retrying workers and linked children.
    """
    id: int
    task_id: str
    profile: str
    outcome: str | None  # completed/blocked/crashed/failed/gave_up
    summary: str
    metadata: dict
    error: str
    started_at: str | None  # ISO-8601 string (matches TaskRun.to_dict())
    ended_at: str | None    # ISO-8601 string; None while the run is open


@runtime_checkable
class KanbanStoreProtocol(Protocol):
    """Protocol contract for kanban store implementations.
    
    This protocol defines the core interface that PraisonAIUI expects
    for injected kanban stores. Wrapper implementations must
    implement all methods to be compatible.
    
    Duck typing contract matches InjectedKanbanStore in PraisonAIUI.
    """
    
    def get_board(
        self,
        *,
        board: str = "default",
        tenant: str | None = None,
        include_archived: bool = False,
    ) -> dict:
        """Get board data with tasks grouped by status.
        
        Args:
            board: Board name (default: "default")
            tenant: Optional tenant filter
            include_archived: Whether to include archived tasks
            
        Returns:
            Board data with tasks organized by status columns
        """
        ...

    def get_task(self, task_id: str) -> dict | None:
        """Get a single task by ID.
        
        Args:
            task_id: Task identifier
            
        Returns:
            Task data or None if not found
        """
        ...

    def create_task(self, data: dict) -> dict:
        """Create a new task.
        
        Args:
            data: Task creation data (title, body, status, etc.)
            
        Returns:
            Created task data with assigned ID
        """
        ...

    def update_task(self, task_id: str, data: dict) -> dict | None:
        """Update an existing task.
        
        Args:
            task_id: Task identifier
            data: Fields to update
            
        Returns:
            Updated task data or None if not found
        """
        ...

    def move_task(self, task_id: str, status: str) -> dict | None:
        """Move a task to a different status.
        
        Args:
            task_id: Task identifier
            status: New status (must be in VALID_KANBAN_STATUSES)
            
        Returns:
            Updated task data or None if not found
        """
        ...

    def bulk_update(self, task_ids: list[str], status: str) -> dict:
        """Update multiple tasks to the same status.
        
        Args:
            task_ids: List of task identifiers
            status: New status for all tasks
            
        Returns:
            Results summary with success/failure counts
        """
        ...

    def delete_task(self, task_id: str) -> bool:
        """Delete a task.
        
        Args:
            task_id: Task identifier
            
        Returns:
            True if deleted, False if not found
        """
        ...

    def list_events(self, since: float = 0.0, board: str = "default") -> list[dict]:
        """List kanban events since a timestamp.
        
        Args:
            since: Unix timestamp to filter events from
            board: Board name to filter events
            
        Returns:
            List of event data
        """
        ...

    def health(self) -> dict:
        """Check store health status.
        
        Returns:
            Health status information
        """
        ...


@runtime_checkable
class KanbanCommentingProtocol(Protocol):
    """Extension protocol for kanban task commenting functionality.
    
    This protocol is implemented separately from KanbanStoreProtocol to allow
    stores to optionally support commenting without breaking isinstance checks
    on the core protocol.
    """
    
    def add_comment(self, task_id: str, text: str, author: str | None = None) -> dict | None:
        """Add a comment to a task.
        
        Args:
            task_id: Task identifier
            text: Comment text
            author: Optional comment author
            
        Returns:
            Comment data or None if task not found
        """
        ...


@runtime_checkable
class KanbanReclaimProtocol(Protocol):
    """Extension protocol for durable claim leases and stale-claim reclamation.

    Stores implementing this protocol support recovering tasks stranded by
    crashed, killed, or hung workers. The dispatcher tick calls
    ``reclaim_stale_claims`` to return such tasks to ``ready`` for re-dispatch.

    This is kept separate from KanbanStoreProtocol so stores can adopt
    reclamation incrementally without breaking isinstance checks on the core
    protocol.
    """

    def claim_task(
        self,
        task_id: str,
        worker_id: str,
        *,
        ttl_seconds: int = 900,
        worker_pid: int | None = None,
    ) -> bool:
        """Claim a ready task with a lease (TTL) and optional owner PID.

        Returns:
            True if the claim succeeded.
        """
        ...

    def heartbeat(
        self,
        task_id: str,
        worker_id: str,
        *,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Record a worker heartbeat, optionally extending the claim lease.

        Returns:
            True if the heartbeat was recorded (worker owns the claim).
        """
        ...

    def reclaim_stale_claims(self, *, stale_timeout_seconds: int = 1800) -> list[str]:
        """Reclaim running tasks whose lease expired and whose worker is dead/stale.

        Returns:
            List of task IDs returned to ``ready``.
        """
        ...


@runtime_checkable 
class KanbanLinkingProtocol(Protocol):
    """Extension protocol for kanban task linking functionality.
    
    This protocol is implemented separately from KanbanStoreProtocol to allow
    stores to optionally support task relationships without breaking isinstance
    checks on the core protocol.
    """
    
    def link_tasks(self, parent_id: str, child_id: str) -> bool:
        """Link two tasks in parent-child relationship.
        
        Args:
            parent_id: Parent task identifier
            child_id: Child task identifier
            
        Returns:
            True if linked successfully, False otherwise
        """
        ...

    def unlink_tasks(self, parent_id: str, child_id: str) -> bool:
        """Unlink parent-child task relationship.
        
        Args:
            parent_id: Parent task identifier
            child_id: Child task identifier
            
        Returns:
            True if unlinked successfully, False otherwise
        """
        ...


@runtime_checkable
class KanbanPromotionProtocol(Protocol):
    """Extension protocol for dependency-driven task promotion.

    Implemented separately from KanbanStoreProtocol so that stores can opt
    into auto-promotion without breaking isinstance checks on the core
    protocol. This is the engine that turns a linked parent->child DAG into
    a self-driving pipeline: the dispatcher calls ``recompute_ready`` each
    tick before claiming work.
    """

    def recompute_ready(self) -> list[str]:
        """Promote dependent tasks to 'ready' when all parents are terminal.

        Scans tasks waiting on dependencies and advances any whose parent
        tasks are all in a terminal state ('done'/'archived') to 'ready'.

        Returns:
            List of task IDs promoted to 'ready' in this pass.
        """
        ...


@runtime_checkable
class KanbanRunsProtocol(Protocol):
    """Extension protocol for per-task attempt (run) history and retry.

    Implemented separately from KanbanStoreProtocol so stores can optionally
    support durable attempt history, structured handoff and a per-task
    circuit-breaker without breaking isinstance checks on the core protocol.
    """

    def record_run(
        self,
        task_id: str,
        outcome: str,
        *,
        profile: str = "",
        summary: str | None = None,
        metadata: dict | None = None,
        error: str | None = None,
    ) -> dict:
        """Record a completed attempt (open + close in one call).

        Args:
            task_id: Task that was attempted.
            outcome: One of completed/blocked/crashed/failed/gave_up.
            profile: Optional worker/profile identifier.
            summary: Structured summary of what was done (handoff).
            metadata: Structured handoff fields (e.g. changed_files, tests_run).
            error: Error text for failed/crashed attempts.

        Returns:
            The recorded run data.
        """
        ...

    def get_runs(self, task_id: str) -> list[dict]:
        """Return all attempts for a task, oldest first.

        Args:
            task_id: Task identifier.

        Returns:
            List of run data (KanbanRunProtocol shape).
        """
        ...

    def record_failure(self, task_id: str, *, error: str | None = None) -> bool:
        """Increment the consecutive-failure counter; auto-block at the limit.

        Args:
            task_id: Task that just failed an attempt.
            error: Optional last error to attach when auto-blocking.

        Returns:
            True if the task was circuit-broken (auto-blocked) by this call.
        """
        ...