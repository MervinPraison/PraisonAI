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
    normalized = path.replace("\\", "/")
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
    normalized = path.replace("\\", "/")
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
