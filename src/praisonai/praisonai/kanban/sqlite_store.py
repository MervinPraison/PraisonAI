"""SQLite kanban store implementation."""
import sqlite3
import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pathlib import Path

from .models import (
    Task, TaskStatus, TaskComment, TaskLink, TaskEvent, TaskRun, RunOutcome,
    KanbanStoreProtocol,
)
from .paths import get_kanban_db_path

# Board-wide default for the per-task retry/circuit-breaker.
DEFAULT_MAX_RETRIES = 3


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
                    claim_expires TIMESTAMP,  -- Claim lease expiry (TTL)
                    worker_pid INTEGER,  -- PID of claiming worker for liveness checks
                    last_heartbeat_at TIMESTAMP,  -- Last heartbeat from worker
                    metadata TEXT,  -- JSON blob
                    idempotency_key TEXT,  -- optional dedup key for create
                    max_retries INTEGER,  -- per-task override; NULL -> board default
                    consecutive_failures INTEGER DEFAULT 0,
                    current_run_id INTEGER,  -- active task_runs row
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
            
            # Task runs table (one row per attempt)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    profile TEXT DEFAULT '',
                    outcome TEXT,  -- completed/blocked/crashed/failed/gave_up; NULL while open
                    summary TEXT DEFAULT '',
                    metadata TEXT,  -- JSON blob
                    error TEXT DEFAULT '',
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ended_at TIMESTAMP,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                )
            """)
            
            # Run migrations for pre-existing databases
            self._migrate_schema(conn)
            
            # Indexes for performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_board ON tasks(board)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_task_comments_task ON task_comments(task_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_task_events_task ON task_events(task_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_task_events_created ON task_events(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_task_runs_task ON task_runs(task_id)")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_idempotency "
                "ON tasks(board, tenant, idempotency_key) WHERE idempotency_key IS NOT NULL"
            )

    def _migrate_schema(self, conn: sqlite3.Connection):
        """Add columns introduced after the initial schema for existing DBs."""
        cursor = conn.execute("PRAGMA table_info(tasks)")
        existing = {row[1] for row in cursor.fetchall()}
        migrations = {
            'idempotency_key': "ALTER TABLE tasks ADD COLUMN idempotency_key TEXT",
            'max_retries': "ALTER TABLE tasks ADD COLUMN max_retries INTEGER",
            'consecutive_failures': "ALTER TABLE tasks ADD COLUMN consecutive_failures INTEGER DEFAULT 0",
            'current_run_id': "ALTER TABLE tasks ADD COLUMN current_run_id INTEGER",
        }
        for column, ddl in migrations.items():
            if column not in existing:
                conn.execute(ddl)

        # Migrate pre-existing databases that lack the reclamation columns.
        self._ensure_columns(conn, "tasks", {
            "claim_expires": "TIMESTAMP",
            "worker_pid": "INTEGER",
            "last_heartbeat_at": "TIMESTAMP",
        })

        # Drop a pre-existing idempotency index that is not tenant-scoped so the
        # tenant-aware unique index below can replace it. Legacy DBs created the
        # index on (board, idempotency_key); reusing the same name with
        # IF NOT EXISTS would otherwise leave two tenants able to collide on the
        # same board+key after migration.
        cursor = conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'index' AND name = 'idx_tasks_idempotency'"
        )
        index_row = cursor.fetchone()
        if index_row and index_row[0] and 'tenant' not in index_row[0]:
            conn.execute("DROP INDEX idx_tasks_idempotency")

    def _ensure_columns(self, conn: sqlite3.Connection, table: str, columns: Dict[str, str]):
        """Add missing columns to an existing table (idempotent migration)."""
        existing = {row['name'] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, col_type in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}")

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

    def create_task(self, task_data: Dict[str, Any], *, idempotency_key: Optional[str] = None) -> Task:
        """Create a new task.

        Args:
            task_data: Task creation fields.
            idempotency_key: Optional dedup key. Falls back to
                ``task_data['idempotency_key']``. A repeat create with the same
                key on the same board returns the existing task unchanged.
        """
        task_id = task_data.get('id', self._generate_id())
        now = datetime.now(timezone.utc)
        board = task_data.get('board', self.board or 'default')
        tenant = task_data.get('tenant', 'default')
        if idempotency_key is None:
            idempotency_key = task_data.get('idempotency_key')
        # Reject non-positive / non-integer overrides so a bad caller value
        # cannot auto-block a task on its first failure; fall back to the
        # board default instead.
        max_retries = task_data.get('max_retries')
        if max_retries is not None:
            try:
                max_retries = int(max_retries)
            except (TypeError, ValueError):
                max_retries = None
            else:
                if max_retries < 1:
                    max_retries = None

        task = Task(
            id=task_id,
            title=task_data['title'],
            body=task_data.get('body', ''),
            status=TaskStatus(task_data.get('status', 'todo')),
            assignee=task_data.get('assignee', ''),
            priority=task_data.get('priority', 0),
            tenant=tenant,
            board=board,
            workspace_kind=task_data.get('workspace_kind', 'default'),
            metadata=task_data.get('metadata', {}),
            max_retries=max_retries,
            created_at=now,
            updated_at=now
        )

        def _find_existing(conn):
            cursor = conn.execute(
                "SELECT * FROM tasks WHERE board = ? AND tenant = ? AND idempotency_key = ?",
                (board, tenant, idempotency_key)
            )
            row = cursor.fetchone()
            return Task.from_dict(dict(row)) if row else None

        with self._get_connection() as conn:
            # Idempotent create: return existing task if key already used
            # (scoped per board + tenant to avoid cross-tenant collisions).
            if idempotency_key is not None:
                existing = _find_existing(conn)
                if existing:
                    return existing

            try:
                conn.execute("""
                    INSERT INTO tasks (
                        id, title, body, status, assignee, priority,
                        tenant, board, workspace_kind, metadata,
                        idempotency_key, max_retries, consecutive_failures,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    task.id, task.title, task.body, task.status.value,
                    task.assignee, task.priority, task.tenant, task.board,
                    task.workspace_kind, json.dumps(task.metadata),
                    idempotency_key, max_retries, 0,
                    task.created_at.isoformat(), task.updated_at.isoformat()
                ))
            except sqlite3.IntegrityError:
                # Lost a concurrent race on the idempotency key: return the
                # row that won instead of bubbling up the duplicate error.
                if idempotency_key is not None:
                    existing = _find_existing(conn)
                    if existing:
                        return existing
                raise

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
            now = datetime.now(timezone.utc)
            
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
                return self._get_task_with_conn(task_id, conn)
            
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
            
            return self._get_task_with_conn(task_id, conn)

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
            
            # Update task status. Terminal statuses also clear the claim so a
            # finished/archived task is no longer reported as owned by a worker.
            status_updates = {'status': status}
            if new_status in (TaskStatus.DONE, TaskStatus.ARCHIVED):
                status_updates['claim_lock'] = None
            updated_task = self._update_task_with_conn(task_id, status_updates, conn)
            
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

    def claim_task(
        self,
        task_id: str,
        worker_id: str,
        *,
        ttl_seconds: int = 900,
        worker_pid: Optional[int] = None,
    ) -> bool:
        """Claim a ready task for execution (CAS operation) with a lease.

        Args:
            task_id: Task to claim.
            worker_id: Identifier of the claiming worker.
            ttl_seconds: Lease duration; the claim is reclaimable after expiry.
            worker_pid: PID of the worker process for liveness checks.

        Returns:
            True if the claim succeeded.
        """
        from datetime import timezone, timedelta
        with self._get_connection() as conn:
            now = datetime.now(timezone.utc)
            expires = now + timedelta(seconds=ttl_seconds)
            # Atomic claim with CAS on status and claim_lock, increment version for optimistic locking
            result = conn.execute("""
                UPDATE tasks 
                SET claim_lock = ?, claim_expires = ?, worker_pid = ?,
                    last_heartbeat_at = ?, updated_at = ?,
                    status = 'running', version = version + 1
                WHERE id = ? AND status = 'ready' AND (claim_lock IS NULL OR claim_lock = '')
            """, (
                worker_id, expires.isoformat(), worker_pid,
                now.isoformat(), now.isoformat(), task_id,
            ))
            
            if result.rowcount > 0:
                self._log_event(conn, task_id, 'claimed', {
                    'worker_id': worker_id,
                    'worker_pid': worker_pid,
                    'claim_expires': expires.isoformat(),
                })
                return True
            
            return False

    def heartbeat(
        self,
        task_id: str,
        worker_id: str,
        *,
        ttl_seconds: Optional[int] = None,
    ) -> bool:
        """Record a heartbeat for a claimed task, optionally extending the lease.

        Args:
            task_id: Task being worked on.
            worker_id: Owner worker; must match the current claim_lock.
            ttl_seconds: If provided, extends claim_expires to now + ttl_seconds.

        Returns:
            True if the heartbeat was recorded (i.e. the worker owns the claim).
        """
        from datetime import timezone, timedelta
        with self._get_connection() as conn:
            now = datetime.now(timezone.utc)
            if ttl_seconds is not None:
                expires = (now + timedelta(seconds=ttl_seconds)).isoformat()
                result = conn.execute("""
                    UPDATE tasks
                    SET last_heartbeat_at = ?, claim_expires = ?, version = version + 1
                    WHERE id = ? AND claim_lock = ?
                """, (now.isoformat(), expires, task_id, worker_id))
            else:
                result = conn.execute("""
                    UPDATE tasks
                    SET last_heartbeat_at = ?, version = version + 1
                    WHERE id = ? AND claim_lock = ?
                """, (now.isoformat(), task_id, worker_id))

            return result.rowcount > 0

    def release_claim(self, task_id: str, worker_id: str) -> bool:
        """Release claim on task."""
        with self._get_connection() as conn:
            # Release claim and increment version for optimistic locking
            from datetime import timezone
            # Only revert to 'ready' when the task is still 'running'. A task
            # that already moved on (e.g. 'done'/'blocked' after completion)
            # must not be requeued if a later cleanup step releases the claim,
            # so we scope the status reset to running tasks only.
            result = conn.execute("""
                UPDATE tasks 
                SET claim_lock = NULL, claim_expires = NULL, worker_pid = NULL,
                    last_heartbeat_at = NULL, updated_at = ?,
                    status = CASE WHEN status = 'running' THEN 'ready' ELSE status END,
                    version = version + 1
                WHERE id = ? AND claim_lock = ?
            """, (datetime.now(timezone.utc).isoformat(), task_id, worker_id))
            
            if result.rowcount > 0:
                self._log_event(conn, task_id, 'released', {'worker_id': worker_id})
                return True
            
            return False

    @staticmethod
    def _pid_alive(pid: Optional[int]) -> bool:
        """Best-effort check whether a process is alive on this host."""
        if not pid or pid <= 0:
            return False
        import os
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            # Process exists but is owned by another user.
            return True
        except OSError:
            return False
        return True

    def reclaim_stale_claims(self, *, stale_timeout_seconds: int = 1800) -> List[str]:
        """Reclaim running tasks whose lease expired and whose worker is dead/stale.

        A task is reclaimed (returned to 'ready') when its lease (claim_expires)
        has elapsed AND either:
          * its worker PID is no longer alive (crash/kill), or
          * its last heartbeat is older than stale_timeout_seconds (hang),
          * or there is no liveness signal at all.

        Tasks whose lease expired but whose worker PID is still alive and
        recently heartbeating are left untouched (the worker may extend its
        own lease via heartbeat()).

        Args:
            stale_timeout_seconds: Heartbeat staleness threshold.

        Returns:
            List of task IDs that were reclaimed back to 'ready'.
        """
        from datetime import timezone, timedelta
        reclaimed: List[str] = []
        now = datetime.now(timezone.utc)

        def _parse(value: Any) -> Optional[datetime]:
            if not value:
                return None
            try:
                parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            except (ValueError, TypeError):
                return None
            # Normalize naive timestamps (legacy rows) to UTC for comparison.
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed

        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT id, claim_lock, claim_expires, worker_pid, last_heartbeat_at, version
                FROM tasks
                WHERE status = 'running' AND claim_lock IS NOT NULL AND claim_lock != ''
            """)
            candidates = [dict(row) for row in cursor.fetchall()]

            for row in candidates:
                expires = _parse(row.get('claim_expires'))
                # No lease recorded (legacy claim) -> treat as eligible for reclaim
                # only when the worker is clearly gone; otherwise require expiry.
                if expires is not None and expires > now:
                    continue  # lease still valid

                pid = row.get('worker_pid')
                heartbeat = _parse(row.get('last_heartbeat_at'))

                worker_alive = self._pid_alive(pid)
                heartbeat_fresh = (
                    heartbeat is not None
                    and (now - heartbeat) < timedelta(seconds=stale_timeout_seconds)
                )

                # Keep the claim if the worker is alive and still heartbeating.
                if worker_alive and heartbeat_fresh:
                    continue

                # Guard against a heartbeat/claim landing between the SELECT and
                # this UPDATE: only reclaim if the row is still on the same
                # version we evaluated. A live worker's heartbeat bumps version,
                # so a raced update will simply skip this row (rowcount == 0).
                result = conn.execute("""
                    UPDATE tasks
                    SET claim_lock = NULL, claim_expires = NULL, worker_pid = NULL,
                        last_heartbeat_at = NULL,
                        updated_at = ?, status = 'ready', version = version + 1
                    WHERE id = ? AND status = 'running' AND claim_lock = ?
                          AND version = ?
                """, (now.isoformat(), row['id'], row['claim_lock'], row['version']))

                if result.rowcount > 0:
                    reclaimed.append(row['id'])
                    self._log_event(conn, row['id'], 'reclaimed', {
                        'worker_id': row['claim_lock'],
                        'worker_pid': pid,
                        'reason': 'dead' if not worker_alive else 'stale_heartbeat',
                    })

        return reclaimed

    # ------------------------------------------------------------------
    # Task runs (attempt history) + per-task retry / circuit-breaker
    # ------------------------------------------------------------------

    def start_run(self, task_id: str, profile: str = "") -> int:
        """Open a new attempt (run) row and point the task at it.

        Args:
            task_id: Task being attempted.
            profile: Optional worker/profile identifier for the attempt.

        Returns:
            The new run id.
        """
        from datetime import timezone
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO task_runs (task_id, profile, started_at) VALUES (?, ?, ?)",
                (task_id, profile, now)
            )
            run_id = cursor.lastrowid
            conn.execute(
                "UPDATE tasks SET current_run_id = ?, updated_at = ? WHERE id = ?",
                (run_id, now, task_id)
            )
            self._log_event(conn, task_id, 'run_started', {'run_id': run_id, 'profile': profile})
            return run_id

    def close_run(
        self,
        run_id: int,
        outcome: str,
        *,
        summary: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Optional[TaskRun]:
        """Close an attempt with its outcome and structured handoff.

        Args:
            run_id: Run to close.
            outcome: One of RunOutcome values.
            summary: Structured human/agent summary of what was done.
            metadata: Structured handoff (e.g. changed_files, tests_run).
            error: Error text for failed/crashed attempts.

        Returns:
            The closed TaskRun, or None if run_id is unknown.
        """
        from datetime import timezone
        outcome_value = outcome.value if isinstance(outcome, RunOutcome) else str(outcome)
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM task_runs WHERE id = ?", (run_id,))
            row = cursor.fetchone()
            if not row:
                return None
            run = TaskRun.from_row(dict(row))
            # Reject already-finalized runs: once ended_at is set the outcome is
            # immutable. This guards against a stale current_run_id (e.g. the
            # dispatcher already closed this run as 'failed') being re-closed as
            # 'completed', which would rewrite audit/retry history with the wrong
            # result. Return the existing run unchanged instead.
            if row['ended_at']:
                return run
            new_summary = summary if summary is not None else run.summary
            new_error = error if error is not None else run.error
            new_metadata = metadata if metadata is not None else run.metadata
            conn.execute("""
                UPDATE task_runs
                SET outcome = ?, summary = ?, metadata = ?, error = ?, ended_at = ?
                WHERE id = ?
            """, (
                outcome_value, new_summary or '', json.dumps(new_metadata or {}),
                new_error or '', now, run_id
            ))
            # The attempt is no longer active: clear the task pointer, but only
            # if it still points at THIS run so a late close from an older run
            # cannot wipe a newer active attempt.
            conn.execute(
                "UPDATE tasks SET current_run_id = NULL, updated_at = ? "
                "WHERE id = ? AND current_run_id = ?",
                (now, run.task_id, run_id)
            )
            # Successful completion resets the failure counter
            if outcome_value == RunOutcome.COMPLETED.value:
                conn.execute(
                    "UPDATE tasks SET consecutive_failures = 0, updated_at = ? WHERE id = ?",
                    (now, run.task_id)
                )
            self._log_event(conn, run.task_id, 'run_closed', {
                'run_id': run_id,
                'outcome': outcome_value,
            })
            cursor = conn.execute("SELECT * FROM task_runs WHERE id = ?", (run_id,))
            return TaskRun.from_row(dict(cursor.fetchone()))

    def get_runs(self, task_id: str) -> List[TaskRun]:
        """Return all attempts for a task, oldest first."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM task_runs WHERE task_id = ? ORDER BY started_at ASC, id ASC",
                (task_id,)
            )
            return [TaskRun.from_row(dict(row)) for row in cursor.fetchall()]

    def record_run(
        self,
        task_id: str,
        outcome: str,
        *,
        profile: str = "",
        summary: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> TaskRun:
        """Convenience: open and immediately close a run in one call."""
        run_id = self.start_run(task_id, profile=profile)
        return self.close_run(
            run_id, outcome, summary=summary, metadata=metadata, error=error
        )

    def record_failure(self, task_id: str, *, error: Optional[str] = None) -> bool:
        """Increment the consecutive-failure counter; auto-block at the limit.

        Args:
            task_id: Task that just failed an attempt.
            error: Optional last error to attach when auto-blocking.

        Returns:
            True if the task was circuit-broken (auto-blocked) by this call.
        """
        from datetime import timezone
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT consecutive_failures, max_retries, status FROM tasks WHERE id = ?",
                (task_id,)
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Task {task_id} not found")
            # A terminal task (already completed/archived by another caller,
            # e.g. kanban_complete) must not be re-failed: a stale process-exit
            # handler could otherwise increment the counter and re-block a task
            # that already finished. Treat as a no-op (not circuit-broken).
            if (row['status'] or '') in ('done', 'archived'):
                return False
            failures = (row['consecutive_failures'] or 0) + 1
            # Normalize the persisted limit too: a task created before create-path
            # validation (or via migration) may carry max_retries=0/negative,
            # which would otherwise auto-block on the first failure. Fall back to
            # the board default for any non-positive / non-integer stored value.
            stored_limit = row['max_retries']
            try:
                stored_limit = int(stored_limit) if stored_limit is not None else None
            except (TypeError, ValueError):
                stored_limit = None
            limit = stored_limit if (stored_limit is not None and stored_limit >= 1) else DEFAULT_MAX_RETRIES
            blocked = failures >= limit
            if blocked:
                conn.execute("""
                    UPDATE tasks
                    SET consecutive_failures = ?, status = 'blocked',
                        claim_lock = NULL, updated_at = ?, version = version + 1
                    WHERE id = ?
                """, (failures, now, task_id))
                self._log_event(conn, task_id, 'circuit_broken', {
                    'consecutive_failures': failures,
                    'max_retries': limit,
                    'error': (error or '')[:500],
                })
            else:
                conn.execute(
                    "UPDATE tasks SET consecutive_failures = ?, updated_at = ? WHERE id = ?",
                    (failures, now, task_id)
                )
                self._log_event(conn, task_id, 'failure_recorded', {
                    'consecutive_failures': failures,
                    'max_retries': limit,
                })
            return blocked

    def get_retry_context(self, task_id: str) -> List[Dict[str, Any]]:
        """Prior attempts' outcomes/summaries/errors for a retrying worker.

        Returns a list (oldest first) of dicts so a retrying worker can avoid
        repeating known-failed paths.
        """
        context = []
        for run in self.get_runs(task_id):
            context.append({
                'run_id': run.id,
                'outcome': run.outcome,
                'summary': run.summary,
                'error': run.error,
                'metadata': run.metadata,
            })
        return context
