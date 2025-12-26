"""
Job Store for PraisonAI Async Jobs API.

Provides storage backends for job state persistence.
"""

import asyncio
import logging
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
        self._lock = asyncio.Lock()
    
    async def save(self, job: Job) -> None:
        """Save or update a job."""
        async with self._lock:
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
        return self._jobs.get(job_id)
    
    async def get_by_idempotency_key(self, key: str) -> Optional[Job]:
        """Get a job by idempotency key."""
        job_id = self._idempotency_keys.get(key)
        if job_id:
            return self._jobs.get(job_id)
        return None
    
    async def list_jobs(
        self,
        status: Optional[JobStatus] = None,
        session_id: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[Job]:
        """List jobs with optional filters."""
        jobs = list(self._jobs.values())
        
        # Apply filters
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
        jobs = list(self._jobs.values())
        
        if status:
            jobs = [j for j in jobs if j.status == status]
        if session_id:
            jobs = [j for j in jobs if j.session_id == session_id]
        
        return len(jobs)
    
    async def delete(self, job_id: str) -> bool:
        """Delete a job by ID."""
        async with self._lock:
            job = self._jobs.pop(job_id, None)
            if job:
                if job.idempotency_key:
                    self._idempotency_keys.pop(job.idempotency_key, None)
                return True
            return False
    
    async def cleanup_old_jobs(self, max_age_seconds: int = 86400) -> int:
        """Remove jobs older than max_age_seconds."""
        async with self._lock:
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
    
    def get_stats(self) -> Dict[str, Any]:
        """Get store statistics."""
        status_counts = {}
        for job in self._jobs.values():
            status_counts[job.status.value] = status_counts.get(job.status.value, 0) + 1
        
        return {
            "total_jobs": len(self._jobs),
            "idempotency_keys": len(self._idempotency_keys),
            "max_jobs": self._max_jobs,
            "status_counts": status_counts
        }
