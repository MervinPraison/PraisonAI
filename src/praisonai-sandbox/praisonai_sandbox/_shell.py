"""Shared utilities for safe shell command handling across sandbox backends."""

import shlex
from typing import List, Union


def build_argv(command: Union[str, List[str]], shell: bool = False) -> List[str]:
    """
    Safely build command argv with explicit shell control.
    
    Args:
        command: String command or list of arguments
        shell: If True, explicitly use shell. If False, parse safely without shell.
    
    Returns:
        List of command arguments safe for subprocess execution
        
    Security:
        - shell=False (default): No shell injection possible
        - shell=True: Caller explicitly opts into shell evaluation
    """
    if isinstance(command, str):
        if not shell:
            # Safe parse: convert string to argv without invoking shell
            return shlex.split(command)
        else:
            # Explicit shell: caller has opted in
            return ["sh", "-c", command]
    else:
        # List input
        cmd_list = list(command)
        if shell:
            # Quote each element when combining into shell command
            quoted_cmd = " ".join(shlex.quote(arg) for arg in cmd_list)
            return ["sh", "-c", quoted_cmd]
        else:
            # Direct argv execution - no shell
            return cmd_list
