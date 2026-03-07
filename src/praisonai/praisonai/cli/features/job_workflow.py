"""
Job Workflow Executor for PraisonAI CLI.

General-purpose, deterministic step executor for workflows with `type: job`.
Supports multiple step types: shell commands, Python scripts, inline Python,
and built-in actions — all in a single YAML workflow.

Usage:
    praisonai workflow run publish-pypi.yaml
    praisonai workflow run publish-pypi.yaml --dry-run
    praisonai workflow run publish-pypi.yaml --major
"""

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class JobWorkflowExecutor:
    """
    Execute a `type: job` workflow — ordered, deterministic steps.

    Step types (detected by key):
        run:     Shell command via subprocess
        python:  Python script file
        script:  Inline Python code
        action:  Built-in action (e.g., bump-version)
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
        from rich.table import Table

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
                console.print(f"  [red]✗ {step_name}[/red] — unknown step type (need run/python/script/action)")
                results.append({"name": step_name, "status": "error", "error": "unknown step type"})
                failed = True
                break

            # Resolve variables in the target
            step_target = self._resolve_vars(step_target, flags)

            if dry_run:
                console.print(f"  [cyan]● {step_name}[/cyan] — [dim]{step_type}: {self._truncate(step_target, 80)}[/dim]")
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
        if "run" in step:
            return "shell", step["run"]
        if "python" in step:
            return "python", step["python"]
        if "script" in step:
            return "script", step["script"]
        if "action" in step:
            return "action", step["action"]
        return None, None

    # ------------------------------------------------------------------
    # Step executors
    # ------------------------------------------------------------------

    def _execute_step(self, step_type: str, target: str, step: Dict, flags: Dict) -> Dict:
        """Route to the correct executor."""
        try:
            if step_type == "shell":
                return self._exec_shell(target, step)
            elif step_type == "python":
                return self._exec_python_script(target, step)
            elif step_type == "script":
                return self._exec_inline_python(target, step, flags)
            elif step_type == "action":
                return self._exec_action(target, step, flags)
            else:
                return {"ok": False, "error": f"Unknown step type: {step_type}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _exec_shell(self, cmd: str, step: Dict) -> Dict:
        """Execute a shell command."""
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
        namespace = {
            "flags": flags,
            "vars": {k: self._resolve_var_value(v) for k, v in self._vars.items()},
            "env": os.environ.copy(),
            "cwd": self._cwd,
            "__builtins__": __builtins__,
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
        return {"ok": False, "error": f"Action '{name}' has no run/script/python key"}

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
        """Evaluate a simple condition expression."""
        # Strip {{ }} if present
        condition = condition.strip()
        if condition.startswith("{{") and condition.endswith("}}"):
            condition = condition[2:-2].strip()

        # Build evaluation context
        context = {"flags": type("Flags", (), flags)(), "env": os.environ}
        try:
            return bool(eval(condition, {"__builtins__": {}}, context))
        except Exception:
            return False

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
