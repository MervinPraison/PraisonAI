"""
Custom agent and command definitions discovery system.

Discovers and loads custom agents and commands from project and user directories:
- .praisonai/agents/*.md|*.yaml - Reusable named agents
- .praisonai/commands/*.md - Reusable named commands with template interpolation

Discovery order (later wins on name collision):
1. User-global: ~/.praisonai/{agents,commands}/
2. Project-level: ./.praisonai/{agents,commands}/ (walk up to repo root)
"""

import os
import re
import subprocess
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
    source: str = "unknown"  # 'user' or 'project'


class CustomDefinitionsDiscovery:
    """Discovers and manages custom agents and commands from filesystem."""
    
    def __init__(self):
        self._agents: Dict[str, CustomAgent] = {}
        self._commands: Dict[str, CustomCommand] = {}
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
                source=source
            )
        
        except Exception as e:
            import logging
            logging.warning(f"Failed to load command from {file_path}: {e}")
            return None
    
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


class TemplateInterpolator:
    """Handles template interpolation for custom commands."""
    
    @staticmethod
    def interpolate(template: str, arguments: str = "", working_dir: Optional[Path] = None) -> str:
        """
        Interpolate a command template.
        
        Supported patterns:
        - $ARGUMENTS - User-provided arguments
        - @path/to/file - Inline file contents
        - $(command) - Shell command substitution (escaped)
        
        Args:
            template: Template string to interpolate
            arguments: User arguments to substitute for $ARGUMENTS
            working_dir: Working directory for file resolution
            
        Returns:
            Interpolated string
        """
        result = template
        
        # Replace $ARGUMENTS
        result = result.replace("$ARGUMENTS", arguments)
        
        # Replace @file references
        result = TemplateInterpolator._interpolate_files(result, working_dir)
        
        # Handle escaped shell substitution $(...) 
        # (We escape it to prevent accidental execution)
        result = TemplateInterpolator._escape_shell_substitution(result)
        
        return result
    
    @staticmethod
    def _interpolate_files(text: str, working_dir: Optional[Path] = None) -> str:
        """Replace @file references with file contents."""
        # Pattern to match @path/to/file
        pattern = r'@([^\s]+)'
        
        def replace_file(match):
            file_path_str = match.group(1)
            
            # Resolve relative to working_dir if provided
            if working_dir:
                file_path = working_dir / file_path_str
            else:
                file_path = Path(file_path_str)
            
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
    permission_config = resolve_permission_config(agent.permission, agent.mode)
    if permission_config:
        config["permissions"] = permission_config

    return config


def interpolate_command_template(name: str, arguments: str = "") -> Optional[str]:
    """
    Load and interpolate a command template by name.
    
    Args:
        name: Command name to load
        arguments: Arguments to substitute for $ARGUMENTS
        
    Returns:
        Interpolated command text, or None if not found
    """
    discovery = CustomDefinitionsDiscovery()
    command = discovery.get_command(name)
    
    if not command:
        return None
    
    interpolator = TemplateInterpolator()
    return interpolator.interpolate(command.template, arguments, Path.cwd())