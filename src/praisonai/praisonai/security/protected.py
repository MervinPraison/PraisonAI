"""
Protected paths guard for PraisonAI security.

Defines files and directories that agents must never modify.
Used by code tools (apply_diff, execute_command, write_file) to
prevent accidental or malicious self-modification.
"""
import os
import re
from typing import Optional, Sequence

# Exact filename/directory matches (case-insensitive basename check)
PROTECTED_PATHS: frozenset = frozenset([
    ".env",
    ".env.local",
    ".env.production",
    ".env.staging",
    ".env.development",
    ".git",
    "__pycache__",
    "praisonaiagents",
    "node_modules",
    "wallet.json",
    "id_rsa",
    "id_ed25519",
    "authorized_keys",
    "known_hosts",
])

# Glob-like suffix/prefix patterns (checked against full path)
PROTECTED_PATTERNS: tuple = (
    r"\.env(\.[a-z]+)?$",          # .env, .env.local, .env.production, etc.
    r"\.pem$",                      # SSL/TLS certificates
    r"\.key$",                      # Private keys
    r"\.p12$",                      # PKCS12 keystores
    r"\.pfx$",                      # PFX keystores
    r"\.pyc$",                      # Compiled Python
    r"__pycache__",                 # Python cache dirs
    r"\.git[/\\]",                  # Git internals
    r"node_modules[/\\]",           # Node modules
    r"praisonaiagents[/\\]",        # Core SDK — never self-modify
    r"wallet\.json$",               # Crypto wallet
    r"audit\.jsonl$",               # Audit log itself
)

# Human-readable reason per pattern
_REASONS: tuple = (
    "Environment file containing secrets",
    "SSL/TLS certificate",
    "Private key file",
    "PKCS12 keystore",
    "PFX keystore",
    "Compiled Python bytecode",
    "Python cache directory",
    "Git internal directory",
    "Node modules directory",
    "PraisonAI Core SDK — immutable",
    "Crypto wallet file",
    "Audit log — immutable",
)


def is_protected(path: str, extra_protected: Optional[Sequence[str]] = None) -> bool:
    """
    Check whether a file path is protected from modification.

    Args:
        path: The file path to check (absolute or relative).
        extra_protected: Optional additional paths/patterns to treat as protected.

    Returns:
        True if the path is protected, False otherwise.

    Example:
        >>> is_protected(".env")
        True
        >>> is_protected("src/myapp/main.py")
        False
    """
    # Resolve symlinks so a same-directory symlink to a protected file (e.g.
    # ``harmless.txt -> .env``) is checked by its real target, not its
    # innocuous-looking name. ``realpath`` also normalises ``..``/``.``.
    try:
        resolved = os.path.realpath(path)
    except OSError:
        resolved = path
    normalized = resolved.replace("\\", "/")
    basename = os.path.basename(normalized)

    # Exact basename match (fast path)
    if basename.lower() in {p.lower() for p in PROTECTED_PATHS}:
        return True

    # Pattern match against full path
    for pattern in PROTECTED_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            return True

    # User-supplied extra protected
    if extra_protected:
        for extra in extra_protected:
            extra_norm = extra.replace("\\", "/")
            if basename.lower() == os.path.basename(extra_norm).lower():
                return True
            if re.search(re.escape(extra_norm), normalized, re.IGNORECASE):
                return True

    return False


def resolve_real_path(path: str) -> str:
    """Return the fully symlink-resolved absolute path.

    Editing tools must classify *and act on the same target*. Returning the
    resolved path lets callers both validate against — and write to — the real
    file, so a same-directory symlink (``harmless.txt -> .env``) cannot let a
    protected file slip through a later ``open()`` that follows the link.

    Args:
        path: The file path to resolve (absolute or relative).

    Returns:
        The ``os.path.realpath`` of ``path``, falling back to the input on
        ``OSError`` (e.g. a broken/looping symlink).
    """
    try:
        return os.path.realpath(path)
    except OSError:
        return path


def get_protection_reason(path: str) -> Optional[str]:
    """
    Get the human-readable reason why a path is protected.

    Args:
        path: The file path to check.

    Returns:
        Reason string if protected, None if not protected.

    Example:
        >>> get_protection_reason(".env")
        'Environment file containing secrets'
    """
    # Mirror ``is_protected``: resolve symlinks so the reason reflects the real
    # target rather than an innocuous-looking symlink name.
    try:
        resolved = os.path.realpath(path)
    except OSError:
        resolved = path
    normalized = resolved.replace("\\", "/")
    basename = os.path.basename(normalized)

    if basename.lower() in {p.lower() for p in PROTECTED_PATHS}:
        # Find the best matching reason
        for i, pattern in enumerate(PROTECTED_PATTERNS):
            if re.search(pattern, normalized, re.IGNORECASE):
                return _REASONS[i]
        return "Protected system file"

    for i, pattern in enumerate(PROTECTED_PATTERNS):
        if re.search(pattern, normalized, re.IGNORECASE):
            return _REASONS[i]

    return None
