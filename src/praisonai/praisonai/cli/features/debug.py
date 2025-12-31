"""
Debug CLI handler for PraisonAI.

Provides non-interactive debug commands for testing interactive flows:
- debug interactive: Run single interactive turn
- debug lsp: Direct LSP probes
- debug acp: Direct ACP probes
- debug trace: Trace record/replay/diff
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class DebugHandler:
    """Handler for debug CLI commands."""
    
    @staticmethod
    def setup_subparser(subparsers) -> None:
        """Set up the debug subcommand parser."""
        debug_parser = subparsers.add_parser(
            "debug",
            help="Debug and test interactive flows",
            description="Debug commands for testing interactive coding assistant flows"
        )
        
        debug_subparsers = debug_parser.add_subparsers(dest="debug_command", help="Debug subcommands")
        
        # debug interactive
        interactive_parser = debug_subparsers.add_parser(
            "interactive",
            help="Run single interactive turn non-interactively",
            description="Execute one interactive turn with full LSP/ACP pipeline"
        )
        interactive_parser.add_argument(
            "-p", "--prompt",
            type=str,
            required=True,
            help="Prompt to execute"
        )
        interactive_parser.add_argument(
            "--lsp",
            action="store_true",
            default=True,
            help="Enable LSP (default: enabled)"
        )
        interactive_parser.add_argument(
            "--no-lsp",
            action="store_true",
            help="Disable LSP"
        )
        interactive_parser.add_argument(
            "--acp",
            action="store_true",
            default=True,
            help="Enable ACP (default: enabled)"
        )
        interactive_parser.add_argument(
            "--no-acp",
            action="store_true",
            help="Disable ACP"
        )
        interactive_parser.add_argument(
            "--approval",
            type=str,
            choices=["manual", "auto", "scoped"],
            default="auto",
            help="Approval mode (default: auto for debug)"
        )
        interactive_parser.add_argument(
            "--workspace", "-w",
            type=str,
            default=".",
            help="Workspace root directory"
        )
        interactive_parser.add_argument(
            "--json",
            action="store_true",
            help="Output JSON trace"
        )
        interactive_parser.add_argument(
            "--trace-file",
            type=str,
            help="Save trace to file"
        )
        interactive_parser.add_argument(
            "--timeout",
            type=float,
            default=60.0,
            help="Timeout in seconds"
        )
        interactive_parser.add_argument(
            "--model",
            type=str,
            help="LLM model to use"
        )
        interactive_parser.set_defaults(func=DebugHandler.handle_interactive)
        
        # debug lsp
        lsp_parser = debug_subparsers.add_parser(
            "lsp",
            help="Direct LSP probes",
            description="Probe LSP server directly"
        )
        lsp_subparsers = lsp_parser.add_subparsers(dest="lsp_command", help="LSP subcommands")
        
        # debug lsp status
        lsp_status = lsp_subparsers.add_parser("status", help="Show LSP status")
        lsp_status.add_argument("--workspace", "-w", type=str, default=".")
        lsp_status.add_argument("--json", action="store_true")
        lsp_status.set_defaults(func=DebugHandler.handle_lsp_status)
        
        # debug lsp symbols
        lsp_symbols = lsp_subparsers.add_parser("symbols", help="List symbols in file")
        lsp_symbols.add_argument("file", type=str, help="File path")
        lsp_symbols.add_argument("--workspace", "-w", type=str, default=".")
        lsp_symbols.add_argument("--json", action="store_true")
        lsp_symbols.set_defaults(func=DebugHandler.handle_lsp_symbols)
        
        # debug lsp definition
        lsp_def = lsp_subparsers.add_parser("definition", help="Get definition location")
        lsp_def.add_argument("location", type=str, help="file:line:col")
        lsp_def.add_argument("--workspace", "-w", type=str, default=".")
        lsp_def.add_argument("--json", action="store_true")
        lsp_def.set_defaults(func=DebugHandler.handle_lsp_definition)
        
        # debug lsp references
        lsp_refs = lsp_subparsers.add_parser("references", help="Get references")
        lsp_refs.add_argument("location", type=str, help="file:line:col")
        lsp_refs.add_argument("--workspace", "-w", type=str, default=".")
        lsp_refs.add_argument("--json", action="store_true")
        lsp_refs.set_defaults(func=DebugHandler.handle_lsp_references)
        
        # debug lsp diagnostics
        lsp_diag = lsp_subparsers.add_parser("diagnostics", help="Get diagnostics")
        lsp_diag.add_argument("file", type=str, nargs="?", help="File path (optional)")
        lsp_diag.add_argument("--all", action="store_true", help="Get all diagnostics")
        lsp_diag.add_argument("--workspace", "-w", type=str, default=".")
        lsp_diag.add_argument("--json", action="store_true")
        lsp_diag.set_defaults(func=DebugHandler.handle_lsp_diagnostics)
        
        # debug acp
        acp_parser = debug_subparsers.add_parser(
            "acp",
            help="Direct ACP probes",
            description="Probe ACP server directly"
        )
        acp_subparsers = acp_parser.add_subparsers(dest="acp_command", help="ACP subcommands")
        
        # debug acp status
        acp_status = acp_subparsers.add_parser("status", help="Show ACP status")
        acp_status.add_argument("--workspace", "-w", type=str, default=".")
        acp_status.add_argument("--json", action="store_true")
        acp_status.set_defaults(func=DebugHandler.handle_acp_status)
        
        # debug acp plan
        acp_plan = acp_subparsers.add_parser("plan", help="Create action plan")
        acp_plan.add_argument("-p", "--prompt", type=str, required=True)
        acp_plan.add_argument("--workspace", "-w", type=str, default=".")
        acp_plan.add_argument("--json", action="store_true")
        acp_plan.set_defaults(func=DebugHandler.handle_acp_plan)
        
        # debug acp apply
        acp_apply = acp_subparsers.add_parser("apply", help="Apply action plan")
        acp_apply.add_argument("-p", "--prompt", type=str, required=True)
        acp_apply.add_argument("--approval", type=str, choices=["manual", "auto", "scoped"], default="auto")
        acp_apply.add_argument("--workspace", "-w", type=str, default=".")
        acp_apply.add_argument("--json", action="store_true")
        acp_apply.set_defaults(func=DebugHandler.handle_acp_apply)
        
        # debug trace
        trace_parser = debug_subparsers.add_parser(
            "trace",
            help="Trace record/replay/diff",
            description="Manage trace recordings"
        )
        trace_subparsers = trace_parser.add_subparsers(dest="trace_command", help="Trace subcommands")
        
        # debug trace record
        trace_record = trace_subparsers.add_parser("record", help="Record session trace")
        trace_record.add_argument("-o", "--output", type=str, required=True, help="Output file")
        trace_record.set_defaults(func=DebugHandler.handle_trace_record)
        
        # debug trace replay
        trace_replay = trace_subparsers.add_parser("replay", help="Replay recorded trace")
        trace_replay.add_argument("file", type=str, help="Trace file to replay")
        trace_replay.add_argument("--json", action="store_true")
        trace_replay.set_defaults(func=DebugHandler.handle_trace_replay)
        
        # debug trace diff
        trace_diff = trace_subparsers.add_parser("diff", help="Compare two traces")
        trace_diff.add_argument("file1", type=str, help="First trace file")
        trace_diff.add_argument("file2", type=str, help="Second trace file")
        trace_diff.add_argument("--json", action="store_true")
        trace_diff.set_defaults(func=DebugHandler.handle_trace_diff)
    
    @staticmethod
    def handle_interactive(args: argparse.Namespace) -> int:
        """Handle debug interactive command."""
        return asyncio.run(DebugHandler._run_interactive(args))
    
    @staticmethod
    async def _run_interactive(args: argparse.Namespace) -> int:
        """Run interactive turn asynchronously."""
        from .interactive_runtime import create_runtime
        from .code_intelligence import CodeIntelligenceRouter
        from .action_orchestrator import ActionOrchestrator
        
        start_time = time.time()
        
        # Create runtime
        runtime = create_runtime(
            workspace=args.workspace,
            lsp=args.lsp and not args.no_lsp,
            acp=args.acp and not args.no_acp,
            approval=args.approval,
            trace=True,
            trace_file=args.trace_file,
            json_output=args.json,
            timeout=args.timeout,
            model=getattr(args, 'model', None)
        )
        
        result = {
            "prompt": args.prompt,
            "workspace": args.workspace,
            "start_time": start_time
        }
        
        try:
            # Start runtime
            status = await runtime.start()
            result["runtime_status"] = status
            
            if not status.get("started"):
                result["error"] = "Failed to start runtime"
                DebugHandler._output_result(result, args.json)
                return 1
            
            # Classify intent
            code_router = CodeIntelligenceRouter(runtime)
            action_orchestrator = ActionOrchestrator(runtime)
            
            prompt = args.prompt.lower()
            
            # Determine if this is a code query or action
            is_code_query = any(kw in prompt for kw in [
                "list", "show", "find", "where", "definition", "reference",
                "symbol", "function", "class", "diagnostic", "error"
            ])
            
            is_action = any(kw in prompt for kw in [
                "create", "edit", "modify", "delete", "rename", "add", "remove",
                "change", "update", "refactor"
            ])
            
            if is_code_query:
                # Route to code intelligence
                query_result = await code_router.handle_query(args.prompt)
                result["type"] = "code_query"
                result["query_result"] = query_result.to_dict()
                result["lsp_used"] = query_result.lsp_used
                result["citations"] = query_result.citations
                
            elif is_action:
                # Route to action orchestrator
                action_result = await action_orchestrator.execute(
                    args.prompt,
                    auto_approve=(args.approval == "auto")
                )
                result["type"] = "action"
                result["action_result"] = action_result.to_dict()
                result["read_only_blocked"] = action_result.read_only_blocked
                
            else:
                # General query - just return status
                result["type"] = "general"
                result["message"] = "Query processed"
            
            # Get trace
            trace = runtime.get_trace()
            if trace:
                result["trace"] = trace.to_dict()
            
            result["success"] = True
            
        except Exception as e:
            result["error"] = str(e)
            result["success"] = False
            logger.exception("Debug interactive failed")
            
        finally:
            await runtime.stop()
            result["end_time"] = time.time()
            result["duration_ms"] = (result["end_time"] - start_time) * 1000
        
        # Save trace if requested
        if args.trace_file and "trace" in result:
            with open(args.trace_file, "w") as f:
                json.dump(result["trace"], f, indent=2, default=str)
            if not args.json:
                print(f"Trace saved to: {args.trace_file}")
        
        DebugHandler._output_result(result, args.json)
        return 0 if result.get("success") else 1
    
    @staticmethod
    def handle_lsp_status(args: argparse.Namespace) -> int:
        """Handle debug lsp status command."""
        return asyncio.run(DebugHandler._run_lsp_status(args))
    
    @staticmethod
    async def _run_lsp_status(args: argparse.Namespace) -> int:
        """Run LSP status check."""
        from .interactive_runtime import create_runtime
        
        runtime = create_runtime(
            workspace=args.workspace,
            lsp=True,
            acp=False
        )
        
        try:
            await runtime.start()
            result = {
                "lsp_enabled": True,
                "lsp_ready": runtime.lsp_ready,
                "lsp_status": runtime._lsp_state.status.value,
                "lsp_error": runtime._lsp_state.error,
                "workspace": args.workspace
            }
            
            DebugHandler._output_result(result, args.json)
            return 0 if runtime.lsp_ready else 1
            
        finally:
            await runtime.stop()
    
    @staticmethod
    def handle_lsp_symbols(args: argparse.Namespace) -> int:
        """Handle debug lsp symbols command."""
        return asyncio.run(DebugHandler._run_lsp_symbols(args))
    
    @staticmethod
    async def _run_lsp_symbols(args: argparse.Namespace) -> int:
        """Run LSP symbols query."""
        from .interactive_runtime import create_runtime
        from .code_intelligence import CodeIntelligenceRouter
        
        runtime = create_runtime(
            workspace=args.workspace,
            lsp=True,
            acp=False
        )
        
        try:
            await runtime.start()
            
            if not runtime.lsp_ready:
                # Use fallback
                router = CodeIntelligenceRouter(runtime)
                result = await router._fallback_list_symbols(args.file)
            else:
                symbols = await runtime.lsp_get_symbols(args.file)
                result = {
                    "file": args.file,
                    "symbols": symbols,
                    "count": len(symbols) if symbols else 0,
                    "lsp_used": True
                }
            
            if hasattr(result, 'to_dict'):
                result = result.to_dict()
            
            DebugHandler._output_result(result, args.json)
            return 0
            
        finally:
            await runtime.stop()
    
    @staticmethod
    def handle_lsp_definition(args: argparse.Namespace) -> int:
        """Handle debug lsp definition command."""
        return asyncio.run(DebugHandler._run_lsp_definition(args))
    
    @staticmethod
    async def _run_lsp_definition(args: argparse.Namespace) -> int:
        """Run LSP definition query."""
        from .interactive_runtime import create_runtime
        
        # Parse location
        parts = args.location.split(":")
        if len(parts) != 3:
            print("Error: Location must be in format file:line:col", file=sys.stderr)
            return 1
        
        file_path, line, col = parts[0], int(parts[1]), int(parts[2])
        
        runtime = create_runtime(
            workspace=args.workspace,
            lsp=True,
            acp=False
        )
        
        try:
            await runtime.start()
            
            definitions = await runtime.lsp_get_definition(file_path, line, col)
            result = {
                "file": file_path,
                "line": line,
                "col": col,
                "definitions": definitions,
                "count": len(definitions) if definitions else 0,
                "lsp_used": runtime.lsp_ready
            }
            
            DebugHandler._output_result(result, args.json)
            return 0
            
        finally:
            await runtime.stop()
    
    @staticmethod
    def handle_lsp_references(args: argparse.Namespace) -> int:
        """Handle debug lsp references command."""
        return asyncio.run(DebugHandler._run_lsp_references(args))
    
    @staticmethod
    async def _run_lsp_references(args: argparse.Namespace) -> int:
        """Run LSP references query."""
        from .interactive_runtime import create_runtime
        
        # Parse location
        parts = args.location.split(":")
        if len(parts) != 3:
            print("Error: Location must be in format file:line:col", file=sys.stderr)
            return 1
        
        file_path, line, col = parts[0], int(parts[1]), int(parts[2])
        
        runtime = create_runtime(
            workspace=args.workspace,
            lsp=True,
            acp=False
        )
        
        try:
            await runtime.start()
            
            references = await runtime.lsp_get_references(file_path, line, col)
            result = {
                "file": file_path,
                "line": line,
                "col": col,
                "references": references,
                "count": len(references) if references else 0,
                "lsp_used": runtime.lsp_ready
            }
            
            DebugHandler._output_result(result, args.json)
            return 0
            
        finally:
            await runtime.stop()
    
    @staticmethod
    def handle_lsp_diagnostics(args: argparse.Namespace) -> int:
        """Handle debug lsp diagnostics command."""
        return asyncio.run(DebugHandler._run_lsp_diagnostics(args))
    
    @staticmethod
    async def _run_lsp_diagnostics(args: argparse.Namespace) -> int:
        """Run LSP diagnostics query."""
        from .interactive_runtime import create_runtime
        
        runtime = create_runtime(
            workspace=args.workspace,
            lsp=True,
            acp=False
        )
        
        try:
            await runtime.start()
            
            file_path = args.file if not args.all else None
            diagnostics = await runtime.lsp_get_diagnostics(file_path)
            
            result = {
                "file": file_path or "all",
                "diagnostics": diagnostics,
                "count": len(diagnostics) if diagnostics else 0,
                "lsp_used": runtime.lsp_ready
            }
            
            DebugHandler._output_result(result, args.json)
            return 0
            
        finally:
            await runtime.stop()
    
    @staticmethod
    def handle_acp_status(args: argparse.Namespace) -> int:
        """Handle debug acp status command."""
        return asyncio.run(DebugHandler._run_acp_status(args))
    
    @staticmethod
    async def _run_acp_status(args: argparse.Namespace) -> int:
        """Run ACP status check."""
        from .interactive_runtime import create_runtime
        
        runtime = create_runtime(
            workspace=args.workspace,
            lsp=False,
            acp=True
        )
        
        try:
            await runtime.start()
            result = {
                "acp_enabled": True,
                "acp_ready": runtime.acp_ready,
                "acp_status": runtime._acp_state.status.value,
                "acp_error": runtime._acp_state.error,
                "read_only": runtime.read_only,
                "workspace": args.workspace
            }
            
            DebugHandler._output_result(result, args.json)
            return 0 if runtime.acp_ready else 1
            
        finally:
            await runtime.stop()
    
    @staticmethod
    def handle_acp_plan(args: argparse.Namespace) -> int:
        """Handle debug acp plan command."""
        return asyncio.run(DebugHandler._run_acp_plan(args))
    
    @staticmethod
    async def _run_acp_plan(args: argparse.Namespace) -> int:
        """Run ACP plan creation."""
        from .interactive_runtime import create_runtime
        from .action_orchestrator import ActionOrchestrator
        
        runtime = create_runtime(
            workspace=args.workspace,
            lsp=False,
            acp=True
        )
        
        try:
            await runtime.start()
            
            orchestrator = ActionOrchestrator(runtime)
            result = await orchestrator.create_plan(args.prompt)
            
            DebugHandler._output_result(result.to_dict(), args.json)
            return 0 if result.success else 1
            
        finally:
            await runtime.stop()
    
    @staticmethod
    def handle_acp_apply(args: argparse.Namespace) -> int:
        """Handle debug acp apply command."""
        return asyncio.run(DebugHandler._run_acp_apply(args))
    
    @staticmethod
    async def _run_acp_apply(args: argparse.Namespace) -> int:
        """Run ACP plan and apply."""
        from .interactive_runtime import create_runtime
        from .action_orchestrator import ActionOrchestrator
        
        runtime = create_runtime(
            workspace=args.workspace,
            lsp=False,
            acp=True,
            approval=args.approval
        )
        
        try:
            await runtime.start()
            
            orchestrator = ActionOrchestrator(runtime)
            result = await orchestrator.execute(
                args.prompt,
                auto_approve=(args.approval == "auto")
            )
            
            DebugHandler._output_result(result.to_dict(), args.json)
            return 0 if result.success else 1
            
        finally:
            await runtime.stop()
    
    @staticmethod
    def handle_trace_record(args: argparse.Namespace) -> int:
        """Handle debug trace record command."""
        print(f"Trace recording will be saved to: {args.output}")
        print("Start an interactive session with --trace-file to record.")
        return 0
    
    @staticmethod
    def handle_trace_replay(args: argparse.Namespace) -> int:
        """Handle debug trace replay command."""
        try:
            with open(args.file) as f:
                trace = json.load(f)
            
            if args.json:
                print(json.dumps(trace, indent=2))
            else:
                print(f"Trace from: {args.file}")
                print(f"Start time: {trace.get('start_time')}")
                print(f"End time: {trace.get('end_time')}")
                print(f"Entries: {len(trace.get('entries', []))}")
                print("\nEntries:")
                for entry in trace.get("entries", []):
                    print(f"  [{entry.get('category')}] {entry.get('action')}")
                    if entry.get('duration_ms'):
                        print(f"    Duration: {entry.get('duration_ms'):.2f}ms")
                    if entry.get('error'):
                        print(f"    Error: {entry.get('error')}")
            
            return 0
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    
    @staticmethod
    def handle_trace_diff(args: argparse.Namespace) -> int:
        """Handle debug trace diff command."""
        try:
            with open(args.file1) as f:
                trace1 = json.load(f)
            with open(args.file2) as f:
                trace2 = json.load(f)
            
            diff = {
                "file1": args.file1,
                "file2": args.file2,
                "entries_diff": {
                    "file1_count": len(trace1.get("entries", [])),
                    "file2_count": len(trace2.get("entries", []))
                },
                "duration_diff": {
                    "file1": trace1.get("end_time", 0) - trace1.get("start_time", 0),
                    "file2": trace2.get("end_time", 0) - trace2.get("start_time", 0)
                }
            }
            
            DebugHandler._output_result(diff, args.json)
            return 0
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    
    @staticmethod
    def _output_result(result: Dict[str, Any], as_json: bool) -> None:
        """Output result in appropriate format."""
        if as_json:
            print(json.dumps(result, indent=2, default=str))
        else:
            for key, value in result.items():
                if isinstance(value, dict):
                    print(f"{key}:")
                    for k, v in value.items():
                        print(f"  {k}: {v}")
                elif isinstance(value, list):
                    print(f"{key}: ({len(value)} items)")
                    for item in value[:5]:  # Show first 5
                        print(f"  - {item}")
                    if len(value) > 5:
                        print(f"  ... and {len(value) - 5} more")
                else:
                    print(f"{key}: {value}")


def setup_debug_subparser(subparsers) -> None:
    """Set up the debug subcommand parser."""
    DebugHandler.setup_subparser(subparsers)


def run_debug_command(args: List[str]) -> int:
    """Run debug command from CLI."""
    parser = argparse.ArgumentParser(
        prog="praisonai debug",
        description="Debug and test interactive coding assistant flows"
    )
    subparsers = parser.add_subparsers(dest="debug_command", help="Debug subcommands")
    
    # debug interactive
    interactive_parser = subparsers.add_parser(
        "interactive",
        help="Run single interactive turn non-interactively",
        description="Execute one interactive turn with full LSP/ACP pipeline"
    )
    interactive_parser.add_argument("-p", "--prompt", type=str, required=True, help="Prompt to execute")
    interactive_parser.add_argument("--lsp", action="store_true", default=True, help="Enable LSP (default: enabled)")
    interactive_parser.add_argument("--no-lsp", action="store_true", help="Disable LSP")
    interactive_parser.add_argument("--acp", action="store_true", default=True, help="Enable ACP (default: enabled)")
    interactive_parser.add_argument("--no-acp", action="store_true", help="Disable ACP")
    interactive_parser.add_argument("--approval", type=str, choices=["manual", "auto", "scoped"], default="auto", help="Approval mode")
    interactive_parser.add_argument("--workspace", "-w", type=str, default=".", help="Workspace root directory")
    interactive_parser.add_argument("--json", action="store_true", help="Output JSON trace")
    interactive_parser.add_argument("--trace-file", type=str, help="Save trace to file")
    interactive_parser.add_argument("--timeout", type=float, default=60.0, help="Timeout in seconds")
    interactive_parser.add_argument("--model", type=str, help="LLM model to use")
    interactive_parser.set_defaults(func=DebugHandler.handle_interactive)
    
    # debug lsp
    lsp_parser = subparsers.add_parser("lsp", help="Direct LSP probes")
    lsp_subparsers = lsp_parser.add_subparsers(dest="lsp_command", help="LSP subcommands")
    
    # debug lsp status
    lsp_status = lsp_subparsers.add_parser("status", help="Show LSP status")
    lsp_status.add_argument("--workspace", "-w", type=str, default=".")
    lsp_status.add_argument("--json", action="store_true")
    lsp_status.set_defaults(func=DebugHandler.handle_lsp_status)
    
    # debug lsp symbols
    lsp_symbols = lsp_subparsers.add_parser("symbols", help="List symbols in file")
    lsp_symbols.add_argument("file", type=str, help="File path")
    lsp_symbols.add_argument("--workspace", "-w", type=str, default=".")
    lsp_symbols.add_argument("--json", action="store_true")
    lsp_symbols.set_defaults(func=DebugHandler.handle_lsp_symbols)
    
    # debug lsp definition
    lsp_def = lsp_subparsers.add_parser("definition", help="Get definition location")
    lsp_def.add_argument("location", type=str, help="file:line:col")
    lsp_def.add_argument("--workspace", "-w", type=str, default=".")
    lsp_def.add_argument("--json", action="store_true")
    lsp_def.set_defaults(func=DebugHandler.handle_lsp_definition)
    
    # debug lsp references
    lsp_refs = lsp_subparsers.add_parser("references", help="Get references")
    lsp_refs.add_argument("location", type=str, help="file:line:col")
    lsp_refs.add_argument("--workspace", "-w", type=str, default=".")
    lsp_refs.add_argument("--json", action="store_true")
    lsp_refs.set_defaults(func=DebugHandler.handle_lsp_references)
    
    # debug lsp diagnostics
    lsp_diag = lsp_subparsers.add_parser("diagnostics", help="Get diagnostics")
    lsp_diag.add_argument("file", type=str, nargs="?", help="File path (optional)")
    lsp_diag.add_argument("--all", action="store_true", help="Get all diagnostics")
    lsp_diag.add_argument("--workspace", "-w", type=str, default=".")
    lsp_diag.add_argument("--json", action="store_true")
    lsp_diag.set_defaults(func=DebugHandler.handle_lsp_diagnostics)
    
    # debug acp
    acp_parser = subparsers.add_parser("acp", help="Direct ACP probes")
    acp_subparsers = acp_parser.add_subparsers(dest="acp_command", help="ACP subcommands")
    
    # debug acp status
    acp_status = acp_subparsers.add_parser("status", help="Show ACP status")
    acp_status.add_argument("--workspace", "-w", type=str, default=".")
    acp_status.add_argument("--json", action="store_true")
    acp_status.set_defaults(func=DebugHandler.handle_acp_status)
    
    # debug acp plan
    acp_plan = acp_subparsers.add_parser("plan", help="Create action plan")
    acp_plan.add_argument("-p", "--prompt", type=str, required=True)
    acp_plan.add_argument("--workspace", "-w", type=str, default=".")
    acp_plan.add_argument("--json", action="store_true")
    acp_plan.set_defaults(func=DebugHandler.handle_acp_plan)
    
    # debug acp apply
    acp_apply = acp_subparsers.add_parser("apply", help="Apply action plan")
    acp_apply.add_argument("-p", "--prompt", type=str, required=True)
    acp_apply.add_argument("--approval", type=str, choices=["manual", "auto", "scoped"], default="auto")
    acp_apply.add_argument("--workspace", "-w", type=str, default=".")
    acp_apply.add_argument("--json", action="store_true")
    acp_apply.set_defaults(func=DebugHandler.handle_acp_apply)
    
    # debug trace
    trace_parser = subparsers.add_parser("trace", help="Trace record/replay/diff")
    trace_subparsers = trace_parser.add_subparsers(dest="trace_command", help="Trace subcommands")
    
    # debug trace record
    trace_record = trace_subparsers.add_parser("record", help="Record session trace")
    trace_record.add_argument("-o", "--output", type=str, required=True, help="Output file")
    trace_record.set_defaults(func=DebugHandler.handle_trace_record)
    
    # debug trace replay
    trace_replay = trace_subparsers.add_parser("replay", help="Replay recorded trace")
    trace_replay.add_argument("file", type=str, help="Trace file to replay")
    trace_replay.add_argument("--json", action="store_true")
    trace_replay.set_defaults(func=DebugHandler.handle_trace_replay)
    
    # debug trace diff
    trace_diff = trace_subparsers.add_parser("diff", help="Compare two traces")
    trace_diff.add_argument("file1", type=str, help="First trace file")
    trace_diff.add_argument("file2", type=str, help="Second trace file")
    trace_diff.add_argument("--json", action="store_true")
    trace_diff.set_defaults(func=DebugHandler.handle_trace_diff)
    
    parsed = parser.parse_args(args)
    if hasattr(parsed, 'func'):
        return parsed.func(parsed)
    else:
        parser.print_help()
        return 0
