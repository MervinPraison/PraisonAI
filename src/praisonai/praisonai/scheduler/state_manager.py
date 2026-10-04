"""
Scheduler state manager for persistent storage of scheduler processes.
"""
import json
import os
import re
import signal
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from ._base_scheduler import _atomic_write_json

# A scheduler name is interpolated into a filename; reject path separators and
# ``..`` so a crafted name can't escape the state directory.
_NAME_RE = re.compile(r"^[A-Za-z0-9_\-.]{1,128}$")


def _validate_name(name: str) -> str:
    """Reject a scheduler name that is unsafe as a filesystem path component."""
    if not isinstance(name, str) or ".." in name or not _NAME_RE.match(name):
        raise ValueError(f"invalid scheduler name for filesystem storage: {name!r}")
    return name


def _process_start_time(pid: int) -> Optional[float]:
    """Return the process start time (clock ticks since boot) or None.

    Used to distinguish "the same process we started" from "a different process
    that now owns a recycled PID". Linux ``/proc`` only; returns None on any
    error so callers can conservatively treat the PID as not ours.
    """
    try:
        with open(f"/proc/{pid}/stat") as f:
            fields = f.read().rsplit(") ", 1)[1].split()
        return float(fields[19])  # starttime
    except (OSError, ValueError, IndexError):
        return None


class SchedulerStateManager:
    """Manages persistent state for scheduler processes."""
    
    def __init__(self, state_dir: Optional[Path] = None):
        """
        Initialize state manager.
        
        Args:
            state_dir: Directory to store state files. Defaults to ~/.praisonai/schedulers
        """
        if state_dir is None:
            home = Path.home()
            state_dir = home / ".praisonai" / "schedulers"
        
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
    
    def save_state(self, name: str, state: Dict) -> None:
        """
        Save scheduler state to JSON file.
        
        Args:
            name: Scheduler name
            state: State dictionary to save
        """
        _validate_name(name)
        state_file = self.state_dir / f"{name}.json"

        # Record the owning process's start time so a later PID-reuse can be
        # detected (see is_process_alive). Only when a live pid is present.
        pid = state.get("pid")
        if isinstance(pid, int) and "start_time" not in state:
            start_time = _process_start_time(pid)
            if start_time is not None:
                state = {**state, "start_time": start_time}

        _atomic_write_json(str(state_file), state)
    
    def load_state(self, name: str) -> Optional[Dict]:
        """
        Load scheduler state from JSON file.
        
        Args:
            name: Scheduler name
            
        Returns:
            State dictionary or None if not found
        """
        try:
            _validate_name(name)
        except ValueError:
            return None
        state_file = self.state_dir / f"{name}.json"
        
        if not state_file.exists():
            return None
        
        try:
            with open(state_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
    
    def delete_state(self, name: str) -> bool:
        """
        Delete scheduler state file.
        
        Args:
            name: Scheduler name
            
        Returns:
            True if deleted, False if not found
        """
        try:
            _validate_name(name)
        except ValueError:
            # A crafted name must never traverse out of the state dir to
            # unlink an arbitrary ``*.json`` file.
            return False
        state_file = self.state_dir / f"{name}.json"
        
        if state_file.exists():
            state_file.unlink()
            return True
        
        return False
    
    def list_all(self) -> List[Dict]:
        """
        List all scheduler states.
        
        Returns:
            List of state dictionaries
        """
        states = []
        
        for state_file in self.state_dir.glob("*.json"):
            try:
                with open(state_file) as f:
                    state = json.load(f)
                    states.append(state)
            except (json.JSONDecodeError, IOError):
                continue
        
        return states
    
    def generate_unique_name(self, base_name: str = "scheduler") -> str:
        """
        Atomically claim a unique scheduler name.

        Uses ``O_CREAT | O_EXCL`` to create a placeholder state file so two
        concurrent ``schedule start`` invocations can never both pick the same
        name and orphan each other's daemon (TOCTOU). The real state is written
        afterwards via :meth:`save_state`.

        Args:
            base_name: Base name for the scheduler

        Returns:
            Unique name like "scheduler-0", "scheduler-1", etc.
        """
        _validate_name(base_name)
        counter = 0
        while True:
            name = f"{base_name}-{counter}"
            path = self.state_dir / f"{name}.json"
            try:
                fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
                return name
            except FileExistsError:
                counter += 1
    
    def is_process_alive(self, pid: int, expected_start_time: Optional[float] = None) -> bool:
        """
        Check if a process is still alive.

        When ``expected_start_time`` is provided (recorded by :meth:`save_state`),
        the process's actual start time is compared so a recycled PID now owned by
        an unrelated process is reported as *not* alive — preventing
        ``stop_daemon`` from signalling an innocent process.

        Args:
            pid: Process ID
            expected_start_time: Start time recorded when the daemon was saved

        Returns:
            True if the process is alive and (when checkable) is the one we started
        """
        try:
            # Send signal 0 to check if process exists
            os.kill(pid, 0)
        except (OSError, ProcessLookupError):
            return False

        if expected_start_time is None:
            # Backward-compatible: no recorded identity to verify against.
            return True

        actual = _process_start_time(pid)
        if actual is None:
            # Can't prove ownership (e.g. non-Linux); fail safe: not ours.
            return False
        return abs(actual - expected_start_time) < 1.0
    
    def cleanup_dead_processes(self) -> int:
        """
        Clean up state files for dead processes.
        
        Returns:
            Number of dead processes cleaned up
        """
        cleaned = 0
        states = self.list_all()
        
        for state in states:
            pid = state.get("pid")
            name = state.get("name")
            start_time = state.get("start_time")
            
            if pid and name and not self.is_process_alive(pid, start_time):
                self.delete_state(name)
                cleaned += 1
        
        return cleaned
