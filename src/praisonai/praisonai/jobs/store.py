"""
Job Store for PraisonAI Async Jobs API.

Provides storage backends for job state persistence.
"""

import asyncio
import logging
import threading
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from .models import Job, JobStatus

logger = logging.getLogger(__name__)


class JobStore(ABC):
    """Abstract base class for job storage backends."""
    
    @abstractmethod
    async def save(self, job: Job) -> None:
        """Save or update a job."""
        pass
    
    @abstractmethod
    async def get(self, job_id: str) -> Optional[Job]:
        """Get a job by ID."""
        pass
    
    @abstractmethod
    async def get_by_idempotency_key(self, key: str) -> Optional[Job]:
        """Get a job by idempotency key."""
        pass
    
    @abstractmethod
    async def list_jobs(
        self,
        status: Optional[JobStatus] = None,
        session_id: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[Job]:
        """List jobs with optional filters."""
        pass
    
    @abstractmethod
    async def count(
        self,
        status: Optional[JobStatus] = None,
        session_id: Optional[str] = None
    ) -> int:
        """Count jobs matching filters."""
        pass
    
    @abstractmethod
    async def delete(self, job_id: str) -> bool:
        """Delete a job by ID."""
        pass
    
    @abstractmethod
    async def cleanup_old_jobs(self, max_age_seconds: int = 86400) -> int:
        """Remove jobs older than max_age_seconds. Returns count deleted."""
        pass

    async def save_if_absent(self, job: Job) -> Job:
        """Insert ``job`` unless one with the same idempotency key already exists.

        Returns the effective job (the newly saved one, or the pre-existing
        winner of a concurrent submit). The default is a best-effort
        check-then-save; backends with a native uniqueness guarantee (e.g.
        :class:`SqliteJobStore`) override this to be truly atomic.
        """
        if job.idempotency_key:
            existing = await self.get_by_idempotency_key(job.idempotency_key)
            if existing:
                return existing
        await self.save(job)
        return job


class InMemoryJobStore(JobStore):
    """
    In-memory job store.
    
    Suitable for development and single-process deployments.
    Jobs are lost on restart.
    """
    
    def __init__(self, max_jobs: int = 1000):
        self._jobs: Dict[str, Job] = {}
        self._idempotency_keys: Dict[str, str] = {}  # key -> job_id
        self._max_jobs = max_jobs
        # Note: asyncio.Lock() is created lazily via _get_lock() to support
        # Python 3.9 where Lock() requires an event loop at creation time.
        self.__lock: Optional[asyncio.Lock] = None
    
    def _get_lock(self) -> asyncio.Lock:
        """Get the asyncio lock, creating it lazily if needed.
        
        Deferred creation avoids touching the event loop at __init__ time,
        which keeps the store safe to instantiate from sync contexts on
        Python 3.9 (where asyncio.Lock() implicitly calls get_event_loop()).
        """
        if self.__lock is None:
            self.__lock = asyncio.Lock()
        return self.__lock
    
    async def save(self, job: Job) -> None:
        """Save or update a job."""
        async with self._get_lock():
            self._jobs[job.id] = job
            
            # Track idempotency key
            if job.idempotency_key:
                self._idempotency_keys[job.idempotency_key] = job.id
            
            # Enforce max jobs limit by removing oldest completed
            if len(self._jobs) > self._max_jobs:
                await self._evict_oldest_completed()
    
    async def _evict_oldest_completed(self) -> None:
        """Remove oldest completed jobs to stay under limit."""
        completed = [
            (job_id, job) for job_id, job in self._jobs.items()
            if job.is_terminal
        ]
        
        if not completed:
            return
        
        # Sort by completed_at, oldest first
        completed.sort(key=lambda x: x[1].completed_at or datetime.min)
        
        # Remove oldest 10%
        to_remove = max(1, len(completed) // 10)
        for job_id, job in completed[:to_remove]:
            del self._jobs[job_id]
            if job.idempotency_key:
                self._idempotency_keys.pop(job.idempotency_key, None)
    
    async def get(self, job_id: str) -> Optional[Job]:
        """Get a job by ID."""
        async with self._get_lock():
            return self._jobs.get(job_id)
    
    async def get_by_idempotency_key(self, key: str) -> Optional[Job]:
        """Get a job by idempotency key."""
        async with self._get_lock():
            job_id = self._idempotency_keys.get(key)
            return self._jobs.get(job_id) if job_id else None
    
    async def list_jobs(
        self,
        status: Optional[JobStatus] = None,
        session_id: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[Job]:
        """List jobs with optional filters."""
        async with self._get_lock():
            jobs = list(self._jobs.values())
        
        # Apply filters outside the lock - values() snapshot is already taken
        if status:
            jobs = [j for j in jobs if j.status == status]
        if session_id:
            jobs = [j for j in jobs if j.session_id == session_id]
        
        # Sort by created_at descending (newest first)
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        
        # Apply pagination
        return jobs[offset:offset + limit]
    
    async def count(
        self,
        status: Optional[JobStatus] = None,
        session_id: Optional[str] = None
    ) -> int:
        """Count jobs matching filters."""
        async with self._get_lock():
            jobs = list(self._jobs.values())
        
        if status:
            jobs = [j for j in jobs if j.status == status]
        if session_id:
            jobs = [j for j in jobs if j.session_id == session_id]
        
        return len(jobs)
    
    async def delete(self, job_id: str) -> bool:
        """Delete a job by ID."""
        async with self._get_lock():
            job = self._jobs.pop(job_id, None)
            if job:
                if job.idempotency_key:
                    self._idempotency_keys.pop(job.idempotency_key, None)
                return True
            return False
    
    async def cleanup_old_jobs(self, max_age_seconds: int = 86400) -> int:
        """Remove jobs older than max_age_seconds."""
        async with self._get_lock():
            cutoff = datetime.utcnow() - timedelta(seconds=max_age_seconds)
            to_remove = []
            
            for job_id, job in self._jobs.items():
                if job.is_terminal and job.completed_at and job.completed_at < cutoff:
                    to_remove.append(job_id)
            
            for job_id in to_remove:
                job = self._jobs.pop(job_id)
                if job.idempotency_key:
                    self._idempotency_keys.pop(job.idempotency_key, None)
            
            if to_remove:
                logger.info(f"Cleaned up {len(to_remove)} old jobs")
            
            return len(to_remove)
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get store statistics."""
        async with self._get_lock():
            # Take a snapshot to avoid RuntimeError if the dict is mutated concurrently
            jobs_snapshot = list(self._jobs.values())
            idempotency_count = len(self._idempotency_keys)
        
        status_counts = {}
        for job in jobs_snapshot:
            status_counts[job.status.value] = status_counts.get(job.status.value, 0) + 1
        
        return {
            "total_jobs": len(jobs_snapshot),
            "idempotency_keys": idempotency_count,
            "max_jobs": self._max_jobs,
            "status_counts": status_counts
        }


class SqliteJobStore(JobStore):
    """Persistent job store backed by stdlib ``sqlite3``.

    Survives process restarts so in-flight job state and idempotency keys are
    NOT lost, closing the "restart duplicates side-effects" gap of the
    in-memory store. Uses only the standard library (no new dependencies),
    keeping the wrapper lightweight. Blocking sqlite calls run off the event
    loop via ``asyncio.to_thread`` so the executor loop is never parked.
    """

    def __init__(self, path: str = "praisonai_jobs.db"):
        import sqlite3

        self._path = path
        # check_same_thread=False + a lock lets us reuse one connection across
        # the thread-pool workers to_thread hands us.
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                session_id TEXT,
                idempotency_key TEXT,
                created_at TEXT,
                completed_at TEXT,
                data TEXT NOT NULL
            )
            """
        )
        # UNIQUE (not just an index) so two concurrent requests carrying the
        # same idempotency key cannot both INSERT distinct job ids — the second
        # INSERT raises IntegrityError, which save_if_absent() turns into a
        # "return the winner" so external side-effects run exactly once. NULLs
        # are exempt from UNIQUE in sqlite, so keyless jobs are unaffected.
        self._conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_idempotency "
            "ON jobs(idempotency_key)"
        )
        self._conn.commit()
        self._lock = threading.Lock()
        # Reconcile jobs that were still QUEUED/RUNNING when the previous
        # process died: with no executor to resume them they would poll forever
        # and pin their idempotency key to a job that can never complete. Mark
        # them FAILED terminally so callers (and idempotent retries) get a
        # definitive outcome instead of hanging.
        self._reconcile_interrupted_jobs()

    def _reconcile_interrupted_jobs(self) -> None:
        import sqlite3

        nonterminal = (JobStatus.QUEUED.value, JobStatus.RUNNING.value)
        placeholders = ",".join("?" for _ in nonterminal)
        now = datetime.utcnow().isoformat()
        try:
            with self._lock:
                rows = self._conn.execute(
                    f"SELECT data FROM jobs WHERE status IN ({placeholders})",
                    nonterminal,
                ).fetchall()
                for (data,) in rows:
                    job = self._row_to_job(data)
                    job.status = JobStatus.FAILED
                    if job.error is None:
                        job.error = "Interrupted by service restart"
                    if job.completed_at is None:
                        job.completed_at = datetime.utcnow()
                    self._conn.execute(
                        "UPDATE jobs SET status = ?, completed_at = ?, data = ? "
                        "WHERE id = ?",
                        (job.status.value, now, job.model_dump_json(), job.id),
                    )
                self._conn.commit()
            if rows:
                logger.warning(
                    "Reconciled %d interrupted job(s) to FAILED after restart",
                    len(rows),
                )
        except sqlite3.Error as exc:  # pragma: no cover - defensive
            logger.error("Failed to reconcile interrupted jobs: %s", exc)

    def _row_to_job(self, data: str) -> Job:
        return Job.model_validate_json(data)

    async def save(self, job: Job) -> None:
        def _save():
            with self._lock:
                self._conn.execute(
                    "INSERT OR REPLACE INTO jobs "
                    "(id, status, session_id, idempotency_key, created_at, completed_at, data) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        job.id,
                        job.status.value,
                        job.session_id,
                        job.idempotency_key,
                        job.created_at.isoformat() if job.created_at else None,
                        job.completed_at.isoformat() if job.completed_at else None,
                        job.model_dump_json(),
                    ),
                )
                self._conn.commit()

        await asyncio.to_thread(_save)

    async def save_if_absent(self, job: Job) -> Job:
        """Atomically insert ``job`` unless its idempotency key already exists.

        Returns the job that "won" the race: the newly inserted ``job`` when this
        caller committed first, or the pre-existing job with the same key when a
        concurrent caller beat it. This closes the check-then-insert race the
        plain get→save path leaves open, so an idempotency-keyed side effect can
        only ever be created once even under concurrent submits. Jobs without an
        idempotency key fall back to a normal insert.
        """
        import sqlite3

        def _save_if_absent() -> Job:
            with self._lock:
                try:
                    self._conn.execute(
                        "INSERT INTO jobs "
                        "(id, status, session_id, idempotency_key, created_at, completed_at, data) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            job.id,
                            job.status.value,
                            job.session_id,
                            job.idempotency_key,
                            job.created_at.isoformat() if job.created_at else None,
                            job.completed_at.isoformat() if job.completed_at else None,
                            job.model_dump_json(),
                        ),
                    )
                    self._conn.commit()
                    return job
                except sqlite3.IntegrityError:
                    # Lost the race (UNIQUE idempotency_key). Return the winner.
                    self._conn.rollback()
                    if job.idempotency_key:
                        cur = self._conn.execute(
                            "SELECT data FROM jobs WHERE idempotency_key = ? LIMIT 1",
                            (job.idempotency_key,),
                        )
                        row = cur.fetchone()
                        if row:
                            return self._row_to_job(row[0])
                    raise

        return await asyncio.to_thread(_save_if_absent)

    async def get(self, job_id: str) -> Optional[Job]:
        def _get():
            with self._lock:
                cur = self._conn.execute(
                    "SELECT data FROM jobs WHERE id = ?", (job_id,)
                )
                row = cur.fetchone()
            return self._row_to_job(row[0]) if row else None

        return await asyncio.to_thread(_get)

    async def get_by_idempotency_key(self, key: str) -> Optional[Job]:
        def _get():
            with self._lock:
                cur = self._conn.execute(
                    "SELECT data FROM jobs WHERE idempotency_key = ? "
                    "ORDER BY created_at DESC LIMIT 1",
                    (key,),
                )
                row = cur.fetchone()
            return self._row_to_job(row[0]) if row else None

        return await asyncio.to_thread(_get)

    async def list_jobs(
        self,
        status: Optional[JobStatus] = None,
        session_id: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Job]:
        def _list():
            query = "SELECT data FROM jobs"
            clauses = []
            params: List[Any] = []
            if status:
                clauses.append("status = ?")
                params.append(status.value)
            if session_id:
                clauses.append("session_id = ?")
                params.append(session_id)
            if clauses:
                query += " WHERE " + " AND ".join(clauses)
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            with self._lock:
                cur = self._conn.execute(query, params)
                rows = cur.fetchall()
            return [self._row_to_job(r[0]) for r in rows]

        return await asyncio.to_thread(_list)

    async def count(
        self,
        status: Optional[JobStatus] = None,
        session_id: Optional[str] = None,
    ) -> int:
        def _count():
            query = "SELECT COUNT(*) FROM jobs"
            clauses = []
            params: List[Any] = []
            if status:
                clauses.append("status = ?")
                params.append(status.value)
            if session_id:
                clauses.append("session_id = ?")
                params.append(session_id)
            if clauses:
                query += " WHERE " + " AND ".join(clauses)
            with self._lock:
                cur = self._conn.execute(query, params)
                return int(cur.fetchone()[0])

        return await asyncio.to_thread(_count)

    async def delete(self, job_id: str) -> bool:
        def _delete():
            with self._lock:
                cur = self._conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
                self._conn.commit()
                return cur.rowcount > 0

        return await asyncio.to_thread(_delete)

    async def cleanup_old_jobs(self, max_age_seconds: int = 86400) -> int:
        def _cleanup():
            cutoff = (datetime.utcnow() - timedelta(seconds=max_age_seconds)).isoformat()
            terminal = (
                JobStatus.SUCCEEDED.value,
                JobStatus.FAILED.value,
                JobStatus.CANCELLED.value,
            )
            placeholders = ",".join("?" for _ in terminal)
            with self._lock:
                cur = self._conn.execute(
                    f"DELETE FROM jobs WHERE status IN ({placeholders}) "
                    "AND completed_at IS NOT NULL AND completed_at < ?",
                    (*terminal, cutoff),
                )
                self._conn.commit()
                count = cur.rowcount
            if count:
                logger.info(f"Cleaned up {count} old jobs")
            return count

        return await asyncio.to_thread(_cleanup)

    async def get_stats(self) -> Dict[str, Any]:
        def _stats():
            with self._lock:
                total = int(self._conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0])
                idem = int(
                    self._conn.execute(
                        "SELECT COUNT(*) FROM jobs WHERE idempotency_key IS NOT NULL"
                    ).fetchone()[0]
                )
                rows = self._conn.execute(
                    "SELECT status, COUNT(*) FROM jobs GROUP BY status"
                ).fetchall()
            return {
                "backend": "sqlite",
                "path": self._path,
                "total_jobs": total,
                "idempotency_keys": idem,
                "status_counts": {status: count for status, count in rows},
            }

        return await asyncio.to_thread(_stats)
