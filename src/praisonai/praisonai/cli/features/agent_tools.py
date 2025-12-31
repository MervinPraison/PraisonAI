"""
Agent-Centric Tools for PraisonAI Interactive Mode.

These tools route file operations and code intelligence through LSP/ACP,
making the Agent the central orchestrator for all actions.
"""

import asyncio
import json
import logging
from typing import Callable, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .interactive_runtime import InteractiveRuntime
    from .code_intelligence import CodeIntelligenceRouter
    from .action_orchestrator import ActionOrchestrator

logger = logging.getLogger(__name__)


def create_agent_centric_tools(
    runtime: "InteractiveRuntime",
    router: "CodeIntelligenceRouter" = None,
    orchestrator: "ActionOrchestrator" = None
) -> List[Callable]:
    """
    Create tools that route through LSP/ACP for agent-centric architecture.
    
    Args:
        runtime: The InteractiveRuntime instance
        router: Optional CodeIntelligenceRouter (created if not provided)
        orchestrator: Optional ActionOrchestrator (created if not provided)
        
    Returns:
        List of tool functions for the Agent
    """
    from .code_intelligence import CodeIntelligenceRouter
    from .action_orchestrator import ActionOrchestrator
    
    if router is None:
        router = CodeIntelligenceRouter(runtime)
    if orchestrator is None:
        orchestrator = ActionOrchestrator(runtime)
    
    # Helper to run async functions synchronously
    def run_async(coro):
        """Run async coroutine synchronously."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create a new loop in a thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, coro)
                    return future.result(timeout=60)
            else:
                return loop.run_until_complete(coro)
        except RuntimeError:
            return asyncio.run(coro)
    
    # =========================================================================
    # ACP-Powered File Tools
    # =========================================================================
    
    def acp_create_file(filepath: str, content: str) -> str:
        """
        Create a file through ACP with plan/approve/apply/verify flow.
        
        This tool routes file creation through the ActionOrchestrator,
        ensuring proper tracking, approval, and verification.
        
        Args:
            filepath: Path to the file to create (relative to workspace)
            content: Content to write to the file
            
        Returns:
            JSON string with result including plan status and verification
        """
        async def _create():
            # Build a detailed prompt for the orchestrator
            prompt = f"create file {filepath}"
            
            # Create plan
            result = await orchestrator.create_plan(prompt)
            if not result.success:
                return json.dumps({
                    "success": False,
                    "error": result.error,
                    "read_only": result.read_only_blocked
                })
            
            plan = result.plan
            
            # Update the plan step with actual content
            if plan.steps:
                plan.steps[0].params["content"] = content
            
            # Approve based on runtime config
            auto_approve = runtime.config.approval_mode == "auto"
            approved = await orchestrator.approve_plan(plan, auto=auto_approve)
            
            if not approved and runtime.config.approval_mode == "manual":
                return json.dumps({
                    "success": False,
                    "error": "Manual approval required",
                    "plan": plan.to_dict(),
                    "requires_approval": True
                })
            
            # Apply the plan
            result = await orchestrator.apply_plan(plan, force=auto_approve)
            if not result.success:
                return json.dumps({
                    "success": False,
                    "error": result.error,
                    "plan": plan.to_dict()
                })
            
            # Verify
            result = await orchestrator.verify_plan(plan)
            
            return json.dumps({
                "success": result.success,
                "file_created": filepath,
                "plan_id": plan.id,
                "status": plan.status.value,
                "verified": result.success
            })
        
        return run_async(_create())
    
    def acp_edit_file(filepath: str, new_content: str) -> str:
        """
        Edit a file through ACP with plan/approve/apply/verify flow.
        
        Args:
            filepath: Path to the file to edit (relative to workspace)
            new_content: New content for the file
            
        Returns:
            JSON string with result including plan status
        """
        async def _edit():
            prompt = f"edit file {filepath}"
            
            result = await orchestrator.create_plan(prompt)
            if not result.success:
                return json.dumps({
                    "success": False,
                    "error": result.error,
                    "read_only": result.read_only_blocked
                })
            
            plan = result.plan
            
            # Update step with new content
            if plan.steps:
                plan.steps[0].params["new_content"] = new_content
            
            auto_approve = runtime.config.approval_mode == "auto"
            approved = await orchestrator.approve_plan(plan, auto=auto_approve)
            
            if not approved and runtime.config.approval_mode == "manual":
                return json.dumps({
                    "success": False,
                    "error": "Manual approval required",
                    "requires_approval": True
                })
            
            result = await orchestrator.apply_plan(plan, force=auto_approve)
            
            return json.dumps({
                "success": result.success,
                "file_edited": filepath,
                "plan_id": plan.id,
                "error": result.error
            })
        
        return run_async(_edit())
    
    def acp_delete_file(filepath: str) -> str:
        """
        Delete a file through ACP with plan/approve/apply/verify flow.
        
        Args:
            filepath: Path to the file to delete
            
        Returns:
            JSON string with result
        """
        async def _delete():
            prompt = f"delete file {filepath}"
            
            result = await orchestrator.create_plan(prompt)
            if not result.success:
                return json.dumps({
                    "success": False,
                    "error": result.error
                })
            
            plan = result.plan
            
            # Delete requires explicit approval even in auto mode
            auto_approve = runtime.config.approval_mode == "auto"
            approved = await orchestrator.approve_plan(plan, auto=auto_approve)
            
            if not approved:
                return json.dumps({
                    "success": False,
                    "error": "Delete requires approval",
                    "requires_approval": True
                })
            
            result = await orchestrator.apply_plan(plan)
            result = await orchestrator.verify_plan(plan)
            
            return json.dumps({
                "success": result.success,
                "file_deleted": filepath,
                "verified": result.success
            })
        
        return run_async(_delete())
    
    def acp_execute_command(command: str, cwd: str = None) -> str:
        """
        Execute a shell command through ACP with tracking.
        
        Args:
            command: The command to execute
            cwd: Working directory (optional)
            
        Returns:
            JSON string with command output
        """
        async def _execute():
            prompt = f"run command: {command}"
            
            result = await orchestrator.create_plan(prompt)
            if not result.success:
                return json.dumps({
                    "success": False,
                    "error": result.error
                })
            
            plan = result.plan
            
            # Commands require approval
            auto_approve = runtime.config.approval_mode == "auto"
            approved = await orchestrator.approve_plan(plan, auto=auto_approve)
            
            if not approved:
                return json.dumps({
                    "success": False,
                    "error": "Command requires approval",
                    "requires_approval": True
                })
            
            result = await orchestrator.apply_plan(plan)
            
            # Extract command result
            if plan.steps and plan.steps[0].result:
                cmd_result = plan.steps[0].result
                return json.dumps({
                    "success": result.success,
                    "command": command,
                    "stdout": cmd_result.get("stdout", ""),
                    "stderr": cmd_result.get("stderr", ""),
                    "returncode": cmd_result.get("returncode", -1)
                })
            
            return json.dumps({
                "success": result.success,
                "error": result.error
            })
        
        return run_async(_execute())
    
    # =========================================================================
    # LSP-Powered Code Intelligence Tools
    # =========================================================================
    
    def lsp_list_symbols(file_path: str) -> str:
        """
        List all symbols (functions, classes, methods) in a file using LSP.
        
        Falls back to regex-based extraction if LSP is unavailable.
        
        Args:
            file_path: Path to the file to analyze
            
        Returns:
            JSON string with list of symbols and their locations
        """
        async def _list():
            result = await router.handle_query(
                f"list all functions and classes in {file_path}",
                file_path=file_path
            )
            return json.dumps(result.to_dict())
        
        return run_async(_list())
    
    def lsp_find_definition(symbol: str, file_path: str = None) -> str:
        """
        Find where a symbol is defined using LSP.
        
        Args:
            symbol: The symbol name to find
            file_path: Optional file path for context
            
        Returns:
            JSON string with definition location(s)
        """
        async def _find():
            query = f"where is {symbol} defined"
            if file_path:
                query += f" in {file_path}"
            
            result = await router.handle_query(query, file_path=file_path)
            return json.dumps(result.to_dict())
        
        return run_async(_find())
    
    def lsp_find_references(symbol: str, file_path: str = None) -> str:
        """
        Find all references to a symbol using LSP.
        
        Args:
            symbol: The symbol name to find references for
            file_path: Optional file path for context
            
        Returns:
            JSON string with reference locations
        """
        async def _find():
            query = f"find all references to {symbol}"
            if file_path:
                query += f" in {file_path}"
            
            result = await router.handle_query(query, file_path=file_path)
            return json.dumps(result.to_dict())
        
        return run_async(_find())
    
    def lsp_get_diagnostics(file_path: str = None) -> str:
        """
        Get diagnostics (errors, warnings) for a file using LSP.
        
        Args:
            file_path: Path to the file (optional, gets all if not specified)
            
        Returns:
            JSON string with diagnostic information
        """
        async def _get():
            query = "show all errors and warnings"
            if file_path:
                query += f" in {file_path}"
            
            result = await router.handle_query(query, file_path=file_path)
            return json.dumps(result.to_dict())
        
        return run_async(_get())
    
    # =========================================================================
    # Basic File Tools (for read-only operations)
    # =========================================================================
    
    def read_file(filepath: str) -> str:
        """
        Read content from a file.
        
        This is a read-only operation that doesn't require ACP.
        
        Args:
            filepath: Path to the file to read
            
        Returns:
            File content or error message
        """
        from pathlib import Path
        
        try:
            path = Path(filepath)
            if not path.is_absolute():
                path = Path(runtime.config.workspace) / filepath
            
            if not path.exists():
                return json.dumps({"error": f"File not found: {filepath}"})
            
            content = path.read_text()
            
            # Track in trace if enabled
            if runtime._trace:
                runtime._trace.add_entry(
                    category="file",
                    action="read",
                    params={"file": str(path)},
                    result={"size": len(content)}
                )
            
            return content
            
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    def list_files(directory: str = ".", pattern: str = "*") -> str:
        """
        List files in a directory.
        
        Args:
            directory: Directory to list (relative to workspace)
            pattern: Glob pattern to filter files
            
        Returns:
            JSON string with list of files
        """
        from pathlib import Path
        
        try:
            path = Path(directory)
            if not path.is_absolute():
                path = Path(runtime.config.workspace) / directory
            
            if not path.exists():
                return json.dumps({"error": f"Directory not found: {directory}"})
            
            files = []
            for f in path.glob(pattern):
                files.append({
                    "name": f.name,
                    "path": str(f.relative_to(runtime.config.workspace)),
                    "is_dir": f.is_dir(),
                    "size": f.stat().st_size if f.is_file() else None
                })
            
            return json.dumps({"files": files, "count": len(files)})
            
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    # Return all tools
    return [
        # ACP-powered file tools
        acp_create_file,
        acp_edit_file,
        acp_delete_file,
        acp_execute_command,
        # LSP-powered code intelligence
        lsp_list_symbols,
        lsp_find_definition,
        lsp_find_references,
        lsp_get_diagnostics,
        # Basic read-only tools
        read_file,
        list_files,
    ]


def get_tool_descriptions() -> Dict[str, str]:
    """Get descriptions of all agent-centric tools."""
    return {
        "acp_create_file": "Create a file through ACP with plan/approve/apply/verify",
        "acp_edit_file": "Edit a file through ACP with tracking",
        "acp_delete_file": "Delete a file through ACP (requires approval)",
        "acp_execute_command": "Execute a shell command through ACP",
        "lsp_list_symbols": "List symbols in a file using LSP",
        "lsp_find_definition": "Find where a symbol is defined",
        "lsp_find_references": "Find all references to a symbol",
        "lsp_get_diagnostics": "Get errors and warnings for a file",
        "read_file": "Read content from a file (read-only)",
        "list_files": "List files in a directory",
    }
