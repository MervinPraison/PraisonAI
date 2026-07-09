"""
Port checking and PID lock utilities for gateway collision prevention.

Provides utilities to check if ports are in use and manage single-instance locks.
"""

from __future__ import annotations

import os
import socket
import time
from pathlib import Path
from typing import Optional, Tuple


def is_port_in_use(host: str = "127.0.0.1", port: int = 8765) -> bool:
    """Check if a port is already in use.
    
    Args:
        host: Host to check (default: 127.0.0.1)
        port: Port to check (default: 8765)
        
    Returns:
        True if port is in use, False otherwise
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex((host, port)) == 0


def check_port_available(host: str, port: int) -> Tuple[bool, Optional[int]]:
    """Check if a port is available and attempt to find the process using it.
    
    Args:
        host: Host to check
        port: Port to check
        
    Returns:
        Tuple of (is_available, pid_using_port)
    """
    if not is_port_in_use(host, port):
        return True, None
    
    # Try to find the process using the port
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name', 'connections']):
            try:
                connections = proc.info['connections']
                if connections:
                    for conn in connections:
                        if (hasattr(conn, 'laddr') and conn.laddr and 
                            conn.laddr.port == port and 
                            conn.laddr.ip in ('0.0.0.0', '127.0.0.1', host)):
                            return False, proc.info['pid']
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except ImportError:
        # psutil not available, can't identify process
        pass
    
    return False, None


class GatewayPIDLock:
    """Manages PID lock file for single-instance gateway enforcement."""
    
    def __init__(self, lock_dir: Optional[Path] = None, host: str = "127.0.0.1", port: int = 8765):
        """Initialize PID lock manager.
        
        Args:
            lock_dir: Directory for lock file (default: ~/.praisonai/)
            host: Gateway host
            port: Gateway port
        """
        self.lock_dir = lock_dir or Path.home() / ".praisonai"
        # Make lock file specific to host and port to allow multiple instances
        safe_host = host.replace(":", "_").replace(".", "_")
        self.lock_file = self.lock_dir / f"gateway-{safe_host}-{port}.pid"
        self.lock_dir.mkdir(exist_ok=True)
    
    def acquire_lock(self, host: str, port: int) -> bool:
        """Acquire the PID lock for the gateway.
        
        Args:
            host: Gateway host
            port: Gateway port
            
        Returns:
            True if lock acquired successfully, False if conflict
        """
        current_pid = os.getpid()
        
        # Check if lock file exists
        if self.lock_file.exists():
            try:
                lock_content = self.lock_file.read_text().strip()
                if lock_content:
                    lines = lock_content.split('\n')
                    if lines:
                        existing_pid = int(lines[0])
                        
                        # Check if process is still running
                        if self._is_process_running(existing_pid):
                            return False  # Lock held by active process
                        
                        # Process dead, remove stale lock
                        self._remove_stale_lock()
            except (ValueError, OSError):
                # Corrupted lock file, remove it
                self._remove_stale_lock()
        
        # Write new lock atomically to avoid race condition
        lock_content = f"{current_pid}\n{host}\n{port}\n{int(time.time())}\n"
        try:
            # Use a temporary file and atomic rename to prevent race conditions
            temp_lock_file = self.lock_file.with_suffix(".tmp")
            temp_lock_file.write_text(lock_content)
            temp_lock_file.replace(self.lock_file)
            return True
        except OSError:
            return False
    
    def release_lock(self) -> None:
        """Release the PID lock."""
        try:
            if self.lock_file.exists():
                self.lock_file.unlink()
        except OSError:
            pass
    
    def get_lock_info(self) -> Optional[dict]:
        """Get information about the current lock.
        
        Returns:
            Dict with lock info or None if no valid lock
        """
        if not self.lock_file.exists():
            return None
        
        try:
            lock_content = self.lock_file.read_text().strip()
            if not lock_content:
                return None
            
            lines = lock_content.split('\n')
            if len(lines) < 4:
                return None
            
            pid = int(lines[0])
            host = lines[1]
            port = int(lines[2])
            timestamp = int(lines[3])
            
            return {
                'pid': pid,
                'host': host,
                'port': port,
                'timestamp': timestamp,
                'is_running': self._is_process_running(pid)
            }
        except (ValueError, OSError):
            return None
    
    def _is_process_running(self, pid: int) -> bool:
        """Check if a process with given PID is running."""
        try:
            # Send signal 0 to check if process exists
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError, SystemError, ValueError):
            # On Windows, os.kill(pid, 0) can raise SystemError; treat any
            # failure as "not running" so status checks never propagate.
            return False
    
    def _remove_stale_lock(self) -> None:
        """Remove stale lock file."""
        try:
            if self.lock_file.exists():
                self.lock_file.unlink()
        except OSError:
            pass


def format_collision_error(host: str, port: int, lock_info: Optional[dict] = None) -> str:
    """Format a user-friendly error message for port collisions.
    
    Args:
        host: Gateway host
        port: Gateway port
        lock_info: Optional lock information
        
    Returns:
        Formatted error message with actionable guidance
    """
    port_desc = f"{host}:{port}" if host != "127.0.0.1" else f"port {port}"
    
    lines = [
        f"Error: Gateway {port_desc} is already in use.",
        ""
    ]
    
    if lock_info and lock_info.get('is_running'):
        pid = lock_info['pid']
        lines.extend([
            f"  Another gateway may be running (PID {pid}).",
            f"  Stop it:  praisonai gateway stop",
            f"  Or use a different port:  GATEWAY_PORT={port + 1} praisonai gateway start",
            "",
            "  Only ONE gateway process should poll each Telegram bot token.",
        ])
    else:
        lines.extend([
            "  Another process may be using this port.",
            f"  Use a different port:  praisonai gateway start --port {port + 1}",
            f"  Or set environment variable:  GATEWAY_PORT={port + 1}",
        ])
    
    return "\n".join(lines)