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
from typing import Dict, List, Optional, Union

class ShellTools:
    """Tools for executing shell commands safely."""
    
    def __init__(self):
        """Initialize ShellTools."""
        self._check_dependencies()
    
    def _check_dependencies(self):
        """Check if required packages are installed."""
        try:
            import psutil
        except ImportError:
            raise ImportError(
                "Required package not available. Please install: psutil\n"
                "Run: pip install psutil"
            )
    
    def execute_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 30,
        shell: bool = False,
        env: Optional[Dict[str, str]] = None,
        max_output_size: int = 10000
    ) -> Dict[str, Union[str, int, bool]]:
        """Execute a shell command safely.
        
        Args:
            command: Command to execute
            cwd: Working directory
            timeout: Maximum execution time in seconds
            shell: Whether to run command in shell
            env: Environment variables
            max_output_size: Maximum output size in bytes
            
        Returns:
            Dictionary with execution results
        """
        try:
            # Split command if not using shell
            if not shell:
                command = shlex.split(command)
            
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
                shell=shell,
                env=process_env,
                text=True
            )
            
            try:
                # Wait for process with timeout
                stdout, stderr = process.communicate(timeout=timeout)
                
                # Truncate output if too large
                if len(stdout) > max_output_size:
                    stdout = stdout[:max_output_size] + "...[truncated]"
                if len(stderr) > max_output_size:
                    stderr = stderr[:max_output_size] + "...[truncated]"
                
                return {
                    'stdout': stdout,
                    'stderr': stderr,
                    'exit_code': process.returncode,
                    'success': process.returncode == 0,
                    'execution_time': time.time() - start_time
                }
            
            except subprocess.TimeoutExpired:
                # Kill process on timeout
                parent = psutil.Process(process.pid)
                children = parent.children(recursive=True)
                for child in children:
                    child.kill()
                parent.kill()
                
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
    
    def list_processes(self) -> List[Dict[str, Union[int, str, float]]]:
        """List running processes with their details.
        
        Returns:
            List of process information dictionaries
        """
        try:
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'username', 'memory_percent', 'cpu_percent']):
                try:
                    pinfo = proc.info
                    processes.append({
                        'pid': pinfo['pid'],
                        'name': pinfo['name'],
                        'username': pinfo['username'],
                        'memory_percent': round(pinfo['memory_percent'], 2),
                        'cpu_percent': round(pinfo['cpu_percent'], 2)
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            return processes
        except Exception as e:
            error_msg = f"Error listing processes: {str(e)}"
            logging.error(error_msg)
            return []
    
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
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
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
                'platform': os.uname().sysname
            }
        except Exception as e:
            error_msg = f"Error getting system info: {str(e)}"
            logging.error(error_msg)
            return {}

# Create instance for direct function access
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
