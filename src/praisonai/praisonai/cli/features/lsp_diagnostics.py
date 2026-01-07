"""
LSP Diagnostics Hook for PraisonAI CLI.

Provides automatic LSP diagnostics after file edits.
Reuses existing LSP client from praisonaiagents.
"""

import logging
from typing import List, Dict, Optional, Any, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Diagnostic:
    """LSP diagnostic entry."""
    severity: str  # "error", "warning", "info", "hint"
    message: str
    line: int
    column: int = 0
    source: str = ""
    code: str = ""
    
    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "message": self.message,
            "line": self.line,
            "column": self.column,
            "source": self.source,
            "code": self.code,
        }


class DiagnosticsHook:
    """
    Hook for collecting LSP diagnostics after file edits.
    
    Integrates with the existing LSP client to provide feedback
    after code modifications.
    
    Usage:
        hook = DiagnosticsHook()
        
        # After editing a file
        diagnostics = hook.on_file_edit("/path/to/file.py")
        for d in diagnostics:
            print(f"{d.severity}: {d.message} at line {d.line}")
    """
    
    def __init__(self, lsp_client: Optional[Any] = None):
        self._lsp_client = lsp_client
        self._callbacks: List[Callable[[str, List[Diagnostic]], None]] = []
    
    def set_lsp_client(self, client: Any) -> None:
        """Set the LSP client to use for diagnostics."""
        self._lsp_client = client
    
    def register_callback(
        self, 
        callback: Callable[[str, List[Diagnostic]], None]
    ) -> None:
        """Register a callback to be called when diagnostics are available."""
        self._callbacks.append(callback)
    
    def _get_lsp_diagnostics(self, file_path: str) -> List[Dict]:
        """Get diagnostics from LSP client."""
        if self._lsp_client is None:
            return []
        
        try:
            # Try to get diagnostics from LSP client
            if hasattr(self._lsp_client, 'get_diagnostics'):
                return self._lsp_client.get_diagnostics(file_path)
            elif hasattr(self._lsp_client, 'diagnostics'):
                return self._lsp_client.diagnostics(file_path)
        except Exception as e:
            logger.debug(f"Failed to get LSP diagnostics: {e}")
        
        return []
    
    def _convert_diagnostics(self, raw_diagnostics: List[Dict]) -> List[Diagnostic]:
        """Convert raw LSP diagnostics to Diagnostic objects."""
        diagnostics = []
        
        severity_map = {
            1: "error",
            2: "warning", 
            3: "info",
            4: "hint",
        }
        
        for raw in raw_diagnostics:
            severity = raw.get("severity", 1)
            if isinstance(severity, int):
                severity = severity_map.get(severity, "error")
            
            # Handle different diagnostic formats
            line = raw.get("line", 1)
            if "range" in raw:
                line = raw["range"].get("start", {}).get("line", 1) + 1
            
            column = raw.get("column", 0)
            if "range" in raw:
                column = raw["range"].get("start", {}).get("character", 0)
            
            diagnostics.append(Diagnostic(
                severity=severity,
                message=raw.get("message", "Unknown error"),
                line=line,
                column=column,
                source=raw.get("source", ""),
                code=str(raw.get("code", "")),
            ))
        
        return diagnostics
    
    def on_file_edit(self, file_path: str) -> List[Diagnostic]:
        """
        Called after a file is edited to collect diagnostics.
        
        Args:
            file_path: Path to the edited file
            
        Returns:
            List of diagnostics for the file
        """
        raw_diagnostics = self._get_lsp_diagnostics(file_path)
        diagnostics = self._convert_diagnostics(raw_diagnostics)
        
        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(file_path, diagnostics)
            except Exception as e:
                logger.warning(f"Diagnostics callback failed: {e}")
        
        return diagnostics
    
    def format_diagnostics(
        self, 
        diagnostics: List[Diagnostic],
        max_items: int = 10,
    ) -> str:
        """Format diagnostics for display."""
        if not diagnostics:
            return "No diagnostics"
        
        lines = []
        errors = [d for d in diagnostics if d.severity == "error"]
        warnings = [d for d in diagnostics if d.severity == "warning"]
        
        if errors:
            lines.append(f"❌ {len(errors)} error(s)")
        if warnings:
            lines.append(f"⚠️ {len(warnings)} warning(s)")
        
        # Show first few diagnostics
        shown = diagnostics[:max_items]
        for d in shown:
            icon = "❌" if d.severity == "error" else "⚠️" if d.severity == "warning" else "ℹ️"
            lines.append(f"  {icon} Line {d.line}: {d.message}")
        
        if len(diagnostics) > max_items:
            lines.append(f"  ... and {len(diagnostics) - max_items} more")
        
        return "\n".join(lines)


# Global diagnostics hook instance
_diagnostics_hook: Optional[DiagnosticsHook] = None


def get_diagnostics_hook() -> DiagnosticsHook:
    """Get the global diagnostics hook."""
    global _diagnostics_hook
    if _diagnostics_hook is None:
        _diagnostics_hook = DiagnosticsHook()
    return _diagnostics_hook


def on_file_edited(file_path: str) -> List[Diagnostic]:
    """Convenience function to trigger diagnostics after file edit."""
    return get_diagnostics_hook().on_file_edit(file_path)
