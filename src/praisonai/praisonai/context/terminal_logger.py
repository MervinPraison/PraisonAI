"""
Terminal Logger for Dynamic Context Discovery.

Captures shell command outputs to artifacts for later retrieval.
Implements TerminalLoggerProtocol.

Usage:
    from praisonai.context import TerminalLogger
    
    logger = TerminalLogger(base_dir="~/.praison/runs")
    
    # Log a command execution
    ref = logger.log_command(
        command="ls -la",
        output="total 100\ndrwxr-xr-x ...",
        exit_code=0,
        agent_id="agent1",
        run_id="run123"
    )
    
    # Tail the session log
    recent = logger.tail_session(agent_id="agent1", run_id="run123", lines=50)
"""

import json
import re
import time
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from praisonaiagents.context.artifacts import (
    ArtifactRef,
    GrepMatch,
    compute_checksum,
)

logger = logging.getLogger(__name__)


class TerminalLogger:
    """
    Filesystem-backed terminal session logging.
    
    Captures shell command executions to log files for later retrieval.
    
    Directory layout:
    ~/.praison/runs/{run_id}/terminal/{agent_id}.log
    
    Log format (per command):
    === COMMAND [timestamp] ===
    $ command
    --- OUTPUT (exit_code) ---
    output content
    === END ===
    
    Features:
    - Append-only logging
    - Structured command/output format
    - Efficient tail/grep operations
    """
    
    def __init__(self, base_dir: str = "~/.praison/runs"):
        """
        Initialize the terminal logger.
        
        Args:
            base_dir: Base directory for terminal logs
        """
        self.base_dir = Path(base_dir).expanduser().resolve()
    
    def _get_log_path(self, run_id: str, agent_id: str) -> Path:
        """Get the path to the terminal log file."""
        terminal_dir = self.base_dir / run_id / "terminal"
        terminal_dir.mkdir(parents=True, exist_ok=True)
        return terminal_dir / f"{agent_id}.log"
    
    def log_command(
        self,
        command: str,
        output: str,
        exit_code: int,
        agent_id: str,
        run_id: str,
    ) -> ArtifactRef:
        """
        Log a command execution.
        
        Args:
            command: The command that was executed
            output: Combined stdout/stderr output
            exit_code: Command exit code
            agent_id: ID of the agent
            run_id: ID of the run/session
            
        Returns:
            ArtifactRef to the logged output
        """
        log_path = self._get_log_path(run_id, agent_id)
        timestamp = datetime.now().isoformat()
        
        # Format the log entry
        entry = (
            f"\n=== COMMAND [{timestamp}] ===\n"
            f"$ {command}\n"
            f"--- OUTPUT (exit_code={exit_code}) ---\n"
            f"{output}\n"
            f"=== END ===\n"
        )
        
        # Append to log
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry)
        
        # Get file stats
        stat = log_path.stat()
        
        return ArtifactRef(
            path=str(log_path),
            summary=f"Terminal log: {command[:50]}... (exit={exit_code})",
            size_bytes=stat.st_size,
            mime_type="text/plain",
            checksum="",  # Don't compute for append-only logs
            created_at=time.time(),
            artifact_id=f"terminal_{agent_id}",
            agent_id=agent_id,
            run_id=run_id,
            tool_name="shell",
        )
    
    def get_session_ref(self, agent_id: str, run_id: str) -> Optional[ArtifactRef]:
        """
        Get artifact reference for terminal session log.
        
        Args:
            agent_id: ID of the agent
            run_id: ID of the run/session
            
        Returns:
            ArtifactRef if session exists, None otherwise
        """
        log_path = self._get_log_path(run_id, agent_id)
        
        if not log_path.exists():
            return None
        
        stat = log_path.stat()
        
        # Count commands
        command_count = 0
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("=== COMMAND"):
                    command_count += 1
        
        return ArtifactRef(
            path=str(log_path),
            summary=f"Terminal session with {command_count} commands",
            size_bytes=stat.st_size,
            mime_type="text/plain",
            checksum=compute_checksum(log_path.read_bytes()),
            created_at=stat.st_mtime,
            artifact_id=f"terminal_{agent_id}",
            agent_id=agent_id,
            run_id=run_id,
        )
    
    def tail_session(
        self,
        agent_id: str,
        run_id: str,
        lines: int = 100,
    ) -> str:
        """
        Get last N lines from terminal session.
        
        Args:
            agent_id: ID of the agent
            run_id: ID of the run/session
            lines: Number of lines to return
            
        Returns:
            String containing the last N lines
        """
        log_path = self._get_log_path(run_id, agent_id)
        
        if not log_path.exists():
            return "No terminal session found."
        
        # Efficient tail
        with open(log_path, "rb") as f:
            f.seek(0, 2)
            file_size = f.tell()
            
            chunk_size = 8192
            found_lines = []
            position = file_size
            
            while position > 0 and len(found_lines) < lines + 1:
                read_size = min(chunk_size, position)
                position -= read_size
                f.seek(position)
                chunk = f.read(read_size).decode("utf-8", errors="replace")
                
                chunk_lines = chunk.split("\n")
                if found_lines:
                    chunk_lines[-1] += found_lines[0]
                    found_lines = chunk_lines + found_lines[1:]
                else:
                    found_lines = chunk_lines
            
            return "\n".join(found_lines[-lines:])
    
    def grep_session(
        self,
        pattern: str,
        agent_id: str,
        run_id: str,
        max_matches: int = 50,
    ) -> List[GrepMatch]:
        """
        Search terminal session for pattern.
        
        Args:
            pattern: Regex pattern to search for
            agent_id: ID of the agent
            run_id: ID of the run/session
            max_matches: Maximum matches to return
            
        Returns:
            List of GrepMatch objects
        """
        log_path = self._get_log_path(run_id, agent_id)
        
        if not log_path.exists():
            return []
        
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            regex = re.compile(re.escape(pattern), re.IGNORECASE)
        
        matches = []
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        
        for i, line in enumerate(all_lines):
            if regex.search(line):
                start = max(0, i - 2)
                end = min(len(all_lines), i + 3)
                
                match = GrepMatch(
                    line_number=i + 1,
                    line_content=line.rstrip("\n"),
                    context_before=[ln.rstrip("\n") for ln in all_lines[start:i]],
                    context_after=[ln.rstrip("\n") for ln in all_lines[i+1:end]],
                )
                matches.append(match)
                
                if len(matches) >= max_matches:
                    break
        
        return matches
    
    def get_commands(
        self,
        agent_id: str,
        run_id: str,
        last_n: Optional[int] = None,
    ) -> List[dict]:
        """
        Get executed commands from session.
        
        Args:
            agent_id: ID of the agent
            run_id: ID of the run/session
            last_n: Return only last N commands (None for all)
            
        Returns:
            List of command dicts with command, output, exit_code, timestamp
        """
        log_path = self._get_log_path(run_id, agent_id)
        
        if not log_path.exists():
            return []
        
        commands = []
        current_command = None
        current_output_lines = []
        in_output = False
        
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("=== COMMAND"):
                    # Extract timestamp
                    match = re.search(r'\[(.*?)\]', line)
                    timestamp = match.group(1) if match else ""
                    current_command = {"timestamp": timestamp}
                    in_output = False
                    current_output_lines = []
                elif line.startswith("$ ") and current_command:
                    current_command["command"] = line[2:].rstrip("\n")
                elif line.startswith("--- OUTPUT"):
                    match = re.search(r'exit_code=(\d+)', line)
                    if match and current_command:
                        current_command["exit_code"] = int(match.group(1))
                    in_output = True
                elif line.startswith("=== END"):
                    if current_command:
                        current_command["output"] = "\n".join(current_output_lines)
                        commands.append(current_command)
                    current_command = None
                    in_output = False
                elif in_output:
                    current_output_lines.append(line.rstrip("\n"))
        
        if last_n:
            return commands[-last_n:]
        return commands
    
    def clear(self, agent_id: str, run_id: str) -> bool:
        """
        Clear terminal log for an agent.
        
        Args:
            agent_id: ID of the agent
            run_id: ID of the run/session
            
        Returns:
            True if cleared successfully
        """
        log_path = self._get_log_path(run_id, agent_id)
        
        if log_path.exists():
            log_path.unlink()
            return True
        return False
    
    def export(
        self,
        agent_id: str,
        run_id: str,
        format: str = "text",
    ) -> str:
        """
        Export terminal log in specified format.
        
        Args:
            agent_id: ID of the agent
            run_id: ID of the run/session
            format: Export format (text, json)
            
        Returns:
            Exported content as string
        """
        if format == "text":
            log_path = self._get_log_path(run_id, agent_id)
            if not log_path.exists():
                return ""
            return log_path.read_text(encoding="utf-8", errors="replace")
        elif format == "json":
            commands = self.get_commands(agent_id, run_id)
            return json.dumps(commands, indent=2)
        else:
            raise ValueError(f"Unknown format: {format}")


def create_terminal_tools(
    terminal_logger: Optional[TerminalLogger] = None,
    base_dir: str = "~/.praison/runs",
):
    """
    Create tools for agents to interact with terminal logs.
    
    Returns a list of tool functions that can be passed to Agent(tools=[...]).
    
    Tools created:
    - terminal_tail: Get recent terminal output
    - terminal_grep: Search terminal logs
    - terminal_commands: List executed commands
    
    Example:
        tools = create_terminal_tools()
        agent = Agent(name="MyAgent", tools=tools)
    """
    term_logger = terminal_logger or TerminalLogger(base_dir=base_dir)
    
    def terminal_tail(
        agent_id: str = "default",
        run_id: str = "default",
        lines: int = 50,
    ) -> str:
        """
        Get the most recent terminal output.
        
        Args:
            agent_id: ID of the agent
            run_id: ID of the run/session
            lines: Number of lines to return
            
        Returns:
            Recent terminal output
        """
        return term_logger.tail_session(
            agent_id=agent_id,
            run_id=run_id,
            lines=lines,
        )
    
    def terminal_grep(
        pattern: str,
        agent_id: str = "default",
        run_id: str = "default",
        max_matches: int = 20,
    ) -> str:
        """
        Search terminal logs for a pattern.
        
        Args:
            pattern: Regex pattern to search for
            agent_id: ID of the agent
            run_id: ID of the run/session
            max_matches: Maximum matches to return
            
        Returns:
            Formatted search results
        """
        matches = term_logger.grep_session(
            pattern=pattern,
            agent_id=agent_id,
            run_id=run_id,
            max_matches=max_matches,
        )
        
        if not matches:
            return f"No matches found for: {pattern}"
        
        result_lines = [f"Found {len(matches)} matches:"]
        for match in matches:
            result_lines.append(f"\n--- Line {match.line_number} ---")
            for ctx in match.context_before:
                result_lines.append(f"  {ctx}")
            result_lines.append(f"> {match.line_content}")
            for ctx in match.context_after:
                result_lines.append(f"  {ctx}")
        
        return "\n".join(result_lines)
    
    def terminal_commands(
        agent_id: str = "default",
        run_id: str = "default",
        last_n: int = 10,
    ) -> str:
        """
        List recently executed commands.
        
        Args:
            agent_id: ID of the agent
            run_id: ID of the run/session
            last_n: Number of recent commands to show
            
        Returns:
            Formatted list of commands
        """
        commands = term_logger.get_commands(
            agent_id=agent_id,
            run_id=run_id,
            last_n=last_n,
        )
        
        if not commands:
            return "No commands found."
        
        result_lines = [f"Last {len(commands)} commands:"]
        for cmd in commands:
            exit_code = cmd.get("exit_code", "?")
            command = cmd.get("command", "?")
            timestamp = cmd.get("timestamp", "?")
            status = "✓" if exit_code == 0 else "✗"
            result_lines.append(f"\n{status} [{timestamp}] $ {command}")
            result_lines.append(f"   Exit code: {exit_code}")
        
        return "\n".join(result_lines)
    
    return [terminal_tail, terminal_grep, terminal_commands]
