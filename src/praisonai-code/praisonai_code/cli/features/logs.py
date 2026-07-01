"""
Logs Command for PraisonAI CLI.

Provides log viewing with tail and follow functionality.
"""

import os
import time
import logging
from typing import List, Optional, Generator
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_LOG_DIR = "~/.praison/logs"
DEFAULT_LOG_FILE = "praison.log"


class LogsHandler:
    """
    Handler for viewing and following log files.
    
    Usage:
        handler = LogsHandler()
        
        # View last N lines
        lines = handler.tail("/path/to/log", n=100)
        
        # Follow log file
        for line in handler.follow("/path/to/log"):
            print(line)
    """
    
    def __init__(self, log_dir: Optional[str] = None):
        self.log_dir = os.path.expanduser(log_dir or DEFAULT_LOG_DIR)
        os.makedirs(self.log_dir, exist_ok=True)
    
    def get_default_log_path(self) -> str:
        """Get path to default log file."""
        return os.path.join(self.log_dir, DEFAULT_LOG_FILE)
    
    def tail(self, filepath: Optional[str] = None, n: int = 100) -> List[str]:
        """
        Get last N lines from a log file.
        
        Args:
            filepath: Path to log file (uses default if None)
            n: Number of lines to return
            
        Returns:
            List of log lines
        """
        filepath = filepath or self.get_default_log_path()
        
        if not os.path.exists(filepath):
            return []
        
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                return [line.rstrip("\n") for line in lines[-n:]]
        except Exception as e:
            logger.error(f"Failed to read log file: {e}")
            return []
    
    def follow(
        self, 
        filepath: Optional[str] = None,
        poll_interval: float = 0.5,
    ) -> Generator[str, None, None]:
        """
        Follow a log file (like tail -f).
        
        Args:
            filepath: Path to log file (uses default if None)
            poll_interval: Seconds between polls
            
        Yields:
            New log lines as they appear
        """
        filepath = filepath or self.get_default_log_path()
        
        if not os.path.exists(filepath):
            # Wait for file to be created
            while not os.path.exists(filepath):
                time.sleep(poll_interval)
        
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            # Go to end of file
            f.seek(0, 2)
            
            while True:
                line = f.readline()
                if line:
                    yield line.rstrip("\n")
                else:
                    time.sleep(poll_interval)
    
    def list_logs(self) -> List[str]:
        """List all log files in log directory."""
        if not os.path.exists(self.log_dir):
            return []
        
        logs = []
        for filename in os.listdir(self.log_dir):
            if filename.endswith(".log"):
                logs.append(os.path.join(self.log_dir, filename))
        
        return sorted(logs, key=os.path.getmtime, reverse=True)
    
    def clear_logs(self, filepath: Optional[str] = None) -> bool:
        """Clear a log file."""
        filepath = filepath or self.get_default_log_path()
        
        try:
            with open(filepath, "w") as f:
                f.write("")
            return True
        except Exception as e:
            logger.error(f"Failed to clear log file: {e}")
            return False
    
    def get_log_size(self, filepath: Optional[str] = None) -> int:
        """Get size of log file in bytes."""
        filepath = filepath or self.get_default_log_path()
        
        if not os.path.exists(filepath):
            return 0
        
        return os.path.getsize(filepath)
    
    def search(
        self, 
        pattern: str, 
        filepath: Optional[str] = None,
        max_results: int = 100,
    ) -> List[str]:
        """
        Search log file for pattern.
        
        Args:
            pattern: String to search for
            filepath: Path to log file
            max_results: Maximum number of results
            
        Returns:
            List of matching lines
        """
        filepath = filepath or self.get_default_log_path()
        
        if not os.path.exists(filepath):
            return []
        
        results = []
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if pattern.lower() in line.lower():
                        results.append(line.rstrip("\n"))
                        if len(results) >= max_results:
                            break
        except Exception as e:
            logger.error(f"Failed to search log file: {e}")
        
        return results


def setup_file_logging(
    log_dir: Optional[str] = None,
    log_file: str = DEFAULT_LOG_FILE,
    level: int = logging.INFO,
) -> logging.Handler:
    """
    Set up file logging for the application.
    
    Args:
        log_dir: Directory for log files
        log_file: Log file name
        level: Logging level
        
    Returns:
        The file handler
    """
    log_dir = os.path.expanduser(log_dir or DEFAULT_LOG_DIR)
    os.makedirs(log_dir, exist_ok=True)
    
    filepath = os.path.join(log_dir, log_file)
    
    handler = logging.FileHandler(filepath, encoding="utf-8")
    handler.setLevel(level)
    
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    
    # Add to root logger
    logging.getLogger().addHandler(handler)
    
    return handler
