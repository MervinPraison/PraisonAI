"""SQLite kanban store implementation."""
import sqlite3
import json
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

from .models import Task, TaskStatus, TaskComment, TaskLink, TaskEvent, KanbanStoreProtocol
from .paths import get_kanban_db_path


class SQLiteKanbanStore:
    """SQLite implementation of kanban store with WAL mode and CAS operations."""
    
    def __init__(self, board: Optional[str] = None):
        """Initialize store.
        
        Args:
            board: Board slug. Uses PRAISONAI_KANBAN_BOARD env var or 'default'.
        """
        self.board = board
        self.db_path = get_kanban_db_path(board)
        
        # Ensure db_path is a Path object
        if not isinstance(self.db_path, Path):
            self.db_path = Path(self.db_path)
            
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize database with schema."""
        with self._get_connection() as conn:
            # Enable WAL mode for better concurrency
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            
            # Tasks table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    body TEXT DEFAULT '',
                    status TEXT DEFAULT 'todo',
                    assignee TEXT DEFAULT '',
                    priority INTEGER DEFAULT 0,
                    tenant TEXT DEFAULT 'default',
                    board TEXT DEFAULT 'default',
                    workspace_kind TEXT DEFAULT 'default',
                    claim_lock TEXT,
                    metadata TEXT,  -- JSON blob
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    version INTEGER DEFAULT 1  -- For optimistic locking
                )
            """)
            
            # Task links table (DAG)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_links (
                    parent_id TEXT NOT NULL,
                    child_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (parent_id, child_id),
                    FOREIGN KEY (parent_id) REFERENCES tasks(id) ON DELETE CASCADE,
                    FOREIGN KEY (child_id) REFERENCES tasks(id) ON DELETE CASCADE
                )
            """)
            
            # Task comments table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_comments (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    author TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                )
            """)
            
            # Task events table (audit log)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_events (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    data TEXT NOT NULL,  -- JSON blob
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Indexes for performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_board ON tasks(board)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_task_comments_task ON task_comments(task_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_task_events_task ON task_events(task_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_task_events_created ON task_events(created_at)")

    @contextmanager
    def _get_connection(self):
        """Get database connection with proper cleanup."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        # Enable foreign key constraints for this connection
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _generate_id(self) -> str:
        """Generate unique task ID."""
        return f"task_{uuid.uuid4().hex[:12]}"

    def _log_event(self, conn: sqlite3.Connection, task_id: str, event_type: str, data: Dict[str, Any]):
        """Log audit event."""
        event_id = f"event_{uuid.uuid4().hex[:12]}"
        conn.execute(
            "INSERT INTO task_events (id, task_id, event_type, data) VALUES (?, ?, ?, ?)",
            (event_id, task_id, event_type, json.dumps(data))
        )

    def create_task(self, task_data: Dict[str, Any]) -> Task:
        """Create a new task."""
        task_id = task_data.get('id', self._generate_id())
        now = datetime.utcnow()
        
        task = Task(
            id=task_id,
            title=task_data['title'],
            body=task_data.get('body', ''),
            status=TaskStatus(task_data.get('status', 'todo')),
            assignee=task_data.get('assignee', ''),
            priority=task_data.get('priority', 0),
            tenant=task_data.get('tenant', 'default'),
            board=task_data.get('board', self.board or 'default'),
            workspace_kind=task_data.get('workspace_kind', 'default'),
            metadata=task_data.get('metadata', {}),
            created_at=now,
            updated_at=now
        )
        
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO tasks (
                    id, title, body, status, assignee, priority, 
                    tenant, board, workspace_kind, metadata, 
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.id, task.title, task.body, task.status.value,
                task.assignee, task.priority, task.tenant, task.board,
                task.workspace_kind, json.dumps(task.metadata),
                task.created_at.isoformat(), task.updated_at.isoformat()
            ))
            
            self._log_event(conn, task_id, 'created', task.to_dict())
        
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            return Task.from_dict(dict(row))

    def update_task(self, task_id: str, updates: Dict[str, Any]) -> Task:
        """Update task with optimistic locking."""
        with self._get_connection() as conn:
            # Get current version for CAS
            cursor = conn.execute("SELECT version FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Task {task_id} not found")
            
            current_version = row['version']
            new_version = current_version + 1
            now = datetime.utcnow()
            
            # Build update query dynamically
            update_fields = []
            values = []
            
            for field, value in updates.items():
                if field in ['status', 'title', 'body', 'assignee', 'priority', 'claim_lock', 'metadata']:
                    if field == 'status' and isinstance(value, str):
                        value = TaskStatus(value).value
                    elif field == 'metadata':
                        value = json.dumps(value) if value else None
                    update_fields.append(f"{field} = ?")
                    values.append(value)
            
            if not update_fields:
                # No valid updates, return current task
                return self.get_task(task_id)
            
            update_fields.append("updated_at = ?")
            update_fields.append("version = ?")
            values.extend([now.isoformat(), new_version, task_id, current_version])
            
            # CAS update with version check
            result = conn.execute(f"""
                UPDATE tasks 
                SET {', '.join(update_fields)}
                WHERE id = ? AND version = ?
            """, values)
            
            if result.rowcount == 0:
                raise ValueError(f"Task {task_id} was modified by another process")
            
            # Log event
            self._log_event(conn, task_id, 'updated', updates)
            
            return self.get_task(task_id)

    def delete_task(self, task_id: str) -> bool:
        """Delete task."""
        with self._get_connection() as conn:
            # Log before deletion
            self._log_event(conn, task_id, 'deleted', {'task_id': task_id})
            
            result = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            return result.rowcount > 0

    def list_tasks(self, filters: Optional[Dict[str, Any]] = None) -> List[Task]:
        """List tasks with optional filters."""
        query = "SELECT * FROM tasks WHERE 1=1"
        values = []
        
        if filters:
            if 'status' in filters:
                if isinstance(filters['status'], list):
                    placeholders = ','.join(['?'] * len(filters['status']))
                    query += f" AND status IN ({placeholders})"
                    values.extend(filters['status'])
                else:
                    query += " AND status = ?"
                    values.append(filters['status'])
            
            if 'assignee' in filters:
                query += " AND assignee = ?"
                values.append(filters['assignee'])
            
            if 'board' in filters:
                query += " AND board = ?"
                values.append(filters['board'])
            
            if 'tenant' in filters:
                query += " AND tenant = ?"
                values.append(filters['tenant'])
        
        query += " ORDER BY priority DESC, created_at ASC"
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, values)
            return [Task.from_dict(dict(row)) for row in cursor.fetchall()]

    def _get_task_with_conn(self, task_id: str, conn: sqlite3.Connection) -> Optional[Task]:
        """Get task using existing connection to avoid nesting."""
        cursor = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        )
        row = cursor.fetchone()
        if row:
            return Task.from_dict(dict(row))
        return None
    
    def _update_task_with_conn(self, task_id: str, updates: Dict[str, Any], conn: sqlite3.Connection) -> Task:
        """Update task using existing connection to avoid nesting."""
        from datetime import timezone
        
        if not updates:
            return self._get_task_with_conn(task_id, conn)
        
        # Build update query
        set_clauses = []
        params = []
        
        for key, value in updates.items():
            if key in ['id', 'created_at']:  # Don't allow updating immutable fields
                continue
            set_clauses.append(f"{key} = ?")
            params.append(value)
        
        if not set_clauses:
            return self._get_task_with_conn(task_id, conn)
        
        # Always update timestamp and version
        set_clauses.append("updated_at = ?")
        set_clauses.append("version = version + 1")
        params.append(datetime.now(timezone.utc).isoformat())
        params.append(task_id)
        
        query = f"UPDATE tasks SET {', '.join(set_clauses)} WHERE id = ?"
        cursor = conn.execute(query, params)
        
        if cursor.rowcount == 0:
            raise ValueError(f"Task {task_id} not found")
        
        # Log the update
        self._log_event(conn, task_id, 'updated', updates)
        
        return self._get_task_with_conn(task_id, conn)

    def move_task(self, task_id: str, status: str) -> Task:
        """Move task to new status with parent/child promotion logic."""
        with self._get_connection() as conn:
            # Check if task exists
            task = self._get_task_with_conn(task_id, conn)
            if not task:
                raise ValueError(f"Task {task_id} not found")
            
            new_status = TaskStatus(status)
            
            # Check for blocking parents if moving to ready
            if new_status == TaskStatus.READY:
                cursor = conn.execute("""
                    SELECT COUNT(*) as incomplete_parents
                    FROM task_links tl
                    JOIN tasks t ON t.id = tl.parent_id
                    WHERE tl.child_id = ? AND t.status NOT IN ('done', 'archived')
                """, (task_id,))
                
                if cursor.fetchone()['incomplete_parents'] > 0:
                    raise ValueError("Cannot move to ready: incomplete parent tasks")
            
            # Update task status
            updated_task = self._update_task_with_conn(task_id, {'status': status}, conn)
            
            # Promote children if moving to done
            if new_status == TaskStatus.DONE:
                cursor = conn.execute("""
                    SELECT child_id FROM task_links WHERE parent_id = ?
                """, (task_id,))
                
                for row in cursor.fetchall():
                    child_id = row['child_id']
                    child_task = self._get_task_with_conn(child_id, conn)
                    
                    if child_task and child_task.status == TaskStatus.TODO:
                        # Check if all other parents are done
                        parent_check = conn.execute("""
                            SELECT COUNT(*) as incomplete_parents
                            FROM task_links tl
                            JOIN tasks t ON t.id = tl.parent_id
                            WHERE tl.child_id = ? AND t.status NOT IN ('done', 'archived')
                        """, (child_id,))
                        
                        if parent_check.fetchone()['incomplete_parents'] == 0:
                            self._update_task_with_conn(child_id, {'status': TaskStatus.READY.value}, conn)
            
            self._log_event(conn, task_id, 'moved', {
                'old_status': task.status.value,
                'new_status': status
            })
            
            return updated_task

    def recompute_ready(self) -> List[str]:
        """Promote dependent tasks to 'ready' once all parents are terminal.

        Scans tasks currently in 'todo'/'blocked' that have at least one
        parent link and, for each one whose parents are *all* in a terminal
        state ('done'/'archived'), advances it to 'ready'.

        Parentless tasks are intentionally left untouched so that 'todo'
        remains usable as a manual staging column (backward compatible);
        only dependency-driven tasks are auto-promoted.

        This is the engine that turns a static dependency graph into a
        self-driving pipeline; the dispatcher calls it each tick before
        claiming work.

        Returns:
            List of task IDs that were promoted to 'ready' this pass.
        """
        promoted: List[str] = []

        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT t.id AS id, t.status AS status
                FROM tasks t
                WHERE t.status IN ('todo', 'blocked')
                  AND EXISTS (
                      SELECT 1 FROM task_links tl WHERE tl.child_id = t.id
                  )
                ORDER BY t.priority DESC, t.created_at ASC
            """)
            candidates = [(row['id'], row['status']) for row in cursor.fetchall()]

            for task_id, _old_status in candidates:
                parent_check = conn.execute("""
                    SELECT COUNT(*) as incomplete_parents
                    FROM task_links tl
                    JOIN tasks t ON t.id = tl.parent_id
                    WHERE tl.child_id = ? AND t.status NOT IN ('done', 'archived')
                """, (task_id,))

                if parent_check.fetchone()['incomplete_parents'] == 0:
                    # Guard against a concurrent transition: only promote if the
                    # task is *still* waiting. This prevents overwriting a newer
                    # status (e.g. archived/moved) set since the candidate scan.
                    from datetime import timezone
                    cursor_update = conn.execute(
                        """
                        UPDATE tasks
                        SET status = ?, updated_at = ?, version = version + 1
                        WHERE id = ? AND status IN ('todo', 'blocked')
                        """,
                        (
                            TaskStatus.READY.value,
                            datetime.now(timezone.utc).isoformat(),
                            task_id,
                        ),
                    )
                    if cursor_update.rowcount == 0:
                        continue
                    self._log_event(conn, task_id, 'promoted', {
                        'old_status': _old_status,
                        'new_status': TaskStatus.READY.value,
                    })
                    promoted.append(task_id)

        return promoted

    def get_ready_children(self, parent_id: str) -> List[str]:
        """Return children of ``parent_id`` that are now ready to promote.

        A child is returned when it is in 'todo'/'blocked' and *all* of its
        parents (not just ``parent_id``) are in a terminal state.

        Args:
            parent_id: Parent task identifier.

        Returns:
            List of child task IDs eligible for promotion.
        """
        ready_children: List[str] = []

        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT tl.child_id
                FROM task_links tl
                JOIN tasks t ON t.id = tl.child_id
                WHERE tl.parent_id = ? AND t.status IN ('todo', 'blocked')
            """, (parent_id,))
            child_ids = [row['child_id'] for row in cursor.fetchall()]

            for child_id in child_ids:
                parent_check = conn.execute("""
                    SELECT COUNT(*) as incomplete_parents
                    FROM task_links tl
                    JOIN tasks t ON t.id = tl.parent_id
                    WHERE tl.child_id = ? AND t.status NOT IN ('done', 'archived')
                """, (child_id,))

                if parent_check.fetchone()['incomplete_parents'] == 0:
                    ready_children.append(child_id)

        return ready_children

    def get_board(self, board: str = "default") -> Dict[str, Any]:
        """Get board layout for UI."""
        tasks = self.list_tasks({'board': board})
        
        # Group by status for kanban columns
        columns = {}
        for status in TaskStatus:
            columns[status.value] = []
        
        for task in tasks:
            if task.status.value in columns:
                columns[task.status.value].append(task.to_dict())
        
        return {
            'board': board,
            'columns': columns,
            'task_count': len(tasks)
        }

    def bulk_update(self, operations: List[Dict[str, Any]]) -> List[Task]:
        """Bulk update operations."""
        results = []
        
        with self._get_connection() as conn:
            for op in operations:
                op_type = op.get('operation')
                
                if op_type == 'update':
                    task = self.update_task(op['task_id'], op['updates'])
                    results.append(task)
                elif op_type == 'move':
                    task = self.move_task(op['task_id'], op['status'])
                    results.append(task)
                elif op_type == 'delete':
                    if self.delete_task(op['task_id']):
                        results.append({'deleted': op['task_id']})
        
        return results

    def add_comment(self, task_id: str, author: str, text: str) -> TaskComment:
        """Add comment to task."""
        comment_id = f"comment_{uuid.uuid4().hex[:12]}"
        comment = TaskComment(
            id=comment_id,
            task_id=task_id,
            author=author,
            text=text
        )
        
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO task_comments (id, task_id, author, text, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                comment.id, comment.task_id, comment.author, 
                comment.text, comment.created_at.isoformat()
            ))
            
            self._log_event(conn, task_id, 'commented', {
                'author': author,
                'text': text[:100] + '...' if len(text) > 100 else text
            })
        
        return comment

    def get_comments(self, task_id: str) -> List[TaskComment]:
        """Get task comments."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM task_comments 
                WHERE task_id = ? 
                ORDER BY created_at ASC
            """, (task_id,))
            
            comments = []
            for row in cursor.fetchall():
                comment_data = dict(row)
                comment_data['created_at'] = datetime.fromisoformat(comment_data['created_at'])
                comments.append(TaskComment(**comment_data))
            
            return comments

    def add_link(self, parent_id: str, child_id: str) -> TaskLink:
        """Create task dependency."""
        link = TaskLink(parent_id=parent_id, child_id=child_id)
        
        with self._get_connection() as conn:
            # Check for cycles (simplified cycle detection)
            cursor = conn.execute("""
                WITH RECURSIVE cycle_check AS (
                    SELECT parent_id, child_id, 1 as depth
                    FROM task_links 
                    WHERE parent_id = ?
                    
                    UNION ALL
                    
                    SELECT tl.parent_id, tl.child_id, cc.depth + 1
                    FROM task_links tl
                    JOIN cycle_check cc ON cc.child_id = tl.parent_id
                    WHERE cc.depth < 10
                )
                SELECT COUNT(*) as cycle_found
                FROM cycle_check
                WHERE child_id = ?
            """, (child_id, parent_id))
            
            if cursor.fetchone()['cycle_found'] > 0:
                raise ValueError("Would create dependency cycle")
            
            conn.execute("""
                INSERT OR IGNORE INTO task_links (parent_id, child_id, created_at)
                VALUES (?, ?, ?)
            """, (parent_id, child_id, link.created_at.isoformat()))
            
            self._log_event(conn, child_id, 'linked', {
                'parent_id': parent_id,
                'child_id': child_id
            })
        
        return link

    def remove_link(self, parent_id: str, child_id: str) -> bool:
        """Remove task dependency."""
        with self._get_connection() as conn:
            result = conn.execute("""
                DELETE FROM task_links 
                WHERE parent_id = ? AND child_id = ?
            """, (parent_id, child_id))
            
            if result.rowcount > 0:
                self._log_event(conn, child_id, 'unlinked', {
                    'parent_id': parent_id,
                    'child_id': child_id
                })
            
            return result.rowcount > 0

    def list_events(self, since: Optional[datetime] = None) -> List[TaskEvent]:
        """List events for SSE."""
        query = "SELECT * FROM task_events"
        values = []
        
        if since:
            query += " WHERE created_at > ?"
            values.append(since.isoformat())
        
        query += " ORDER BY created_at DESC LIMIT 100"
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, values)
            events = []
            
            for row in cursor.fetchall():
                event_data = dict(row)
                event_data['created_at'] = datetime.fromisoformat(event_data['created_at'])
                event_data['data'] = json.loads(event_data['data'])
                events.append(TaskEvent(**event_data))
            
            return events

    def claim_task(self, task_id: str, worker_id: str) -> bool:
        """Claim a ready task for execution (CAS operation)."""
        with self._get_connection() as conn:
            # Atomic claim with CAS on status and claim_lock, increment version for optimistic locking
            from datetime import timezone
            result = conn.execute("""
                UPDATE tasks 
                SET claim_lock = ?, updated_at = ?, status = 'running', version = version + 1
                WHERE id = ? AND status = 'ready' AND (claim_lock IS NULL OR claim_lock = '')
            """, (worker_id, datetime.now(timezone.utc).isoformat(), task_id))
            
            if result.rowcount > 0:
                self._log_event(conn, task_id, 'claimed', {'worker_id': worker_id})
                return True
            
            return False

    def release_claim(self, task_id: str, worker_id: str) -> bool:
        """Release claim on task."""
        with self._get_connection() as conn:
            # Release claim and increment version for optimistic locking
            from datetime import timezone
            result = conn.execute("""
                UPDATE tasks 
                SET claim_lock = NULL, updated_at = ?, status = 'ready', version = version + 1
                WHERE id = ? AND claim_lock = ?
            """, (datetime.now(timezone.utc).isoformat(), task_id, worker_id))
            
            if result.rowcount > 0:
                self._log_event(conn, task_id, 'released', {'worker_id': worker_id})
                return True
            
            return False