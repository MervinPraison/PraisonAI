"""
Claude Memory Tool - File-based persistent memory for Claude models.

This module implements Anthropic's Memory Tool API (beta) which enables Claude
to store and retrieve information across conversations through a memory file directory.

The memory tool operates client-side - you control where and how the data is stored.

Beta Header: context-management-2025-06-27
Tool Type: memory_20250818

Supported Models:
- Claude Sonnet 4.5 (claude-sonnet-4-5-20250929)
- Claude Sonnet 4 (claude-sonnet-4-20250514)
- Claude Haiku 4.5 (claude-haiku-4-5-20251001)
- Claude Opus 4.5 (claude-opus-4-5-20251101)
- Claude Opus 4.1 (claude-opus-4-1-20250805)
- Claude Opus 4 (claude-opus-4-20250514)

Reference: https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/memory-tool
"""

import shutil
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Memory system prompt that Claude uses to manage memory
MEMORY_SYSTEM_PROMPT = """
IMPORTANT: ALWAYS VIEW YOUR MEMORY DIRECTORY BEFORE DOING ANYTHING ELSE.

MEMORY PROTOCOL:
1. Use the `view` command of your `memory` tool to check for earlier progress.
2. ... (work on the task) ...
   - As you make progress, record status / progress / thoughts etc in your memory.

ASSUME INTERRUPTION: Your context window might be reset at any moment, so you risk losing any progress that is not recorded in your memory directory.

When editing your memory folder, always try to keep its content up-to-date, coherent and organized. You can rename or delete files that are no longer relevant. Do not create new files unless necessary.
"""


class ClaudeMemoryTool:
    """
    File-based memory tool for Claude models.
    
    Implements Anthropic's Memory Tool API (beta). Claude autonomously decides
    what to store and retrieve from the memory directory.
    
    Storage: {base_path}/memories/
    
    Commands:
    - view: Show directory contents or file contents with optional line ranges
    - create: Create or overwrite a file
    - str_replace: Replace text in a file
    - insert: Insert text at a specific line
    - delete: Delete a file or directory
    - rename: Rename or move a file/directory
    
    Example:
        ```python
        from praisonaiagents import Agent
        from praisonaiagents.tools import ClaudeMemoryTool
        
        # Use default storage
        agent = Agent(
            name="Assistant",
            llm="anthropic/claude-sonnet-4-20250514",
            claude_memory=True
        )
        
        # Or with custom storage path
        memory = ClaudeMemoryTool(base_path="./my_project/memory")
        agent = Agent(
            name="Assistant",
            llm="anthropic/claude-sonnet-4-20250514",
            claude_memory=memory
        )
        ```
    
    Security:
        - All paths are validated to prevent directory traversal attacks
        - Paths must start with /memories
        - Symlinks are not followed outside the memory directory
    """
    
    # Beta header required for memory tool
    BETA_HEADER = "context-management-2025-06-27"
    
    # Tool definition for API requests
    TOOL_DEFINITION = {
        "type": "memory_20250818",
        "name": "memory"
    }
    
    def __init__(
        self,
        base_path: Optional[str] = None,
        user_id: Optional[str] = None,
        max_file_size: int = 1024 * 1024,  # 1MB default
        max_files: int = 100
    ):
        """
        Initialize the Claude Memory Tool.
        
        Args:
            base_path: Base directory for memory storage. 
                       Defaults to .praison/claude_memory/{user_id}
            user_id: User identifier for user-specific memory.
                     Defaults to "default"
            max_file_size: Maximum size per file in bytes (default 1MB)
            max_files: Maximum number of files allowed (default 100)
        """
        self.user_id = user_id or "default"
        
        if base_path:
            self.base_path = Path(base_path)
        else:
            self.base_path = Path(f".praison/claude_memory/{self.user_id}")
        
        self.memory_root = self.base_path / "memories"
        self.max_file_size = max_file_size
        self.max_files = max_files
        
        # Create memory directory
        self.memory_root.mkdir(parents=True, exist_ok=True)
        
        logger.debug(f"ClaudeMemoryTool initialized at {self.memory_root}")
    
    def _validate_path(self, path: str) -> Path:
        """
        Validate and resolve memory paths securely.
        
        Args:
            path: Path string starting with /memories
            
        Returns:
            Resolved Path object within memory directory
            
        Raises:
            ValueError: If path is invalid or attempts directory traversal
        """
        if not path:
            raise ValueError("Path cannot be empty")
        
        if not path.startswith("/memories"):
            raise ValueError(f"Path must start with /memories, got: {path}")
        
        # Remove /memories prefix and leading slashes
        relative_path = path[len("/memories"):].lstrip("/")
        
        # Resolve the full path
        if relative_path:
            full_path = self.memory_root / relative_path
        else:
            full_path = self.memory_root
        
        # Security check: ensure resolved path is within memory_root
        try:
            resolved = full_path.resolve()
            resolved.relative_to(self.memory_root.resolve())
        except ValueError as e:
            raise ValueError(f"Path {path} would escape /memories directory") from e
        
        # Check for suspicious patterns
        if ".." in path or "~" in path:
            raise ValueError(f"Invalid path pattern in: {path}")
        
        return full_path
    
    def execute(self, command: str, **kwargs) -> str:
        """
        Execute a memory command.
        
        Args:
            command: Command name (view, create, str_replace, insert, delete, rename)
            **kwargs: Command-specific arguments
            
        Returns:
            Result string from the command
            
        Raises:
            ValueError: If command is unknown
        """
        commands = {
            "view": self.view,
            "create": self.create,
            "str_replace": self.str_replace,
            "insert": self.insert,
            "delete": self.delete,
            "rename": self.rename
        }
        
        if command not in commands:
            raise ValueError(f"Unknown command: {command}. Valid commands: {list(commands.keys())}")
        
        return commands[command](**kwargs)
    
    def view(self, path: str, view_range: Optional[List[int]] = None) -> str:
        """
        Show directory contents or file contents with optional line ranges.
        
        Args:
            path: Path to view (e.g., "/memories" or "/memories/notes.txt")
            view_range: Optional [start_line, end_line] for file viewing.
                        Use -1 for end_line to read to end of file.
                        
        Returns:
            Directory listing or file contents with line numbers
            
        Raises:
            RuntimeError: If path cannot be read
        """
        full_path = self._validate_path(path)
        
        if full_path.is_dir():
            # List directory contents
            items: List[str] = []
            try:
                for item in sorted(full_path.iterdir()):
                    # Skip hidden files
                    if item.name.startswith("."):
                        continue
                    # Add trailing slash for directories
                    items.append(f"{item.name}/" if item.is_dir() else item.name)
                
                result = f"Directory: {path}\n"
                if items:
                    result += "\n".join([f"- {item}" for item in items])
                else:
                    result += "(empty directory)"
                return result
                
            except Exception as e:
                raise RuntimeError(f"Cannot read directory {path}: {e}") from e
        
        elif full_path.is_file():
            # Read file contents
            try:
                content = full_path.read_text(encoding="utf-8")
                lines = content.splitlines()
                
                # Apply view range if specified
                if view_range:
                    start_line = max(1, view_range[0]) - 1  # Convert to 0-indexed
                    end_line = len(lines) if view_range[1] == -1 else view_range[1]
                    lines = lines[start_line:end_line]
                    start_num = start_line + 1
                else:
                    start_num = 1
                
                # Add line numbers
                numbered_lines = [
                    f"{i + start_num:4d}: {line}" 
                    for i, line in enumerate(lines)
                ]
                return "\n".join(numbered_lines) if numbered_lines else "(empty file)"
                
            except Exception as e:
                raise RuntimeError(f"Cannot read file {path}: {e}") from e
        
        else:
            raise RuntimeError(f"Path not found: {path}")
    
    def create(self, path: str, file_text: str) -> str:
        """
        Create or overwrite a file.
        
        Args:
            path: Path for the new file (e.g., "/memories/notes.txt")
            file_text: Content to write to the file
            
        Returns:
            Success message
            
        Raises:
            ValueError: If file would exceed size limit or max files reached
        """
        full_path = self._validate_path(path)
        
        # Check file size limit
        if len(file_text.encode('utf-8')) > self.max_file_size:
            raise ValueError(
                f"File content exceeds maximum size of {self.max_file_size} bytes"
            )
        
        # Check max files limit (only for new files)
        if not full_path.exists():
            current_files = sum(1 for _ in self.memory_root.rglob("*") if _.is_file())
            if current_files >= self.max_files:
                raise ValueError(
                    f"Maximum number of files ({self.max_files}) reached. "
                    "Delete some files before creating new ones."
                )
        
        # Create parent directories if needed
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write file
        full_path.write_text(file_text, encoding="utf-8")
        
        return f"File created successfully at {path}"
    
    def str_replace(self, path: str, old_str: str, new_str: str) -> str:
        """
        Replace text in a file.
        
        Args:
            path: Path to the file
            old_str: Text to find (must be unique in file)
            new_str: Replacement text
            
        Returns:
            Success message
            
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If old_str not found or appears multiple times
        """
        full_path = self._validate_path(path)
        
        if not full_path.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        
        content = full_path.read_text(encoding="utf-8")
        
        # Count occurrences
        count = content.count(old_str)
        
        if count == 0:
            raise ValueError(f"Text not found in {path}")
        elif count > 1:
            raise ValueError(
                f"Text appears {count} times in {path}. Must be unique for replacement."
            )
        
        # Replace and write
        new_content = content.replace(old_str, new_str)
        
        # Check size limit
        if len(new_content.encode('utf-8')) > self.max_file_size:
            raise ValueError(
                f"Resulting file would exceed maximum size of {self.max_file_size} bytes"
            )
        
        full_path.write_text(new_content, encoding="utf-8")
        
        return f"File {path} has been edited"
    
    def insert(self, path: str, insert_line: int, insert_text: str) -> str:
        """
        Insert text at a specific line.
        
        Args:
            path: Path to the file
            insert_line: Line number to insert at (0-indexed)
            insert_text: Text to insert
            
        Returns:
            Success message
            
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If line number is invalid
        """
        full_path = self._validate_path(path)
        
        if not full_path.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        
        lines = full_path.read_text(encoding="utf-8").splitlines()
        
        # Validate line number
        if insert_line < 0 or insert_line > len(lines):
            raise ValueError(
                f"Invalid insert_line {insert_line}. Must be 0-{len(lines)}"
            )
        
        # Insert the text (strip trailing newline to avoid double newlines)
        lines.insert(insert_line, insert_text.rstrip("\n"))
        
        # Reconstruct content
        new_content = "\n".join(lines) + "\n"
        
        # Check size limit
        if len(new_content.encode('utf-8')) > self.max_file_size:
            raise ValueError(
                f"Resulting file would exceed maximum size of {self.max_file_size} bytes"
            )
        
        full_path.write_text(new_content, encoding="utf-8")
        
        return f"Text inserted at line {insert_line} in {path}"
    
    def delete(self, path: str) -> str:
        """
        Delete a file or directory.
        
        Args:
            path: Path to delete
            
        Returns:
            Success message
            
        Raises:
            ValueError: If trying to delete /memories root
            FileNotFoundError: If path doesn't exist
        """
        # Prevent deleting the root memories directory
        if path == "/memories" or path == "/memories/":
            raise ValueError("Cannot delete the /memories directory itself")
        
        full_path = self._validate_path(path)
        
        if full_path.is_file():
            full_path.unlink()
            return f"File deleted: {path}"
        elif full_path.is_dir():
            shutil.rmtree(full_path)
            return f"Directory deleted: {path}"
        else:
            raise FileNotFoundError(f"Path not found: {path}")
    
    def rename(self, old_path: str, new_path: str) -> str:
        """
        Rename or move a file/directory.
        
        Args:
            old_path: Current path
            new_path: New path
            
        Returns:
            Success message
            
        Raises:
            FileNotFoundError: If source doesn't exist
            ValueError: If destination already exists
        """
        old_full_path = self._validate_path(old_path)
        new_full_path = self._validate_path(new_path)
        
        if not old_full_path.exists():
            raise FileNotFoundError(f"Source path not found: {old_path}")
        
        if new_full_path.exists():
            raise ValueError(f"Destination already exists: {new_path}")
        
        # Create parent directories if needed
        new_full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Rename/move
        old_full_path.rename(new_full_path)
        
        return f"Renamed {old_path} to {new_path}"
    
    def clear_all(self) -> str:
        """
        Clear all memory files.
        
        Returns:
            Success message
        """
        if self.memory_root.exists():
            shutil.rmtree(self.memory_root)
        self.memory_root.mkdir(parents=True, exist_ok=True)
        
        return "All memory cleared"
    
    def get_tool_definition(self) -> Dict[str, Any]:
        """
        Get the tool definition for API requests.
        
        Returns:
            Tool definition dict for Anthropic API
        """
        return self.TOOL_DEFINITION.copy()
    
    def get_beta_header(self) -> str:
        """
        Get the beta header value for API requests.
        
        Returns:
            Beta header string
        """
        return self.BETA_HEADER
    
    def get_system_prompt(self) -> str:
        """
        Get the memory system prompt to append to agent instructions.
        
        Returns:
            Memory protocol system prompt
        """
        return MEMORY_SYSTEM_PROMPT
    
    def process_tool_call(self, tool_input: Dict[str, Any]) -> str:
        """
        Process a memory tool call from Claude.
        
        Args:
            tool_input: The input dict from Claude's tool_use block
                        Contains 'command' and command-specific parameters
                        
        Returns:
            Result string to return to Claude
            
        Example:
            ```python
            # Claude sends:
            # {"command": "view", "path": "/memories"}
            result = memory_tool.process_tool_call(tool_input)
            ```
        """
        command = tool_input.get("command")
        if not command:
            return "Error: No command specified in tool input"
        
        try:
            # Extract command-specific parameters
            params = {k: v for k, v in tool_input.items() if k != "command"}
            return self.execute(command, **params)
        except Exception as e:
            return f"Error: {str(e)}"
    
    def __repr__(self) -> str:
        return f"ClaudeMemoryTool(base_path='{self.base_path}', user_id='{self.user_id}')"
