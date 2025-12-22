"""
Scheduler state manager for persistent storage of scheduler processes.
"""
import json
import os
import signal
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime


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
        state_file = self.state_dir / f"{name}.json"
        
        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2)
    
    def load_state(self, name: str) -> Optional[Dict]:
        """
        Load scheduler state from JSON file.
        
        Args:
            name: Scheduler name
            
        Returns:
            State dictionary or None if not found
        """
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
        Generate a unique scheduler name.
        
        Args:
            base_name: Base name for the scheduler
            
        Returns:
            Unique name like "scheduler-0", "scheduler-1", etc.
        """
        existing_states = self.list_all()
        existing_names = {s.get("name", "") for s in existing_states}
        
        counter = 0
        while True:
            name = f"{base_name}-{counter}"
            if name not in existing_names:
                return name
            counter += 1
    
    def is_process_alive(self, pid: int) -> bool:
        """
        Check if a process is still alive.
        
        Args:
            pid: Process ID
            
        Returns:
            True if process is alive, False otherwise
        """
        try:
            # Send signal 0 to check if process exists
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False
    
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
            
            if pid and name and not self.is_process_alive(pid):
                self.delete_state(name)
                cleaned += 1
        
        return cleaned
