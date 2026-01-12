"""
Interactive Runtime for PraisonAI.

Provides the core runtime that powers both TUI interactive mode and debug non-interactive mode.
Manages LSP and ACP subsystem lifecycle with graceful degradation.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SubsystemStatus(Enum):
    """Status of a subsystem."""
    NOT_STARTED = "not_started"
    STARTING = "starting"
    READY = "ready"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class SubsystemState:
    """State of a subsystem."""
    status: SubsystemStatus = SubsystemStatus.NOT_STARTED
    error: Optional[str] = None
    start_time: Optional[float] = None
    ready_time: Optional[float] = None


@dataclass
class RuntimeConfig:
    """Configuration for InteractiveRuntime."""
    workspace: str = "."
    lsp_enabled: bool = True
    acp_enabled: bool = True
    approval_mode: str = "auto"  # auto (full privileges), manual, scoped
    trace_enabled: bool = False
    trace_file: Optional[str] = None
    json_output: bool = False
    timeout: float = 60.0
    model: Optional[str] = None
    verbose: bool = False


@dataclass
class TraceEntry:
    """A single trace entry."""
    timestamp: float
    category: str  # lsp, acp, tool, llm, file
    action: str
    params: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Any] = None
    duration_ms: Optional[float] = None
    error: Optional[str] = None


@dataclass
class RuntimeTrace:
    """Trace of a runtime session."""
    version: str = "1.0"
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    config: Optional[RuntimeConfig] = None
    entries: List[TraceEntry] = field(default_factory=list)
    
    def add_entry(self, category: str, action: str, params: Dict[str, Any] = None,
                  result: Any = None, duration_ms: float = None, error: str = None):
        """Add a trace entry."""
        self.entries.append(TraceEntry(
            timestamp=time.time(),
            category=category,
            action=action,
            params=params or {},
            result=result,
            duration_ms=duration_ms,
            error=error
        ))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert trace to dictionary."""
        return {
            "version": self.version,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "config": {
                "workspace": self.config.workspace if self.config else None,
                "lsp_enabled": self.config.lsp_enabled if self.config else None,
                "acp_enabled": self.config.acp_enabled if self.config else None,
                "approval_mode": self.config.approval_mode if self.config else None,
            } if self.config else None,
            "entries": [
                {
                    "timestamp": e.timestamp,
                    "category": e.category,
                    "action": e.action,
                    "params": e.params,
                    "result": e.result,
                    "duration_ms": e.duration_ms,
                    "error": e.error
                }
                for e in self.entries
            ]
        }


class InteractiveRuntime:
    """
    Core runtime for interactive coding assistant.
    
    Manages:
    - LSP subsystem for code intelligence
    - ACP subsystem for action orchestration
    - Trace collection for debugging
    - Graceful degradation when subsystems fail
    """
    
    def __init__(self, config: RuntimeConfig = None):
        """Initialize the runtime."""
        self.config = config or RuntimeConfig()
        self._lsp_state = SubsystemState()
        self._acp_state = SubsystemState()
        self._lsp_client = None
        self._acp_session = None
        self._trace = RuntimeTrace(config=self.config) if self.config.trace_enabled else None
        self._started = False
        self._read_only = False  # Enforced when ACP fails
        
    @property
    def lsp_ready(self) -> bool:
        """Check if LSP is ready."""
        return self._lsp_state.status == SubsystemStatus.READY
    
    @property
    def acp_ready(self) -> bool:
        """Check if ACP is ready."""
        return self._acp_state.status == SubsystemStatus.READY
    
    @property
    def read_only(self) -> bool:
        """Check if runtime is in read-only mode.
        
        Note: When approval_mode=auto (via config or env), we allow writes even 
        without ACP to support non-interactive automation and testing scenarios.
        """
        # Check config approval_mode first (takes precedence)
        if self.config.approval_mode == "auto":
            return False
        
        # Then check environment variable as fallback
        import os as _os
        env_approval_mode = _os.environ.get("PRAISON_APPROVAL_MODE", "").lower()
        if env_approval_mode == "auto":
            return False
        
        # Only enforce read-only if explicitly set or ACP not ready
        return self._read_only
    
    def get_status(self) -> Dict[str, Any]:
        """Get runtime status."""
        return {
            "started": self._started,
            "workspace": self.config.workspace,
            "lsp": {
                "enabled": self.config.lsp_enabled,
                "status": self._lsp_state.status.value,
                "ready": self.lsp_ready,
                "error": self._lsp_state.error
            },
            "acp": {
                "enabled": self.config.acp_enabled,
                "status": self._acp_state.status.value,
                "ready": self.acp_ready,
                "error": self._acp_state.error
            },
            "read_only": self.read_only,
            "approval_mode": self.config.approval_mode
        }
    
    async def start(self) -> Dict[str, Any]:
        """
        Start the runtime and all enabled subsystems.
        
        Returns status dict with subsystem states.
        """
        if self._started:
            return self.get_status()
        
        workspace = Path(self.config.workspace).resolve()
        if not workspace.exists():
            workspace.mkdir(parents=True, exist_ok=True)
        
        self.config.workspace = str(workspace)
        
        # Start subsystems in parallel
        tasks = []
        if self.config.lsp_enabled:
            tasks.append(self._start_lsp())
        if self.config.acp_enabled:
            tasks.append(self._start_acp())
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        # Enforce read-only if ACP failed
        if self.config.acp_enabled and not self.acp_ready:
            self._read_only = True
            logger.warning("ACP unavailable - runtime is READ-ONLY")
        
        self._started = True
        
        if self._trace:
            self._trace.add_entry(
                category="runtime",
                action="start",
                params={"workspace": self.config.workspace},
                result=self.get_status()
            )
        
        return self.get_status()
    
    async def _start_lsp(self):
        """Start LSP subsystem."""
        self._lsp_state.status = SubsystemStatus.STARTING
        self._lsp_state.start_time = time.time()
        
        try:
            # Lazy import LSP client
            from praisonaiagents.lsp import LSPClient
            
            # Detect language from workspace
            language = self._detect_workspace_language()
            
            self._lsp_client = LSPClient(
                language=language,
                root_uri=f"file://{self.config.workspace}"
            )
            await self._lsp_client.start()
            
            # Wait for initialization
            if self._lsp_client.is_running:
                self._lsp_state.status = SubsystemStatus.READY
                self._lsp_state.ready_time = time.time()
                logger.info(f"LSP ready for {language}")
            else:
                raise RuntimeError("LSP client failed to start")
                
        except ImportError as e:
            self._lsp_state.status = SubsystemStatus.FAILED
            self._lsp_state.error = f"LSP module not available: {e}"
            logger.warning(self._lsp_state.error)
        except Exception as e:
            self._lsp_state.status = SubsystemStatus.FAILED
            self._lsp_state.error = str(e)
            logger.warning(f"LSP failed to start: {e}")
    
    async def _start_acp(self):
        """Start ACP subsystem (in-process session)."""
        self._acp_state.status = SubsystemStatus.STARTING
        self._acp_state.start_time = time.time()
        
        try:
            # Lazy import ACP
            from praisonai.acp.session import ACPSession
            from pathlib import Path
            
            # Create a session for the workspace
            self._acp_session = ACPSession.create(
                workspace=Path(self.config.workspace)
            )
            self._acp_session.mode = self.config.approval_mode
            
            self._acp_state.status = SubsystemStatus.READY
            self._acp_state.ready_time = time.time()
            logger.info("ACP session ready")
            
        except ImportError as e:
            self._acp_state.status = SubsystemStatus.FAILED
            self._acp_state.error = f"ACP module not available: {e}"
            logger.warning(self._acp_state.error)
        except Exception as e:
            self._acp_state.status = SubsystemStatus.FAILED
            self._acp_state.error = str(e)
            logger.warning(f"ACP failed to start: {e}")
    
    async def stop(self):
        """Stop the runtime and all subsystems."""
        if self._lsp_client:
            try:
                await self._lsp_client.stop()
            except Exception as e:
                logger.warning(f"Error stopping LSP: {e}")
            self._lsp_state.status = SubsystemStatus.STOPPED
        
        if self._acp_session:
            # ACPSession is a dataclass, no close method needed
            self._acp_session = None
            self._acp_state.status = SubsystemStatus.STOPPED
        
        if self._trace:
            self._trace.end_time = time.time()
            self._trace.add_entry(
                category="runtime",
                action="stop",
                result=self.get_status()
            )
        
        self._started = False
    
    def _detect_workspace_language(self) -> str:
        """Detect primary language in workspace."""
        workspace = Path(self.config.workspace)
        
        # Count files by extension
        extensions = {}
        for ext in [".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java"]:
            count = len(list(workspace.rglob(f"*{ext}")))
            if count > 0:
                extensions[ext] = count
        
        if not extensions:
            return "python"  # Default
        
        # Map extensions to languages
        ext_to_lang = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".jsx": "javascript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java"
        }
        
        # Return language with most files
        top_ext = max(extensions, key=extensions.get)
        return ext_to_lang.get(top_ext, "python")
    
    # LSP Operations
    async def lsp_get_symbols(self, file_path: str) -> List[Dict[str, Any]]:
        """Get symbols in a file via LSP."""
        if not self.lsp_ready:
            return []
        
        start = time.time()
        try:
            # Use workspace symbols or document symbols
            result = await self._lsp_client.get_document_symbols(file_path)
            duration = (time.time() - start) * 1000
            
            if self._trace:
                self._trace.add_entry(
                    category="lsp",
                    action="get_symbols",
                    params={"file": file_path},
                    result={"count": len(result) if result else 0},
                    duration_ms=duration
                )
            
            return result or []
        except Exception as e:
            if self._trace:
                self._trace.add_entry(
                    category="lsp",
                    action="get_symbols",
                    params={"file": file_path},
                    error=str(e)
                )
            return []
    
    async def lsp_get_definition(self, file_path: str, line: int, col: int) -> List[Dict[str, Any]]:
        """Get definition location via LSP."""
        if not self.lsp_ready:
            return []
        
        start = time.time()
        try:
            result = await self._lsp_client.get_definition(file_path, line, col)
            duration = (time.time() - start) * 1000
            
            if self._trace:
                self._trace.add_entry(
                    category="lsp",
                    action="get_definition",
                    params={"file": file_path, "line": line, "col": col},
                    result={"count": len(result) if result else 0},
                    duration_ms=duration
                )
            
            return [loc.__dict__ if hasattr(loc, '__dict__') else loc for loc in (result or [])]
        except Exception as e:
            if self._trace:
                self._trace.add_entry(
                    category="lsp",
                    action="get_definition",
                    params={"file": file_path, "line": line, "col": col},
                    error=str(e)
                )
            return []
    
    async def lsp_get_references(self, file_path: str, line: int, col: int) -> List[Dict[str, Any]]:
        """Get references via LSP."""
        if not self.lsp_ready:
            return []
        
        start = time.time()
        try:
            result = await self._lsp_client.get_references(file_path, line, col)
            duration = (time.time() - start) * 1000
            
            if self._trace:
                self._trace.add_entry(
                    category="lsp",
                    action="get_references",
                    params={"file": file_path, "line": line, "col": col},
                    result={"count": len(result) if result else 0},
                    duration_ms=duration
                )
            
            return [loc.__dict__ if hasattr(loc, '__dict__') else loc for loc in (result or [])]
        except Exception as e:
            if self._trace:
                self._trace.add_entry(
                    category="lsp",
                    action="get_references",
                    params={"file": file_path, "line": line, "col": col},
                    error=str(e)
                )
            return []
    
    async def lsp_get_diagnostics(self, file_path: str = None) -> List[Dict[str, Any]]:
        """Get diagnostics via LSP."""
        if not self.lsp_ready:
            return []
        
        start = time.time()
        try:
            if file_path:
                result = await self._lsp_client.get_diagnostics(file_path)
            else:
                result = self._lsp_client._diagnostics  # All cached diagnostics
            duration = (time.time() - start) * 1000
            
            if self._trace:
                self._trace.add_entry(
                    category="lsp",
                    action="get_diagnostics",
                    params={"file": file_path},
                    result={"count": len(result) if result else 0},
                    duration_ms=duration
                )
            
            return [d.__dict__ if hasattr(d, '__dict__') else d for d in (result or [])]
        except Exception as e:
            if self._trace:
                self._trace.add_entry(
                    category="lsp",
                    action="get_diagnostics",
                    params={"file": file_path},
                    error=str(e)
                )
            return []
    
    # ACP Operations
    async def acp_create_plan(self, prompt: str) -> Dict[str, Any]:
        """Create an action plan via ACP session tracking."""
        if not self.acp_ready:
            return {"error": "ACP not available", "read_only": True}
        
        start = time.time()
        try:
            # ACP session tracks the plan but doesn't create it
            # Return empty steps - ActionOrchestrator handles actual planning
            result = {"steps": [], "prompt": prompt}
            duration = (time.time() - start) * 1000
            
            if self._trace:
                self._trace.add_entry(
                    category="acp",
                    action="create_plan",
                    params={"prompt": prompt[:100]},
                    result=result,
                    duration_ms=duration
                )
            
            return result
        except Exception as e:
            if self._trace:
                self._trace.add_entry(
                    category="acp",
                    action="create_plan",
                    params={"prompt": prompt[:100]},
                    error=str(e)
                )
            return {"error": str(e)}
    
    async def acp_apply_plan(self, plan: Dict[str, Any], auto_approve: bool = False) -> Dict[str, Any]:
        """Apply an action plan via ACP session tracking."""
        if self.read_only:
            return {"error": "Runtime is read-only", "applied": False}
        
        start = time.time()
        try:
            # Track the action in session
            if self._acp_session:
                self._acp_session.add_tool_call(
                    tool_call_id=f"plan_{int(time.time())}",
                    title="apply_plan",
                    status="applied" if auto_approve else "pending"
                )
            
            result = {"applied": True, "auto_approve": auto_approve}
            duration = (time.time() - start) * 1000
            
            if self._trace:
                self._trace.add_entry(
                    category="acp",
                    action="apply_plan",
                    params={"plan_id": plan.get("id"), "auto_approve": auto_approve},
                    result=result,
                    duration_ms=duration
                )
            
            return result
        except Exception as e:
            if self._trace:
                self._trace.add_entry(
                    category="acp",
                    action="apply_plan",
                    params={"plan_id": plan.get("id")},
                    error=str(e)
                )
            return {"error": str(e), "applied": False}
    
    def get_trace(self) -> Optional[RuntimeTrace]:
        """Get the runtime trace."""
        return self._trace
    
    def save_trace(self, path: str = None):
        """Save trace to file."""
        if not self._trace:
            return
        
        import json
        path = path or self.config.trace_file or "praisonai_trace.json"
        with open(path, "w") as f:
            json.dump(self._trace.to_dict(), f, indent=2, default=str)
        logger.info(f"Trace saved to {path}")


def create_runtime(
    workspace: str = ".",
    lsp: bool = True,
    acp: bool = True,
    approval: str = "manual",
    trace: bool = False,
    trace_file: str = None,
    json_output: bool = False,
    timeout: float = 60.0,
    model: str = None,
    verbose: bool = False
) -> InteractiveRuntime:
    """
    Factory function to create an InteractiveRuntime.
    
    Args:
        workspace: Workspace root directory
        lsp: Enable LSP subsystem
        acp: Enable ACP subsystem
        approval: Approval mode (manual, auto, scoped)
        trace: Enable trace collection
        trace_file: Path to save trace
        json_output: Enable JSON output mode
        timeout: Operation timeout
        model: LLM model to use
        verbose: Enable verbose output
        
    Returns:
        Configured InteractiveRuntime instance
    """
    config = RuntimeConfig(
        workspace=workspace,
        lsp_enabled=lsp,
        acp_enabled=acp,
        approval_mode=approval,
        trace_enabled=trace,
        trace_file=trace_file,
        json_output=json_output,
        timeout=timeout,
        model=model,
        verbose=verbose
    )
    return InteractiveRuntime(config)
