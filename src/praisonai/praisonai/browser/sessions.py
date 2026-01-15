"""Session Manager for browser automation sessions.

Provides persistence for browser automation sessions using SQLite.
"""

import os
import json
import sqlite3
import time
import uuid
import threading
from typing import List, Optional, Dict, Any
from contextlib import contextmanager


class SessionManager:
    """Manages browser automation sessions with SQLite persistence.
    
    Thread-safe session management for multi-agent scenarios.
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize session manager.
        
        Args:
            db_path: Path to SQLite database. Defaults to ~/.praisonai/browser_sessions.db
        """
        if db_path is None:
            home = os.path.expanduser("~")
            praisonai_dir = os.path.join(home, ".praisonai")
            os.makedirs(praisonai_dir, exist_ok=True)
            db_path = os.path.join(praisonai_dir, "browser_sessions.db")
        
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, "connection") or self._local.connection is None:
            self._local.connection = sqlite3.connect(self.db_path)
            self._local.connection.row_factory = sqlite3.Row
        return self._local.connection
    
    @contextmanager
    def _db(self):
        """Context manager for database operations."""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    
    def _init_db(self):
        """Initialize database schema."""
        with self._db() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    status TEXT DEFAULT 'running',
                    current_url TEXT DEFAULT '',
                    started_at REAL NOT NULL,
                    ended_at REAL,
                    error TEXT,
                    metadata TEXT DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    step_number INTEGER NOT NULL,
                    observation TEXT,
                    action TEXT,
                    thought TEXT DEFAULT '',
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_steps_session 
                ON steps(session_id, step_number)
            """)
    
    def create_session(self, goal: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create a new browser session.
        
        Args:
            goal: The automation goal
            metadata: Optional metadata dict
            
        Returns:
            Session dict with session_id
        """
        session_id = str(uuid.uuid4())
        started_at = time.time()
        
        with self._db() as conn:
            conn.execute(
                """
                INSERT INTO sessions (session_id, goal, status, started_at, metadata)
                VALUES (?, ?, 'running', ?, ?)
                """,
                (session_id, goal, started_at, json.dumps(metadata or {}))
            )
        
        return {
            "session_id": session_id,
            "goal": goal,
            "status": "running",
            "current_url": "",
            "started_at": started_at,
            "ended_at": None,
            "error": None,
            "steps": [],
        }
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session by ID.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Session dict or None if not found
        """
        with self._db() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,)
            ).fetchone()
            
            if row is None:
                return None
            
            # Get steps
            steps = conn.execute(
                """
                SELECT step_number, observation, action, thought, timestamp
                FROM steps WHERE session_id = ? ORDER BY step_number
                """,
                (session_id,)
            ).fetchall()
            
            return {
                "session_id": row["session_id"],
                "goal": row["goal"],
                "status": row["status"],
                "current_url": row["current_url"],
                "started_at": row["started_at"],
                "ended_at": row["ended_at"],
                "error": row["error"],
                "steps": [
                    {
                        "step_number": s["step_number"],
                        "observation": json.loads(s["observation"]) if s["observation"] else None,
                        "action": json.loads(s["action"]) if s["action"] else None,
                        "thought": s["thought"],
                        "timestamp": s["timestamp"],
                    }
                    for s in steps
                ],
            }
    
    def update_session(
        self,
        session_id: str,
        status: Optional[str] = None,
        current_url: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update session fields.
        
        Args:
            session_id: Session identifier
            status: New status
            current_url: Current page URL
            error: Error message if failed
        """
        updates = []
        params = []
        
        if status is not None:
            updates.append("status = ?")
            params.append(status)
            if status in ("completed", "failed", "stopped"):
                updates.append("ended_at = ?")
                params.append(time.time())
        
        if current_url is not None:
            updates.append("current_url = ?")
            params.append(current_url)
        
        if error is not None:
            updates.append("error = ?")
            params.append(error)
        
        if not updates:
            return
        
        params.append(session_id)
        
        with self._db() as conn:
            conn.execute(
                f"UPDATE sessions SET {', '.join(updates)} WHERE session_id = ?",
                params
            )
    
    def add_step(
        self,
        session_id: str,
        step_number: int,
        observation: Optional[Dict[str, Any]] = None,
        action: Optional[Dict[str, Any]] = None,
        thought: str = "",
    ) -> None:
        """Add a step to session history.
        
        Args:
            session_id: Session identifier
            step_number: Step number (1-indexed)
            observation: Observation dict
            action: Action dict
            thought: Agent's reasoning
        """
        with self._db() as conn:
            conn.execute(
                """
                INSERT INTO steps (session_id, step_number, observation, action, thought, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    step_number,
                    json.dumps(observation) if observation else None,
                    json.dumps(action) if action else None,
                    thought,
                    time.time(),
                )
            )
    
    def list_sessions(
        self,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List sessions with optional filtering.
        
        Args:
            status: Filter by status
            limit: Maximum number of sessions to return
            
        Returns:
            List of session dicts (without full steps)
        """
        with self._db() as conn:
            if status:
                rows = conn.execute(
                    """
                    SELECT * FROM sessions 
                    WHERE status = ?
                    ORDER BY started_at DESC LIMIT ?
                    """,
                    (status, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM sessions 
                    ORDER BY started_at DESC LIMIT ?
                    """,
                    (limit,)
                ).fetchall()
            
            return [
                {
                    "session_id": row["session_id"],
                    "goal": row["goal"],
                    "status": row["status"],
                    "current_url": row["current_url"],
                    "started_at": row["started_at"],
                    "ended_at": row["ended_at"],
                    "error": row["error"],
                }
                for row in rows
            ]
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session and its steps.
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if deleted, False if not found
        """
        with self._db() as conn:
            # Delete steps first
            conn.execute("DELETE FROM steps WHERE session_id = ?", (session_id,))
            
            # Delete session
            cursor = conn.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,)
            )
            return cursor.rowcount > 0
    
    def close(self):
        """Close database connection."""
        if hasattr(self._local, "connection") and self._local.connection:
            self._local.connection.close()
            self._local.connection = None
