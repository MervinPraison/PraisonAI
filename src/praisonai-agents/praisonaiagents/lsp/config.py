"""
LSP Configuration for PraisonAI Agents.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List


# Default language server commands
DEFAULT_SERVERS = {
    "python": {
        "command": "pylsp",
        "args": [],
    },
    "javascript": {
        "command": "typescript-language-server",
        "args": ["--stdio"],
    },
    "typescript": {
        "command": "typescript-language-server",
        "args": ["--stdio"],
    },
    "rust": {
        "command": "rust-analyzer",
        "args": [],
    },
    "go": {
        "command": "gopls",
        "args": [],
    },
}


@dataclass
class LSPConfig:
    """Configuration for LSP client."""
    language: str
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    root_uri: Optional[str] = None
    initialization_options: Dict = field(default_factory=dict)
    timeout: float = 30.0
    
    def __post_init__(self):
        # Use default server if not specified
        if self.command is None:
            if self.language in DEFAULT_SERVERS:
                server = DEFAULT_SERVERS[self.language]
                self.command = server["command"]
                self.args = server["args"]
            else:
                raise ValueError(f"No default server for language: {self.language}")
