"""
Rules Manager for PraisonAI Agents.

Provides persistent rules/instructions support similar to:
- Cursor (.cursor/rules/*.mdc)
- Windsurf (.windsurf/rules/)
- Claude Code (CLAUDE.md, .claude/rules/)
- Codex CLI (AGENTS.md)
- Gemini CLI (GEMINI.md)

Features:
- Auto-discovery of root instruction files (CLAUDE.md, AGENTS.md, etc.)
- Git root discovery for monorepo support
- @Import syntax for including other files
- Local override files (CLAUDE.local.md)
- Multiple activation modes (always, glob, manual, ai_decision)
- Character limits for context window management
- Symlink support for shared rules

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
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal, Callable
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
        "CLAUDE.local.md",  # Claude Code local overrides (gitignored)
        "AGENTS.md",        # OpenAI Codex CLI instructions
        "GEMINI.md",        # Gemini CLI memory file
        ".cursorrules",     # Cursor legacy rules (deprecated but supported)
        ".windsurfrules",   # Windsurf legacy rules
        "PRAISON.md",       # PraisonAI native instructions
        "PRAISON.local.md", # PraisonAI local overrides (gitignored)
    ]
    
    # Additional rules directories to discover (like Claude, Windsurf)
    ADDITIONAL_RULES_DIRS = [
        ".claude/rules",     # Claude Code modular rules
        ".windsurf/rules",   # Windsurf rules
        ".cursor/rules",     # Cursor rules
    ]
    
    # Maximum characters per rule (like Windsurf's 12000 limit)
    MAX_RULE_CHARS = 12000
    
    # Import pattern for @path/to/file syntax
    IMPORT_PATTERN = re.compile(r'(?<!`)@([\w./-]+)(?!`)')
    
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
    
    def _find_git_root(self, start_path: Optional[Path] = None) -> Optional[Path]:
        """
        Find the git repository root from a starting path.
        
        Uses pure Python (no gitpython dependency) for performance.
        Falls back to subprocess if needed.
        
        Args:
            start_path: Starting path (defaults to workspace_path)
            
        Returns:
            Path to git root, or None if not in a git repo
        """
        start = start_path or self.workspace_path
        
        # Method 1: Walk up looking for .git directory (fastest, no subprocess)
        current = Path(start).resolve()
        while current != current.parent:
            git_dir = current / ".git"
            if git_dir.exists():
                return current
            current = current.parent
        
        # Method 2: Fallback to git command (handles edge cases like worktrees)
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=str(start),
                capture_output=True,
                text=True,
                timeout=2  # Prevent hanging
            )
            if result.returncode == 0:
                return Path(result.stdout.strip())
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        
        return None
    
    def _process_imports(self, content: str, base_path: Path, depth: int = 0) -> str:
        """
        Process @import syntax in rule content.
        
        Supports:
        - @path/to/file - Import relative to workspace
        - @~/path/to/file - Import from home directory
        - @./path/to/file - Import relative to current file
        
        Args:
            content: Rule content with potential @imports
            base_path: Base path for relative imports
            depth: Current recursion depth (max 5 to prevent loops)
            
        Returns:
            Content with imports resolved
        """
        if depth > 5:
            self._log("Import depth exceeded (max 5), stopping", logging.WARNING)
            return content
        
        def replace_import(match):
            import_path = match.group(1)
            
            # Skip if it looks like a mention (@username) or package (@org/pkg)
            if "/" not in import_path and "." not in import_path:
                return match.group(0)
            
            # Resolve path
            if import_path.startswith("~/"):
                file_path = Path.home() / import_path[2:]
            elif import_path.startswith("./"):
                file_path = base_path / import_path[2:]
            else:
                file_path = self.workspace_path / import_path
            
            # Try with and without .md extension
            if not file_path.exists() and not file_path.suffix:
                file_path = file_path.with_suffix(".md")
            
            if file_path.exists() and file_path.is_file():
                try:
                    imported_content = file_path.read_text(encoding="utf-8")
                    # Recursively process imports in imported content
                    imported_content = self._process_imports(
                        imported_content, 
                        file_path.parent, 
                        depth + 1
                    )
                    return imported_content
                except Exception as e:
                    self._log(f"Failed to import {file_path}: {e}", logging.WARNING)
                    return match.group(0)
            else:
                # Not a file import, leave as-is (might be @mention)
                return match.group(0)
        
        return self.IMPORT_PATTERN.sub(replace_import, content)
    
    def _truncate_rule_content(self, content: str) -> str:
        """Truncate rule content to MAX_RULE_CHARS if needed."""
        if len(content) <= self.MAX_RULE_CHARS:
            return content
        
        truncated = content[:self.MAX_RULE_CHARS - 50]
        return truncated + "\n\n... (truncated, exceeded 12000 char limit)"
    
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
        """Load a single rule file with @import processing and truncation."""
        try:
            content = file_path.read_text(encoding="utf-8")
            frontmatter, body = self._parse_frontmatter(content)
            
            # Process @imports in the body
            body = self._process_imports(body, file_path.parent)
            
            # Truncate if exceeds limit
            body = self._truncate_rule_content(body)
            
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
        """Load a root instruction file (CLAUDE.md, AGENTS.md, etc.) with @import processing."""
        try:
            if not file_path.exists():
                return None
            
            # Handle symlinks (like Claude Code supports)
            if file_path.is_symlink():
                file_path = file_path.resolve()
                if not file_path.exists():
                    return None
            
            content = file_path.read_text(encoding="utf-8")
            frontmatter, body = self._parse_frontmatter(content)
            
            # Process @imports in the body
            body_content = body if body else content
            body_content = self._process_imports(body_content, file_path.parent)
            
            # Truncate if exceeds limit
            body_content = self._truncate_rule_content(body_content)
            
            # Use filename (without extension) as rule name
            name = file_path.stem.lower().replace(".", "_")
            
            # Determine description based on file type
            descriptions = {
                "claude": "Claude Code memory instructions",
                "claude_local": "Claude Code local overrides",
                "agents": "OpenAI Codex CLI instructions",
                "gemini": "Gemini CLI memory instructions",
                "cursorrules": "Cursor IDE rules (legacy)",
                "windsurfrules": "Windsurf IDE rules (legacy)",
                "praison": "PraisonAI native instructions",
                "praison_local": "PraisonAI local overrides",
            }
            description = descriptions.get(name, f"Instructions from {file_path.name}")
            
            # Local files get higher priority (override main files)
            base_priority = 600 if "_local" in name else 500
            
            rule = Rule(
                name=name,
                content=body_content,
                description=frontmatter.get("description", description),
                globs=frontmatter.get("globs", []),
                activation=frontmatter.get("activation", "always"),
                priority=frontmatter.get("priority", base_priority),
                file_path=str(file_path)
            )
            
            self._log(f"Loaded root instruction file '{file_path.name}'")
            return rule
            
        except Exception as e:
            self._log(f"Error loading root instruction file {file_path}: {e}", logging.WARNING)
            return None
    
    def _load_all_rules(self):
        """Load rules from all sources including git root and additional directories."""
        self._rules = {}
        
        # Find git root for monorepo support
        git_root = self._find_git_root()
        
        # 1. Load global rules (lowest priority)
        global_rules = self._discover_rules_in_dir(self.global_rules_path)
        for rule in global_rules:
            rule.priority = rule.priority - 1000  # Lower priority for global
            self._rules[f"global:{rule.name}"] = rule
        
        # 2. Load root instruction files from git root (if different from workspace)
        if git_root and git_root != self.workspace_path:
            for filename in self.ROOT_INSTRUCTION_FILES:
                file_path = git_root / filename
                rule = self._load_root_instruction_file(file_path)
                if rule:
                    rule.priority = rule.priority - 100  # Slightly lower than workspace
                    self._rules[f"gitroot:{rule.name}"] = rule
        
        # 3. Load root instruction files from workspace (CLAUDE.md, AGENTS.md, etc.)
        for filename in self.ROOT_INSTRUCTION_FILES:
            file_path = self.workspace_path / filename
            rule = self._load_root_instruction_file(file_path)
            if rule:
                self._rules[f"root:{rule.name}"] = rule
        
        # 4. Load workspace rules from .praison/rules/
        workspace_rules_dir = self.workspace_path / self.RULES_DIR_NAME.replace("/", os.sep)
        workspace_rules = self._discover_rules_in_dir(workspace_rules_dir)
        for rule in workspace_rules:
            self._rules[f"workspace:{rule.name}"] = rule
        
        # 5. Load additional rules directories (.claude/rules, .windsurf/rules, .cursor/rules)
        for rules_dir_name in self.ADDITIONAL_RULES_DIRS:
            # Check workspace
            rules_dir = self.workspace_path / rules_dir_name.replace("/", os.sep)
            additional_rules = self._discover_rules_in_dir(rules_dir)
            for rule in additional_rules:
                rule.priority = rule.priority + 50  # Slightly higher priority
                dir_prefix = rules_dir_name.split("/")[0].strip(".")
                self._rules[f"{dir_prefix}:{rule.name}"] = rule
            
            # Check git root if different
            if git_root and git_root != self.workspace_path:
                rules_dir = git_root / rules_dir_name.replace("/", os.sep)
                additional_rules = self._discover_rules_in_dir(rules_dir)
                for rule in additional_rules:
                    dir_prefix = rules_dir_name.split("/")[0].strip(".")
                    self._rules[f"gitroot_{dir_prefix}:{rule.name}"] = rule
        
        # 6. Load subdirectory rules (walk up from cwd to workspace/git root)
        stop_at = git_root if git_root else self.workspace_path
        current = Path.cwd()
        while current != stop_at and current != current.parent:
            # Check .praison/rules/
            subdir_rules_dir = current / self.RULES_DIR_NAME.replace("/", os.sep)
            subdir_rules = self._discover_rules_in_dir(subdir_rules_dir)
            for rule in subdir_rules:
                rule.priority = rule.priority + 100  # Higher priority for closer dirs
                self._rules[f"subdir:{rule.name}"] = rule
            
            # Check additional rules directories in subdirs
            for rules_dir_name in self.ADDITIONAL_RULES_DIRS:
                subdir_rules_dir = current / rules_dir_name.replace("/", os.sep)
                subdir_rules = self._discover_rules_in_dir(subdir_rules_dir)
                for rule in subdir_rules:
                    rule.priority = rule.priority + 150  # Even higher for subdir additional
                    dir_prefix = rules_dir_name.split("/")[0].strip(".")
                    self._rules[f"subdir_{dir_prefix}:{rule.name}"] = rule
            
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
    
    def evaluate_ai_decision(
        self,
        rule: Rule,
        context: str,
        llm_func: Optional[Callable[[str], str]] = None
    ) -> bool:
        """
        Evaluate if an ai_decision rule should be applied.
        
        Uses the rule's description to determine relevance to current context.
        
        Args:
            rule: Rule with activation="ai_decision"
            context: Current conversation/task context
            llm_func: Optional LLM function for evaluation (if None, returns True)
            
        Returns:
            True if rule should be applied, False otherwise
        """
        if rule.activation != "ai_decision":
            return rule.activation == "always"
        
        if not llm_func:
            # Without LLM, include ai_decision rules by default
            return True
        
        # Use LLM to decide
        prompt = f"""Determine if the following rule should be applied to the current context.

Rule Name: {rule.name}
Rule Description: {rule.description}

Current Context:
{context[:1000]}

Should this rule be applied? Answer only "yes" or "no"."""

        try:
            response = llm_func(prompt).strip().lower()
            return response.startswith("yes")
        except Exception as e:
            self._log(f"Error evaluating ai_decision for rule '{rule.name}': {e}", logging.WARNING)
            return True  # Default to including the rule
    
    def get_stats(self) -> Dict[str, Any]:
        """Get rules statistics."""
        rules = list(self._rules.values())
        
        # Count rules by source
        source_counts = {}
        for key in self._rules.keys():
            source = key.split(":")[0]
            source_counts[source] = source_counts.get(source, 0) + 1
        
        return {
            "total_rules": len(rules),
            "always_rules": len([r for r in rules if r.activation == "always"]),
            "glob_rules": len([r for r in rules if r.activation == "glob"]),
            "manual_rules": len([r for r in rules if r.activation == "manual"]),
            "ai_decision_rules": len([r for r in rules if r.activation == "ai_decision"]),
            "global_rules": source_counts.get("global", 0),
            "root_rules": source_counts.get("root", 0),
            "gitroot_rules": source_counts.get("gitroot", 0),
            "workspace_rules": source_counts.get("workspace", 0),
            "subdir_rules": source_counts.get("subdir", 0),
            "claude_rules": source_counts.get("claude", 0),
            "windsurf_rules": source_counts.get("windsurf", 0),
            "cursor_rules": source_counts.get("cursor", 0),
            "sources": source_counts
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
