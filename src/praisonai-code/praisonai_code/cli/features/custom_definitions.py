"""
Custom agent and command definitions discovery system.

Discovers and loads custom agents, commands and tools from project and user
directories:
- .praisonai/agents/*.md|*.yaml - Reusable named agents
- .praisonai/commands/*.md - Reusable named commands with template interpolation
- .praisonai/tools/*.py - Project-local Python tools (auto-loaded)

Discovery order (later wins on name collision):
1. User-global: ~/.praisonai/{agents,commands,tools}/
2. Project-level: ./.praisonai/{agents,commands,tools}/ (walk up to repo root)
"""

import inspect
import os
import re
import secrets
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from ...cli.utils.project import get_git_root


@dataclass
class CustomAgent:
    """Represents a custom agent definition."""
    name: str
    path: Path
    model: Optional[str] = None
    tools: Optional[List[str]] = None
    role: Optional[str] = None
    goal: Optional[str] = None
    instructions: Optional[str] = None
    system_prompt: Optional[str] = None
    permission: Optional[Dict[str, Any]] = None
    mode: Optional[str] = None
    source: str = "unknown"  # 'user' or 'project' or 'builtin'


# Coarse permission modes mapped to a flat {pattern: action} rule set.
# These are convenience shorthands that the per-rule ``permission`` block
# can further override (the ``permission`` block always wins on conflicts).
MODE_RULES: Dict[str, Dict[str, str]] = {
    # Full toolset, no restrictions.
    "build": {},
    "full": {},
    # Read-only exploration: deny any mutating tool, allow reads.
    "read-only": {
        "read:*": "allow",
        "edit:*": "deny",
        "write:*": "deny",
        "bash:*": "deny",
        "execute:*": "deny",
    },
    # Plan mode is an alias of read-only.
    "plan": {
        "read:*": "allow",
        "edit:*": "deny",
        "write:*": "deny",
        "bash:*": "deny",
        "execute:*": "deny",
    },
    # Review: read everything, never mutate, but ask before shell.
    "review": {
        "read:*": "allow",
        "edit:*": "deny",
        "write:*": "deny",
        "bash:*": "ask",
        "execute:*": "deny",
    },
}


# Allowed permission actions. Anything else is rejected to fail closed.
VALID_PERMISSION_ACTIONS = {"allow", "deny", "ask"}


# Environment gate mirroring PRAISONAI_ALLOW_LOCAL_TOOLS: live shell
# substitution in command templates is disabled unless explicitly enabled.
SHELL_SUBSTITUTION_ENV = "PRAISONAI_ALLOW_SHELL"

# Safety bounds for opt-in `!`cmd`` substitution.
SHELL_SUBSTITUTION_TIMEOUT = 30  # seconds
SHELL_SUBSTITUTION_MAX_BYTES = 100_000  # captured stdout byte cap


class ShellSubstitutionError(Exception):
    """Raised when a command template contains live shell substitution that
    cannot be executed (e.g. it is present but shell execution is not enabled)."""


def _coerce_bool(value: Any) -> bool:
    """Coerce a config/frontmatter value to a strict boolean.

    YAML already yields real booleans for ``true``/``false``, but values can
    also arrive quoted (``"false"``, ``"0"``, ``"no"``). Using ``bool(value)``
    would treat any non-empty string as ``True``, silently enabling a
    security-sensitive flag. This fails closed: only explicit truthy tokens
    enable the flag.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return False


# Built-in, zero-config agent presets shipped with the wrapper.
# Resolved before user/project definitions so they can be overridden by name.
# Each entry maps a preset name to its CustomAgent field kwargs.
BUILTIN_PRESETS: Dict[str, Dict[str, Any]] = {
    "build": {
        "mode": "build",
        "role": "Builder",
        "goal": "Implement and modify code with the full toolset",
        "instructions": "You are a capable engineering assistant with full tool access.",
    },
    "plan": {
        "mode": "plan",
        "role": "Planner",
        "goal": "Explore and plan without making any changes",
        "instructions": (
            "You are a read-only planning assistant. Explore the repository, "
            "answer questions, and propose plans. Never modify files or run "
            "mutating commands."
        ),
    },
    "review": {
        "mode": "review",
        "role": "Reviewer",
        "goal": "Audit code and diffs without making changes",
        "instructions": (
            "You are a meticulous code reviewer. Read code and diffs and "
            "provide thorough review feedback. Do not modify files."
        ),
    },
}


def resolve_permission_config(
    permission: Optional[Dict[str, Any]] = None,
    mode: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """Translate an agent ``mode`` shorthand and ``permission`` block into a
    flat ``{pattern: action}`` permission config.

    The ``permission`` block may use either a flat mapping
    (``{"read": "allow"}``) or a nested per-capability mapping
    (``{"shell": {"git *": "ask", "*": "deny"}}``). Bare capability keys
    (e.g. ``read``) are normalised to glob patterns (``read:*``).

    Precedence: explicit ``permission`` rules override ``mode`` defaults.

    Returns:
        A flat dict suitable for ``ApprovalConfig(permissions=...)``, or
        None if neither mode nor permission produced any rules.

    Raises:
        ValueError: If ``mode`` is not a known mode, or if any permission
            action is not one of ``allow``/``deny``/``ask``. Failing closed
            prevents a typo (e.g. ``mode: readonly``) from silently producing
            an unrestricted agent.
    """
    config: Dict[str, str] = {}

    if mode:
        mode_key = str(mode).strip().lower()
        if mode_key not in MODE_RULES:
            raise ValueError(
                f"Unknown agent permission mode: {mode!r}. "
                f"Valid modes: {sorted(MODE_RULES)}"
            )
        config.update(MODE_RULES[mode_key])

    if permission:
        for capability, value in permission.items():
            if isinstance(value, dict):
                # Nested per-capability patterns, e.g. bash: {"git *": ask}
                for sub_pattern, action in value.items():
                    action = str(action).strip().lower()
                    if action not in VALID_PERMISSION_ACTIONS:
                        raise ValueError(
                            f"Invalid permission action: {action!r}. "
                            f"Valid actions: {sorted(VALID_PERMISSION_ACTIONS)}"
                        )
                    pattern = f"{capability}:{sub_pattern}"
                    config[pattern] = action
            else:
                action = str(value).strip().lower()
                if action not in VALID_PERMISSION_ACTIONS:
                    raise ValueError(
                        f"Invalid permission action: {action!r}. "
                        f"Valid actions: {sorted(VALID_PERMISSION_ACTIONS)}"
                    )
                # Flat capability → action. Normalise bare capability to glob.
                pattern = capability if ":" in capability else f"{capability}:*"
                config[pattern] = action

    return config if config else None


@dataclass
class CustomCommand:
    """Represents a custom command definition."""
    name: str
    path: Path
    description: Optional[str] = None
    template: str = ""
    allow_shell: bool = False  # per-command opt-in for live `!`cmd`` substitution
    source: str = "unknown"  # 'user' or 'project'


@dataclass
class CustomTool:
    """Represents a project-local tool callable discovered from ``.praisonai/tools/*.py``.

    ``name`` is namespaced by module filename (``module.func``) to avoid
    collisions between tools of the same function name in different files.
    ``callable`` is the resolved callable (a ``@tool``-decorated function or a
    plain public callable) that is handed directly to the Agent.
    """
    name: str
    path: Path
    callable: Any
    source: str = "unknown"  # 'user' or 'project'


class CustomDefinitionsDiscovery:
    """Discovers and manages custom agents and commands from filesystem."""
    
    def __init__(self):
        self._agents: Dict[str, CustomAgent] = {}
        self._commands: Dict[str, CustomCommand] = {}
        self._tools: Dict[str, CustomTool] = {}
        self._discovered = False
    
    def discover(self, force: bool = False) -> None:
        """
        Discover custom definitions from user and project directories.
        
        Args:
            force: Force re-discovery even if already done
        """
        if self._discovered and not force:
            return
        
        self._agents.clear()
        self._commands.clear()
        self._tools.clear()
        
        # Register built-in presets first (lowest precedence)
        self._register_builtin_presets()
        
        # Discover from user-global directory first
        user_dir = self._get_user_dir()
        if user_dir.exists():
            self._discover_from_dir(user_dir, source="user")
        
        # Then discover from project directory (overwrites on collision)
        project_dirs = self._find_project_dirs()
        for project_dir in project_dirs:
            if project_dir.exists():
                self._discover_from_dir(project_dir, source="project")
        
        self._discovered = True
    
    def _register_builtin_presets(self) -> None:
        """Register the shipped, zero-config agent presets."""
        for name, kwargs in BUILTIN_PRESETS.items():
            self._agents[name] = CustomAgent(
                name=name,
                path=Path(f"<builtin:{name}>"),
                source="builtin",
                **kwargs,
            )

    def _get_user_dir(self) -> Path:
        """Get user-global definitions directory."""
        return Path.home() / ".praisonai"
    
    def _find_project_dirs(self) -> List[Path]:
        """Find project-level .praisonai directories by walking up."""
        dirs = []
        current = Path.cwd()
        
        # Walk up to git root or filesystem root
        git_root = get_git_root()
        stop_at = git_root if git_root else Path("/")
        
        while current != current.parent:
            praisonai_dir = current / ".praisonai"
            if praisonai_dir.exists() and praisonai_dir.is_dir():
                dirs.append(praisonai_dir)
            
            if current == stop_at:
                break
            current = current.parent
        
        return dirs
    
    def _discover_from_dir(self, base_dir: Path, source: str) -> None:
        """Discover definitions from a specific directory."""
        # Discover agents
        agents_dir = base_dir / "agents"
        if agents_dir.exists() and agents_dir.is_dir():
            for file_path in agents_dir.iterdir():
                if file_path.suffix in [".md", ".yaml", ".yml"]:
                    agent = self._load_agent(file_path, source)
                    if agent:
                        self._agents[agent.name] = agent
        
        # Discover commands
        commands_dir = base_dir / "commands"
        if commands_dir.exists() and commands_dir.is_dir():
            for file_path in commands_dir.iterdir():
                if file_path.suffix == ".md":
                    command = self._load_command(file_path, source)
                    if command:
                        self._commands[command.name] = command

        # Discover tools (project-local Python modules). Loading executes
        # user code, so it is gated by the same PRAISONAI_ALLOW_LOCAL_TOOLS
        # opt-in the rest of the wrapper enforces via load_user_module.
        tools_dir = base_dir / "tools"
        if tools_dir.exists() and tools_dir.is_dir():
            for file_path in sorted(tools_dir.iterdir()):
                if file_path.suffix == ".py" and not file_path.name.startswith("_"):
                    for tool in self._load_tools(file_path, source):
                        self._tools[tool.name] = tool
    
    def _load_agent(self, file_path: Path, source: str) -> Optional[CustomAgent]:
        """Load an agent definition from a file."""
        name = file_path.stem
        
        try:
            if file_path.suffix in [".yaml", ".yml"]:
                # Load YAML agent
                with open(file_path, 'r') as f:
                    data = yaml.safe_load(f) or {}
                
                return CustomAgent(
                    name=name,
                    path=file_path,
                    model=data.get("model"),
                    tools=data.get("tools"),
                    role=data.get("role"),
                    goal=data.get("goal"),
                    instructions=data.get("instructions") or data.get("system_prompt"),
                    system_prompt=data.get("system_prompt") or data.get("instructions"),
                    permission=data.get("permission"),
                    mode=data.get("mode"),
                    source=source
                )
            
            elif file_path.suffix == ".md":
                # Load Markdown agent with frontmatter
                frontmatter, body = self._parse_markdown_frontmatter(file_path)
                
                return CustomAgent(
                    name=name,
                    path=file_path,
                    model=frontmatter.get("model"),
                    tools=frontmatter.get("tools"),
                    role=frontmatter.get("role"),
                    goal=frontmatter.get("goal"),
                    instructions=frontmatter.get("instructions") or body,
                    system_prompt=body or frontmatter.get("instructions"),
                    permission=frontmatter.get("permission"),
                    mode=frontmatter.get("mode"),
                    source=source
                )
        
        except Exception as e:
            import logging
            logging.warning(f"Failed to load agent from {file_path}: {e}")
            return None
    
    def _load_command(self, file_path: Path, source: str) -> Optional[CustomCommand]:
        """Load a command definition from a Markdown file."""
        name = file_path.stem
        
        try:
            frontmatter, body = self._parse_markdown_frontmatter(file_path)
            
            return CustomCommand(
                name=name,
                path=file_path,
                description=frontmatter.get("description"),
                template=body,
                allow_shell=_coerce_bool(frontmatter.get("allow_shell", False)),
                source=source
            )
        
        except Exception as e:
            import logging
            logging.warning(f"Failed to load command from {file_path}: {e}")
            return None
    
    def _load_tools(self, file_path: Path, source: str) -> List[CustomTool]:
        """Load tool callables from a project-local ``.praisonai/tools/*.py`` module.

        Each public (non-underscore) callable is exposed as a tool, preferring
        ``@tool``-decorated functions when any are present so a helper module
        can keep private helpers alongside its exported tools. Tools are
        namespaced ``<module>.<func>`` to avoid collisions across files.

        Executing the module is gated by ``PRAISONAI_ALLOW_LOCAL_TOOLS`` via the
        shared safe loader; when disabled or on error this returns an empty list.
        """
        try:
            from praisonai_code._safe_loader import load_user_module

            module = load_user_module(
                file_path, name=f"praisonai_tools_{file_path.stem}"
            )
            if module is None:
                return []

            # Prefer the core @tool marker when available so a helper module can
            # keep private helpers alongside its exported tools; fall back to a
            # structural check so this works even if core is not importable.
            try:
                from praisonaiagents.tools.decorator import is_tool as _is_tool
            except Exception:
                def _is_tool(obj: Any) -> bool:  # pragma: no cover - fallback
                    return hasattr(obj, "run") and hasattr(obj, "name")

            # Only members defined in this module (skip imported names) that are
            # public callables. FunctionTool/BaseTool instances lack a matching
            # __module__, so accept them whenever is_tool() recognises them.
            members = []
            for name, obj in inspect.getmembers(module, callable):
                if name.startswith("_"):
                    continue
                if _is_tool(obj) or getattr(obj, "__module__", None) == module.__name__:
                    members.append((name, obj))

            decorated = [(n, o) for n, o in members if _is_tool(o)]
            selected = decorated or members

            return [
                CustomTool(
                    name=f"{file_path.stem}.{name}",
                    path=file_path,
                    callable=obj,
                    source=source,
                )
                for name, obj in selected
            ]
        except Exception as e:
            import logging
            logging.warning(f"Failed to load tools from {file_path}: {e}")
            return []

    def _parse_markdown_frontmatter(self, file_path: Path) -> Tuple[Dict[str, Any], str]:
        """Parse Markdown file with YAML frontmatter."""
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Check for frontmatter
        if content.startswith("---\n"):
            parts = content.split("\n---\n", 1)
            if len(parts) == 2:
                frontmatter_text = parts[0][4:]  # Skip opening "---\n"
                body = parts[1].strip()
                
                try:
                    frontmatter = yaml.safe_load(frontmatter_text) or {}
                except yaml.YAMLError:
                    frontmatter = {}
            else:
                # No closing "---"
                frontmatter = {}
                body = content.strip()
        else:
            # No frontmatter
            frontmatter = {}
            body = content.strip()
        
        return frontmatter, body
    
    def get_agent(self, name: str) -> Optional[CustomAgent]:
        """Get a discovered agent by name."""
        self.discover()
        return self._agents.get(name)
    
    def get_command(self, name: str) -> Optional[CustomCommand]:
        """Get a discovered command by name."""
        self.discover()
        return self._commands.get(name)
    
    def list_agents(self) -> List[CustomAgent]:
        """List all discovered agents."""
        self.discover()
        return list(self._agents.values())
    
    def list_commands(self) -> List[CustomCommand]:
        """List all discovered commands."""
        self.discover()
        return list(self._commands.values())

    def get_tool(self, name: str) -> Optional[CustomTool]:
        """Get a discovered project-local tool by its namespaced name."""
        self.discover()
        return self._tools.get(name)

    def list_tools(self) -> List[CustomTool]:
        """List all discovered project-local tools."""
        self.discover()
        return list(self._tools.values())


class TemplateInterpolator:
    """Handles template interpolation for custom commands."""
    
    # Opt-in live substitution syntax: !`command`. Chosen over $(...) to avoid
    # ambiguity with the existing $(...) escape behaviour and to keep the safe
    # default unchanged.
    SHELL_PATTERN = re.compile(r'!`([^`]+)`')

    @staticmethod
    def interpolate(
        template: str,
        arguments: str = "",
        working_dir: Optional[Path] = None,
        allow_shell: bool = False,
    ) -> str:
        """
        Interpolate a command template.
        
        Supported patterns:
        - $ARGUMENTS - User-provided arguments
        - @path/to/file - Inline file contents
        - $(command) - Shell command substitution (always escaped, never run)
        - !`command` - Live shell substitution (opt-in via ``allow_shell``)
        
        Args:
            template: Template string to interpolate
            arguments: User arguments to substitute for $ARGUMENTS
            working_dir: Working directory for file resolution
            allow_shell: When True, ``!`cmd``` substitutions are executed in
                ``working_dir`` with a timeout and output byte cap and their
                stdout inlined. When False (default), the presence of any
                ``!`cmd``` substitution raises :class:`ShellSubstitutionError`
                so the failure is explicit rather than silent.
            
        Returns:
            Interpolated string
        """
        # IMPORTANT (security & correctness):
        #   * Live shell substitution (!`cmd`) is resolved against the ORIGINAL
        #     template only, BEFORE $ARGUMENTS / @file injection, so untrusted
        #     input can never introduce a !`cmd` that gets executed.
        #   * Executed-command stdout is held aside as opaque placeholders so it
        #     is NOT mangled by the $(...) escape pass and cannot itself be
        #     re-parsed; it is restored verbatim at the very end.
        if not allow_shell and TemplateInterpolator.SHELL_PATTERN.search(template):
            raise ShellSubstitutionError(
                "Command template contains live shell substitution (!`...`) but "
                "shell execution is not enabled. Enable it with "
                f"{SHELL_SUBSTITUTION_ENV}=true, the `commands.allow_shell` config "
                "flag, or `allow_shell: true` in the command's frontmatter."
            )

        shell_outputs: List[str] = []
        if allow_shell:
            template = TemplateInterpolator._extract_shell(
                template, working_dir, shell_outputs
            )

        # Escape literal $(...) from the template.
        result = TemplateInterpolator._escape_shell_substitution(template)

        # Inject untrusted $ARGUMENTS, escaping $(...) it carries so it can never
        # be executed downstream.
        safe_arguments = TemplateInterpolator._escape_shell_substitution(arguments)
        result = result.replace("$ARGUMENTS", safe_arguments)

        # Replace @file references.
        result = TemplateInterpolator._interpolate_files(result, working_dir)

        # Restore executed-command stdout verbatim (after all escaping passes).
        if shell_outputs:
            result = TemplateInterpolator._restore_shell(result, shell_outputs)

        return result
    
    @staticmethod
    def _interpolate_files(text: str, working_dir: Optional[Path] = None) -> str:
        """Replace @file references with file contents."""
        # Pattern to match @path/to/file
        pattern = r'@([^\s]+)'
        
        def replace_file(match):
            file_path_str = match.group(1)

            if working_dir:
                root = working_dir.resolve()
                candidate = (working_dir / file_path_str).resolve()
                try:
                    candidate.relative_to(root)
                except ValueError:
                    return match.group(0)
                file_path = candidate
            else:
                file_path = Path(file_path_str).resolve()
            
            # Try to read the file
            try:
                if file_path.exists() and file_path.is_file():
                    with open(file_path, 'r') as f:
                        return f.read()
                else:
                    # File not found, leave as-is
                    return match.group(0)
            except Exception:
                # Error reading, leave as-is
                return match.group(0)
        
        return re.sub(pattern, replace_file, text)
    
    @staticmethod
    def _escape_shell_substitution(text: str) -> str:
        """Escape shell command substitution for safety."""
        # Replace $(...) with \$(...)
        return re.sub(r'\$\(([^)]+)\)', r'\\$(\1)', text)

    # Per-process random token making shell-output placeholders unguessable so
    # untrusted $ARGUMENTS / @file content cannot forge one to inject text at a
    # command-output position.
    _SHELL_PLACEHOLDER_TOKEN = secrets.token_hex(8)

    @staticmethod
    def _shell_placeholder(index: int) -> str:
        return f"\x00PRAISONAI_SHELL_{TemplateInterpolator._SHELL_PLACEHOLDER_TOKEN}_{index}\x00"

    @staticmethod
    def _run_shell_command(command: str, cwd: Optional[str]) -> str:
        """Run a single ``!`cmd``` and return its bounded stdout.

        stdout is read incrementally and capped at
        ``SHELL_SUBSTITUTION_MAX_BYTES`` *while* reading, so a noisy command
        cannot buffer unbounded output in memory before the cap is applied.
        The process is killed once the cap is reached and a wall-clock timeout
        still bounds total runtime.
        """
        try:
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            raise ShellSubstitutionError(
                f"Failed to run shell substitution {command!r}: {exc}"
            ) from exc

        deadline = time.monotonic() + SHELL_SUBSTITUTION_TIMEOUT
        collected = bytearray()
        capped = False
        assert process.stdout is not None
        try:
            os.set_blocking(process.stdout.fileno(), False)
            while True:
                if time.monotonic() > deadline:
                    TemplateInterpolator._kill_process(process)
                    raise ShellSubstitutionError(
                        f"Shell substitution timed out after "
                        f"{SHELL_SUBSTITUTION_TIMEOUT}s: {command!r}"
                    )

                chunk = process.stdout.read(8192)
                if chunk:
                    remaining = SHELL_SUBSTITUTION_MAX_BYTES - len(collected)
                    collected.extend(chunk[:remaining])
                    if len(collected) >= SHELL_SUBSTITUTION_MAX_BYTES:
                        # Cap reached: stop reading and terminate the producer.
                        # Treat this as success-with-truncation rather than a
                        # failure, since the kill is our own doing.
                        capped = True
                        TemplateInterpolator._kill_process(process)
                        break
                elif process.poll() is not None:
                    # No data and process exited: drain any final bytes.
                    tail = process.stdout.read()
                    if tail:
                        remaining = SHELL_SUBSTITUTION_MAX_BYTES - len(collected)
                        collected.extend(tail[:remaining])
                        if len(collected) >= SHELL_SUBSTITUTION_MAX_BYTES:
                            capped = True
                    break
                else:
                    time.sleep(0.01)
        finally:
            try:
                process.stdout.close()
            except OSError:
                pass

        returncode = process.wait()
        if returncode != 0 and not capped:
            try:
                stderr = (process.stderr.read() or b"").decode(
                    "utf-8", errors="replace"
                ).strip()
            except (OSError, AttributeError):
                stderr = ""
            finally:
                if process.stderr is not None:
                    process.stderr.close()
            raise ShellSubstitutionError(
                f"Shell substitution {command!r} exited with "
                f"{returncode}: {stderr}"
            )

        if process.stderr is not None:
            process.stderr.close()

        output = bytes(collected).decode("utf-8", errors="replace")
        return output.rstrip("\n")

    @staticmethod
    def _kill_process(process: "subprocess.Popen") -> None:
        """Terminate a runaway shell-substitution process, best-effort."""
        try:
            process.kill()
            process.wait(timeout=5)
        except Exception:
            pass

    @staticmethod
    def _extract_shell(
        text: str,
        working_dir: Optional[Path],
        outputs: List[str],
    ) -> str:
        """Execute the template's ``!`cmd``` markers and replace each with an
        opaque placeholder, collecting their stdout in ``outputs``.

        Running here (on the original template, before any untrusted injection)
        and deferring re-insertion via :meth:`_restore_shell` keeps command
        output out of the escaping passes and prevents injected text from being
        executed as shell.
        """
        cwd = str(working_dir) if working_dir else None

        def replace_command(match):
            command = match.group(1).strip()
            outputs.append(TemplateInterpolator._run_shell_command(command, cwd))
            return TemplateInterpolator._shell_placeholder(len(outputs) - 1)

        return TemplateInterpolator.SHELL_PATTERN.sub(replace_command, text)

    @staticmethod
    def _restore_shell(text: str, outputs: List[str]) -> str:
        """Replace shell-output placeholders with their captured stdout."""
        for index, output in enumerate(outputs):
            text = text.replace(TemplateInterpolator._shell_placeholder(index), output)
        return text


def discover_project_tools() -> List[Any]:
    """Auto-discover project-local tool callables from ``.praisonai/tools/*.py``.

    Walks the same user-global + project walk-up layers as agents/commands and
    returns the resolved tool callables ready to hand to an ``Agent``. Loading
    is gated by ``PRAISONAI_ALLOW_LOCAL_TOOLS`` (enforced by the shared safe
    loader), so this returns an empty list when the opt-in is not set.

    Returns:
        A list of tool callables (possibly empty).
    """
    discovery = CustomDefinitionsDiscovery()
    return [t.callable for t in discovery.list_tools()]


def load_agent_from_name(name: str) -> Optional[Dict[str, Any]]:
    """
    Load an agent configuration by name.
    
    Args:
        name: Agent name to load
        
    Returns:
        Agent configuration dict suitable for Agent(**config)
    """
    discovery = CustomDefinitionsDiscovery()
    agent = discovery.get_agent(name)
    
    if not agent:
        return None
    
    config = {
        "name": agent.name,
    }
    
    if agent.model:
        config["llm"] = agent.model
    if agent.role:
        config["role"] = agent.role
    if agent.goal:
        config["goal"] = agent.goal
    if agent.instructions:
        config["instructions"] = agent.instructions
    if agent.system_prompt:
        # Use system_prompt as backstory if not already in instructions
        if "backstory" not in config:
            config["backstory"] = agent.system_prompt
    if agent.tools:
        # Tools will need to be resolved from the tools registry
        config["tools"] = agent.tools

    # Translate declarative permission/mode block into a flat permission
    # config that maps onto the Agent's existing approval/permission engine.
    # ``mode: subagent`` is a delegatability marker (not a permission mode) and
    # must be ignored here so it is never rejected as an unknown mode.
    permission_mode = agent.mode
    if permission_mode and str(permission_mode).strip().lower() == "subagent":
        permission_mode = None
    permission_config = resolve_permission_config(agent.permission, permission_mode)
    if permission_config:
        config["permissions"] = permission_config

    return config


def _agent_config_from_definition(agent: CustomAgent) -> Dict[str, Any]:
    """Build an ``Agent(**config)`` kwargs dict from a discovered definition.

    Mirrors :func:`load_agent_from_name` but works from an already-resolved
    ``CustomAgent`` so the same frontmatter (model/tools/permission/mode) is
    honoured when the agent is instantiated as a delegation target.
    """
    config: Dict[str, Any] = {"name": agent.name}

    if agent.model:
        config["llm"] = agent.model
    if agent.role:
        config["role"] = agent.role
    if agent.goal:
        config["goal"] = agent.goal
    if agent.instructions:
        config["instructions"] = agent.instructions
    if agent.system_prompt:
        config["backstory"] = agent.system_prompt
    if agent.tools:
        config["tools"] = agent.tools

    # ``mode: subagent`` is a delegatability marker, not a permission mode, so
    # it must not be fed to resolve_permission_config (which would reject it as
    # an unknown mode). Treat it as "no permission mode" here.
    permission_mode = agent.mode
    if permission_mode and str(permission_mode).strip().lower() == "subagent":
        permission_mode = None

    permission_config = resolve_permission_config(agent.permission, permission_mode)
    if permission_config:
        config["permissions"] = permission_config

    return config


def list_delegatable_agents(
    allow_list: Optional[List[str]] = None,
) -> List[CustomAgent]:
    """Return discovered agents that may be offered as delegation targets.

    An agent is delegatable when it is either explicitly named in
    ``allow_list`` (e.g. from ``--subagents a,b,c``) or, when no allow-list is
    given, when its frontmatter marks it with ``mode: subagent``.

    Args:
        allow_list: Optional explicit list of agent names to expose. When
            provided it takes precedence over the ``mode: subagent`` marker so
            a user can opt any named agent in from the CLI without editing it.

    Returns:
        The matching ``CustomAgent`` definitions.
    """
    discovery = CustomDefinitionsDiscovery()
    agents = discovery.list_agents()

    if allow_list:
        wanted = {name.strip() for name in allow_list if name and name.strip()}
        return [a for a in agents if a.name in wanted]

    return [
        a
        for a in agents
        if a.mode and str(a.mode).strip().lower() == "subagent"
    ]


def build_subagent_resolver(
    allow_list: Optional[List[str]] = None,
) -> Tuple[Optional[Any], Dict[str, str]]:
    """Build a named-agent resolver for ``create_subagent_tool``.

    Bridges the wrapper's ``.praisonai/agents`` discovery to the core
    delegation seam: returns a ``resolver(name) -> Agent`` callback plus a
    ``{name: description}`` map for the tool description. The resolver lazily
    imports and instantiates the core ``Agent`` from each definition's
    frontmatter so no agents are constructed unless actually delegated to.

    Args:
        allow_list: Optional explicit list of delegatable agent names. When
            omitted, agents marked ``mode: subagent`` are used.

    Returns:
        A ``(resolver, descriptions)`` tuple. ``resolver`` is ``None`` when
        there are no delegatable agents (so callers can skip wiring the tool).
    """
    delegatable = list_delegatable_agents(allow_list)
    if not delegatable:
        return None, {}

    configs = {a.name: _agent_config_from_definition(a) for a in delegatable}
    descriptions = {
        a.name: (a.description if hasattr(a, "description") else None)
        or a.goal
        or a.role
        or ""
        for a in delegatable
    }

    def resolver(name: str) -> Optional[Any]:
        config = configs.get(name)
        if config is None:
            return None
        from praisonaiagents import Agent

        # ``permissions`` is a declarative block, not an ``Agent`` kwarg. Mirror
        # the primary-run path (_run_custom_agent) and convert it into an
        # ``approval`` config so the delegated agent runs under its own
        # restrictions instead of failing at construction.
        agent_config = dict(config)
        agent_permissions = agent_config.pop("permissions", None) or {}
        if agent_permissions:
            from praisonai_code.cli.features._approval_bridge import (
                resolve_approval_config,
            )

            has_ask_rules = any(
                str(action).strip().lower() == "ask"
                for action in agent_permissions.values()
            )
            agent_config["approval"] = resolve_approval_config(
                "console",
                non_interactive=not has_ask_rules,
                permissions_config=agent_permissions,
            )

        return Agent(**agent_config)

    return resolver, descriptions


def _env_flag(name: str) -> bool:
    """Return True when an environment flag is set to a truthy value."""
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _config_allows_shell() -> bool:
    """Resolve the ``commands.allow_shell`` flag from project config.

    Returns False on any error so the safe default is preserved when no config
    is present or it cannot be parsed.
    """
    try:
        from ...cli.configuration.resolver import resolve_config

        config = resolve_config()
    except Exception:
        return False

    # ``commands`` is not a first-class resolved-config field, so the resolver
    # stores it under ``extra`` (see ResolvedConfig.from_dict). Read it from
    # there; fall back to a direct attribute for forward compatibility.
    commands = None
    extra = getattr(config, "extra", None)
    if isinstance(extra, dict):
        commands = extra.get("commands")
    if commands is None:
        commands = getattr(config, "commands", None)

    if isinstance(commands, dict):
        return _coerce_bool(commands.get("allow_shell", False))
    return False


def interpolate_command_template(
    name: str,
    arguments: str = "",
    allow_shell: Optional[bool] = None,
) -> Optional[str]:
    """
    Load and interpolate a command template by name.
    
    Args:
        name: Command name to load
        arguments: Arguments to substitute for $ARGUMENTS
        allow_shell: Explicitly enable/disable live ``!`cmd``` substitution.
            When None (default), the value is resolved from (in order, any
            enabling): the ``PRAISONAI_ALLOW_SHELL`` env var, the
            ``commands.allow_shell`` config flag, or the command's
            ``allow_shell: true`` frontmatter.
        
    Returns:
        Interpolated command text, or None if not found
    """
    discovery = CustomDefinitionsDiscovery()
    command = discovery.get_command(name)
    
    if not command:
        return None

    if allow_shell is None:
        allow_shell = (
            _env_flag(SHELL_SUBSTITUTION_ENV)
            or _config_allows_shell()
            or command.allow_shell
        )

    interpolator = TemplateInterpolator()
    return interpolator.interpolate(
        command.template, arguments, Path.cwd(), allow_shell=allow_shell
    )