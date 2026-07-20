"""
Config YAML-based schedule store for PraisonAI Agents.

Persists scheduled jobs to ``~/.praisonai/config.yaml`` under
the ``schedules`` top-level key.  Thread-safe, preserves all
other config.yaml content.
"""

import contextlib
import logging
from praisonaiagents._logging import get_logger
import os
import threading
import time
from typing import Dict, Iterator, List, Optional

from .models import ScheduleJob, RunRecord
from .due import is_due as _is_due

logger = get_logger(__name__)

_HISTORY_FILE = "run_history.yaml"
_LOCK_FILE = "config.schedules.lock"
_MAX_HISTORY = 200

class ConfigYamlScheduleStore:
    """CRUD store backed by ``config.yaml``.

    Schedules are stored as a dict under the ``schedules`` key,
    alongside existing keys like ``agents``, ``server``, etc.

    Thread-safe for multi-agent scenarios.
    """

    def __init__(self, config_path: Optional[str] = None, max_history: int = _MAX_HISTORY):
        if config_path is None:
            from ..paths import get_data_dir
            config_path = str(get_data_dir() / "config.yaml")
        self._path = config_path
        self._history_path = os.path.join(os.path.dirname(config_path), _HISTORY_FILE)
        self._lock_path = os.path.join(os.path.dirname(config_path), _LOCK_FILE)
        self._max_history = max_history
        self._lock = threading.RLock()
        self._jobs: Dict[str, ScheduleJob] = {}
        self._history: List[RunRecord] = []
        # In-memory record of leases we currently hold, so ``complete`` can
        # release them. Cross-process leases live in the persisted job
        # (``lease_until`` / ``lease_owner``) which is the source of truth.
        self._held_leases: Dict[str, str] = {}
        self._load()
        self._load_history()

    # ── public API ───────────────────────────────────────────────────

    def add(self, job: ScheduleJob) -> None:
        """Add a job. Raises ``ValueError`` if id already exists."""
        with self._lock, self._file_lock():
            # Reload under the cross-process lock so we don't overwrite lease
            # / last_run_at written by a concurrent ``claim_due`` in another
            # process before applying our change.
            self._reload_locked()
            if job.id in self._jobs:
                raise ValueError(f"Job '{job.id}' already exists")
            self._jobs[job.id] = job
            self._save()

    def get(self, job_id: str) -> Optional[ScheduleJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def get_by_name(self, name: str) -> Optional[ScheduleJob]:
        with self._lock:
            for job in self._jobs.values():
                if job.name == name:
                    return job
            return None

    def list(self, agent_id: Optional[str] = None) -> List[ScheduleJob]:
        with self._lock:
            jobs = list(self._jobs.values())
        if agent_id is not None:
            jobs = [j for j in jobs if j.agent_id == agent_id]
        return jobs

    def update(self, job: ScheduleJob) -> None:
        with self._lock, self._file_lock():
            # Reload latest on-disk state, then preserve any active lease held
            # for this job (written by a concurrent ``claim_due``) so a plain
            # ``update`` from a stale in-memory copy cannot silently drop it.
            self._reload_locked()
            existing = self._jobs.get(job.id)
            if existing is not None:
                if not getattr(job, "_lease_until", 0.0):
                    job._lease_until = getattr(existing, "_lease_until", 0.0) or 0.0
                    job._lease_owner = getattr(existing, "_lease_owner", None)
            self._jobs[job.id] = job
            self._save()

    def remove(self, job_id: str) -> bool:
        with self._lock, self._file_lock():
            self._reload_locked()
            if job_id in self._jobs:
                del self._jobs[job_id]
                self._save()
                return True
            return False

    def remove_by_name(self, name: str) -> bool:
        with self._lock, self._file_lock():
            self._reload_locked()
            for jid, job in list(self._jobs.items()):
                if job.name == name:
                    del self._jobs[jid]
                    self._save()
                    return True
            return False

    # ── atomic claim / lease ──────────────────────────────────────────

    def claim_due(
        self,
        now: float,
        owner_id: str,
        lease_seconds: float = 300.0,
    ) -> List[ScheduleJob]:
        """Atomically claim due jobs; return only those won by ``owner_id``.

        Under a cross-process OS advisory file lock we re-read the on-disk
        state (so we see claims made by other processes), then for each enabled
        job that is due and not already leased by someone else we:

        * advance ``last_run_at`` to ``now`` (pre-advancing the schedule so a
          later poll no longer sees it as due — at-least-once → at-most-once),
        * take a lease (``lease_until = now + lease_seconds``, ``lease_owner``),
          persisting both in the same atomic write,
        * remove one-shot jobs (``delete_after_run``) immediately so no other
          ticker can pick them up.

        A crashed run leaves a lease that expires after ``lease_seconds``; the
        job then becomes due again and is retried. Losers of the race simply do
        not see the job in their returned list.
        """
        claimed: List[ScheduleJob] = []
        with self._lock, self._file_lock():
            # Re-read from disk so we observe cross-process claims/leases.
            self._reload_locked()
            changed = False
            for job in list(self._jobs.values()):
                if not job.enabled:
                    continue
                lease_until = getattr(job, "_lease_until", 0.0) or 0.0
                lease_owner = getattr(job, "_lease_owner", None)
                # An unexpired lease held by another owner blocks the claim.
                if lease_until > now and lease_owner != owner_id:
                    continue
                if not _is_due(job, now):
                    continue
                # Win the claim: pre-advance + lease atomically.
                job.last_run_at = now
                job._lease_until = now + lease_seconds
                job._lease_owner = owner_id
                self._held_leases[job.id] = owner_id
                claimed.append(job)
                changed = True
                if job.delete_after_run:
                    # One-shot: remove now so no competitor re-claims it.
                    del self._jobs[job.id]
            if changed:
                self._save()
        return claimed

    def complete(self, job_id: str, owner_id: str) -> None:
        """Release the lease for ``job_id`` if held by ``owner_id`` (idempotent)."""
        with self._lock, self._file_lock():
            self._reload_locked()
            self._held_leases.pop(job_id, None)
            job = self._jobs.get(job_id)
            if job is None:
                return
            if getattr(job, "_lease_owner", None) != owner_id:
                return
            job._lease_until = 0.0
            job._lease_owner = None
            self._save()

    # ── cross-process lock ────────────────────────────────────────────

    @contextlib.contextmanager
    def _file_lock(self) -> Iterator[None]:
        """Hold an OS advisory lock on a sidecar file for the block's duration.

        Uses ``fcntl`` on POSIX and ``msvcrt`` on Windows. If neither is
        available (or locking fails) we degrade to the in-process
        ``threading`` lock already held by callers — correctness within a
        single process is preserved, only cross-process atomicity is lost.
        """
        lock_dir = os.path.dirname(self._lock_path)
        if lock_dir:
            os.makedirs(lock_dir, exist_ok=True)
        fh = None
        locked = False
        try:
            fh = open(self._lock_path, "a+")
            try:
                import fcntl  # type: ignore[import-not-found]
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
                locked = True
            except ImportError:
                try:
                    import msvcrt  # type: ignore[import-not-found]
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
                    locked = True
                except Exception as e:  # pragma: no cover - platform dependent
                    logger.debug("No OS file lock available (%s); using thread lock only", e)
            except Exception as e:  # pragma: no cover - defensive
                logger.debug("Failed to acquire file lock (%s); using thread lock only", e)
            yield
        finally:
            if fh is not None:
                try:
                    if locked:
                        try:
                            import fcntl  # type: ignore[import-not-found]
                            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                        except ImportError:
                            try:
                                import msvcrt  # type: ignore[import-not-found]
                                fh.seek(0)
                                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                            except Exception:  # pragma: no cover
                                pass
                except Exception:  # pragma: no cover - defensive
                    pass
                fh.close()

    def _reload_locked(self) -> None:
        """Re-read jobs from disk (caller must hold both thread + file lock).

        Ensures a claim decision is based on the latest cross-process state so
        a job already claimed/leased by another process is observed.
        """
        self._jobs = {}
        self._load()

    # ── execution history ─────────────────────────────────────────────

    def log_run(
        self,
        job_id: str,
        status: str,
        result: Optional[str] = None,
        error: Optional[str] = None,
        duration: float = 0.0,
        delivered: bool = False,
        job_name: str = "",
    ) -> None:
        """Log an execution run for a job."""
        record = RunRecord(
            job_id=job_id,
            job_name=job_name,
            status=status,
            result=result[:2000] if result and len(result) > 2000 else result,
            error=error,
            duration=duration,
            delivered=delivered,
            timestamp=time.time(),
        )
        with self._lock:
            self._history.insert(0, record)
            # Prune to max_history
            if len(self._history) > self._max_history:
                self._history = self._history[:self._max_history]
            self._save_history()

    def get_history(
        self,
        job_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[RunRecord]:
        """Get execution history records, newest first."""
        with self._lock:
            records = list(self._history)
        if job_id is not None:
            records = [r for r in records if r.job_id == job_id]
        return records[:limit]

    # ── persistence ──────────────────────────────────────────────────

    def _load(self) -> None:
        """Load schedule jobs from config.yaml's ``schedules`` section."""
        if not os.path.exists(self._path):
            return
        try:
            import yaml
            with open(self._path, "r") as f:
                data = yaml.safe_load(f) or {}
            schedules = data.get("schedules", {})
            if isinstance(schedules, dict):
                for job_id, job_data in schedules.items():
                    if isinstance(job_data, dict) and job_data.get("name"):
                        job_data.setdefault("id", job_id)
                        job = ScheduleJob.from_dict(job_data)
                        self._jobs[job.id] = job
        except Exception as e:
            logger.warning("Failed to load schedules from %s: %s", self._path, e)

    def _save(self) -> None:
        """Write schedule jobs into config.yaml's ``schedules`` key.

        Preserves all other top-level keys (agents, server, etc.).
        """
        try:
            import yaml

            # Read existing config
            data: dict = {}
            if os.path.exists(self._path):
                with open(self._path, "r") as f:
                    data = yaml.safe_load(f) or {}

            # Update only the schedules section
            schedules = {}
            for job in self._jobs.values():
                schedules[job.id] = job.to_dict()
            data["schedules"] = schedules

            # Atomic write
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            tmp = self._path + ".tmp"
            with open(tmp, "w") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            os.replace(tmp, self._path)
        except Exception as e:
            logger.warning("Failed to save schedules to %s: %s", self._path, e)

    def _load_history(self) -> None:
        """Load execution history from run_history.yaml."""
        if not os.path.exists(self._history_path):
            return
        try:
            import yaml
            with open(self._history_path, "r") as f:
                data = yaml.safe_load(f) or []
            if isinstance(data, list):
                for d in data:
                    if isinstance(d, dict):
                        record = RunRecord.from_dict(d)
                        self._history.append(record)
        except Exception as e:
            logger.warning("Failed to load history from %s: %s", self._history_path, e)

    def _save_history(self) -> None:
        """Save execution history to run_history.yaml."""
        try:
            import yaml
            os.makedirs(os.path.dirname(self._history_path), exist_ok=True)
            data = [r.to_dict() for r in self._history]
            tmp = self._history_path + ".tmp"
            with open(tmp, "w") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            os.replace(tmp, self._history_path)
        except Exception as e:
            logger.warning("Failed to save history to %s: %s", self._history_path, e)

    # ── migration ────────────────────────────────────────────────────

    def migrate_from_json(self, json_path: Optional[str] = None) -> int:
        """Import jobs from a legacy ``jobs.json`` file.

        Args:
            json_path: Path to ``jobs.json``. Defaults to
                       ``~/.praisonai/schedules/jobs.json``.

        Returns:
            Number of jobs migrated.
        """
        import json

        if json_path is None:
            from ..paths import get_schedules_dir
            json_path = str(get_schedules_dir() / "jobs.json")

        if not os.path.exists(json_path):
            return 0

        try:
            with open(json_path, "r") as f:
                items = json.load(f)
            if not isinstance(items, list):
                return 0
            count = 0
            with self._lock:
                for d in items:
                    job = ScheduleJob.from_dict(d)
                    if job.id not in self._jobs:
                        self._jobs[job.id] = job
                        count += 1
                if count:
                    self._save()
                    logger.info(
                        "Migrated %d schedule(s) from %s into config.yaml",
                        count, json_path,
                    )
            return count
        except Exception as e:
            logger.warning("Failed to migrate from %s: %s", json_path, e)
            return 0
