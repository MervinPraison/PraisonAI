"""
Job Workflow Executor for PraisonAI CLI.

General-purpose step executor for workflows with `type: job`.
Supports multiple step types:

**Deterministic steps** (no LLM):
    - run:     Shell command via subprocess
    - python:  Python script file
    - script:  Inline Python code
    - action:  Built-in or YAML-defined action

**Agent-centric steps** (AI-powered):
    - agent:   Single AI agent execution
    - judge:   AI quality gate with threshold
    - approve: AI or human approval gate

Usage:
    praisonai workflow run publish-pypi.yaml
    praisonai workflow run publish-pypi.yaml --dry-run
    praisonai workflow run publish-pypi.yaml --major
"""

import ast
import operator
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class JobWorkflowExecutor:
    """
    Execute a `type: job` workflow — ordered steps with optional AI integration.

    Step types (detected by key):
        Deterministic (no LLM):
            run:     Shell command via subprocess
            python:  Python script file
            script:  Inline Python code
            action:  Built-in or YAML-defined action

        Agent-centric (AI-powered):
            agent:   Single AI agent execution
            judge:   AI quality gate with threshold
            approve: AI or human approval gate
    """

    # Built-in actions registry
    BUILT_IN_ACTIONS = {"bump-version"}

    def __init__(self, data: Dict[str, Any], file_path: str):
        self._data = data
        self._file_path = file_path
        self._name = data.get("name", Path(file_path).stem)
        self._description = data.get("description", "")
        self._steps = data.get("steps", [])
        self._vars = data.get("vars", {})
        self._flag_defs = data.get("flags", {})
        self._cwd = str(Path(file_path).parent.resolve())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, args: List[str]) -> Optional[Dict[str, Any]]:
        """
        Execute the workflow.

        Args:
            args: Raw CLI args (may contain --dry-run, --major, etc.)

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
            title=f"⚡ Job Workflow — {mode}",
            border_style="cyan",
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

            # Detect step type
            step_type, step_target = self._detect_step_type(step)
            if not step_type:
                console.print(f"  [red]✗ {step_name}[/red] — unknown step type (need run/python/script/action/agent/judge/approve)")
                results.append({"name": step_name, "status": "error", "error": "unknown step type"})
                failed = True
                break

            # Resolve variables in the target (only for string targets)
            if isinstance(step_target, str):
                step_target = self._resolve_vars(step_target, flags)

            if dry_run:
                # Format dry-run display based on step type
                if step_type == "agent":
                    agent_info = step_target if isinstance(step_target, dict) else {"instructions": step_target}
                    role = agent_info.get("role", "Assistant")
                    model = agent_info.get("model", "gpt-4o-mini")
                    display = f"agent: {role} (model: {model})"
                elif step_type == "judge":
                    judge_info = step_target if isinstance(step_target, dict) else {"criteria": step_target}
                    threshold = judge_info.get("threshold", 7.0)
                    display = f"judge: threshold={threshold}"
                elif step_type == "approve":
                    approve_info = step_target if isinstance(step_target, dict) else {"description": step_target}
                    risk = approve_info.get("risk_level", "medium")
                    display = f"approve: risk={risk}"
                else:
                    display = f"{step_type}: {self._truncate(str(step_target), 80)}"
                console.print(f"  [cyan]● {step_name}[/cyan] — [dim]{display}[/dim]")
                results.append({"name": step_name, "status": "dry-run", "type": step_type})
                continue

            # Execute
            console.print(f"  [bold]▸ {step_name}[/bold] ", end="")
            t0 = time.time()
            result = self._execute_step(step_type, step_target, step, flags)
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
            console.print(f"[yellow]⚡ Dry run complete — {len(results)} steps planned[/yellow]")
        elif failed:
            console.print("[red]✗ Workflow failed[/red]")
        else:
            console.print(f"[green]✓ Workflow completed — {len(results)} steps[/green]")

        return {"name": self._name, "results": results, "ok": not failed, "dry_run": dry_run}

    # ------------------------------------------------------------------
    # Step type detection
    # ------------------------------------------------------------------

    def _detect_step_type(self, step: Dict) -> tuple:
        """Detect step type from keys. Returns (type, target) or (None, None)."""
        # Deterministic steps
        if "run" in step:
            return "shell", step["run"]
        if "python" in step:
            return "python", step["python"]
        if "script" in step:
            return "script", step["script"]
        if "action" in step:
            return "action", step["action"]
        # Agent-centric steps
        if "agent" in step:
            return "agent", step["agent"]
        if "judge" in step:
            return "judge", step["judge"]
        if "approve" in step:
            return "approve", step["approve"]
        return None, None

    # ------------------------------------------------------------------
    # Step executors
    # ------------------------------------------------------------------

    def _execute_step(self, step_type: str, target: Any, step: Dict, flags: Dict) -> Dict:
        """Route to the correct executor."""
        try:
            # Deterministic steps
            if step_type == "shell":
                return self._exec_shell(target, step)
            elif step_type == "python":
                return self._exec_python_script(target, step)
            elif step_type == "script":
                return self._exec_inline_python(target, step, flags)
            elif step_type == "action":
                return self._exec_action(target, step, flags)
            # Agent-centric steps
            elif step_type == "agent":
                return self._exec_agent_step(target, step, flags)
            elif step_type == "judge":
                return self._exec_judge_step(target, step, flags)
            elif step_type == "approve":
                return self._exec_approve_step(target, step, flags)
            else:
                return {"ok": False, "error": f"Unknown step type: {step_type}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _exec_shell(self, cmd: str, step: Dict) -> Dict:
        """Execute a shell command."""
        # Block dangerous shell injection characters
        banned_chars = [';', '&', '|', '$', '`']
        if any(char in cmd for char in banned_chars):
            return {"ok": False, "error": "Command contains blocked shell characters"}
            
        cwd = step.get("cwd", self._cwd)
        env = self._build_env(step)
        result = subprocess.run(
            cmd, shell=True, cwd=cwd, env=env,
            capture_output=True, text=True,
            timeout=step.get("timeout", 300),
        )
        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip() or f"Exit code {result.returncode}"
            return {"ok": False, "error": error, "returncode": result.returncode}
        return {"ok": True, "output": result.stdout.strip()}

    def _exec_python_script(self, script_path: str, step: Dict) -> Dict:
        """Execute a Python script file."""
        # Resolve relative to workflow file
        resolved = Path(self._cwd) / script_path
        if not resolved.exists():
            return {"ok": False, "error": f"Script not found: {resolved}"}

        args_str = step.get("args", "")
        args_list = args_str.split() if isinstance(args_str, str) else args_str
        cmd = [sys.executable, str(resolved)] + args_list

        env = self._build_env(step)
        result = subprocess.run(
            cmd, cwd=self._cwd, env=env,
            capture_output=True, text=True,
            timeout=step.get("timeout", 300),
        )
        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip() or f"Exit code {result.returncode}"
            return {"ok": False, "error": error, "returncode": result.returncode}
        return {"ok": True, "output": result.stdout.strip()}

    def _exec_inline_python(self, code: str, step: Dict, flags: Dict) -> Dict:
        """Execute inline Python code in an isolated namespace."""
        _safe_builtins = {
            "True": True, "False": False, "None": None,
            "int": int, "float": float, "str": str, "bool": bool,
            "list": list, "dict": dict, "tuple": tuple, "set": set,
            "len": len, "range": range, "enumerate": enumerate,
            "zip": zip, "map": map, "filter": filter,
            "sorted": sorted, "reversed": reversed,
            "min": min, "max": max, "sum": sum, "abs": abs, "round": round,
            "isinstance": isinstance, "type": type,
            "print": print, "repr": repr,
            "hasattr": hasattr, "getattr": getattr, "setattr": setattr,
        }
        namespace = {
            "flags": flags,
            "vars": {k: self._resolve_var_value(v) for k, v in self._vars.items()},
            "env": os.environ.copy(),
            "cwd": self._cwd,
            "__builtins__": _safe_builtins,
        }
        try:
            exec(code, namespace)
            return {"ok": True, "output": namespace.get("result", "")}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _exec_action(self, action_name: str, step: Dict, flags: Dict) -> Dict:
        """
        Execute an action with dynamic resolution.

        Resolution order:
            1. YAML-defined actions (actions: block in the workflow)
            2. File-based actions (.py files from actions/ or .praison/actions/)
            3. Built-in actions (bump-version, etc.)
        """
        # 1. YAML-defined actions
        yaml_actions = self._data.get("actions", {})
        if action_name in yaml_actions:
            return self._exec_yaml_action(action_name, yaml_actions[action_name], step, flags)

        # 2. File-based actions
        action_file = self._find_action_file(action_name)
        if action_file:
            return self._exec_file_action(action_file, step, flags)

        # 3. Built-in actions
        builtin = self._get_builtin_action(action_name)
        if builtin:
            return builtin(step, flags)

        return {"ok": False, "error": f"Unknown action: {action_name}"}

    def _exec_yaml_action(self, name: str, action_def: Dict, step: Dict, flags: Dict) -> Dict:
        """Execute an action defined inline in the YAML actions: block."""
        # Agent-powered action
        if "agent" in action_def:
            return self._exec_agent_step(action_def["agent"], {**action_def, **step}, flags)
        if "script" in action_def:
            # Merge action-level config into namespace
            merged_step = {**action_def, **step}
            return self._exec_inline_python(action_def["script"], merged_step, flags)
        elif "run" in action_def:
            merged_step = {**action_def, **step}
            return self._exec_shell(action_def["run"], merged_step)
        elif "python" in action_def:
            merged_step = {**action_def, **step}
            return self._exec_python_script(action_def["python"], merged_step)
        return {"ok": False, "error": f"Action '{name}' has no run/script/python/agent key"}

    def _find_action_file(self, action_name: str) -> Optional[Path]:
        """
        Find an action .py file by name.

        Search order:
            1. ./actions/{action_name}.py  (next to workflow)
            2. .praison/actions/{action_name}.py  (project-level)
        """
        # Normalize name: bump-version → bump_version.py
        file_name = action_name.replace("-", "_") + ".py"

        # Search next to workflow file
        local = Path(self._cwd) / "actions" / file_name
        if local.exists():
            return local

        # Search project-level
        project = Path(self._cwd) / ".praison" / "actions" / file_name
        if project.exists():
            return project

        return None

    def _exec_file_action(self, action_file: Path, step: Dict, flags: Dict) -> Dict:
        """
        Execute a file-based action.

        The action file must define a `run(step, flags, cwd)` function
        that returns a dict with at minimum {"ok": True/False}.
        """
        import importlib.util

        try:
            spec = importlib.util.spec_from_file_location("action_module", str(action_file))
            if not spec or not spec.loader:
                return {"ok": False, "error": f"Cannot load action: {action_file}"}

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if not hasattr(module, "run"):
                return {"ok": False, "error": f"Action file {action_file.name} missing run(step, flags, cwd) function"}

            result = module.run(step=step, flags=flags, cwd=self._cwd)
            if not isinstance(result, dict):
                return {"ok": True, "output": str(result)}
            return result

        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _get_builtin_action(self, action_name: str):
        """Return built-in action handler or None."""
        builtins = {
            "bump-version": self._action_bump_version,
        }
        return builtins.get(action_name)

    # ------------------------------------------------------------------
    # Agent-centric step executors
    # ------------------------------------------------------------------

    def _exec_agent_step(self, agent_config: Any, step: Dict, flags: Dict) -> Dict:
        """
        Execute an agent step using praisonaiagents.Agent.
        
        Args:
            agent_config: Agent configuration (dict with role, instructions, tools, etc.)
            step: Full step definition (may include output_file)
            flags: Workflow flags
            
        Returns:
            Dict with ok, output, and optionally error
        """
        try:
            from praisonaiagents import Agent
        except ImportError:
            return {"ok": False, "error": "praisonaiagents not installed. Install with: pip install praisonaiagents"}
        
        # Handle both dict config and simple string
        if isinstance(agent_config, str):
            agent_config = {"instructions": agent_config}
        
        # Build agent
        agent_name = agent_config.get("name", step.get("name", "workflow-agent"))
        role = agent_config.get("role", "Assistant")
        instructions = agent_config.get("instructions", "")
        model = agent_config.get("model", "gpt-4o-mini")
        tools = self._resolve_agent_tools(agent_config.get("tools", []))
        
        try:
            agent = Agent(
                name=agent_name,
                role=role,
                instructions=instructions,
                tools=tools,
                llm=model,
            )
            
            # Get prompt - use prompt field, or instructions, or goal
            prompt = agent_config.get("prompt", agent_config.get("goal", instructions))
            prompt = self._resolve_vars(str(prompt), flags)
            
            # Execute agent
            result = agent.chat(prompt)
            output = str(result) if result else ""
            
            # Write to file if specified
            output_file = step.get("output_file") or agent_config.get("output_file")
            if output_file:
                output_path = Path(self._cwd) / output_file
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(output)
            
            return {"ok": True, "output": output}
            
        except Exception as e:
            error_msg = str(e)
            # Check for API key issues
            if "api_key" in error_msg.lower() or "authentication" in error_msg.lower():
                return {"ok": False, "error": f"Agent step '{agent_name}' requires an LLM API key. Set OPENAI_API_KEY or use --model ollama/llama3 for local execution. Original error: {error_msg}"}
            return {"ok": False, "error": error_msg}

    def _exec_judge_step(self, judge_config: Any, step: Dict, flags: Dict) -> Dict:
        """
        Execute a judge step for quality gating.
        
        Args:
            judge_config: Judge configuration (dict with input_file, criteria, threshold, etc.)
            step: Full step definition
            flags: Workflow flags
            
        Returns:
            Dict with ok, score, feedback, and optionally error
        """
        try:
            from praisonaiagents.eval import Judge
        except ImportError:
            return {"ok": False, "error": "praisonaiagents.eval not available. Install with: pip install praisonaiagents"}
        
        # Handle both dict config and simple string (criteria)
        if isinstance(judge_config, str):
            judge_config = {"criteria": judge_config}
        
        # Get input
        input_file = judge_config.get("input_file")
        if input_file:
            input_path = Path(self._cwd) / input_file
            if not input_path.exists():
                return {"ok": False, "error": f"Input file not found: {input_path}"}
            input_text = input_path.read_text()
        else:
            input_text = judge_config.get("input", "")
        
        if not input_text:
            return {"ok": False, "error": "Judge step requires input_file or input"}
        
        criteria = judge_config.get("criteria", "Output is high quality")
        threshold = float(judge_config.get("threshold", 7.0))
        model = judge_config.get("model", "gpt-4o-mini")
        on_fail = judge_config.get("on_fail", "stop")  # stop | warn | retry
        
        try:
            judge = Judge(criteria=criteria, model=model)
            result = judge.evaluate(input_text)
            
            score = result.score if hasattr(result, 'score') else 0.0
            feedback = result.feedback if hasattr(result, 'feedback') else str(result)
            passed = score >= threshold
            
            if not passed and on_fail == "warn":
                # Warn but continue
                return {"ok": True, "score": score, "feedback": feedback, "passed": False, "warning": f"Score {score} below threshold {threshold}"}
            
            return {"ok": passed, "score": score, "feedback": feedback, "passed": passed}
            
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _exec_approve_step(self, approve_config: Any, step: Dict, flags: Dict) -> Dict:
        """
        Execute an approval gate step.
        
        Args:
            approve_config: Approval configuration (dict with description, risk_level, etc.)
            step: Full step definition
            flags: Workflow flags
            
        Returns:
            Dict with ok, reason, and optionally error
        """
        try:
            from praisonaiagents.approval.backends import ConsoleBackend, AutoApproveBackend
            from praisonaiagents.approval.protocols import ApprovalRequest
        except ImportError:
            return {"ok": False, "error": "praisonaiagents.approval not available. Install with: pip install praisonaiagents"}
        
        # Handle both dict config and simple string (description)
        if isinstance(approve_config, str):
            approve_config = {"description": approve_config}
        
        description = approve_config.get("description", step.get("name", "Workflow step"))
        risk_level = approve_config.get("risk_level", "medium")
        auto_approve = approve_config.get("auto_approve", False)
        
        # Build context from previous step results if available
        context = {
            "step_name": step.get("name", "Unknown"),
            "workflow": self._name,
            "description": description,
        }
        
        request = ApprovalRequest(
            tool_name="workflow_step",
            arguments=context,
            risk_level=risk_level,
            agent_name=self._name,
        )
        
        try:
            if auto_approve:
                backend = AutoApproveBackend()
            else:
                backend = ConsoleBackend()
            
            decision = backend.request_approval_sync(request)
            
            return {
                "ok": decision.approved,
                "reason": decision.reason,
                "approver": getattr(decision, 'approver', 'user'),
            }
            
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _resolve_agent_tools(self, tool_names: List) -> List:
        """
        Resolve tool names to actual tool functions.
        
        Args:
            tool_names: List of tool names (strings) or tool functions
            
        Returns:
            List of resolved tool functions
        """
        if not tool_names:
            return []
        
        resolved = []
        for tool in tool_names:
            if callable(tool):
                # Already a function
                resolved.append(tool)
            elif isinstance(tool, str):
                # Try to resolve from registry
                try:
                    from praisonaiagents.tools import get_tool
                    resolved_tool = get_tool(tool)
                    if resolved_tool:
                        resolved.append(resolved_tool)
                except (ImportError, Exception):
                    # Try common tools
                    if tool == "execute_command":
                        try:
                            from praisonaiagents.tools import execute_command
                            resolved.append(execute_command)
                        except ImportError:
                            pass
                    elif tool == "read_file":
                        try:
                            from praisonaiagents.tools import read_file
                            resolved.append(read_file)
                        except ImportError:
                            pass
                    elif tool == "write_file":
                        try:
                            from praisonaiagents.tools import write_file
                            resolved.append(write_file)
                        except ImportError:
                            pass
        return resolved

    # ------------------------------------------------------------------
    # Built-in actions
    # ------------------------------------------------------------------

    def _action_bump_version(self, step: Dict, flags: Dict) -> Dict:
        """Bump version in pyproject.toml (or similar)."""
        file_path = step.get("file", "pyproject.toml")
        resolved = Path(self._cwd) / file_path
        if not resolved.exists():
            return {"ok": False, "error": f"File not found: {resolved}"}

        # Determine strategy from flags, falling back to step config
        if flags.get("major"):
            strategy = "major"
        elif flags.get("minor"):
            strategy = "minor"
        else:
            strategy = step.get("strategy", "patch")

        try:
            content = resolved.read_text()
            # Match version = "X.Y.Z" in pyproject.toml
            pattern = r'(version\s*=\s*["\'])(\d+)\.(\d+)\.(\d+)(["\'])'
            match = re.search(pattern, content)
            if not match:
                return {"ok": False, "error": f"No version found in {file_path}"}

            major, minor, patch = int(match.group(2)), int(match.group(3)), int(match.group(4))
            old_version = f"{major}.{minor}.{patch}"

            if strategy == "major":
                major += 1
                minor = 0
                patch = 0
            elif strategy == "minor":
                minor += 1
                patch = 0
            else:  # patch
                patch += 1

            new_version = f"{major}.{minor}.{patch}"
            new_content = re.sub(
                pattern,
                rf'\g<1>{new_version}\g<5>',
                content,
                count=1,
            )
            resolved.write_text(new_content)
            return {"ok": True, "output": f"{old_version} → {new_version}", "old_version": old_version, "new_version": new_version}

        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Variable / env resolution
    # ------------------------------------------------------------------

    def _resolve_vars(self, text: str, flags: Dict) -> str:
        """Resolve ${{ env.VAR }} and {{ flags.X }} in text."""
        if not isinstance(text, str):
            return text

        # ${{ env.VAR_NAME }}
        def env_replacer(m):
            var_name = m.group(1).strip()
            return os.environ.get(var_name, f"${{{{ env.{var_name} }}}}")

        text = re.sub(r'\$\{\{\s*env\.(\w+)\s*\}\}', env_replacer, text)

        # {{ flags.X }}
        def flag_replacer(m):
            flag_name = m.group(1).strip()
            return str(flags.get(flag_name, ""))

        text = re.sub(r'\{\{\s*flags\.(\w+)\s*\}\}', flag_replacer, text)

        return text

    def _resolve_var_value(self, var_def) -> str:
        """Resolve a var definition to its value."""
        if isinstance(var_def, dict):
            default = var_def.get("default", "")
            # Check env var with same name
            env_name = str(default)
            return os.environ.get(env_name, default)
        return str(var_def)

    def _build_env(self, step: Dict) -> Dict[str, str]:
        """Build environment for subprocess, merging step-level env."""
        env = os.environ.copy()
        step_env = step.get("env", {})
        if step_env:
            env.update({k: str(v) for k, v in step_env.items()})
        return env

    # ------------------------------------------------------------------
    # Flag parsing
    # ------------------------------------------------------------------

    def _parse_flags(self, args: List[str]) -> Dict[str, bool]:
        """Parse CLI flags based on workflow flag definitions."""
        flags = {}
        for flag_name in self._flag_defs:
            # Normalize: no-bump → no_bump for Python, but match --no-bump on CLI
            cli_flag = f"--{flag_name}"
            flags[flag_name.replace("-", "_")] = cli_flag in args
        return flags

    # ------------------------------------------------------------------
    # Condition evaluation
    # ------------------------------------------------------------------

    def _eval_condition(self, condition: str, flags: Dict) -> bool:
        """Evaluate a simple condition expression safely using AST evaluation."""
        # Strip {{ }} if present
        condition = condition.strip()
        if condition.startswith("{{") and condition.endswith("}}"):
            condition = condition[2:-2].strip()

        # Parse and validate AST - only allow safe node types
        try:
            tree = ast.parse(condition, mode='eval')
        except SyntaxError:
            return False

        # Build evaluation context
        context = {"flags": type("Flags", (), flags)(), "env": os.environ}
        
        try:
            return bool(self._safe_eval_ast(tree.body, context))
        except Exception:
            return False
    
    def _safe_eval_ast(self, node, context):
        """Safely evaluate AST node without using eval()."""
        # Map of safe binary/unary/comparison operations
        ops = {
            ast.Add: operator.add, ast.Sub: operator.sub,
            ast.Mult: operator.mul, ast.Div: operator.truediv,
            ast.Mod: operator.mod, ast.Pow: operator.pow,
            ast.Eq: operator.eq, ast.NotEq: operator.ne,
            ast.Lt: operator.lt, ast.LtE: operator.le,
            ast.Gt: operator.gt, ast.GtE: operator.ge,
            ast.Is: operator.is_, ast.IsNot: operator.is_not,
            ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b,
            ast.Not: operator.not_,
        }
        
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Name):
            if node.id in context:
                return context[node.id]
            raise NameError(f"name '{node.id}' is not defined")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith('__'):
                raise AttributeError(f"access to attribute '{node.attr}' is not allowed")
            value = self._safe_eval_ast(node.value, context)
            return getattr(value, node.attr)
        elif isinstance(node, ast.BinOp):
            left = self._safe_eval_ast(node.left, context)
            right = self._safe_eval_ast(node.right, context)
            return ops[type(node.op)](left, right)
        elif isinstance(node, ast.UnaryOp):
            operand = self._safe_eval_ast(node.operand, context)
            return ops[type(node.op)](operand)
        elif isinstance(node, ast.Compare):
            left = self._safe_eval_ast(node.left, context)
            for op, comparator in zip(node.ops, node.comparators):
                right = self._safe_eval_ast(comparator, context)
                if not ops[type(op)](left, right):
                    return False
                left = right
            return True
        elif isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                for value in node.values:
                    if not self._safe_eval_ast(value, context):
                        return False
                return True
            elif isinstance(node.op, ast.Or):
                for value in node.values:
                    if self._safe_eval_ast(value, context):
                        return True
                return False
            else:
                raise TypeError(f"unsupported boolean operator: {type(node.op)}")
        else:
            raise TypeError(f"unsupported node type: {type(node)}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        """Truncate text for display."""
        text = text.replace("\n", " ").strip()
        if len(text) > max_len:
            return text[:max_len - 3] + "..."
        return text
