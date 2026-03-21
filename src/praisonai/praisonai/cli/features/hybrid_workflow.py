"""
Hybrid Workflow Executor for PraisonAI CLI.

Executes workflows with `type: hybrid` that combine:
- Deterministic steps (run, python, script, action) from JobWorkflowExecutor
- Agent-centric steps (agent, judge, approve) from JobWorkflowExecutor
- Multi-agent workflow steps (using praisonaiagents)

This provides a unified executor that can handle both paradigms in a single workflow.

Usage:
    praisonai workflow run hybrid-workflow.yaml
    praisonai workflow run hybrid-workflow.yaml --dry-run
"""

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class HybridWorkflowExecutor:
    """
    Execute a `type: hybrid` workflow — combines job and agent workflow capabilities.

    Step types (detected by key):
        From JobWorkflowExecutor (deterministic + agent-centric):
            run:     Shell command via subprocess
            python:  Python script file
            script:  Inline Python code
            action:  Built-in or YAML-defined action
            agent:   Single AI agent execution
            judge:   AI quality gate with threshold
            approve: AI or human approval gate

        From Agent Workflows (multi-agent):
            workflow: Execute a multi-agent workflow step
            parallel: Execute multiple steps in parallel
    """

    def __init__(self, data: Dict[str, Any], file_path: str):
        self._data = data
        self._file_path = file_path
        self._name = data.get("name", Path(file_path).stem)
        self._description = data.get("description", "")
        self._steps = data.get("steps", [])
        self._agents = data.get("agents", {})
        self._vars = data.get("vars", {})
        self._flag_defs = data.get("flags", {})
        self._cwd = str(Path(file_path).parent.resolve())
        
        # Lazy-loaded executors
        self._job_executor = None

    def _get_job_executor(self):
        """Lazy-load JobWorkflowExecutor for deterministic/agent-centric steps."""
        if self._job_executor is None:
            from .job_workflow import JobWorkflowExecutor
            self._job_executor = JobWorkflowExecutor(self._data, self._file_path)
        return self._job_executor

    def run(self, args: List[str]) -> Optional[Dict[str, Any]]:
        """
        Execute the hybrid workflow.

        Args:
            args: Raw CLI args (may contain --dry-run, etc.)

        Returns:
            Result dict with status and step outcomes.
        """
        from rich.console import Console
        from rich.panel import Panel

        console = Console()
        dry_run = "--dry-run" in args
        flags = self._parse_flags(args)

        # Header
        mode = "[yellow]DRY RUN[/yellow]" if dry_run else "[green]EXECUTE[/green]"
        console.print(Panel(
            f"[bold]{self._name}[/bold]\n{self._description}",
            title=f"🔀 Hybrid Workflow — {mode}",
            border_style="magenta",
        ))

        if flags:
            flag_str = ", ".join(f"--{k}" for k, v in flags.items() if v)
            console.print(f"  [dim]Flags:[/dim] {flag_str}")
        console.print()

        results: List[Dict[str, Any]] = []
        failed = False

        for i, step in enumerate(self._steps, 1):
            step_name = step.get("name", f"Step {i}")

            # Conditional: if
            condition = step.get("if")
            if condition and not self._eval_condition(condition, flags):
                console.print(f"  [dim]⊘ {step_name} — skipped (condition false)[/dim]")
                results.append({"name": step_name, "status": "skipped"})
                continue

            # Detect step type and route to appropriate executor
            step_type = self._detect_step_type(step)

            if dry_run:
                display = self._format_dry_run_display(step_type, step)
                console.print(f"  [cyan]● {step_name}[/cyan] — [dim]{display}[/dim]")
                results.append({"name": step_name, "status": "dry-run", "type": step_type})
                continue

            # Execute
            console.print(f"  [bold]▸ {step_name}[/bold] ", end="")
            t0 = time.time()
            
            try:
                if step_type in ("shell", "python", "script", "action", "agent", "judge", "approve"):
                    # Route to JobWorkflowExecutor
                    result = self._execute_job_step(step_type, step, flags)
                elif step_type == "workflow":
                    # Execute multi-agent workflow step
                    result = self._execute_workflow_step(step, flags)
                elif step_type == "parallel":
                    # Execute parallel steps
                    result = self._execute_parallel_step(step, flags)
                else:
                    result = {"ok": False, "error": f"Unknown step type: {step_type}"}
            except Exception as e:
                result = {"ok": False, "error": str(e)}

            elapsed = time.time() - t0

            if result["ok"]:
                console.print(f"[green]✓[/green] [dim]({elapsed:.1f}s)[/dim]")
            else:
                console.print(f"[red]✗[/red] [dim]({elapsed:.1f}s)[/dim]")
                if result.get("error"):
                    console.print(f"    [red]{result['error']}[/red]")
                failed = True

            results.append({
                "name": step_name,
                "status": "ok" if result["ok"] else "error",
                "type": step_type,
                "elapsed": elapsed,
                **({k: v for k, v in result.items() if k not in ("ok",)}),
            })

            # Stop on failure unless continue_on_error
            if failed and not step.get("continue_on_error", False):
                break

        # Summary
        console.print()
        if dry_run:
            console.print(f"[yellow]🔀 Dry run complete — {len(results)} steps planned[/yellow]")
        elif failed:
            console.print("[red]✗ Hybrid workflow failed[/red]")
        else:
            console.print(f"[green]✓ Hybrid workflow completed — {len(results)} steps[/green]")

        return {"name": self._name, "results": results, "ok": not failed, "dry_run": dry_run}

    def _detect_step_type(self, step: Dict) -> str:
        """Detect step type from keys."""
        # Job workflow step types
        if "run" in step:
            return "shell"
        if "python" in step:
            return "python"
        if "script" in step:
            return "script"
        if "action" in step:
            return "action"
        if "agent" in step:
            return "agent"
        if "judge" in step:
            return "judge"
        if "approve" in step:
            return "approve"
        # Hybrid-specific step types
        if "workflow" in step:
            return "workflow"
        if "parallel" in step:
            return "parallel"
        return "unknown"

    def _format_dry_run_display(self, step_type: str, step: Dict) -> str:
        """Format dry-run display based on step type."""
        if step_type == "agent":
            agent_info = step.get("agent", {})
            if isinstance(agent_info, dict):
                role = agent_info.get("role", "Assistant")
                model = agent_info.get("model", "gpt-4o-mini")
                return f"agent: {role} (model: {model})"
            return f"agent: {agent_info}"
        elif step_type == "judge":
            judge_info = step.get("judge", {})
            threshold = judge_info.get("threshold", 7.0) if isinstance(judge_info, dict) else 7.0
            return f"judge: threshold={threshold}"
        elif step_type == "approve":
            approve_info = step.get("approve", {})
            risk = approve_info.get("risk_level", "medium") if isinstance(approve_info, dict) else "medium"
            return f"approve: risk={risk}"
        elif step_type == "workflow":
            workflow_info = step.get("workflow", {})
            agent_ref = workflow_info.get("agent", "unknown") if isinstance(workflow_info, dict) else workflow_info
            return f"workflow: agent={agent_ref}"
        elif step_type == "parallel":
            parallel_steps = step.get("parallel", [])
            return f"parallel: {len(parallel_steps)} steps"
        elif step_type == "shell":
            cmd = step.get("run", "")
            return f"shell: {cmd[:60]}..." if len(cmd) > 60 else f"shell: {cmd}"
        else:
            return f"{step_type}"

    def _execute_job_step(self, step_type: str, step: Dict, flags: Dict) -> Dict:
        """Execute a step using JobWorkflowExecutor."""
        executor = self._get_job_executor()
        
        # Get the target based on step type
        type_to_key = {
            "shell": "run",
            "python": "python",
            "script": "script",
            "action": "action",
            "agent": "agent",
            "judge": "judge",
            "approve": "approve",
        }
        key = type_to_key.get(step_type)
        target = step.get(key)
        
        return executor._execute_step(step_type, target, step, flags)

    def _execute_workflow_step(self, step: Dict, flags: Dict) -> Dict:
        """Execute a multi-agent workflow step."""
        workflow_config = step.get("workflow", {})
        
        # Get agent reference
        agent_ref = workflow_config.get("agent") if isinstance(workflow_config, dict) else workflow_config
        
        if not agent_ref:
            return {"ok": False, "error": "Workflow step requires 'agent' reference"}
        
        # Look up agent in agents: block
        agent_config = self._agents.get(agent_ref)
        if not agent_config:
            return {"ok": False, "error": f"Agent not found: {agent_ref}"}
        
        try:
            from praisonaiagents import Agent
            
            agent = Agent(
                name=agent_config.get("name", agent_ref),
                role=agent_config.get("role", "Assistant"),
                instructions=agent_config.get("instructions", ""),
                llm=agent_config.get("model", "gpt-4o-mini"),
            )
            
            action = workflow_config.get("action", agent_config.get("goal", ""))
            result = agent.chat(action)
            
            return {"ok": True, "output": str(result) if result else ""}
            
        except ImportError:
            return {"ok": False, "error": "praisonaiagents not installed"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _execute_parallel_step(self, step: Dict, flags: Dict) -> Dict:
        """Execute multiple steps in parallel."""
        parallel_steps = step.get("parallel", [])
        
        if not parallel_steps:
            return {"ok": True, "output": "No parallel steps to execute"}
        
        # For now, execute sequentially (true parallelism would require asyncio)
        # This maintains compatibility while providing the parallel syntax
        results = []
        all_ok = True
        
        for sub_step in parallel_steps:
            step_type = self._detect_step_type(sub_step)
            
            if step_type in ("shell", "python", "script", "action", "agent", "judge", "approve"):
                result = self._execute_job_step(step_type, sub_step, flags)
            elif step_type == "workflow":
                result = self._execute_workflow_step(sub_step, flags)
            else:
                result = {"ok": False, "error": f"Unknown step type in parallel: {step_type}"}
            
            results.append(result)
            if not result.get("ok"):
                all_ok = False
        
        return {
            "ok": all_ok,
            "results": results,
            "output": f"Executed {len(parallel_steps)} parallel steps",
        }

    def _parse_flags(self, args: List[str]) -> Dict[str, bool]:
        """Parse CLI flags based on workflow flag definitions."""
        flags = {}
        for flag_name in self._flag_defs:
            cli_flag = f"--{flag_name}"
            flags[flag_name.replace("-", "_")] = cli_flag in args
        return flags

    def _eval_condition(self, condition: str, flags: Dict) -> bool:
        """Evaluate a simple condition expression safely."""
        import ast

        condition = condition.strip()
        if condition.startswith("{{") and condition.endswith("}}"):
            condition = condition[2:-2].strip()

        # Handle simple attribute lookups like "flags.verbose" or "env.DEBUG"
        context = {"flags": flags, "env": dict(os.environ)}
        try:
            # Only allow simple attribute access patterns: obj.attr
            parts = condition.split(".")
            if len(parts) == 2 and parts[0] in context:
                obj = context[parts[0]]
                if isinstance(obj, dict):
                    return bool(obj.get(parts[1], False))
            # Try literal eval for simple boolean/numeric expressions
            return bool(ast.literal_eval(condition))
        except (ValueError, KeyError, TypeError):
            return False
