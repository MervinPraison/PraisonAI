"""
Durable run-state journal for resumable agent execution.

The existing stores persist three *unlinked* things:

* workspace **files** — ``checkpoints/`` (shadow-git), ``snapshot/``;
* finished **conversation messages** — ``session/store.py``;

but **nothing persists the execution cursor of a run** — the loop iteration
index, the pending/in-flight tool calls, or the partial assistant turn. So if
the process dies mid tool-loop, the run cannot resume where it left off and any
in-flight tool work is lost (or, worse, re-run on a naive retry).

This module adds the missing piece: a tiny append-only journal, keyed by a
``run_id``, that records an event at every meaningful boundary (model decision,
tool call, tool result, iteration index, approval decision). On resume, the loop
is re-driven from the top and journalled steps return their **recorded** results
instantly — no re-execution of side-effecting tools and no re-billing of LLM
calls — while real work restarts at the first un-journalled step.

Design notes
------------
* Reuses the zero-dependency stdlib ``sqlite3`` persistence pattern already used
  by :mod:`praisonaiagents.runs.sqlite_ledger` and :mod:`praisonaiagents.session`
  (WAL, ``busy_timeout``, a single re-entrant-lock-guarded shared connection).
* **Default-off / zero-overhead:** nothing writes to the journal unless a run
  opts in (e.g. ``Agent(..., durable=True)``). This module is lazy-imported from
  :mod:`praisonaiagents.runtime`, so importing the package stays cheap.
* Complements — does not replace — :mod:`praisonaiagents.runs`, which tracks run
  *status* (queued/running/…); this tracks the per-event *cursor*.

Usage::

    from praisonaiagents.runtime import RunJournal, JournalEvent

    j = RunJournal(":memory:")
    j.open_run("r1", agent="coder", task="migrate module")

    # ── record each boundary as it happens ──
    seq = 0
    j.append(JournalEvent("r1", seq, "model_decision", {"text": "call tool X"}))

    # ── on resume, memoise recorded steps ──
    replay = j.replay_index("r1")            # {(seq, kind): payload}
    if (rec := replay.get((seq, "model_decision"))) is not None:
        resp = rec                            # cached — do NOT re-call the model

    j.close_run("r1", "succeeded")
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .._logging import get_logger

logger = get_logger(__name__)

__all__ = ["JournalEvent", "RunMeta", "RunJournal"]


# ── event kinds ────────────────────────────────────────────────────────────
#: A model response used for a decision (memoised so replay does not re-call
#: — and re-bill — the LLM).
KIND_MODEL_DECISION = "model_decision"
#: A tool call issued: ``{"name", "args", "idempotency_key"}``.
KIND_TOOL_CALL = "tool_call"
#: A tool result received (memoised so replay does not re-run a side-effecting
#: tool).
KIND_TOOL_RESULT = "tool_result"
#: A human/policy approval decision (enables durable pause-for-approval HITL).
KIND_APPROVAL = "approval"
#: The loop iteration index, journalled so the cursor is restored exactly.
KIND_ITERATION = "iteration"

VALID_KINDS = frozenset(
    {
        KIND_MODEL_DECISION,
        KIND_TOOL_CALL,
        KIND_TOOL_RESULT,
        KIND_APPROVAL,
        KIND_ITERATION,
    }
)

_STATUS_RUNNING = "running"
_TERMINAL_STATUSES = frozenset({"done", "succeeded", "failed", "cancelled"})


_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    agent TEXT NOT NULL DEFAULT '',
    task TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'running',
    outcome TEXT,
    checkpoint_id TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    metadata TEXT
);
CREATE TABLE IF NOT EXISTS journal (
    run_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (run_id, seq, kind)
);
CREATE INDEX IF NOT EXISTS idx_journal_run ON journal(run_id, seq);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
"""


@dataclass
class JournalEvent:
    """A single append-only journal event.

    ``(run_id, seq, kind)`` is the natural key: a step number ``seq`` produces
    at most one event of each ``kind`` (e.g. a tool step has one
    ``tool_call`` and one ``tool_result``). ``payload`` is any JSON-serialisable
    dict — the decision text, ``{name, args, idempotency_key}``, the tool
    result, the approval decision, or ``{index}``.
    """

    run_id: str
    seq: int
    kind: str
    payload: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class RunMeta:
    """Durable metadata that binds the three stores under one ``run_id``.

    ``checkpoint_id`` links to the files store (``checkpoints/``) so a resume
    can restore the workspace to the last checkpoint before replaying.
    """

    run_id: str
    agent: str = ""
    task: str = ""
    status: str = _STATUS_RUNNING
    outcome: Optional[str] = None
    checkpoint_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


def _dump(value: Any) -> str:
    """Serialise ``value`` to JSON, never failing on non-JSON-native values."""
    try:
        return json.dumps(value)
    except (TypeError, ValueError):
        return json.dumps(value, default=str)


class RunJournal:
    """Append-only, restart-safe run-state journal backed by SQLite.

    Thread-safe: a single re-entrant lock guards a shared connection opened with
    ``check_same_thread=False``, mirroring :class:`~praisonaiagents.runs.
    sqlite_ledger.SQLiteRunLedger`.

    Args:
        db_path: Path to the SQLite database file. Defaults to
            ``~/.praisonai/runs/journal.db``. Use ``":memory:"`` for tests.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            from ..paths import get_runs_dir

            runs_dir = get_runs_dir()
            os.makedirs(runs_dir, exist_ok=True)
            db_path = str(runs_dir / "journal.db")
        elif db_path != ":memory:":
            parent = os.path.dirname(db_path)
            if parent:
                os.makedirs(parent, exist_ok=True)

        self._db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            db_path, check_same_thread=False, isolation_level=None
        )
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA busy_timeout = 5000")
            if db_path != ":memory:":
                try:
                    self._conn.execute("PRAGMA journal_mode = WAL")
                    self._conn.execute("PRAGMA synchronous = NORMAL")
                except sqlite3.OperationalError:  # pragma: no cover - defensive
                    pass
            self._conn.executescript(_SCHEMA)

    # ── run lifecycle ─────────────────────────────────────────────────

    def open_run(
        self,
        run_id: str,
        *,
        agent: str = "",
        task: str = "",
        checkpoint_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register ``run_id`` as ``running`` (idempotent).

        Re-opening an existing run (e.g. on resume) preserves its journal and
        keeps status ``running`` without clobbering ``created_at``. A newly
        supplied ``checkpoint_id`` is bound on reopen (so a run that crashed
        before ``set_checkpoint`` can still resume from a caller-supplied
        checkpoint); a ``None`` reopen preserves any existing binding.
        """
        now = time.time()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO runs (
                    run_id, agent, task, status, outcome, checkpoint_id,
                    created_at, updated_at, metadata
                ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status='running',
                    checkpoint_id=COALESCE(excluded.checkpoint_id, checkpoint_id),
                    updated_at=excluded.updated_at
                """,
                (
                    run_id,
                    agent,
                    task,
                    _STATUS_RUNNING,
                    checkpoint_id,
                    now,
                    now,
                    _dump(metadata or {}),
                ),
            )

    def set_checkpoint(self, run_id: str, checkpoint_id: str) -> None:
        """Bind the latest files checkpoint to ``run_id`` for resume."""
        with self._lock:
            self._conn.execute(
                "UPDATE runs SET checkpoint_id = ?, updated_at = ? "
                "WHERE run_id = ?",
                (checkpoint_id, time.time(), run_id),
            )

    def close_run(self, run_id: str, outcome: str = "done") -> None:
        """Mark ``run_id`` terminal so it is no longer resumed on restart."""
        status = outcome if outcome in _TERMINAL_STATUSES else "done"
        with self._lock:
            self._conn.execute(
                "UPDATE runs SET status = ?, outcome = ?, updated_at = ? "
                "WHERE run_id = ?",
                (status, outcome, time.time(), run_id),
            )

    def run_meta(self, run_id: str) -> Optional[RunMeta]:
        """Return the :class:`RunMeta` for ``run_id`` or ``None`` if unknown."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            return None
        try:
            metadata = json.loads(row["metadata"]) if row["metadata"] else {}
        except (ValueError, TypeError):
            metadata = {}
        return RunMeta(
            run_id=row["run_id"],
            agent=row["agent"] or "",
            task=row["task"] or "",
            status=row["status"],
            outcome=row["outcome"],
            checkpoint_id=row["checkpoint_id"],
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
            metadata=metadata,
        )

    def interrupted_runs(self) -> List[str]:
        """Return ids of runs still ``running`` — resume candidates on restart.

        A run left ``running`` belonged to a process that exited without
        recording a terminal outcome; the gateway resumes each on boot.
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT run_id FROM runs WHERE status = ? "
                "ORDER BY created_at ASC",
                (_STATUS_RUNNING,),
            ).fetchall()
        return [r["run_id"] for r in rows]

    # ── journal append / read ─────────────────────────────────────────

    def append(self, ev: JournalEvent) -> None:
        """Append ``ev`` to the journal (idempotent on ``run_id/seq/kind``).

        Re-appending the same ``(run_id, seq, kind)`` — which happens if a
        replayed step is (harmlessly) re-journalled — updates the payload
        rather than raising, keeping the journal the single source of truth.
        """
        if ev.kind not in VALID_KINDS:
            raise ValueError(
                f"unknown journal event kind {ev.kind!r}; "
                f"expected one of {sorted(VALID_KINDS)}"
            )
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO journal (run_id, seq, kind, payload, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id, seq, kind) DO UPDATE SET
                    payload=excluded.payload,
                    created_at=excluded.created_at
                """,
                (ev.run_id, int(ev.seq), ev.kind, _dump(ev.payload), ev.created_at),
            )

    def events(self, run_id: str) -> List[JournalEvent]:
        """Return all journal events for ``run_id`` ordered by ``(seq, kind)``.

        Ordering by ``(seq, rowid)`` preserves append order within a step so a
        ``tool_call`` always precedes its ``tool_result``.
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT run_id, seq, kind, payload, created_at FROM journal "
                "WHERE run_id = ? ORDER BY seq ASC, rowid ASC",
                (run_id,),
            ).fetchall()
        out: List[JournalEvent] = []
        for r in rows:
            try:
                payload = json.loads(r["payload"]) if r["payload"] else {}
            except (ValueError, TypeError):
                payload = {}
            out.append(
                JournalEvent(
                    run_id=r["run_id"],
                    seq=int(r["seq"]),
                    kind=r["kind"],
                    payload=payload,
                    created_at=float(r["created_at"]),
                )
            )
        return out

    def replay_index(self, run_id: str) -> Dict[tuple, Dict[str, Any]]:
        """Return a ``{(seq, kind): payload}`` lookup for memoised replay.

        The loop consults this during replay: a hit returns the recorded result
        instantly (no re-execution); a miss means real work restarts there.
        """
        return {(ev.seq, ev.kind): ev.payload for ev in self.events(run_id)}

    def last_iteration(self, run_id: str) -> Optional[int]:
        """Return the highest journalled iteration index, or ``None``.

        Used to restore the loop cursor exactly on resume.
        """
        idx: Optional[int] = None
        for ev in self.events(run_id):
            if ev.kind == KIND_ITERATION:
                try:
                    idx = int(ev.payload.get("index"))
                except (TypeError, ValueError):
                    continue
        return idx

    def assert_replay_order(
        self, run_id: str, expected: List[Any]
    ) -> None:
        """Determinism guardrail: fail loud if replay diverges from the journal.

        During replay the loop must reproduce the recorded sequence of steps.
        Because the memoised :meth:`replay_index` lookup is keyed by
        ``(seq, kind)``, this guard compares the full ``(seq, kind)`` sequence —
        not just the bare kinds — so a replay that reproduces the same *shape*
        at different ``seq`` values (a divergent step order) still fails loud
        rather than silently reusing or skipping the wrong recorded step.

        Args:
            run_id: The run being replayed.
            expected: The steps the replay produced, as either ``(seq, kind)``
                tuples (preferred, position-aware) or bare ``kind`` strings
                (compared against the recorded kinds for backward
                compatibility).
        """
        recorded_events = self.events(run_id)
        expected_list = list(expected)
        # Position-aware comparison when the caller supplies (seq, kind) tuples;
        # fall back to kind-only comparison for the simpler string form.
        if expected_list and not isinstance(expected_list[0], str):
            recorded: List[Any] = [(ev.seq, ev.kind) for ev in recorded_events]
            expected_norm: List[Any] = [tuple(e) for e in expected_list]
        else:
            recorded = [ev.kind for ev in recorded_events]
            expected_norm = expected_list
        if recorded != expected_norm:
            raise RuntimeError(
                f"replay divergence for run {run_id!r}: journal recorded "
                f"{recorded!r} but replay produced {expected_norm!r}"
            )

    def close(self) -> None:
        """Close the underlying database connection."""
        with self._lock:
            try:
                self._conn.close()
            except Exception:  # pragma: no cover - defensive
                pass
