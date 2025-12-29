"""
Daemon process manager for running schedulers in background.
"""
import os
import sys
import signal
import subprocess
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime


class DaemonManager:
    """Manages daemon processes for schedulers."""
    
    def __init__(self, log_dir: Optional[Path] = None, max_log_size_mb: float = 10.0):
        """
        Initialize daemon manager.
        
        Args:
            log_dir: Directory for log files. Defaults to ~/.praisonai/logs
            max_log_size_mb: Maximum log file size in MB before rotation
        """
        if log_dir is None:
            home = Path.home()
            log_dir = home / ".praisonai" / "logs"
        
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.max_log_size_bytes = int(max_log_size_mb * 1024 * 1024)
    
    def start_daemon(
        self,
        name: str,
        task: str,
        interval: str,
        command: List[str]
    ) -> int:
        """
        Start a daemon process.
        
        Args:
            name: Daemon name
            task: Task description
            interval: Schedule interval
            command: Command to run as list
            
        Returns:
            Process ID
        """
        log_file = self.log_dir / f"{name}.log"
        
        # Open log file - use original working approach
        with open(log_file, 'a') as log:
            log.flush()
            
            # Start process as daemon
            proc = subprocess.Popen(
                command,
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,  # Detach from terminal
                cwd=os.getcwd()
            )
        
        return proc.pid
    
    def start_scheduler_daemon(
        self,
        name: str,
        task: Optional[str] = None,
        recipe_name: Optional[str] = None,
        interval: str = "hourly",
        max_cost: Optional[float] = None,
        timeout: Optional[int] = None,
        max_retries: int = 3
    ) -> int:
        """
        Start a PraisonAI scheduler as daemon.
        
        Args:
            name: Scheduler name
            task: Task to schedule (mutually exclusive with recipe_name)
            recipe_name: Recipe name to schedule (mutually exclusive with task)
            interval: Schedule interval
            max_cost: Maximum cost budget
            timeout: Timeout per execution
            max_retries: Maximum retry attempts
            
        Returns:
            Process ID
        """
        # Build command - use CLI without --daemon flag (original working approach)
        command = [
            sys.executable,
            "-m",
            "praisonai.cli.main",
            "schedule",
        ]
        
        # Add task or recipe
        if recipe_name:
            command.append(recipe_name)  # Recipe name will be auto-detected
        elif task:
            command.append(task)
        else:
            raise ValueError("Either task or recipe_name must be provided")
        
        command.extend(["--interval", interval, "--max-retries", str(max_retries)])
        
        if timeout:
            command.extend(["--timeout", str(timeout)])
        
        if max_cost:
            command.extend(["--max-cost", str(max_cost)])
        
        display_task = recipe_name or task
        return self.start_daemon(name, display_task, interval, command)
    
    def stop_daemon(self, pid: int, timeout: int = 10) -> bool:
        """
        Stop a daemon process gracefully.
        
        Args:
            pid: Process ID
            timeout: Timeout in seconds
            
        Returns:
            True if stopped successfully
        """
        try:
            # Try graceful shutdown first (SIGTERM)
            os.kill(pid, signal.SIGTERM)
            
            # Wait for process to terminate
            import time
            for _ in range(timeout * 10):
                try:
                    os.kill(pid, 0)  # Check if still alive
                    time.sleep(0.1)
                except (OSError, ProcessLookupError):
                    return True  # Process terminated
            
            # Force kill if still alive
            try:
                os.kill(pid, signal.SIGKILL)
                time.sleep(0.2)  # Give it time to die
            except (OSError, ProcessLookupError):
                pass
            
            return True
            
        except (OSError, ProcessLookupError):
            return False
    
    def get_status(self, pid: int) -> Optional[Dict]:
        """
        Get daemon process status.
        
        Args:
            pid: Process ID
            
        Returns:
            Status dictionary or None if not found
        """
        try:
            os.kill(pid, 0)  # Check if process exists
            
            return {
                "pid": pid,
                "is_alive": True
            }
        except (OSError, ProcessLookupError):
            return {
                "pid": pid,
                "is_alive": False
            }
    
    def read_logs(self, name: str, lines: int = 50) -> Optional[str]:
        """
        Read daemon logs.
        
        Args:
            name: Daemon name
            lines: Number of lines to read from end
            
        Returns:
            Log content or None if not found
        """
        log_file = self.log_dir / f"{name}.log"
        
        if not log_file.exists():
            return None
        
        try:
            with open(log_file) as f:
                all_lines = f.readlines()
                return ''.join(all_lines[-lines:])
        except IOError:
            return None
    
    def rotate_log(self, name: str) -> bool:
        """
        Rotate log file if it exceeds max size.
        
        Args:
            name: Daemon name
            
        Returns:
            True if rotated
        """
        log_file = self.log_dir / f"{name}.log"
        
        if not log_file.exists():
            return False
        
        if log_file.stat().st_size > self.max_log_size_bytes:
            # Rotate: rename to .log.1, .log.2, etc.
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            rotated_file = self.log_dir / f"{name}.log.{timestamp}"
            log_file.rename(rotated_file)
            return True
        
        return False
