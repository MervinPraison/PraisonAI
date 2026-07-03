"""Environment variable security (C8.4)."""

from __future__ import annotations

from dotenv import load_dotenv

# Security: blocklist of environment variable keys that must not be set from
# untrusted YAML config files. These keys can alter code-loading behaviour
# (LD_PRELOAD, PYTHONPATH, …) or redirect subprocesses (PATH) and are
# therefore a vector for arbitrary code execution (CWE-78).
_BLOCKED_ENV_KEYS = frozenset({
    # Dynamic linker injection
    "LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT",
    "DYLD_INSERT_LIBRARIES", "DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH",
    "DYLD_FALLBACK_LIBRARY_PATH",
    # Executable / module search paths
    "PATH",
    "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP",
    "NODE_PATH", "NODE_OPTIONS",
    "RUBYLIB", "PERL5LIB", "PERL5OPT",
    "CLASSPATH",
    # Proxy / redirect (could exfiltrate traffic)
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
    # Miscellaneous dangerous keys
    "BASH_ENV", "ENV", "CDPATH",
    "PROMPT_COMMAND",
    "SHLVL",
})

# Pre-compute uppercase lookup set once at module load (avoids rebuilding per call)
_BLOCKED_ENV_KEYS_UPPER = frozenset(k.upper() for k in _BLOCKED_ENV_KEYS)


_env_loaded: bool = False


def _load_env_once():
    """Load environment variables from .env file once at CLI startup."""
    global _env_loaded
    if not _env_loaded:
        load_dotenv()
        _env_loaded = True


def _validate_env_key(key) -> None:
    """Raise ``ValueError`` if *key* is a blocked environment variable name.

    The check is case-insensitive so that ``ld_preload`` is caught as well as
    ``LD_PRELOAD``.  Non-string keys (e.g. YAML integer or null keys) are
    rejected with a clear validation error.
    """
    if not isinstance(key, str):
        raise ValueError(
            f"Environment variable key must be a string, got {type(key).__name__}: {key!r}"
        )
    if not key or "=" in key or "\x00" in key:
        raise ValueError(
            "Environment variable key must be a non-empty string without '=' or NUL characters."
        )
    if key.upper() in _BLOCKED_ENV_KEYS_UPPER:
        raise ValueError(
            f"Setting environment variable '{key}' is not allowed in schedule "
            f"config files because it can be used to execute arbitrary code."
        )
