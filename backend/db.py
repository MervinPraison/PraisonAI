"""SQLite persistence for AgentOS agents and chat history."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, Iterator, List, Optional

BASE_DIR = os.path.dirname(__file__)
DB_FILE = os.environ.get("AGENTOS_DB", os.path.join(BASE_DIR, "agentos.db"))
LEGACY_AGENTS_FILE = os.path.join(BASE_DIR, "agents_store.json")
LEGACY_HISTORY_FILE = os.path.join(BASE_DIR, "history_store.json")

ALLOWED_STATUS = {"active", "auditing", "decommissioned"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    instructions TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'auditing', 'decommissioned')),
    generation INTEGER NOT NULL DEFAULT 1,
    parent_id TEXT REFERENCES agents(id) ON DELETE SET NULL,
    performance_score REAL,
    token_spend INTEGER NOT NULL DEFAULT 0,
    exit_summary TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_history (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    user_message TEXT NOT NULL,
    agent_response TEXT NOT NULL,
    activity TEXT NOT NULL DEFAULT '[]',
    timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_history_agent_ts
    ON chat_history(agent_id, timestamp);
"""


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    # Timezone-aware UTC timestamp, ISO-8601 with trailing Z to match prior shape.
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _row_to_dict(row: sqlite3.Row) -> Dict:
    d = dict(row)
    # Legacy alias so existing frontend/clients that read `llm` still work.
    d["llm"] = d["model"]
    return d


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        cur = conn.execute("SELECT COUNT(*) FROM agents")
        if cur.fetchone()[0] == 0:
            _migrate_from_json(conn)
        cur = conn.execute("SELECT COUNT(*) FROM chat_history")
        if cur.fetchone()[0] == 0:
            _migrate_history_from_json(conn)


def _migrate_from_json(conn: sqlite3.Connection) -> None:
    if not os.path.exists(LEGACY_AGENTS_FILE):
        return
    try:
        with open(LEGACY_AGENTS_FILE) as f:
            legacy = json.load(f)
    except (OSError, json.JSONDecodeError):
        return
    for a in legacy:
        status = a.get("status", "active")
        if status not in ALLOWED_STATUS:
            status = "active"
        created = a.get("created_at") or _now()
        conn.execute(
            """
            INSERT OR IGNORE INTO agents
            (id, name, instructions, model, status, generation, parent_id,
             performance_score, token_spend, exit_summary, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 1, NULL, NULL, 0, NULL, ?, ?)
            """,
            (
                a["id"],
                a.get("name", "Unnamed"),
                a.get("instructions", ""),
                a.get("llm") or a.get("model") or "gpt-4o-mini",
                status,
                created,
                created,
            ),
        )


def _migrate_history_from_json(conn: sqlite3.Connection) -> None:
    if not os.path.exists(LEGACY_HISTORY_FILE):
        return
    try:
        with open(LEGACY_HISTORY_FILE) as f:
            legacy = json.load(f)
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(legacy, dict):
        return
    for agent_id, entries in legacy.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            conn.execute(
                """
                INSERT OR IGNORE INTO chat_history
                (id, agent_id, user_message, agent_response, activity, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.get("id") or os.urandom(4).hex(),
                    agent_id,
                    entry.get("user_message", ""),
                    entry.get("agent_response", ""),
                    json.dumps(entry.get("activity", [])),
                    entry.get("timestamp") or _now(),
                ),
            )


def list_agents() -> List[Dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM agents ORDER BY created_at ASC"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_agent(agent_id: str) -> Optional[Dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def create_agent(agent: Dict) -> Dict:
    now = _now()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO agents
            (id, name, instructions, model, status, generation, parent_id,
             performance_score, token_spend, exit_summary, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                agent["id"],
                agent["name"],
                agent.get("instructions", ""),
                agent["model"],
                agent.get("status", "active"),
                agent.get("generation", 1),
                agent.get("parent_id"),
                agent.get("performance_score"),
                agent.get("token_spend", 0),
                agent.get("exit_summary"),
                now,
                now,
            ),
        )
    return get_agent(agent["id"])  # type: ignore[return-value]


UPDATABLE_FIELDS = {
    "name",
    "instructions",
    "model",
    "status",
    "generation",
    "parent_id",
    "performance_score",
    "token_spend",
    "exit_summary",
}


def update_agent(agent_id: str, fields: Dict) -> Optional[Dict]:
    sets = {k: v for k, v in fields.items() if k in UPDATABLE_FIELDS}
    if not sets:
        return get_agent(agent_id)
    columns = ", ".join(f"{k} = ?" for k in sets) + ", updated_at = ?"
    values = list(sets.values()) + [_now(), agent_id]
    with get_conn() as conn:
        cur = conn.execute(
            f"UPDATE agents SET {columns} WHERE id = ?", values
        )
        if cur.rowcount == 0:
            return None
    return get_agent(agent_id)


def delete_agent(agent_id: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
        return cur.rowcount > 0


# ----- chat history --------------------------------------------------------


def _row_to_history(row: sqlite3.Row) -> Dict:
    d = dict(row)
    try:
        d["activity"] = json.loads(d.get("activity") or "[]")
    except json.JSONDecodeError:
        d["activity"] = []
    d.pop("agent_id", None)
    return d


def add_history_entry(agent_id: str, entry: Dict) -> Dict:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO chat_history
            (id, agent_id, user_message, agent_response, activity, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                entry["id"],
                agent_id,
                entry["user_message"],
                entry["agent_response"],
                json.dumps(entry.get("activity", [])),
                entry["timestamp"],
            ),
        )
    return entry


def list_history(agent_id: str) -> List[Dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM chat_history WHERE agent_id = ? ORDER BY timestamp ASC",
            (agent_id,),
        ).fetchall()
    return [_row_to_history(r) for r in rows]


def clear_history(agent_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM chat_history WHERE agent_id = ?", (agent_id,))


def list_activity(agent_id: str, limit: int = 100) -> List[Dict]:
    """Flattened activity across all of an agent's chat entries, newest first, capped."""
    entries = list_history(agent_id)
    activity: List[Dict] = []
    for entry in reversed(entries):
        activity.extend(entry.get("activity", []))
        if len(activity) >= limit:
            break
    return activity[:limit]
