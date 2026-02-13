"""
File-based schedule store for PraisonAI Agents.

Persists scheduled jobs to ``~/.praisonai/schedules/jobs.json``.
Thread-safe, no external dependencies.
"""

import json
import logging
import os
import threading
from typing import Dict, List, Optional

from .models import ScheduleJob

logger = logging.getLogger(__name__)

_DEFAULT_DIR = os.path.join(os.path.expanduser("~"), ".praisonai", "schedules")
_JOBS_FILE = "jobs.json"


class FileScheduleStore:
    """CRUD store backed by a single JSON file.

    Thread-safe for multi-agent scenarios.
    """

    def __init__(self, store_dir: Optional[str] = None):
        self._dir = store_dir or _DEFAULT_DIR
        self._path = os.path.join(self._dir, _JOBS_FILE)
        self._lock = threading.RLock()
        self._jobs: Dict[str, ScheduleJob] = {}
        self._load()

    # ── public API ───────────────────────────────────────────────────

    def add(self, job: ScheduleJob) -> None:
        """Add a job. Raises ``ValueError`` if id already exists."""
        with self._lock:
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
        with self._lock:
            self._jobs[job.id] = job
            self._save()

    def remove(self, job_id: str) -> bool:
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                self._save()
                return True
            return False

    def remove_by_name(self, name: str) -> bool:
        with self._lock:
            for jid, job in list(self._jobs.items()):
                if job.name == name:
                    del self._jobs[jid]
                    self._save()
                    return True
            return False

    # ── persistence ──────────────────────────────────────────────────

    def _load(self) -> None:
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, "r") as f:
                data = json.load(f)
            for d in data:
                job = ScheduleJob.from_dict(d)
                self._jobs[job.id] = job
        except Exception as e:
            logger.warning("Failed to load schedule store from %s: %s", self._path, e)

    def _save(self) -> None:
        try:
            os.makedirs(self._dir, exist_ok=True)
            data = [j.to_dict() for j in self._jobs.values()]
            tmp = self._path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, self._path)
        except Exception as e:
            logger.warning("Failed to save schedule store to %s: %s", self._path, e)
