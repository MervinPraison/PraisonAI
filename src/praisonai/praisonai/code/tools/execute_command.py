"""
Execute Command Tool for PraisonAI Code.

Provides functionality to execute shell commands safely.
"""

import os
import subprocess
import shlex
from typing import Optional, Dict, Any


# Commands that are generally safe to auto-run
SAFE_COMMANDS = {
    'ls', 'dir', 'pwd', 'echo', 'cat', 'head', 'tail', 'wc',
    'grep', 'find', 'which', 'whereis', 'type', 'file',
    'date', 'whoami', 'hostname', 'uname',
    'python', 'python3', 'node', 'npm', 'npx', 'pip', 'pip3',
    'git', 'cargo', 'go', 'ruby', 'java', 'javac',
}

# Commands that should never be auto-run
DANGEROUS_COMMANDS = {
    'rm', 'rmdir', 'del', 'format', 'mkfs',
    'dd', 'shred', 'chmod', 'chown', 'chgrp',
    'kill', 'killall', 'pkill',
    'shutdown', 'reboot', 'halt', 'poweroff',
    'sudo', 'su', 'doas',
    'curl', 'wget', 'ssh', 'scp', 'rsync',
    'mv', 'cp',  # Can be destructive
}


def execute_command(
    command: str,
    cwd: Optional[str] = None,
    workspace: Optional[str] = None,
    timeout: int = 120,
    capture_output: bool = True,
    shell: bool = True,
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Execute a shell command and return the result.
    
    This tool executes shell commands with safety checks and output capture.
    
    Args:
        command: The command to execute
        cwd: Working directory for the command
        workspace: Workspace root (for security validation)
        timeout: Command timeout in seconds
        capture_output: Whether to capture stdout/stderr
        shell: Whether to run through shell
        env: Additional environment variables
        
    Returns:
        Dictionary with:
        - success: bool
        - exit_code: int
        - stdout: str
        - stderr: str
        - command: str
        - error: str (if success is False)
        
    Example:
        >>> result = execute_command("python --version")
        >>> print(result['stdout'])
    """
    if not command or not command.strip():
        return {
            'success': False,
            'error': "Empty command",
            'command': command,
            'exit_code': -1,
            'stdout': '',
            'stderr': '',
        }
    
    # Resolve working directory
    if cwd:
        if workspace and not os.path.isabs(cwd):
            work_dir = os.path.abspath(os.path.join(workspace, cwd))
        else:
            work_dir = os.path.abspath(cwd)
    elif workspace:
        work_dir = workspace
    else:
        work_dir = os.getcwd()
    
    # Validate working directory exists
    if not os.path.isdir(work_dir):
        return {
            'success': False,
            'error': f"Working directory not found: {cwd}",
            'command': command,
            'exit_code': -1,
            'stdout': '',
            'stderr': '',
        }
    
    # Prepare environment
    cmd_env = os.environ.copy()
    if env:
        cmd_env.update(env)
    
    # Set PAGER to cat to avoid interactive pagers
    cmd_env['PAGER'] = 'cat'
    
    try:
        # Execute command
        if shell:
            result = subprocess.run(
                command,
                shell=True,
                cwd=work_dir,
                capture_output=capture_output,
                timeout=timeout,
                env=cmd_env,
                text=True,
            )
        else:
            # Parse command for non-shell execution
            args = shlex.split(command)
            result = subprocess.run(
                args,
                cwd=work_dir,
                capture_output=capture_output,
                timeout=timeout,
                env=cmd_env,
                text=True,
            )
        
        return {
            'success': result.returncode == 0,
            'exit_code': result.returncode,
            'stdout': result.stdout if capture_output else '',
            'stderr': result.stderr if capture_output else '',
            'command': command,
            'cwd': work_dir,
        }
        
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'error': f"Command timed out after {timeout} seconds",
            'command': command,
            'exit_code': -1,
            'stdout': '',
            'stderr': '',
        }
    except FileNotFoundError as e:
        return {
            'success': False,
            'error': f"Command not found: {str(e)}",
            'command': command,
            'exit_code': -1,
            'stdout': '',
            'stderr': '',
        }
    except PermissionError:
        return {
            'success': False,
            'error': "Permission denied",
            'command': command,
            'exit_code': -1,
            'stdout': '',
            'stderr': '',
        }
    except Exception as e:
        return {
            'success': False,
            'error': f"Error executing command: {str(e)}",
            'command': command,
            'exit_code': -1,
            'stdout': '',
            'stderr': '',
        }


def is_safe_command(command: str) -> bool:
    """
    Check if a command is considered safe to auto-run.
    
    Args:
        command: The command to check
        
    Returns:
        True if the command is considered safe
    """
    if not command:
        return False
    
    # Get the base command (first word)
    parts = shlex.split(command)
    if not parts:
        return False
    
    base_cmd = os.path.basename(parts[0]).lower()
    
    # Check against dangerous commands
    if base_cmd in DANGEROUS_COMMANDS:
        return False
    
    # Check against safe commands
    if base_cmd in SAFE_COMMANDS:
        return True
    
    # Default to unsafe
    return False


def get_command_info(command: str) -> Dict[str, Any]:
    """
    Get information about a command without executing it.
    
    Args:
        command: The command to analyze
        
    Returns:
        Dictionary with command analysis
    """
    if not command:
        return {
            'valid': False,
            'error': "Empty command",
        }
    
    try:
        parts = shlex.split(command)
        base_cmd = parts[0] if parts else ''
        
        return {
            'valid': True,
            'base_command': base_cmd,
            'arguments': parts[1:] if len(parts) > 1 else [],
            'is_safe': is_safe_command(command),
            'is_dangerous': os.path.basename(base_cmd).lower() in DANGEROUS_COMMANDS,
        }
    except ValueError as e:
        return {
            'valid': False,
            'error': f"Invalid command syntax: {str(e)}",
        }


def run_python(
    code: str,
    cwd: Optional[str] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    """
    Execute Python code and return the result.
    
    Args:
        code: Python code to execute
        cwd: Working directory
        timeout: Execution timeout
        
    Returns:
        Dictionary with execution result
    """
    # Create a temporary command to run the code
    import sys
    python_cmd = sys.executable
    
    # Escape the code for command line
    escaped_code = code.replace('\\', '\\\\').replace('"', '\\"')
    command = f'{python_cmd} -c "{escaped_code}"'
    
    return execute_command(
        command=command,
        cwd=cwd,
        timeout=timeout,
    )
