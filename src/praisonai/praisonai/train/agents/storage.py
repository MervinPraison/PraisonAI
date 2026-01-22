"""
Storage for Agent Training data.

Provides JSON-based persistence for training iterations, scenarios, and reports.
DRY: Follows the same pattern as praisonaiagents.memory.learn.stores.BaseStore.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

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


@dataclass
class TrainingSessionInfo:
    """Information about a training session."""
    session_id: str
    path: Path
    size_bytes: int
    created_at: datetime
    modified_at: datetime
    iteration_count: int = 0
    
    def to_dict(self):
        return {
            "session_id": self.session_id,
            "path": str(self.path),
            "size_bytes": self.size_bytes,
            "created_at": self.created_at.isoformat(),
            "modified_at": self.modified_at.isoformat(),
            "iteration_count": self.iteration_count,
        }


class TrainingStorage:
    """
    JSON-based storage for training data.
    
    Stores training iterations, scenarios, and reports to JSON files.
    Each training session gets its own file.
    
    Usage:
        storage = TrainingStorage(session_id="train-abc123")
        storage.save_iteration(iteration)
        iterations = storage.load_iterations()
    """
    
    def __init__(
        self,
        session_id: str,
        storage_dir: Optional[Path] = None,
    ):
        """
        Initialize storage.
        
        Args:
            session_id: Unique session identifier
            storage_dir: Directory for storage files (default: ~/.praison/train)
        """
        self.session_id = session_id
        self.storage_dir = storage_dir or get_storage_dir()
        self.storage_dir = Path(self.storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self._data = {
            "session_id": session_id,
            "created_at": datetime.utcnow().isoformat(),
            "scenarios": [],
            "iterations": [],
            "report": None,
        }
        
        # Load existing data if file exists
        if self.storage_path.exists():
            self._load()
    
    @property
    def storage_path(self) -> Path:
        """Get path to storage file."""
        return self.storage_dir / f"{self.session_id}.json"
    
    def _load(self) -> None:
        """Load data from storage file."""
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    
    def _save(self) -> None:
        """Save data to storage file."""
        self._data["updated_at"] = datetime.utcnow().isoformat()
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, default=str)
    
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
    
    Args:
        storage_dir: Directory to search (default: ~/.praison/train)
        limit: Maximum number of sessions to return
        
    Returns:
        List of TrainingSessionInfo objects, sorted by modification time (newest first)
    """
    if storage_dir is None:
        storage_dir = get_storage_dir()
    
    storage_dir = Path(storage_dir)
    if not storage_dir.exists():
        return []
    
    sessions = []
    for session_file in storage_dir.iterdir():
        if session_file.is_file() and session_file.suffix == ".json":
            stat = session_file.stat()
            
            # Count iterations
            iteration_count = 0
            try:
                with open(session_file, "r") as f:
                    data = json.load(f)
                    iteration_count = len(data.get("iterations", []))
            except Exception:
                pass
            
            sessions.append(TrainingSessionInfo(
                session_id=session_file.stem,
                path=session_file,
                size_bytes=stat.st_size,
                created_at=datetime.fromtimestamp(stat.st_ctime),
                modified_at=datetime.fromtimestamp(stat.st_mtime),
                iteration_count=iteration_count,
            ))
    
    # Sort by modification time (newest first)
    sessions.sort(key=lambda s: s.modified_at, reverse=True)
    
    return sessions[:limit]


def cleanup_old_sessions(
    storage_dir: Optional[Path] = None,
    max_age_days: int = 30,
    max_size_mb: int = 100,
) -> int:
    """
    Clean up old training sessions.
    
    Args:
        storage_dir: Directory to clean (default: ~/.praison/train)
        max_age_days: Delete sessions older than this
        max_size_mb: Delete oldest sessions if total size exceeds this
        
    Returns:
        Number of files deleted
    """
    if storage_dir is None:
        storage_dir = get_storage_dir()
    
    storage_dir = Path(storage_dir)
    if not storage_dir.exists():
        return 0
    
    deleted = 0
    now = datetime.now()
    
    # Get all sessions sorted by age (oldest first)
    sessions = list_training_sessions(storage_dir, limit=10000)
    sessions.sort(key=lambda s: s.modified_at)
    
    # Delete old sessions
    for session in sessions:
        age_days = (now - session.modified_at).days
        if age_days > max_age_days:
            try:
                session.path.unlink()
                deleted += 1
            except Exception:
                pass
    
    # Check total size and delete oldest if needed
    total_size_mb = sum(s.size_bytes for s in sessions if s.path.exists()) / (1024 * 1024)
    
    if total_size_mb > max_size_mb:
        remaining = list_training_sessions(storage_dir, limit=10000)
        remaining.sort(key=lambda s: s.modified_at)
        
        for session in remaining:
            if total_size_mb <= max_size_mb:
                break
            try:
                session.path.unlink()
                total_size_mb -= session.size_bytes / (1024 * 1024)
                deleted += 1
            except Exception:
                pass
    
    return deleted
