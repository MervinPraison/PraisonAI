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


def resolve_servers(user_servers: Optional[Dict[str, Dict]] = None) -> Dict[str, Dict]:
    """Return the effective server registry: ``DEFAULT_SERVERS`` merged with
    user-supplied entries.

    User entries override built-ins per language key and add new languages, so
    shipped defaults keep working and a project can register a sixth language or
    pin a different server without editing package source.  With no user config
    the result is byte-for-byte ``DEFAULT_SERVERS``.  The merge is shallow at the
    per-language level (a user language entry replaces the built-in entry for
    that key) and keeps the helper lazy and dependency-free.

    Command/args are treated as a unit: when a user swaps ``command`` for a
    different executable without supplying ``args``, the built-in ``args`` are
    dropped rather than inherited, so arguments belonging to the replaced server
    (e.g. ``--stdio`` for ``typescript-language-server``) are never passed to an
    unrelated replacement binary.
    """
    if not user_servers:
        return DEFAULT_SERVERS
    merged = dict(DEFAULT_SERVERS)
    for language, server in user_servers.items():
        if not isinstance(server, dict):
            continue
        base = dict(merged.get(language, {}))
        overrides_command = (
            "command" in server and server["command"] != base.get("command")
        )
        base.update(server)
        if overrides_command and "args" not in server:
            base["args"] = []
        merged[language] = base
    return merged


def _extension_map(servers: Optional[Dict[str, Dict]] = None) -> Dict[str, str]:
    """Return a ``{extension: language}`` map derived from the registry."""
    mapping: Dict[str, str] = {}
    for language, server in resolve_servers(servers).items():
        for ext in server.get("extensions", []):
            mapping.setdefault(ext.lower(), language)
    return mapping


def detect_language(
    file_path: str, servers: Optional[Dict[str, Dict]] = None
) -> Optional[str]:
    """Resolve the LSP language id for ``file_path`` by extension, else ``None``."""
    return _extension_map(servers).get(os.path.splitext(file_path)[1].lower())


def path_to_uri(path: str) -> str:
    """Convert an absolute filesystem *path* to a valid ``file://`` URI.

    Uses :meth:`pathlib.Path.as_uri`, which percent-encodes reserved characters
    (spaces, ``#`` …) so paths with such characters produce a valid, non-truncated
    URI that language servers accept.
    """
    return Path(os.path.abspath(path)).as_uri()


def detect_root_uri(
    file_path: str,
    language: Optional[str] = None,
    servers: Optional[Dict[str, Dict]] = None,
) -> Optional[str]:
    """Discover the workspace root for ``file_path`` from the nearest root marker.

    Walks up from the file's directory looking for a language-appropriate root
    marker (``pyproject.toml``, ``go.mod``, ``Cargo.toml``, ``tsconfig.json``,
    ``.git`` …).  Returns a ``file://`` URI for the nearest matching directory,
    or ``None`` when no marker is found so the caller can fall back to the CWD.
    """
    registry = resolve_servers(servers)
    language = language or detect_language(file_path, servers)
    server = registry.get(language) if language else None
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


def probe(
    language: str, servers: Optional[Dict[str, Dict]] = None
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Check whether the language server for ``language`` is on ``PATH``.

    Returns ``(available, command, install_hint)``.  ``available`` is ``True``
    when the configured server binary is found via ``shutil.which``; otherwise
    ``command`` and ``install_hint`` describe what is missing and how to install
    it so the degradation can be surfaced instead of silently swallowed.
    """
    server = resolve_servers(servers).get(language)
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
    servers: Optional[Dict[str, Dict]] = None
    
    def __post_init__(self):
        # Use default server if not specified, consulting the effective registry
        # (built-ins deep-merged with any user-supplied ``servers``) so a
        # configured sixth language resolves instead of raising.
        if self.command is None:
            registry = resolve_servers(self.servers)
            if self.language in registry:
                server = registry[self.language]
                self.command = server["command"]
                self.args = list(server.get("args", []))
                if not self.initialization_options and server.get(
                    "initialization_options"
                ):
                    self.initialization_options = dict(
                        server["initialization_options"]
                    )
            else:
                raise ValueError(f"No default server for language: {self.language}")
