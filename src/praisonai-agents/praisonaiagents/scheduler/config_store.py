"""
Config YAML-based schedule store for PraisonAI Agents.

Persists scheduled jobs to ``~/.praisonai/config.yaml`` under
the ``schedules`` top-level key.  Thread-safe, preserves all
other config.yaml content.
"""

import logging
import os
import threading
from typing import Dict, List, Optional

from .models import ScheduleJob

logger = logging.getLogger(__name__)


class ConfigYamlScheduleStore:
    """CRUD store backed by ``config.yaml``.

    Schedules are stored as a dict under the ``schedules`` key,
    alongside existing keys like ``agents``, ``server``, etc.

    Thread-safe for multi-agent scenarios.
    """

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            from ..paths import get_data_dir
            config_path = str(get_data_dir() / "config.yaml")
        self._path = config_path
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
