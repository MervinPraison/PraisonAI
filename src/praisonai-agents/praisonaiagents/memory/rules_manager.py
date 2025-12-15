"""
Rules Manager for PraisonAI Agents.

Provides persistent rules/instructions support similar to:
- Cursor (.cursor/rules/*.mdc)
- Windsurf (.windsurf/rules/)
- Codex CLI (AGENTS.md)
- Gemini CLI (GEMINI.md)

Storage Structure:
    .praison/rules/
    ├── global.md           # Always applied (global)
    ├── python.md           # Glob: **/*.py
    ├── testing.md          # Glob: **/*.test.*
    └── security.md         # Activation: manual (@security)

Rule File Format (YAML frontmatter + Markdown):
    ---
    description: Python coding guidelines
    globs: ["**/*.py", "**/*.pyx"]
    activation: always  # always, glob, manual, ai_decision
    priority: 10
    ---
    
    # Python Guidelines
    - Use type hints
    - Follow PEP 8
"""

import os
import re
import fnmatch
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Rule:
    """A single rule with metadata and content."""
    name: str
    content: str
    description: str = ""
    globs: List[str] = field(default_factory=list)
    activation: Literal["always", "glob", "manual", "ai_decision"] = "always"
    priority: int = 0
    file_path: Optional[str] = None
    
    def matches_file(self, file_path: str) -> bool:
        """Check if this rule matches a given file path."""
        if self.activation == "always":
            return True
        if self.activation == "manual":
            return False  # Only activated via @mention
        if self.activation == "glob" and self.globs:
            for pattern in self.globs:
                if fnmatch.fnmatch(file_path, pattern):
                    return True
                # Also try with ** expansion
                if "**" in pattern:
                    # Convert ** to regex for recursive matching
                    regex_pattern = pattern.replace("**", ".*").replace("*", "[^/]*")
                    if re.match(regex_pattern, file_path):
                        return True
        return False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "content": self.content,
            "description": self.description,
            "globs": self.globs,
            "activation": self.activation,
            "priority": self.priority,
            "file_path": self.file_path
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Rule':
        return cls(**data)


class RulesManager:
    """
    Manages rules/instructions for AI agents.
    
    Supports multiple rule sources:
    - Global rules (~/.praison/rules/)
    - Workspace rules (.praison/rules/)
    - Subdirectory rules (subdir/.praison/rules/)
    - Root instruction files (CLAUDE.md, AGENTS.md, GEMINI.md, .cursorrules, .windsurfrules)
    
    Example:
        ```python
        rules = RulesManager(workspace_path="/path/to/project")
        
        # Get all active rules
        active_rules = rules.get_active_rules()
        
        # Get rules for specific file
        python_rules = rules.get_rules_for_file("src/main.py")
        
        # Get manually invoked rule
        security_rule = rules.get_rule_by_name("security")
        
        # Build context string for LLM
        context = rules.build_rules_context(file_path="src/main.py")
        ```
    """
    
    RULES_DIR_NAME = ".praison/rules"
    SUPPORTED_EXTENSIONS = [".md", ".mdc", ".txt"]
    
    # Root-level instruction files (like Claude, Codex, Gemini, Cursor, Windsurf)
    ROOT_INSTRUCTION_FILES = [
        "CLAUDE.md",        # Claude Code memory file
        "AGENTS.md",        # OpenAI Codex CLI instructions
        "GEMINI.md",        # Gemini CLI memory file
        ".cursorrules",     # Cursor legacy rules (deprecated but supported)
        ".windsurfrules",   # Windsurf legacy rules
        "PRAISON.md",       # PraisonAI native instructions
    ]
    
    def __init__(
        self,
        workspace_path: Optional[str] = None,
        global_rules_path: Optional[str] = None,
        verbose: int = 0
    ):
        """
        Initialize RulesManager.
        
        Args:
            workspace_path: Path to workspace/project root
            global_rules_path: Path to global rules (default: ~/.praison/rules)
            verbose: Verbosity level
        """
        self.workspace_path = Path(workspace_path) if workspace_path else Path.cwd()
        self.global_rules_path = Path(global_rules_path) if global_rules_path else Path.home() / ".praison" / "rules"
        self.verbose = verbose
        
        self._rules: Dict[str, Rule] = {}
        self._load_all_rules()
    
    def _log(self, msg: str, level: int = logging.INFO):
        """Log message if verbose."""
        if self.verbose >= 1:
            logger.log(level, msg)
    
    def _parse_frontmatter(self, content: str) -> tuple[Dict[str, Any], str]:
        """Parse YAML frontmatter from markdown content."""
        frontmatter = {}
        body = content
        
        # Check for YAML frontmatter (--- ... ---)
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                yaml_content = parts[1].strip()
                body = parts[2].strip()
                
                # Simple YAML parsing (avoid dependency)
                for line in yaml_content.split("\n"):
                    line = line.strip()
                    if ":" in line:
                        key, value = line.split(":", 1)
                        key = key.strip()
                        value = value.strip()
                        
                        # Handle lists
                        if value.startswith("[") and value.endswith("]"):
                            # Parse simple list: ["*.py", "*.pyx"]
                            value = [v.strip().strip('"\'') for v in value[1:-1].split(",") if v.strip()]
                        # Handle booleans
                        elif value.lower() in ("true", "false"):
                            value = value.lower() == "true"
                        # Handle numbers
                        elif value.isdigit():
                            value = int(value)
                        # Handle quoted strings
                        elif value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        elif value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]
                        
                        frontmatter[key] = value
        
        return frontmatter, body
    
    def _load_rule_file(self, file_path: Path) -> Optional[Rule]:
        """Load a single rule file."""
        try:
            content = file_path.read_text(encoding="utf-8")
            frontmatter, body = self._parse_frontmatter(content)
            
            # Extract rule name from filename
            name = file_path.stem
            
            # Build Rule object
            rule = Rule(
                name=name,
                content=body,
                description=frontmatter.get("description", ""),
                globs=frontmatter.get("globs", []),
                activation=frontmatter.get("activation", "always"),
                priority=frontmatter.get("priority", 0),
                file_path=str(file_path)
            )
            
            self._log(f"Loaded rule '{name}' from {file_path}")
            return rule
            
        except Exception as e:
            self._log(f"Error loading rule file {file_path}: {e}", logging.WARNING)
            return None
    
    def _discover_rules_in_dir(self, rules_dir: Path) -> List[Rule]:
        """Discover all rule files in a directory."""
        rules = []
        
        if not rules_dir.exists():
            return rules
        
        for ext in self.SUPPORTED_EXTENSIONS:
            for file_path in rules_dir.glob(f"*{ext}"):
                rule = self._load_rule_file(file_path)
                if rule:
                    rules.append(rule)
        
        return rules
    
    def _load_root_instruction_file(self, file_path: Path) -> Optional[Rule]:
        """Load a root instruction file (CLAUDE.md, AGENTS.md, etc.)."""
        try:
            if not file_path.exists():
                return None
            
            content = file_path.read_text(encoding="utf-8")
            frontmatter, body = self._parse_frontmatter(content)
            
            # Use filename (without extension) as rule name
            name = file_path.stem.lower().replace(".", "_")
            
            # Determine description based on file type
            descriptions = {
                "claude": "Claude Code memory instructions",
                "agents": "OpenAI Codex CLI instructions",
                "gemini": "Gemini CLI memory instructions",
                "cursorrules": "Cursor IDE rules (legacy)",
                "windsurfrules": "Windsurf IDE rules (legacy)",
                "praison": "PraisonAI native instructions",
            }
            description = descriptions.get(name, f"Instructions from {file_path.name}")
            
            rule = Rule(
                name=name,
                content=body if body else content,  # Use body if frontmatter was parsed, else full content
                description=frontmatter.get("description", description),
                globs=frontmatter.get("globs", []),
                activation=frontmatter.get("activation", "always"),
                priority=frontmatter.get("priority", 500),  # High priority for root files
                file_path=str(file_path)
            )
            
            self._log(f"Loaded root instruction file '{file_path.name}'")
            return rule
            
        except Exception as e:
            self._log(f"Error loading root instruction file {file_path}: {e}", logging.WARNING)
            return None
    
    def _load_all_rules(self):
        """Load rules from all sources."""
        self._rules = {}
        
        # 1. Load global rules (lowest priority)
        global_rules = self._discover_rules_in_dir(self.global_rules_path)
        for rule in global_rules:
            rule.priority = rule.priority - 1000  # Lower priority for global
            self._rules[f"global:{rule.name}"] = rule
        
        # 2. Load root instruction files (CLAUDE.md, AGENTS.md, GEMINI.md, etc.)
        for filename in self.ROOT_INSTRUCTION_FILES:
            file_path = self.workspace_path / filename
            rule = self._load_root_instruction_file(file_path)
            if rule:
                self._rules[f"root:{rule.name}"] = rule
        
        # 3. Load workspace rules from .praison/rules/
        workspace_rules_dir = self.workspace_path / self.RULES_DIR_NAME.replace("/", os.sep)
        workspace_rules = self._discover_rules_in_dir(workspace_rules_dir)
        for rule in workspace_rules:
            self._rules[f"workspace:{rule.name}"] = rule
        
        # 4. Load subdirectory rules (walk up from cwd to workspace root)
        current = Path.cwd()
        while current != self.workspace_path and current != current.parent:
            subdir_rules_dir = current / self.RULES_DIR_NAME.replace("/", os.sep)
            subdir_rules = self._discover_rules_in_dir(subdir_rules_dir)
            for rule in subdir_rules:
                rule.priority = rule.priority + 100  # Higher priority for closer dirs
                self._rules[f"subdir:{rule.name}"] = rule
            current = current.parent
        
        self._log(f"Loaded {len(self._rules)} rules total")
    
    def reload(self):
        """Reload all rules from disk."""
        self._load_all_rules()
    
    def get_all_rules(self) -> List[Rule]:
        """Get all loaded rules, sorted by priority."""
        rules = list(self._rules.values())
        rules.sort(key=lambda r: r.priority, reverse=True)
        return rules
    
    def get_active_rules(self, file_path: Optional[str] = None) -> List[Rule]:
        """
        Get rules that are currently active.
        
        Args:
            file_path: Optional file path to filter glob-based rules
            
        Returns:
            List of active rules sorted by priority
        """
        active = []
        
        for rule in self._rules.values():
            if rule.activation == "always":
                active.append(rule)
            elif rule.activation == "glob" and file_path:
                if rule.matches_file(file_path):
                    active.append(rule)
            elif rule.activation == "ai_decision":
                # AI will decide - include for context
                active.append(rule)
            # Skip "manual" - only activated via @mention
        
        active.sort(key=lambda r: r.priority, reverse=True)
        return active
    
    def get_rules_for_file(self, file_path: str) -> List[Rule]:
        """Get rules that apply to a specific file."""
        return self.get_active_rules(file_path=file_path)
    
    def get_rule_by_name(self, name: str) -> Optional[Rule]:
        """Get a rule by name (for manual @mention invocation)."""
        # Check all scopes
        for scope in ["subdir", "workspace", "global"]:
            key = f"{scope}:{name}"
            if key in self._rules:
                return self._rules[key]
        
        # Also check without scope prefix
        for rule in self._rules.values():
            if rule.name == name:
                return rule
        
        return None
    
    def get_manual_rules(self) -> List[Rule]:
        """Get all rules that require manual activation."""
        return [r for r in self._rules.values() if r.activation == "manual"]
    
    def build_rules_context(
        self,
        file_path: Optional[str] = None,
        include_manual: Optional[List[str]] = None,
        max_chars: int = 10000
    ) -> str:
        """
        Build context string from active rules for LLM.
        
        Args:
            file_path: Optional file path for glob matching
            include_manual: List of manual rule names to include
            max_chars: Maximum characters in output
            
        Returns:
            Formatted rules context string
        """
        parts = []
        total_chars = 0
        
        # Get active rules
        active_rules = self.get_active_rules(file_path=file_path)
        
        # Add manually invoked rules
        if include_manual:
            for name in include_manual:
                rule = self.get_rule_by_name(name)
                if rule and rule not in active_rules:
                    active_rules.append(rule)
        
        # Sort by priority
        active_rules.sort(key=lambda r: r.priority, reverse=True)
        
        for rule in active_rules:
            if total_chars >= max_chars:
                break
            
            rule_text = rule.content.strip()
            if not rule_text:
                continue
            
            # Add rule with header
            if rule.description:
                header = f"## {rule.name}: {rule.description}"
            else:
                header = f"## {rule.name}"
            
            section = f"{header}\n{rule_text}\n"
            
            if total_chars + len(section) <= max_chars:
                parts.append(section)
                total_chars += len(section)
            else:
                # Truncate last rule
                remaining = max_chars - total_chars
                if remaining > 100:
                    parts.append(section[:remaining] + "\n... (truncated)")
                break
        
        return "\n".join(parts)
    
    def create_rule(
        self,
        name: str,
        content: str,
        description: str = "",
        globs: Optional[List[str]] = None,
        activation: Literal["always", "glob", "manual", "ai_decision"] = "always",
        priority: int = 0,
        scope: Literal["global", "workspace"] = "workspace"
    ) -> Rule:
        """
        Create a new rule file.
        
        Args:
            name: Rule name (used as filename)
            content: Rule content (markdown)
            description: Short description
            globs: Glob patterns for activation
            activation: Activation mode
            priority: Priority (higher = applied first)
            scope: Where to save (global or workspace)
            
        Returns:
            Created Rule object
        """
        # Determine save path
        if scope == "global":
            rules_dir = self.global_rules_path
        else:
            rules_dir = self.workspace_path / self.RULES_DIR_NAME.replace("/", os.sep)
        
        rules_dir.mkdir(parents=True, exist_ok=True)
        file_path = rules_dir / f"{name}.md"
        
        # Build frontmatter
        frontmatter_lines = ["---"]
        if description:
            frontmatter_lines.append(f'description: "{description}"')
        if globs:
            globs_str = ", ".join(f'"{g}"' for g in globs)
            frontmatter_lines.append(f"globs: [{globs_str}]")
        frontmatter_lines.append(f"activation: {activation}")
        if priority != 0:
            frontmatter_lines.append(f"priority: {priority}")
        frontmatter_lines.append("---")
        frontmatter_lines.append("")
        
        # Write file
        full_content = "\n".join(frontmatter_lines) + content
        file_path.write_text(full_content, encoding="utf-8")
        
        # Create and register rule
        rule = Rule(
            name=name,
            content=content,
            description=description,
            globs=globs or [],
            activation=activation,
            priority=priority,
            file_path=str(file_path)
        )
        
        self._rules[f"{scope}:{name}"] = rule
        self._log(f"Created rule '{name}' at {file_path}")
        
        return rule
    
    def delete_rule(self, name: str, scope: Optional[str] = None) -> bool:
        """
        Delete a rule file.
        
        Args:
            name: Rule name
            scope: Scope to delete from (global, workspace, or None for any)
            
        Returns:
            True if deleted, False if not found
        """
        # Find the rule
        rule = None
        key = None
        
        if scope:
            key = f"{scope}:{name}"
            rule = self._rules.get(key)
        else:
            for s in ["subdir", "workspace", "global"]:
                key = f"{s}:{name}"
                if key in self._rules:
                    rule = self._rules[key]
                    break
        
        if not rule or not rule.file_path:
            return False
        
        # Delete file
        try:
            Path(rule.file_path).unlink()
            del self._rules[key]
            self._log(f"Deleted rule '{name}'")
            return True
        except Exception as e:
            self._log(f"Error deleting rule '{name}': {e}", logging.ERROR)
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get rules statistics."""
        rules = list(self._rules.values())
        
        return {
            "total_rules": len(rules),
            "always_rules": len([r for r in rules if r.activation == "always"]),
            "glob_rules": len([r for r in rules if r.activation == "glob"]),
            "manual_rules": len([r for r in rules if r.activation == "manual"]),
            "ai_decision_rules": len([r for r in rules if r.activation == "ai_decision"]),
            "global_rules": len([k for k in self._rules.keys() if k.startswith("global:")]),
            "root_rules": len([k for k in self._rules.keys() if k.startswith("root:")]),
            "workspace_rules": len([k for k in self._rules.keys() if k.startswith("workspace:")]),
            "subdir_rules": len([k for k in self._rules.keys() if k.startswith("subdir:")])
        }


def create_rules_manager(
    workspace_path: Optional[str] = None,
    **kwargs
) -> RulesManager:
    """
    Create a RulesManager instance.
    
    Args:
        workspace_path: Path to workspace
        **kwargs: Additional configuration
        
    Returns:
        RulesManager instance
    """
    return RulesManager(workspace_path=workspace_path, **kwargs)
