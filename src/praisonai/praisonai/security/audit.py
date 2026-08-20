"""
Audit log hook for PraisonAI agents.

Records every tool call to an append-only JSONL file.
Integrates with PraisonAI's AFTER_TOOL hook event.

Zero overhead when not enabled — all imports are local.
"""
import functools
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_DEFAULT_LOG_PATH = os.path.expanduser("~/.praisonai/audit.jsonl")

_DEFAULT_SENSITIVE_KEYS = frozenset({
    "api_key", "apikey", "authorization", "auth", "password", "passwd",
    "secret", "token", "access_token", "refresh_token", "bearer",
    "x-api-key", "openai_api_key", "anthropic_api_key", "cookie",
})
_REDACTED = "***REDACTED***"


def _default_redactor(obj: Any, sensitive: frozenset = _DEFAULT_SENSITIVE_KEYS) -> Any:
    """Recursively redact values whose key matches a sensitive name."""
    if isinstance(obj, dict):
        return {
            k: (_REDACTED if isinstance(k, str) and k.lower() in sensitive
                else _default_redactor(v, sensitive))
            for k, v in obj.items()
        }
    if isinstance(obj, (list, tuple)):
        return type(obj)(_default_redactor(v, sensitive) for v in obj)
    return obj


class AuditLogHook:
    """
    Writes an append-only JSONL audit log of all agent tool calls.

    Each line is a JSON object with: timestamp, session_id, agent_name,
    tool_name, tool_input, execution_time_ms, and optional tool_output.

    Example:
        >>> audit = AuditLogHook(log_path="~/.praisonai/audit.jsonl")
        >>> hook_fn = audit.create_after_tool_hook()
        >>> from praisonaiagents.hooks import add_hook
        >>> add_hook("after_tool", hook_fn)
    """

    def __init__(
        self,
        log_path: Optional[str] = None,
        include_output: bool = False,
        max_output_chars: int = 500,
        redactor: Optional[Callable[[Any], Any]] = _default_redactor,
        sensitive_keys: Optional[frozenset] = None,
    ):
        """
        Args:
            log_path: Path to the JSONL audit log file.
                      Defaults to ~/.praisonai/audit.jsonl.
            include_output: Whether to include tool output in the log.
                            Default False to keep log compact.
            max_output_chars: Maximum characters of tool output to log
                              (only used when include_output=True).
            redactor: Callable applied to tool_input before writing, to strip
                      secrets (api keys, tokens, passwords). Defaults to a
                      built-in key-name denylist redactor. Pass None to disable.
            sensitive_keys: Override the denylist of key names to redact.
        """
        self._log_path = os.path.expanduser(log_path or _DEFAULT_LOG_PATH)
        self._include_output = include_output
        self._max_output_chars = max_output_chars
        self._sensitive_keys = sensitive_keys or _DEFAULT_SENSITIVE_KEYS
        # Bind sensitive_keys to the built-in redactor so every redactor —
        # default or custom — honours the single-arg Callable[[Any], Any]
        # contract. Custom redactors are used exactly as supplied.
        if redactor is _default_redactor:
            redactor = functools.partial(_default_redactor, sensitive=self._sensitive_keys)
        self._redactor = redactor
        self._ensure_dir()
        self._lock = threading.Lock()
        # Single long-lived handle; reopened lazily if it gets rotated out.
        self._fh = None

    def _ensure_dir(self) -> None:
        """Create parent directory if it doesn't exist."""
        parent = Path(self._log_path).parent
        parent.mkdir(parents=True, exist_ok=True)

    def _write(self, entry: dict) -> None:
        """Append a JSON line to the audit log."""
        line = json.dumps(entry, default=str) + "\n"
        try:
            with self._lock:
                # Lazy initialize file handle
                if self._fh is None:
                    # Ensure the log file is user-only (0o600) regardless of
                    # the process umask before the first append.
                    try:
                        Path(self._log_path).touch(mode=0o600, exist_ok=True)
                        os.chmod(self._log_path, 0o600)
                    except OSError:
                        pass
                    self._fh = open(self._log_path, "a", encoding="utf-8")
                self._fh.write(line)
                self._fh.flush()
                os.fsync(self._fh.fileno())   # optional, for crash-durability
        except OSError as e:
            logger.error("[praisonai.security.audit] Failed to write audit log: %s", e)

    def close(self) -> None:
        """Close the audit log file handle."""
        with self._lock:
            if self._fh is not None:
                try:
                    self._fh.close()
                except OSError:
                    pass
                finally:
                    self._fh = None

    def create_after_tool_hook(self) -> Callable:
        """
        Create an AFTER_TOOL hook function.

        Returns:
            Hook function that accepts AfterToolInput and returns None.

        Example:
            >>> from praisonaiagents.hooks import add_hook
            >>> audit = AuditLogHook()
            >>> add_hook("after_tool", audit.create_after_tool_hook())
        """
        hook = self

        def _audit_hook(data: Any) -> None:
            raw_input = getattr(data, "tool_input", {})
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "session_id": getattr(data, "session_id", "unknown"),
                "agent_name": getattr(data, "agent_name", "unknown"),
                "tool_name": getattr(data, "tool_name", "unknown"),
                "tool_input": (
                    hook._redactor(raw_input)
                    if hook._redactor else raw_input
                ),
                "execution_time_ms": getattr(data, "execution_time_ms", 0.0),
                "error": getattr(data, "tool_error", None),
            }
            if hook._include_output:
                raw = getattr(data, "tool_output", None)
                if raw is not None:
                    entry["tool_output"] = str(raw)[: hook._max_output_chars]
            hook._write(entry)
            return None

        return _audit_hook
