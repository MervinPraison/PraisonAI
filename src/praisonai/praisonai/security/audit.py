"""
Audit log hook for PraisonAI agents.

Records every tool call to an append-only JSONL file.
Integrates with PraisonAI's AFTER_TOOL hook event.

Zero overhead when not enabled — all imports are local.
"""
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_DEFAULT_LOG_PATH = os.path.expanduser("~/.praisonai/audit.jsonl")


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
    ):
        """
        Args:
            log_path: Path to the JSONL audit log file.
                      Defaults to ~/.praisonai/audit.jsonl.
            include_output: Whether to include tool output in the log.
                            Default False to keep log compact.
            max_output_chars: Maximum characters of tool output to log
                              (only used when include_output=True).
        """
        self._log_path = os.path.expanduser(log_path or _DEFAULT_LOG_PATH)
        self._include_output = include_output
        self._max_output_chars = max_output_chars
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """Create parent directory if it doesn't exist."""
        parent = Path(self._log_path).parent
        parent.mkdir(parents=True, exist_ok=True)

    def _write(self, entry: dict) -> None:
        """Append a JSON line to the audit log."""
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except OSError as e:
            logger.error("[praisonai.security.audit] Failed to write audit log: %s", e)

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
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "session_id": getattr(data, "session_id", "unknown"),
                "agent_name": getattr(data, "agent_name", "unknown"),
                "tool_name": getattr(data, "tool_name", "unknown"),
                "tool_input": getattr(data, "tool_input", {}),
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
