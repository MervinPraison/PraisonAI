"""Tools for executing Agent Skills scripts.

This module provides tools for running scripts bundled with Agent Skills.
Skills are modular packages that extend agent capabilities through SKILL.md
files and optional scripts.

Usage:
    from praisonaiagents.tools import run_skill_script
    result = run_skill_script("./my-skill/scripts/skill.py", "./data.csv")
"""

import subprocess
import os
import logging


class SkillTools:
    """Tools for executing Agent Skills scripts."""
    
    def __init__(self, working_directory: str = None):
        """Initialize SkillTools.
        
        Args:
            working_directory: Base directory for resolving relative paths.
                              Defaults to current working directory.
        """
        self._working_directory = working_directory or os.getcwd()
    
    @property
    def working_directory(self) -> str:
        """Get the working directory for path resolution."""
        return self._working_directory
    
    @working_directory.setter
    def working_directory(self, value: str):
        """Set the working directory for path resolution."""
        self._working_directory = value
    
    def run_skill_script(
        self,
        script_path: str,
        args: str = "",
        timeout: int = 60
    ) -> str:
        """
        Execute a skill script from a skill's scripts/ directory.
        
        Args:
            script_path: Path to the script file (e.g., ./csv-analyzer/scripts/skill.py)
            args: Arguments to pass to the script (e.g., file path to analyze)
            timeout: Maximum execution time in seconds (default: 60)
            
        Returns:
            The output from running the script, or error message if failed
        """
        try:
            # Resolve the script path
            script_path = os.path.expanduser(script_path)
            if not os.path.isabs(script_path):
                script_path = os.path.join(self._working_directory, script_path)
            script_path = os.path.abspath(script_path)
            
            if not os.path.exists(script_path):
                return f"Error: Script not found at {script_path}"
            
            # Resolve args paths relative to working directory
            resolved_args = []
            if args:
                for arg in args.split():
                    # Skip flags
                    if arg.startswith('-'):
                        resolved_args.append(arg)
                        continue
                    
                    # Try to resolve as a path relative to working directory
                    potential_path = os.path.join(self._working_directory, arg)
                    if os.path.exists(potential_path):
                        resolved_args.append(os.path.abspath(potential_path))
                    elif os.path.isabs(arg) and os.path.exists(arg):
                        # Already absolute and exists
                        resolved_args.append(arg)
                    else:
                        # Keep original arg if path doesn't exist
                        resolved_args.append(arg)
            
            # Determine how to run the script based on extension
            ext = os.path.splitext(script_path)[1].lower()
            
            if ext == '.py':
                cmd = ['python', script_path] + resolved_args
            elif ext == '.sh':
                cmd = ['bash', script_path] + resolved_args
            elif ext == '.js':
                cmd = ['node', script_path] + resolved_args
            else:
                # Try to run directly
                cmd = [script_path] + resolved_args
            
            logging.debug(f"Running skill script: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self._working_directory
            )
            
            output = result.stdout
            if result.stderr:
                output += f"\nStderr: {result.stderr}"
            if result.returncode != 0:
                output += f"\nExit code: {result.returncode}"
            
            return output if output else "Script executed successfully (no output)"
            
        except subprocess.TimeoutExpired:
            return f"Error: Script execution timed out after {timeout} seconds"
        except FileNotFoundError as e:
            return f"Error: Could not find interpreter or script: {str(e)}"
        except PermissionError as e:
            return f"Error: Permission denied: {str(e)}"
        except Exception as e:
            return f"Error executing script: {str(e)}"
    
    def read_skill_file(
        self,
        skill_path: str,
        file_path: str,
        encoding: str = 'utf-8'
    ) -> str:
        """
        Read a file from a skill directory.
        
        Args:
            skill_path: Path to the skill directory (e.g., ./csv-analyzer)
            file_path: Relative path within the skill (e.g., SKILL.md, scripts/skill.py)
            encoding: File encoding (default: utf-8)
            
        Returns:
            File contents or error message
        """
        try:
            # Resolve skill path
            skill_path = os.path.expanduser(skill_path)
            if not os.path.isabs(skill_path):
                skill_path = os.path.join(self._working_directory, skill_path)
            skill_path = os.path.abspath(skill_path)
            
            if not os.path.exists(skill_path):
                return f"Error: Skill directory not found at {skill_path}"
            
            if not os.path.isdir(skill_path):
                return f"Error: {skill_path} is not a directory"
            
            # Resolve file path within skill
            full_path = os.path.join(skill_path, file_path)
            full_path = os.path.abspath(full_path)
            
            # Security check: ensure file is within skill directory
            if not full_path.startswith(skill_path):
                return f"Error: Path traversal detected - {file_path} is outside skill directory"
            
            if not os.path.exists(full_path):
                return f"Error: File not found at {full_path}"
            
            with open(full_path, 'r', encoding=encoding) as f:
                return f.read()
                
        except UnicodeDecodeError as e:
            return f"Error: Could not decode file with {encoding} encoding: {str(e)}"
        except PermissionError as e:
            return f"Error: Permission denied reading file: {str(e)}"
        except Exception as e:
            return f"Error reading skill file: {str(e)}"
    
    def list_skill_scripts(self, skill_path: str) -> str:
        """
        List available scripts in a skill's scripts/ directory.
        
        Args:
            skill_path: Path to the skill directory
            
        Returns:
            JSON string with list of scripts or error message
        """
        import json
        
        try:
            # Resolve skill path
            skill_path = os.path.expanduser(skill_path)
            if not os.path.isabs(skill_path):
                skill_path = os.path.join(self._working_directory, skill_path)
            skill_path = os.path.abspath(skill_path)
            
            if not os.path.exists(skill_path):
                return f"Error: Skill directory not found at {skill_path}"
            
            scripts_dir = os.path.join(skill_path, "scripts")
            if not os.path.exists(scripts_dir):
                return json.dumps({"scripts": [], "message": "No scripts/ directory found"})
            
            scripts = []
            for item in os.listdir(scripts_dir):
                item_path = os.path.join(scripts_dir, item)
                if os.path.isfile(item_path):
                    ext = os.path.splitext(item)[1].lower()
                    if ext in ['.py', '.sh', '.js', '.rb', '.pl']:
                        scripts.append({
                            "name": item,
                            "path": os.path.join("scripts", item),
                            "type": ext[1:]  # Remove the dot
                        })
            
            return json.dumps({"scripts": scripts}, indent=2)
            
        except Exception as e:
            return f"Error listing skill scripts: {str(e)}"


# Create default instance for direct function access
_skill_tools = SkillTools()

def run_skill_script(script_path: str, args: str = "", timeout: int = 60) -> str:
    """
    Execute a skill script from a skill's scripts/ directory.
    
    Args:
        script_path: Path to the script file (e.g., ./csv-analyzer/scripts/script.py)
        args: Arguments to pass to the script (e.g., file path to analyze)
        timeout: Maximum execution time in seconds (default: 60)
        
    Returns:
        The output from running the script, or error message if failed
    """
    return _skill_tools.run_skill_script(script_path, args, timeout)


def read_skill_file(skill_path: str, file_path: str, encoding: str = 'utf-8') -> str:
    """
    Read a file from a skill directory.
    
    Args:
        skill_path: Path to the skill directory (e.g., ./csv-analyzer)
        file_path: Relative path within the skill (e.g., SKILL.md, scripts/script.py)
        encoding: File encoding (default: utf-8)
        
    Returns:
        File contents or error message
    """
    return _skill_tools.read_skill_file(skill_path, file_path, encoding)


def list_skill_scripts(skill_path: str) -> str:
    """
    List available scripts in a skill's scripts/ directory.
    
    Args:
        skill_path: Path to the skill directory
        
    Returns:
        JSON string with list of scripts or error message
    """
    return _skill_tools.list_skill_scripts(skill_path)


def create_skill_tools(working_directory: str = None) -> SkillTools:
    """
    Create a SkillTools instance with a specific working directory.
    
    This is useful when you need to resolve paths relative to a specific
    directory rather than the current working directory.
    
    Args:
        working_directory: Base directory for resolving relative paths
        
    Returns:
        SkillTools instance
    """
    return SkillTools(working_directory)
