"""
Run History Storage Module

Provides storage and retrieval of recipe run history for:
- Export/replay functionality
- Audit trails
- Debugging and analysis
"""

import json
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .models import RecipeResult

if TYPE_CHECKING:
    from praisonaiagents.storage.protocols import StorageBackendProtocol


# Default storage path
DEFAULT_RUNS_PATH = Path.home() / ".praison" / "runs"


class RunHistoryError(Exception):
    """Base exception for run history operations."""
    pass


class RunNotFoundError(RunHistoryError):
    """Run not found in history."""
    pass


def _get_timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


class RunHistory:
    """
    Local run history storage.
    
    Storage structure (file-based):
    ~/.praison/runs/
    ├── index.json           # Run index for fast lookup
    └── <run_id>/
        ├── run.json         # Run metadata and result
        ├── input.json       # Input data
        ├── output.json      # Output data
        └── events.jsonl     # Event stream (if streaming)
    
    Supports pluggable backends (file, sqlite, redis) via the backend parameter.
    
    Example with SQLite backend:
        ```python
        from praisonaiagents.storage import SQLiteBackend
        backend = SQLiteBackend("~/.praison/runs.db")
        history = RunHistory(backend=backend)
        ```
    """
    
    def __init__(
        self,
        path: Optional[Path] = None,
        backend: Optional["StorageBackendProtocol"] = None,
    ):
        """
        Initialize run history storage.
        
        Args:
            path: Path for file-based storage (default: ~/.praison/runs)
            backend: Optional storage backend (file, sqlite, redis).
                     If provided, path is ignored and backend is used.
        """
        self.path = Path(path) if path else DEFAULT_RUNS_PATH
        self.index_path = self.path / "index.json"
        self._backend = backend
        
        if backend is None:
            self._ensure_structure()
    
    def _ensure_structure(self):
        """Ensure storage directory structure exists."""
        self.path.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self._save_index({"runs": {}, "updated": _get_timestamp()})
    
    def _load_index(self) -> Dict[str, Any]:
        """Load run index."""
        if self._backend is not None:
            loaded = self._backend.load("_index")
            return loaded if loaded else {"runs": {}, "updated": _get_timestamp()}
        
        if self.index_path.exists():
            with open(self.index_path) as f:
                return json.load(f)
        return {"runs": {}, "updated": _get_timestamp()}
    
    def _save_index(self, index: Dict[str, Any]):
        """Save run index."""
        index["updated"] = _get_timestamp()
        
        if self._backend is not None:
            self._backend.save("_index", index)
            return
        
        with open(self.index_path, "w") as f:
            json.dump(index, f, indent=2)
    
    def store(
        self,
        result: RecipeResult,
        input_data: Optional[Dict[str, Any]] = None,
        events: Optional[List[Dict[str, Any]]] = None,
        data_policy: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Store a run result in history.
        
        Args:
            result: RecipeResult to store
            input_data: Original input data
            events: List of streaming events (if any)
            data_policy: Data policy for retention/export
            
        Returns:
            run_id
        """
        run_id = result.run_id
        run_dir = self.path / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        
        # Check data policy
        export_allowed = True
        retention_days = None
        if data_policy:
            export_allowed = data_policy.get("export_allowed", True)
            retention_days = data_policy.get("retention_days")
        
        # Store run metadata
        run_data = {
            "run_id": run_id,
            "recipe": result.recipe,
            "version": result.version,
            "status": result.status,
            "ok": result.ok,
            "error": result.error,
            "metrics": result.metrics,
            "trace": result.trace,
            "stored_at": _get_timestamp(),
            "export_allowed": export_allowed,
            "retention_days": retention_days,
        }
        
        if self._backend is not None:
            # Backend-based storage
            full_data = {
                "run": run_data,
                "input": input_data if input_data and export_allowed else None,
                "output": result.output if result.output and export_allowed else None,
                "events": events,
            }
            self._backend.save(f"run:{run_id}", full_data)
        else:
            # File-based storage
            with open(run_dir / "run.json", "w") as f:
                json.dump(run_data, f, indent=2)
            
            # Store input (if allowed)
            if input_data and export_allowed:
                with open(run_dir / "input.json", "w") as f:
                    json.dump(input_data, f, indent=2)
            
            # Store output (if allowed)
            if result.output and export_allowed:
                with open(run_dir / "output.json", "w") as f:
                    json.dump(result.output, f, indent=2)
            
            # Store events (if any)
            if events:
                with open(run_dir / "events.jsonl", "w") as f:
                    for event in events:
                        f.write(json.dumps(event) + "\n")
        
        # Update index
        index = self._load_index()
        index["runs"][run_id] = {
            "recipe": result.recipe,
            "version": result.version,
            "status": result.status,
            "stored_at": run_data["stored_at"],
            "session_id": result.trace.get("session_id"),
        }
        self._save_index(index)
        
        return run_id
    
    def get(self, run_id: str) -> Dict[str, Any]:
        """
        Get a run from history.
        
        Args:
            run_id: Run ID to retrieve
            
        Returns:
            Dict with run data, input, output, events
            
        Raises:
            RunNotFoundError: If run not found
        """
        if self._backend is not None:
            # Backend-based retrieval
            full_data = self._backend.load(f"run:{run_id}")
            if not full_data:
                raise RunNotFoundError(f"Run not found: {run_id}")
            
            run_data = full_data.get("run", {})
            if full_data.get("input"):
                run_data["input"] = full_data["input"]
            if full_data.get("output"):
                run_data["output"] = full_data["output"]
            if full_data.get("events"):
                run_data["events"] = full_data["events"]
            return run_data
        
        # File-based retrieval
        run_dir = self.path / run_id
        if not run_dir.exists():
            raise RunNotFoundError(f"Run not found: {run_id}")
        
        # Load run metadata
        run_path = run_dir / "run.json"
        if not run_path.exists():
            raise RunNotFoundError(f"Run metadata missing: {run_id}")
        
        with open(run_path) as f:
            run_data = json.load(f)
        
        # Load input
        input_path = run_dir / "input.json"
        if input_path.exists():
            with open(input_path) as f:
                run_data["input"] = json.load(f)
        
        # Load output
        output_path = run_dir / "output.json"
        if output_path.exists():
            with open(output_path) as f:
                run_data["output"] = json.load(f)
        
        # Load events
        events_path = run_dir / "events.jsonl"
        if events_path.exists():
            events = []
            with open(events_path) as f:
                for line in f:
                    if line.strip():
                        events.append(json.loads(line))
            run_data["events"] = events
        
        return run_data
    
    def list_runs(
        self,
        recipe: Optional[str] = None,
        session_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        List runs from history.
        
        Args:
            recipe: Filter by recipe name
            session_id: Filter by session ID
            status: Filter by status
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of run summaries
        """
        index = self._load_index()
        runs = []
        
        for run_id, info in index["runs"].items():
            # Apply filters
            if recipe and info.get("recipe") != recipe:
                continue
            if session_id and info.get("session_id") != session_id:
                continue
            if status and info.get("status") != status:
                continue
            
            runs.append({
                "run_id": run_id,
                **info,
            })
        
        # Sort by stored_at descending
        runs.sort(key=lambda x: x.get("stored_at", ""), reverse=True)
        
        # Apply pagination
        return runs[offset:offset + limit]
    
    def export(
        self,
        run_id: str,
        output_path: Optional[Path] = None,
    ) -> Path:
        """
        Export a run as a JSON bundle.
        
        Args:
            run_id: Run ID to export
            output_path: Output file path (default: <run_id>.export.json)
            
        Returns:
            Path to exported file
            
        Raises:
            RunNotFoundError: If run not found
            RunHistoryError: If export not allowed
        """
        run_data = self.get(run_id)
        
        # Check if export is allowed
        if not run_data.get("export_allowed", True):
            raise RunHistoryError(f"Export not allowed for run: {run_id}")
        
        # Prepare export bundle
        export_bundle = {
            "format": "praison-run-export",
            "version": "1.0",
            "exported_at": _get_timestamp(),
            "run": run_data,
        }
        
        # Write to file
        output_path = Path(output_path) if output_path else Path(f"{run_id}.export.json")
        with open(output_path, "w") as f:
            json.dump(export_bundle, f, indent=2)
        
        return output_path
    
    def delete(self, run_id: str) -> bool:
        """
        Delete a run from history.
        
        Args:
            run_id: Run ID to delete
            
        Returns:
            True if deleted
        """
        if self._backend is not None:
            self._backend.delete(f"run:{run_id}")
        else:
            run_dir = self.path / run_id
            if run_dir.exists():
                shutil.rmtree(run_dir)
        
        index = self._load_index()
        if run_id in index["runs"]:
            del index["runs"][run_id]
            self._save_index(index)
        
        return True
    
    def cleanup(self, retention_days: Optional[int] = None) -> int:
        """
        Clean up old runs based on retention policy.
        
        Args:
            retention_days: Override retention days (default: use per-run policy)
            
        Returns:
            Number of runs deleted
        """
        index = self._load_index()
        deleted = 0
        now = datetime.now(timezone.utc)
        
        for run_id in list(index["runs"].keys()):
            run_dir = self.path / run_id
            run_path = run_dir / "run.json"
            
            if not run_path.exists():
                # Clean up orphaned index entry
                del index["runs"][run_id]
                deleted += 1
                continue
            
            with open(run_path) as f:
                run_data = json.load(f)
            
            # Check retention
            run_retention = retention_days or run_data.get("retention_days")
            if run_retention:
                stored_at = datetime.fromisoformat(run_data["stored_at"].replace("Z", "+00:00"))
                if now - stored_at > timedelta(days=run_retention):
                    self.delete(run_id)
                    deleted += 1
        
        return deleted
    
    def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        index = self._load_index()
        
        total_runs = len(index["runs"])
        total_size = 0
        
        for run_id in index["runs"]:
            run_dir = self.path / run_id
            if run_dir.exists():
                for f in run_dir.iterdir():
                    if f.is_file():
                        total_size += f.stat().st_size
        
        return {
            "total_runs": total_runs,
            "total_size_bytes": total_size,
            "storage_path": str(self.path),
        }


# Global instance for convenience
_default_history: Optional[RunHistory] = None


def get_history(path: Optional[Path] = None) -> RunHistory:
    """Get or create default run history instance."""
    global _default_history
    if path:
        return RunHistory(path)
    if _default_history is None:
        _default_history = RunHistory()
    return _default_history


def store_run(
    result: RecipeResult,
    input_data: Optional[Dict[str, Any]] = None,
    events: Optional[List[Dict[str, Any]]] = None,
    data_policy: Optional[Dict[str, Any]] = None,
) -> str:
    """Convenience function to store a run."""
    return get_history().store(result, input_data, events, data_policy)


def get_run(run_id: str) -> Dict[str, Any]:
    """Convenience function to get a run."""
    return get_history().get(run_id)


def list_runs(**kwargs) -> List[Dict[str, Any]]:
    """Convenience function to list runs."""
    return get_history().list_runs(**kwargs)


def export_run(run_id: str, output_path: Optional[Path] = None) -> Path:
    """Convenience function to export a run."""
    return get_history().export(run_id, output_path)
