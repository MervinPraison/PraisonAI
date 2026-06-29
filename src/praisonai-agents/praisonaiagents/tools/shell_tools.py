"""Tools for executing shell commands safely.

This module provides a safe interface for executing shell commands with:
- Timeout control
- Output capture
- Error handling
- Resource limits
"""

import subprocess
import shlex
import logging
import os
import time
import platform
# psutil is imported lazily inside methods that need it
# to avoid hard failure when the package is not installed
from typing import Dict, List, Optional, Union
from ..approval import require_approval

# Minimum grace period (seconds) always granted for stdout/stderr reader threads
# to flush already-written output after the process exits, even when the command
# consumed nearly all of its timeout budget.
_DRAIN_GRACE_SECONDS = 1.0

class ShellTools:
    """Tools for executing shell commands safely."""
    
    def __init__(self):
        """Initialize ShellTools."""
        self._check_dependencies()
    
    def _check_dependencies(self):
        """Check if required packages are installed (lazy — no hard failure)."""
        pass
    
    @require_approval(risk_level="critical")
    def execute_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 30,
        env: Optional[Dict[str, str]] = None,
        max_output_size: int = 10000
    ) -> Dict[str, Union[str, int, bool]]:
        """Execute a shell command safely.
        
        Args:
            command: Command to execute
            cwd: Working directory
            timeout: Maximum execution time in seconds
            env: Environment variables
            max_output_size: Maximum output size in bytes
            
        Returns:
            Dictionary with execution results
        """
        try:
            # Strip wrapping quotes the LLM sometimes adds around the whole command string
            if command and len(command) >= 2 and command[0] == command[-1] and command[0] in ("'", '"'):
                command = command[1:-1]
            # Treat empty-string cwd same as None to avoid subprocess failure
            if not cwd:
                cwd = None
            # Always split command for safety (no shell execution)
            # Use shlex.split with appropriate posix flag
            if platform.system() == 'Windows':
                # Use shlex with posix=False for Windows to handle quotes properly
                command = shlex.split(command, posix=False)
            else:
                command = shlex.split(command)
            # Guard against empty command list (e.g. LLM passed empty string)
            if not command:
                return {"error": "Empty command", "stdout": "", "stderr": "", "exit_code": 1}
            
            # Expand tilde and environment variables in command arguments
            # (shell=False means the shell won't do this for us)
            command = [os.path.expanduser(os.path.expandvars(arg)) for arg in command]
            
            # Expand tilde in cwd (subprocess doesn't do this)
            if cwd:
                cwd = os.path.expanduser(cwd)
                cwd = os.path.expandvars(cwd)  # Also expand $HOME, $USER, etc.
                if not os.path.isdir(cwd):
                    # Fallback: try home directory, then current working directory
                    fallback = os.path.expanduser("~") if os.path.isdir(os.path.expanduser("~")) else os.getcwd()
                    logging.warning(f"Working directory '{cwd}' does not exist, using '{fallback}'")
                    cwd = fallback
            
            # Set up process environment
            process_env = os.environ.copy()
            if env:
                process_env.update(env)
            
            # Start process
            start_time = time.time()
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                shell=False,  # Always use shell=False for security
                env=process_env,
                text=True
            )
            
            try:
                # Read stdout/stderr incrementally so a progress channel (when
                # active) can surface output live while the command runs. Falls
                # back to fully-buffered behaviour when no sink is listening.
                stdout, stderr = self._communicate_streaming(process, timeout)

                # Truncate output if too large (use smart format)
                if len(stdout) > max_output_size:
                    tail_size = min(max_output_size // 5, 500)
                    stdout = stdout[:max_output_size - tail_size] + f"\n...[{len(stdout):,} chars, showing first/last portions]...\n" + stdout[-tail_size:]
                if len(stderr) > max_output_size:
                    tail_size = min(max_output_size // 5, 500)
                    stderr = stderr[:max_output_size - tail_size] + f"\n...[{len(stderr):,} chars, showing first/last portions]...\n" + stderr[-tail_size:]
                
                return {
                    'stdout': stdout,
                    'stderr': stderr,
                    'exit_code': process.returncode,
                    'success': process.returncode == 0,
                    'execution_time': time.time() - start_time
                }
            
            except subprocess.TimeoutExpired:
                # Kill process on timeout
                try:
                    import psutil
                    parent = psutil.Process(process.pid)
                    children = parent.children(recursive=True)
                    for child in children:
                        child.kill()
                    parent.kill()
                except ImportError:
                    # Fallback: kill without psutil
                    process.kill()
                
                return {
                    'stdout': '',
                    'stderr': f'Command timed out after {timeout} seconds',
                    'exit_code': -1,
                    'success': False,
                    'execution_time': timeout
                }
                
        except Exception as e:
            error_msg = f"Error executing command: {str(e)}"
            logging.error(error_msg)
            return {
                'stdout': '',
                'stderr': error_msg,
                'exit_code': -1,
                'success': False,
                'execution_time': 0
            }
    
    def _communicate_streaming(self, process, timeout):
        """Read stdout/stderr line-buffered, emitting live progress.

        Reads both streams concurrently in background threads so a line on
        either stream is surfaced via ``emit_tool_progress`` as soon as it
        arrives. Preserves ``subprocess.communicate`` semantics: returns the
        full ``(stdout, stderr)`` strings and raises ``TimeoutExpired`` on
        timeout. When no progress sink is active, this still buffers the full
        output identically to the previous behaviour (the emit call is a cheap
        no-op).
        """
        import threading

        # Capture the active progress sink (set by the agent's tool-execution
        # loop via a contextvar) in THIS thread, then emit to it directly from
        # the reader threads. Capturing the sink up-front avoids relying on
        # contextvar propagation into the spawned threads.
        _sink = None
        try:
            from ..streaming import events as _stream_events
            _sink = _stream_events._tool_progress_sink.get()
        except Exception:  # streaming module unavailable — no streaming
            _sink = None

        # Stop forwarding progress once the tool has returned (e.g. on timeout),
        # so a still-draining reader thread can never emit after the result.
        stop_emitting = threading.Event()

        def _emit(line, stream_name):
            if _sink is None or stop_emitting.is_set():
                return
            try:
                _sink(_stream_events.StreamEvent(
                    type=_stream_events.StreamEventType.TOOL_PROGRESS,
                    content=line,
                    metadata={"stream": stream_name},
                ))
            except Exception as exc:  # never break command execution on a progress failure
                logging.debug("Tool progress emission failed: %s", exc, exc_info=True)

        stdout_chunks: List[str] = []
        stderr_chunks: List[str] = []
        read_errors: List[BaseException] = []

        def _pump(stream, sink_list, stream_name):
            if stream is None:
                return
            try:
                for line in iter(stream.readline, ''):
                    if line == '':
                        break
                    sink_list.append(line)
                    _emit(line, stream_name)
            except Exception as exc:
                # Surface a failed read (e.g. UnicodeDecodeError) so the caller's
                # error path reports it instead of silently returning a partial
                # prefix as if the command had succeeded.
                read_errors.append(exc)
                logging.debug("Error reading %s stream: %s", stream_name, exc, exc_info=True)
            finally:
                try:
                    stream.close()
                except Exception as exc:
                    logging.debug("Failed to close %s stream: %s", stream_name, exc, exc_info=True)

        t_out = threading.Thread(target=_pump, args=(process.stdout, stdout_chunks, "stdout"), daemon=True)
        t_err = threading.Thread(target=_pump, args=(process.stderr, stderr_chunks, "stderr"), daemon=True)
        t_out.start()
        t_err.start()

        deadline = None if timeout is None else time.monotonic() + timeout
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Disable any further emission before the caller kills the process so
            # no progress is surfaced after the tool has already returned.
            stop_emitting.set()
            # If a reader thread already failed (e.g. UnicodeDecodeError on
            # invalid output bytes), surface that as the real failure instead of
            # masking it with a generic timeout — it is the more actionable error.
            if read_errors:
                raise read_errors[0]
            raise

        # Wait for the readers to drain the pipe buffers before returning,
        # preserving subprocess.communicate()'s "all captured output" semantics.
        # A bounded join keeps the overall call within the original timeout
        # budget: if a background child inherited stdout/stderr and keeps the
        # pipe open after the direct child exits, a reader can stay blocked in
        # readline(). Rather than hang indefinitely, fall back to the configured
        # timeout result once the remaining budget is exhausted. A small minimum
        # grace is always allowed so a command that used most of its timeout can
        # still flush its already-written output.
        for reader in (t_out, t_err):
            if deadline is None:
                remaining = None
            else:
                remaining = max(_DRAIN_GRACE_SECONDS, deadline - time.monotonic())
            reader.join(timeout=remaining)

        if t_out.is_alive() or t_err.is_alive():
            # Readers still blocked on a leaked pipe past the budget — stop
            # emitting and report a timeout so the caller can kill the process.
            stop_emitting.set()
            raise subprocess.TimeoutExpired(process.args, timeout)

        if read_errors:
            raise read_errors[0]

        return "".join(stdout_chunks), "".join(stderr_chunks)

    def list_processes(self) -> List[Dict[str, Union[int, str, float]]]:
        """List running processes with their details.
        
        Returns:
            List of process information dictionaries
        """
        try:
            import psutil
        except ImportError:
            return [{"error": "psutil is required for list_processes. Install with: pip install psutil"}]
        try:
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'username', 'memory_percent', 'cpu_percent']):
                try:
                    pinfo = proc.info
                    # Handle None values for memory_percent and cpu_percent
                    # These can be None for system processes or zombie processes
                    mem_pct = pinfo['memory_percent']
                    cpu_pct = pinfo['cpu_percent']
                    processes.append({
                        'pid': pinfo['pid'],
                        'name': pinfo['name'],
                        'username': pinfo['username'],
                        'memory_percent': round(mem_pct, 2) if mem_pct is not None else 0.0,
                        'cpu_percent': round(cpu_pct, 2) if cpu_pct is not None else 0.0
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            return processes
        except Exception as e:
            error_msg = f"Error listing processes: {str(e)}"
            logging.error(error_msg)
            return []
    
    @require_approval(risk_level="critical")
    def kill_process(
        self,
        pid: int,
        force: bool = False
    ) -> Dict[str, Union[bool, str]]:
        """Kill a process by its PID.
        
        Args:
            pid: Process ID to kill
            force: Whether to force kill (-9)
            
        Returns:
            Dictionary with operation results
        """
        try:
            import psutil
        except ImportError:
            return {
                'success': False,
                'message': 'psutil is required for kill_process. Install with: pip install psutil'
            }
        try:
            process = psutil.Process(pid)
            if force:
                process.kill()  # SIGKILL
            else:
                process.terminate()  # SIGTERM
            
            return {
                'success': True,
                'message': f'Process {pid} killed successfully'
            }
        except psutil.NoSuchProcess:
            return {
                'success': False,
                'message': f'No process found with PID {pid}'
            }
        except psutil.AccessDenied:
            return {
                'success': False,
                'message': f'Access denied to kill process {pid}'
            }
        except Exception as e:
            error_msg = f"Error killing process: {str(e)}"
            logging.error(error_msg)
            return {
                'success': False,
                'message': error_msg
            }
    
    def get_system_info(self) -> Dict[str, Union[float, int, str, Dict]]:
        """Get system information.
        
        Returns:
            Dictionary with system information
        """
        try:
            import psutil
        except ImportError:
            return {"error": "psutil is required for get_system_info. Install with: pip install psutil"}
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            # Use appropriate root path for the OS
            root_path = os.path.abspath(os.sep)
            disk = psutil.disk_usage(root_path)
            
            return {
                'cpu': {
                    'percent': cpu_percent,
                    'cores': psutil.cpu_count(),
                    'physical_cores': psutil.cpu_count(logical=False)
                },
                'memory': {
                    'total': memory.total,
                    'available': memory.available,
                    'percent': memory.percent,
                    'used': memory.used,
                    'free': memory.free
                },
                'disk': {
                    'total': disk.total,
                    'used': disk.used,
                    'free': disk.free,
                    'percent': disk.percent
                },
                'boot_time': psutil.boot_time(),
                'platform': platform.system()
            }
        except Exception as e:
            error_msg = f"Error getting system info: {str(e)}"
            logging.error(error_msg)
            return {}

_shell_tools = ShellTools()
execute_command = _shell_tools.execute_command
list_processes = _shell_tools.list_processes
kill_process = _shell_tools.kill_process
get_system_info = _shell_tools.get_system_info

if __name__ == "__main__":
    # Example usage
    print("\n==================================================")
    print("ShellTools Demonstration")
    print("==================================================\n")
    
    # 1. Execute command
    print("1. Command Execution")
    print("------------------------------")
    # Cross-platform directory listing
    if platform.system() == 'Windows':
        result = execute_command("dir")
    else:
        result = execute_command("ls -la")
    print(f"Success: {result['success']}")
    print(f"Output:\n{result['stdout']}")
    if result['stderr']:
        print(f"Errors:\n{result['stderr']}")
    print(f"Execution time: {result['execution_time']:.2f}s")
    print()
    
    # 2. System Information
    print("2. System Information")
    print("------------------------------")
    info = get_system_info()
    print(f"CPU Usage: {info['cpu']['percent']}%")
    print(f"Memory Usage: {info['memory']['percent']}%")
    print(f"Disk Usage: {info['disk']['percent']}%")
    print(f"Platform: {info['platform']}")
    print()
    
    # 3. Process List
    print("3. Process List (top 5 by CPU)")
    print("------------------------------")
    processes = sorted(
        list_processes(),
        key=lambda x: x['cpu_percent'],
        reverse=True
    )[:5]
    for proc in processes:
        print(f"PID: {proc['pid']}, Name: {proc['name']}, CPU: {proc['cpu_percent']}%")
    print()
    
    print("\n==================================================")
    print("Demonstration Complete")
    print("==================================================")
