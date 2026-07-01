"""
SQLite persistence layer for the PraisonAI Queue System.

Provides crash recovery, session persistence, and run history.
"""

import json
import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import QueuedRun, RunState, RunPriority, QueueStats

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"

SCHEMA_SQL = """
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version TEXT PRIMARY KEY,
    applied_at REAL NOT NULL
);

-- Queue runs
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    input_content TEXT,
    output_content TEXT,
    state TEXT NOT NULL DEFAULT 'queued',
    priority INTEGER NOT NULL DEFAULT 1,
    session_id TEXT,
    trace_id TEXT,
    workspace TEXT,
    user_id TEXT,
    created_at REAL NOT NULL,
    started_at REAL,
    ended_at REAL,
    error TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    parent_run_id TEXT,
    config TEXT,
    metrics TEXT,
    recovered INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_runs_state ON runs(state);
CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id);
CREATE INDEX IF NOT EXISTS idx_runs_priority_created ON runs(priority DESC, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_runs_workspace ON runs(workspace);

-- Messages (chat history per run)
CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES runs(run_id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp REAL NOT NULL,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_run ON messages(run_id);

-- Tool calls
CREATE TABLE IF NOT EXISTS tool_calls (
    call_id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES runs(run_id),
    tool_name TEXT NOT NULL,
    args TEXT,
    result TEXT,
    started_at REAL NOT NULL,
    ended_at REAL,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_tool_calls_run ON tool_calls(run_id);

-- Sessions
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    state TEXT,
    config TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
"""


class QueuePersistence:
    """SQLite-backed persistence for the queue system."""
    
    def __init__(self, db_path: str = ".praison/queue.db"):
        """
        Initialize persistence layer.
        
        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()
        self._initialized = False
    
    def _ensure_dir(self) -> None:
        """Ensure database directory exists."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            self._ensure_dir()
            self._conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0
            )
            self._conn.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrency
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn
    
    @contextmanager
    def _transaction(self):
        """Context manager for database transactions."""
        conn = self._get_connection()
        with self._lock:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    
    def initialize(self) -> None:
        """Initialize database schema."""
        if self._initialized:
            return
        
        with self._transaction() as conn:
            conn.executescript(SCHEMA_SQL)
            
            # Check/set schema version
            cursor = conn.execute(
                "SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1"
            )
            row = cursor.fetchone()
            
            if row is None:
                conn.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, time.time())
                )
            elif row["version"] != SCHEMA_VERSION:
                # Future: handle migrations
                logger.warning(
                    f"Schema version mismatch: {row['version']} vs {SCHEMA_VERSION}"
                )
        
        self._initialized = True
    
    def close(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            self._initialized = False
    
    # Run operations
    
    def save_run(self, run: QueuedRun) -> None:
        """Save or update a run."""
        self.initialize()
        
        with self._transaction() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO runs (
                    run_id, agent_name, input_content, output_content,
                    state, priority, session_id, trace_id, workspace, user_id,
                    created_at, started_at, ended_at, error,
                    retry_count, max_retries, parent_run_id,
                    config, metrics
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run.run_id,
                run.agent_name,
                run.input_content,
                run.output_content,
                run.state.value,
                int(run.priority),
                run.session_id,
                run.trace_id,
                run.workspace,
                run.user_id,
                run.created_at,
                run.started_at,
                run.ended_at,
                run.error,
                run.retry_count,
                run.max_retries,
                run.parent_run_id,
                json.dumps(run.config) if run.config else None,
                json.dumps(run.metrics) if run.metrics else None,
            ))
    
    def load_run(self, run_id: str) -> Optional[QueuedRun]:
        """Load a run by ID."""
        self.initialize()
        
        with self._transaction() as conn:
            cursor = conn.execute(
                "SELECT * FROM runs WHERE run_id = ?",
                (run_id,)
            )
            row = cursor.fetchone()
            
            if row is None:
                return None
            
            return self._row_to_run(row)
    
    def list_runs(
        self,
        state: Optional[RunState] = None,
        session_id: Optional[str] = None,
        workspace: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[QueuedRun]:
        """List runs with optional filters."""
        self.initialize()
        
        query = "SELECT * FROM runs WHERE 1=1"
        params: List[Any] = []
        
        if state is not None:
            query += " AND state = ?"
            params.append(state.value)
        
        if session_id is not None:
            query += " AND session_id = ?"
            params.append(session_id)
        
        if workspace is not None:
            query += " AND workspace = ?"
            params.append(workspace)
        
        query += " ORDER BY priority DESC, created_at ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        with self._transaction() as conn:
            cursor = conn.execute(query, params)
            return [self._row_to_run(row) for row in cursor.fetchall()]
    
    def delete_run(self, run_id: str) -> bool:
        """Delete a run and its related data."""
        self.initialize()
        
        with self._transaction() as conn:
            # Delete related data first
            conn.execute("DELETE FROM messages WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM tool_calls WHERE run_id = ?", (run_id,))
            
            cursor = conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
            return cursor.rowcount > 0
    
    def update_run_state(
        self,
        run_id: str,
        state: RunState,
        error: Optional[str] = None,
        output: Optional[str] = None,
    ) -> bool:
        """Update run state."""
        self.initialize()
        
        updates = ["state = ?"]
        params: List[Any] = [state.value]
        
        if state == RunState.RUNNING:
            updates.append("started_at = ?")
            params.append(time.time())
        elif state.is_terminal():
            updates.append("ended_at = ?")
            params.append(time.time())
        
        if error is not None:
            updates.append("error = ?")
            params.append(error)
        
        if output is not None:
            updates.append("output_content = ?")
            params.append(output)
        
        params.append(run_id)
        
        with self._transaction() as conn:
            cursor = conn.execute(
                f"UPDATE runs SET {', '.join(updates)} WHERE run_id = ?",
                params
            )
            return cursor.rowcount > 0
    
    # Crash recovery
    
    def load_pending_runs(self) -> List[QueuedRun]:
        """Load runs that were QUEUED or RUNNING at crash."""
        self.initialize()
        
        with self._transaction() as conn:
            cursor = conn.execute("""
                SELECT * FROM runs 
                WHERE state IN ('queued', 'running')
                ORDER BY priority DESC, created_at ASC
            """)
            return [self._row_to_run(row) for row in cursor.fetchall()]
    
    def mark_recovered(self, run_id: str) -> None:
        """Mark a run as recovered after restart."""
        self.initialize()
        
        with self._transaction() as conn:
            conn.execute(
                "UPDATE runs SET recovered = 1 WHERE run_id = ?",
                (run_id,)
            )
    
    def mark_interrupted_as_failed(self) -> int:
        """Mark all RUNNING runs as FAILED (for crash recovery)."""
        self.initialize()
        
        with self._transaction() as conn:
            cursor = conn.execute("""
                UPDATE runs 
                SET state = 'failed', 
                    error = 'Interrupted by crash/restart',
                    ended_at = ?
                WHERE state = 'running'
            """, (time.time(),))
            return cursor.rowcount
    
    # Statistics
    
    def get_stats(self, session_id: Optional[str] = None) -> QueueStats:
        """Get queue statistics."""
        self.initialize()
        
        with self._transaction() as conn:
            where = ""
            params: List[Any] = []
            if session_id:
                where = "WHERE session_id = ?"
                params = [session_id]
            
            # Count by state
            cursor = conn.execute(f"""
                SELECT state, COUNT(*) as count
                FROM runs {where}
                GROUP BY state
            """, params)
            
            counts = {row["state"]: row["count"] for row in cursor.fetchall()}
            
            # Average wait time
            cursor = conn.execute(f"""
                SELECT AVG(started_at - created_at) as avg_wait
                FROM runs
                {where + ' AND' if where else 'WHERE'} started_at IS NOT NULL
            """, params)
            row = cursor.fetchone()
            avg_wait = row["avg_wait"] or 0.0
            
            # Average duration
            cursor = conn.execute(f"""
                SELECT AVG(ended_at - started_at) as avg_duration
                FROM runs
                {where + ' AND' if where else 'WHERE'} ended_at IS NOT NULL AND started_at IS NOT NULL
            """, params)
            row = cursor.fetchone()
            avg_duration = row["avg_duration"] or 0.0
            
            return QueueStats(
                queued_count=counts.get("queued", 0),
                running_count=counts.get("running", 0),
                succeeded_count=counts.get("succeeded", 0),
                failed_count=counts.get("failed", 0),
                cancelled_count=counts.get("cancelled", 0),
                total_runs=sum(counts.values()),
                avg_wait_seconds=avg_wait,
                avg_duration_seconds=avg_duration,
            )
    
    # Session operations
    
    def save_session(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        state: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Save or update a session."""
        self.initialize()
        
        now = time.time()
        
        with self._transaction() as conn:
            # Check if exists
            cursor = conn.execute(
                "SELECT session_id FROM sessions WHERE session_id = ?",
                (session_id,)
            )
            exists = cursor.fetchone() is not None
            
            if exists:
                conn.execute("""
                    UPDATE sessions SET
                        user_id = COALESCE(?, user_id),
                        updated_at = ?,
                        state = COALESCE(?, state),
                        config = COALESCE(?, config)
                    WHERE session_id = ?
                """, (
                    user_id,
                    now,
                    json.dumps(state) if state else None,
                    json.dumps(config) if config else None,
                    session_id,
                ))
            else:
                conn.execute("""
                    INSERT INTO sessions (session_id, user_id, created_at, updated_at, state, config)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    session_id,
                    user_id,
                    now,
                    now,
                    json.dumps(state) if state else None,
                    json.dumps(config) if config else None,
                ))
    
    def load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load a session."""
        self.initialize()
        
        with self._transaction() as conn:
            cursor = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,)
            )
            row = cursor.fetchone()
            
            if row is None:
                return None
            
            return {
                "session_id": row["session_id"],
                "user_id": row["user_id"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "state": json.loads(row["state"]) if row["state"] else None,
                "config": json.loads(row["config"]) if row["config"] else None,
            }
    
    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List recent sessions."""
        self.initialize()
        
        with self._transaction() as conn:
            cursor = conn.execute("""
                SELECT * FROM sessions
                ORDER BY updated_at DESC
                LIMIT ?
            """, (limit,))
            
            return [
                {
                    "session_id": row["session_id"],
                    "user_id": row["user_id"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "state": json.loads(row["state"]) if row["state"] else None,
                    "config": json.loads(row["config"]) if row["config"] else None,
                }
                for row in cursor.fetchall()
            ]
    
    # Helper methods
    
    def _row_to_run(self, row: sqlite3.Row) -> QueuedRun:
        """Convert database row to QueuedRun."""
        return QueuedRun(
            run_id=row["run_id"],
            agent_name=row["agent_name"],
            input_content=row["input_content"] or "",
            output_content=row["output_content"],
            state=RunState(row["state"]),
            priority=RunPriority(row["priority"]),
            session_id=row["session_id"],
            trace_id=row["trace_id"],
            workspace=row["workspace"],
            user_id=row["user_id"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            error=row["error"],
            retry_count=row["retry_count"] or 0,
            max_retries=row["max_retries"] or 3,
            parent_run_id=row["parent_run_id"],
            config=json.loads(row["config"]) if row["config"] else {},
            metrics=json.loads(row["metrics"]) if row["metrics"] else {},
        )
    
    # Cleanup
    
    def cleanup_old_runs(self, days: int = 30) -> int:
        """Delete runs older than specified days."""
        self.initialize()
        
        cutoff = time.time() - (days * 24 * 60 * 60)
        
        with self._transaction() as conn:
            # Get run IDs to delete
            cursor = conn.execute("""
                SELECT run_id FROM runs
                WHERE created_at < ? AND state IN ('succeeded', 'failed', 'cancelled')
            """, (cutoff,))
            run_ids = [row["run_id"] for row in cursor.fetchall()]
            
            if not run_ids:
                return 0
            
            placeholders = ",".join("?" * len(run_ids))
            
            # Delete related data
            conn.execute(
                f"DELETE FROM messages WHERE run_id IN ({placeholders})",
                run_ids
            )
            conn.execute(
                f"DELETE FROM tool_calls WHERE run_id IN ({placeholders})",
                run_ids
            )
            
            # Delete runs
            cursor = conn.execute(
                f"DELETE FROM runs WHERE run_id IN ({placeholders})",
                run_ids
            )
            
            return cursor.rowcount
