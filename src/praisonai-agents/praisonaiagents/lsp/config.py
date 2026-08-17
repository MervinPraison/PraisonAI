"""
LSP Configuration for PraisonAI Agents.
"""

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, List, Tuple


# Data-driven language server registry.  Each entry carries the spawn command
# plus enough metadata for zero-config auto-detection:
#   - command / args: how to start the server
#   - extensions: file extensions that map to this language
#   - root_markers: files/dirs that mark a workspace root (nearest wins), so
#     ``rootUri`` is the real project root rather than ``os.getcwd()``
#   - install_hint: an actionable "how to install" string surfaced when the
#     server binary is absent, so degradation is explicit instead of silent
DEFAULT_SERVERS = {
    "python": {
        "command": "pylsp",
        "args": [],
        "extensions": [".py", ".pyi"],
        "root_markers": ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", ".git"],
        "install_hint": "pip install python-lsp-server",
    },
    "javascript": {
        "command": "typescript-language-server",
        "args": ["--stdio"],
        "extensions": [".js", ".jsx", ".mjs", ".cjs"],
        "root_markers": ["package.json", "tsconfig.json", "jsconfig.json", ".git"],
        "install_hint": "npm install -g typescript-language-server typescript",
    },
    "typescript": {
        "command": "typescript-language-server",
        "args": ["--stdio"],
        "extensions": [".ts", ".tsx"],
        "root_markers": ["tsconfig.json", "package.json", "jsconfig.json", ".git"],
        "install_hint": "npm install -g typescript-language-server typescript",
    },
    "rust": {
        "command": "rust-analyzer",
        "args": [],
        "extensions": [".rs"],
        "root_markers": ["Cargo.toml", "Cargo.lock", ".git"],
        "install_hint": "rustup component add rust-analyzer",
    },
    "go": {
        "command": "gopls",
        "args": [],
        "extensions": [".go"],
        "root_markers": ["go.mod", "go.sum", ".git"],
        "install_hint": "go install golang.org/x/tools/gopls@latest",
    },
}


def _extension_map() -> Dict[str, str]:
    """Return a ``{extension: language}`` map derived from the registry."""
    mapping: Dict[str, str] = {}
    for language, server in DEFAULT_SERVERS.items():
        for ext in server.get("extensions", []):
            mapping.setdefault(ext.lower(), language)
    return mapping


def detect_language(file_path: str) -> Optional[str]:
    """Resolve the LSP language id for ``file_path`` by extension, else ``None``."""
    return _extension_map().get(os.path.splitext(file_path)[1].lower())


def path_to_uri(path: str) -> str:
    """Convert an absolute filesystem *path* to a valid ``file://`` URI.

    Uses :meth:`pathlib.Path.as_uri`, which percent-encodes reserved characters
    (spaces, ``#`` …) so paths with such characters produce a valid, non-truncated
    URI that language servers accept.
    """
    return Path(os.path.abspath(path)).as_uri()


def detect_root_uri(file_path: str, language: Optional[str] = None) -> Optional[str]:
    """Discover the workspace root for ``file_path`` from the nearest root marker.

    Walks up from the file's directory looking for a language-appropriate root
    marker (``pyproject.toml``, ``go.mod``, ``Cargo.toml``, ``tsconfig.json``,
    ``.git`` …).  Returns a ``file://`` URI for the nearest matching directory,
    or ``None`` when no marker is found so the caller can fall back to the CWD.
    """
    language = language or detect_language(file_path)
    server = DEFAULT_SERVERS.get(language) if language else None
    markers = server.get("root_markers", []) if server else [".git"]
    start = os.path.dirname(os.path.abspath(file_path))
    current = start
    while True:
        for marker in markers:
            if os.path.exists(os.path.join(current, marker)):
                return path_to_uri(current)
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def probe(language: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Check whether the language server for ``language`` is on ``PATH``.

    Returns ``(available, command, install_hint)``.  ``available`` is ``True``
    when the configured server binary is found via ``shutil.which``; otherwise
    ``command`` and ``install_hint`` describe what is missing and how to install
    it so the degradation can be surfaced instead of silently swallowed.
    """
    server = DEFAULT_SERVERS.get(language)
    if not server:
        return False, None, None
    command = server["command"]
    if shutil.which(command):
        return True, command, server.get("install_hint")
    return False, command, server.get("install_hint")


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
                self.args = list(server["args"])
            else:
                raise ValueError(f"No default server for language: {self.language}")
