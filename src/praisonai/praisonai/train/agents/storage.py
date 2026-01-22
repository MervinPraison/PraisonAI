"""
Storage for Agent Training data.

Provides JSON-based persistence for training iterations, scenarios, and reports.
DRY: Follows the same pattern as praisonaiagents.memory.learn.stores.BaseStore.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

# DRY: Import base classes from praisonaiagents.storage
from praisonaiagents.storage.models import BaseSessionInfo
from praisonaiagents.storage.base import BaseJSONStore, list_json_sessions, cleanup_old_sessions as _cleanup_old_sessions

if TYPE_CHECKING:
    from praisonaiagents.storage.protocols import StorageBackendProtocol

from .models import TrainingIteration, TrainingReport, TrainingScenario


DEFAULT_STORAGE_DIR = "~/.praison/train"


def get_storage_dir() -> Path:
    """
    Get the training storage directory.
    
    Returns:
        Path to storage directory (creates if not exists)
    """
    storage_dir = Path(os.path.expanduser(DEFAULT_STORAGE_DIR))
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir


class TrainingSessionInfo(BaseSessionInfo):
    """
    Information about a training session.
    
    DRY: Inherits from BaseSessionInfo which provides:
    - session_id, path, size_bytes, created_at, modified_at, item_count
    - to_dict(), from_dict(), from_path() methods
    """
    
    @property
    def iteration_count(self) -> int:
        """Alias for item_count for backward compatibility."""
        return self.item_count
    
    def to_dict(self):
        """Override to include iteration_count for backward compatibility."""
        d = super().to_dict()
        d["iteration_count"] = self.iteration_count
        return d


class TrainingStorage:
    """
    JSON-based storage for training data.
    
    Stores training iterations, scenarios, and reports to JSON files.
    Each training session gets its own file.
    
    DRY: Uses BaseJSONStore internally for thread-safe, file-locked storage.
    Supports pluggable backends (file, sqlite, etc.) via the backend parameter.
    
    Usage:
        storage = TrainingStorage(session_id="train-abc123")
        storage.save_iteration(iteration)
        iterations = storage.load_iterations()
        
        # With SQLite backend:
        from praisonaiagents.storage import SQLiteBackend
        storage = TrainingStorage(
            session_id="train-abc123",
            backend=SQLiteBackend("training.db")
        )
    """
    
    def __init__(
        self,
        session_id: str,
        storage_dir: Optional[Path] = None,
        backend: Optional["StorageBackendProtocol"] = None,
    ):
        """
        Initialize storage.
        
        Args:
            session_id: Unique session identifier
            storage_dir: Directory for storage files (default: ~/.praison/train)
            backend: Optional storage backend (file, sqlite, etc.)
                     If provided, storage_dir is ignored and backend is used.
        """
        self.session_id = session_id
        self._backend = backend
        self.storage_dir = storage_dir or get_storage_dir()
        self.storage_dir = Path(self.storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # DRY: Use BaseJSONStore for thread-safe storage
        self._store = BaseJSONStore(
            storage_path=self.storage_path,
            backend=backend,
        )
        
        self._data = self._default_data()
        
        # Load existing data if available
        if self._store.exists():
            self._load()
    
    def _default_data(self):
        """Return default data structure."""
        return {
            "session_id": self.session_id,
            "created_at": datetime.utcnow().isoformat(),
            "scenarios": [],
            "iterations": [],
            "report": None,
        }
    
    @property
    def storage_path(self) -> Path:
        """Get path to storage file."""
        return self.storage_dir / f"{self.session_id}.json"
    
    def _load(self) -> None:
        """Load data from storage using BaseJSONStore."""
        loaded = self._store.load()
        if loaded:
            self._data = loaded
    
    def _save(self) -> None:
        """Save data to storage using BaseJSONStore."""
        self._data["updated_at"] = datetime.utcnow().isoformat()
        self._store.save(self._data)
    
    def save_iteration(self, iteration: TrainingIteration) -> None:
        """
        Save a training iteration.
        
        Args:
            iteration: The iteration to save
        """
        self._data["iterations"].append(iteration.to_dict())
        self._save()
    
    def load_iterations(self) -> List[TrainingIteration]:
        """
        Load all iterations from storage.
        
        Returns:
            List of TrainingIteration objects
        """
        return [
            TrainingIteration.from_dict(it)
            for it in self._data.get("iterations", [])
        ]
    
    def save_scenario(self, scenario: TrainingScenario) -> None:
        """
        Save a training scenario.
        
        Args:
            scenario: The scenario to save
        """
        self._data["scenarios"].append(scenario.to_dict())
        self._save()
    
    def load_scenarios(self) -> List[TrainingScenario]:
        """
        Load all scenarios from storage.
        
        Returns:
            List of TrainingScenario objects
        """
        return [
            TrainingScenario.from_dict(s)
            for s in self._data.get("scenarios", [])
        ]
    
    def save_report(self, report: TrainingReport) -> None:
        """
        Save the training report.
        
        Args:
            report: The report to save
        """
        self._data["report"] = report.to_dict()
        self._save()
    
    def load_report(self) -> Optional[TrainingReport]:
        """
        Load the training report.
        
        Returns:
            TrainingReport or None if not saved
        """
        report_data = self._data.get("report")
        if report_data:
            return TrainingReport.from_dict(report_data)
        return None
    
    def clear(self) -> None:
        """Clear all stored data."""
        self._data = {
            "session_id": self.session_id,
            "created_at": datetime.utcnow().isoformat(),
            "scenarios": [],
            "iterations": [],
            "report": None,
        }
        self._save()


def list_training_sessions(
    storage_dir: Optional[Path] = None,
    limit: int = 50,
) -> List[TrainingSessionInfo]:
    """
    List all training sessions.
    
    DRY: Uses list_json_sessions from praisonaiagents.storage.base.
    
    Args:
        storage_dir: Directory to search (default: ~/.praison/train)
        limit: Maximum number of sessions to return
        
    Returns:
        List of TrainingSessionInfo objects, sorted by modification time (newest first)
    """
    if storage_dir is None:
        storage_dir = get_storage_dir()
    
    # DRY: Use common list_json_sessions function
    base_sessions = list_json_sessions(Path(storage_dir), suffix=".json", limit=limit)
    
    # Convert BaseSessionInfo to TrainingSessionInfo for backward compatibility
    return [
        TrainingSessionInfo(
            session_id=s.session_id,
            path=s.path,
            size_bytes=s.size_bytes,
            created_at=s.created_at,
            modified_at=s.modified_at,
            item_count=s.item_count,
        )
        for s in base_sessions
    ]


def cleanup_old_sessions(
    storage_dir: Optional[Path] = None,
    max_age_days: int = 30,
    max_size_mb: int = 100,
) -> int:
    """
    Clean up old training sessions.
    
    DRY: Uses cleanup_old_sessions from praisonaiagents.storage.base.
    
    Args:
        storage_dir: Directory to clean (default: ~/.praison/train)
        max_age_days: Delete sessions older than this
        max_size_mb: Delete oldest sessions if total size exceeds this
        
    Returns:
        Number of files deleted
    """
    if storage_dir is None:
        storage_dir = get_storage_dir()
    
    # DRY: Use common cleanup function
    return _cleanup_old_sessions(
        storage_dir=Path(storage_dir),
        suffix=".json",
        max_age_days=max_age_days,
        max_size_mb=max_size_mb,
    )
