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


@runtime_checkable
class KanbanStoreProtocol(Protocol):
    """Protocol contract for kanban store implementations.
    
    This protocol defines the interface that PraisonAIUI expects
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

    # Optional P4 extensions - define in protocol now, implement in wrapper later
    # Use default implementations or NotImplementedError in adapters
    
    def add_comment(self, task_id: str, text: str, author: str | None = None) -> dict | None:
        """Add a comment to a task (optional P4 extension).
        
        Args:
            task_id: Task identifier
            text: Comment text
            author: Optional comment author
            
        Returns:
            Comment data or None if task not found
        """
        raise NotImplementedError("Comment functionality not implemented")

    def link_tasks(self, parent_id: str, child_id: str) -> bool:
        """Link two tasks in parent-child relationship (optional P4 extension).
        
        Args:
            parent_id: Parent task identifier
            child_id: Child task identifier
            
        Returns:
            True if linked successfully, False otherwise
        """
        raise NotImplementedError("Task linking not implemented")

    def unlink_tasks(self, parent_id: str, child_id: str) -> bool:
        """Unlink parent-child task relationship (optional P4 extension).
        
        Args:
            parent_id: Parent task identifier
            child_id: Child task identifier
            
        Returns:
            True if unlinked successfully, False otherwise
        """
        raise NotImplementedError("Task unlinking not implemented")