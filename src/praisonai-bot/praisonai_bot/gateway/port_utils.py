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
    
    # Try to find the process using the port. Wrapped in a broad except so a
    # diagnostic can never break startup: on psutil 7 'connections' was removed
    # from the valid process_iter attrs and raises ValueError, so the callers'
    # actionable collision message would otherwise be unreachable.
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                # psutil >=6 renamed Process.connections() to net_connections();
                # fall back to the old name on older releases.
                get_conns = getattr(proc, 'net_connections', None) or proc.connections
                connections = get_conns(kind='inet')
                for conn in connections:
                    if (hasattr(conn, 'laddr') and conn.laddr and
                        conn.laddr.port == port and
                        conn.laddr.ip in ('0.0.0.0', '127.0.0.1', host)):
                        return False, proc.info['pid']
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception:
        # psutil missing or an unexpected failure: fall through and let the
        # caller render its generic collision guidance rather than crashing.
        pass
    
    return False, None


def _process_create_time(pid: int) -> Optional[float]:
    """Return a process start-time fingerprint, or None if unavailable.

    PIDs are recycled. Without a start-time fingerprint, a recycled PID is
    indistinguishable from the original and ``stop`` would signal whatever
    process inherited the number.
    """
    try:
        import psutil
        return psutil.Process(pid).create_time()
    except Exception:
        # psutil missing, process already exited, or access denied: fall back
        # to a PID-only lock rather than crashing.
        return None


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
                        existing_create_time = None
                        if len(lines) >= 5 and lines[4]:
                            try:
                                existing_create_time = float(lines[4])
                            except ValueError:
                                existing_create_time = None
                        
                        # A recycled PID must not be mistaken for the original
                        # holder: if the fingerprint no longer matches, the
                        # original process is gone even though the number is live.
                        if (self._is_process_running(existing_pid)
                                and self._create_time_matches(existing_pid, existing_create_time)):
                            return False  # Lock held by active process
                        
                        # Process dead or recycled PID, remove stale lock
                        self._remove_stale_lock()
            except (ValueError, OSError):
                # Corrupted lock file, remove it
                self._remove_stale_lock()
        
        # Write new lock atomically to avoid race condition. The create-time
        # fingerprint lets a later stop/status distinguish us from a recycled PID.
        create_time = _process_create_time(current_pid)
        create_time_line = "" if create_time is None else repr(create_time)
        lock_content = f"{current_pid}\n{host}\n{port}\n{int(time.time())}\n{create_time_line}\n"
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
            create_time = None
            if len(lines) >= 5 and lines[4]:
                try:
                    create_time = float(lines[4])
                except ValueError:
                    create_time = None
            
            return {
                'pid': pid,
                'host': host,
                'port': port,
                'timestamp': timestamp,
                'create_time': create_time,
                # Alive AND still the process we recorded: a recycled PID is not
                # the original gateway even though the number is running.
                'is_running': (self._is_process_running(pid)
                               and self._create_time_matches(pid, create_time)),
            }
        except (ValueError, OSError):
            return None
    
    def _create_time_matches(self, pid: int, expected_create_time: Optional[float]) -> bool:
        """Return True if pid's start time matches the recorded fingerprint.

        A missing fingerprint (older lock or psutil unavailable) is treated as a
        match so behaviour degrades to the previous PID-only check rather than
        wrongly reclaiming a live lock.
        """
        if expected_create_time is None:
            return True
        actual = _process_create_time(pid)
        if actual is None:
            return True
        return abs(actual - expected_create_time) < 1e-3
    
    def _lock_is_ours(self) -> bool:
        """Return True if the current lock file identifies a live process.

        Used before a stop/refuse decision so a recycled PID is never mistaken
        for the original gateway.
        """
        info = self.get_lock_info()
        return bool(info and info.get('is_running'))
    
    def _is_process_running(self, pid: int) -> bool:
        """Check if a process with given PID is running."""
        try:
            # Send signal 0 to check if process exists
            os.kill(pid, 0)
            return True
        except PermissionError:
            # The process exists and belongs to another user. "I may not signal
            # it" is not "it is not running" — treating it as dead deletes a live
            # gateway's lock and admits a second poller for the same bot token.
            return True
        except (OSError, ProcessLookupError, SystemError, ValueError):
            # On Windows, os.kill(pid, 0) can raise SystemError; treat any
            # other failure as "not running" so status checks never propagate.
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