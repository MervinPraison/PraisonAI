"""
Code Migration CLI for PraisonAI.

Provides migration tools for converting agent code and configurations to PraisonAI format.
Uses pattern-based detection to identify and convert agent definitions.

Design principles:
- Pattern-based detection (no explicit framework naming)
- Stealth approach - generic terminology in user-facing output
- Reuses existing AST capabilities from praisonaiagents
- Lazy imports for performance
- Safe by default (dry-run mode)
"""

from __future__ import annotations

import os
import logging
import shutil
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, List, Set


logger = logging.getLogger(__name__)


# =============================================================================
# Pattern Types and Data Classes (Generic - No Framework Names)
# =============================================================================

class PatternType(Enum):
    """Types of detected code patterns.
    
    Uses generic terminology to avoid exposing competitor framework names.
    """
    AGENT = "agent"
    TASK = "task"
    ORCHESTRATOR = "orchestrator"
    WORKFLOW = "workflow"
    TOOL = "tool"
    CONFIG = "config"


@dataclass
class PatternInfo:
    """Information about a detected code pattern.
    
    Attributes:
        pattern_type: Type of pattern detected
        name: Name of the class/function/variable
        attributes: Detected attributes and their values
        file_path: Source file path
        line_number: Line number in source
        confidence: Detection confidence (0.0 - 1.0)
        original_code: Original code snippet
    """
    pattern_type: PatternType
    name: str
    attributes: Dict[str, Any] = field(default_factory=dict)
    file_path: str = ""
    line_number: int = 0
    confidence: float = 0.0
    original_code: str = ""


@dataclass
class ConversionResult:
    """Result of code conversion.
    
    Attributes:
        success: Whether conversion succeeded
        converted_code: The converted code
        patterns_found: List of detected patterns
        warnings: List of warnings during conversion
        errors: List of errors during conversion
    """
    success: bool
    converted_code: str = ""
    patterns_found: List[PatternInfo] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    """Result of code analysis.
    
    Attributes:
        patterns: List of detected patterns
        files_scanned: Number of files scanned
        convertible_count: Number of convertible patterns
        warnings: List of warnings
    """
    patterns: List[PatternInfo] = field(default_factory=list)
    files_scanned: int = 0
    convertible_count: int = 0
    warnings: List[str] = field(default_factory=list)


# =============================================================================
# Pattern Detection (Uses AST - No Framework Names in Detection Logic)
# =============================================================================

class PatternDetector:
    """Detects agent-related patterns in Python code.
    
    Uses AST analysis to identify:
    - Agent-like classes (with role, goal, backstory attributes)
    - Task-like classes (with description, expected_output)
    - Orchestrator patterns (with agents, tasks lists)
    - Decorated functions (@agent, @task decorators)
    - Pydantic models with agent fields
    
    Pattern detection is generic and doesn't expose framework names.
    """
    
    # Agent pattern attributes (generic - covers multiple frameworks)
    # CrewAI style: role, goal, backstory
    # Agno style: name, model, instructions, tools
    AGENT_ATTRS = {"role", "goal", "backstory", "tools", "llm", "model", "verbose", 
                   "name", "instructions", "markdown", "add_datetime_to_context",
                   "add_history_to_context", "num_history_runs", "db"}
    AGENT_REQUIRED = {"role"}  # Minimum for CrewAI-style detection
    AGENT_AGNO_REQUIRED = {"name", "instructions"}  # Minimum for Agno-style detection
    AGENT_AGNO_ATTRS = {"name", "model", "instructions", "tools", "markdown", 
                        "add_datetime_to_context", "add_history_to_context", "db"}
    
    # Task pattern attributes
    TASK_ATTRS = {"description", "expected_output", "agent", "context", "async_execution"}
    TASK_REQUIRED = {"description"}
    
    # Orchestrator pattern attributes (Crew, Team, Workflow)
    ORCH_ATTRS = {"agents", "tasks", "process", "verbose", "memory", "members", "steps"}
    ORCH_METHODS = {"kickoff", "run", "start", "execute", "print_response"}
    
    # Workflow/Step pattern attributes (Agno style)
    WORKFLOW_ATTRS = {"steps", "name", "description"}
    STEP_ATTRS = {"agent", "name", "description"}
    
    # Decorator patterns (generic names)
    AGENT_DECORATORS = {"agent", "crew_agent", "autogen_agent"}
    TASK_DECORATORS = {"task", "crew_task"}
    
    def detect_patterns(self, code: str, file_path: str = "") -> List[PatternInfo]:
        """Detect patterns in Python code.
        
        Args:
            code: Python source code
            file_path: Optional file path for context
            
        Returns:
            List of detected patterns
        """
        import ast
        
        patterns = []
        
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            logger.warning(f"Syntax error parsing code: {e}")
            return patterns
        
        # Analyze classes
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                pattern = self._analyze_class(node, code, file_path)
                if pattern:
                    patterns.append(pattern)
            
            elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                pattern = self._analyze_function(node, code, file_path)
                if pattern:
                    patterns.append(pattern)
            
            elif isinstance(node, ast.Assign):
                pattern = self._analyze_assignment(node, code, file_path)
                if pattern:
                    patterns.append(pattern)
            
            elif isinstance(node, ast.Call):
                pattern = self._analyze_call(node, code, file_path)
                if pattern:
                    patterns.append(pattern)
        
        return patterns
    
    def _analyze_class(self, node, code: str, file_path: str) -> Optional[PatternInfo]:
        """Analyze a class definition for patterns."""
        import ast
        
        class_attrs: Set[str] = set()
        class_methods: Set[str] = set()
        base_names: Set[str] = set()
        
        # Get base class names
        for base in node.bases:
            if isinstance(base, ast.Name):
                base_names.add(base.id)
            elif isinstance(base, ast.Attribute):
                base_names.add(base.attr)
        
        # Analyze class body
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        class_attrs.add(target.id)
            elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                class_attrs.add(item.target.id)
            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                class_methods.add(item.name)
        
        # Check for agent pattern
        agent_match = class_attrs & self.AGENT_ATTRS
        has_core_attrs = self.AGENT_REQUIRED <= class_attrs
        if has_core_attrs or len(agent_match) >= 2:
            # Weighted confidence: core attrs (role, goal, backstory) count more
            core_attrs = {"role", "goal", "backstory"}
            core_match = class_attrs & core_attrs
            # Give high confidence if all core attrs present, lower for partial matches
            if len(core_match) >= 3:
                confidence = 0.9  # All core CrewAI-style attrs
            elif len(core_match) >= 2:
                confidence = 0.7  # Most core attrs
            else:
                confidence = 0.3 + (len(agent_match) / len(self.AGENT_ATTRS))
            
            # Boost confidence for Pydantic models
            if "BaseModel" in base_names:
                confidence = min(1.0, confidence + 0.1)
            
            return PatternInfo(
                pattern_type=PatternType.AGENT,
                name=node.name,
                attributes={"class_attrs": list(class_attrs), "bases": list(base_names)},
                file_path=file_path,
                line_number=node.lineno,
                confidence=confidence,
                original_code=ast.get_source_segment(code, node) or ""
            )
        
        # Check for task pattern
        task_match = class_attrs & self.TASK_ATTRS
        if self.TASK_REQUIRED <= class_attrs or len(task_match) >= 2:
            confidence = len(task_match) / len(self.TASK_ATTRS)
            
            return PatternInfo(
                pattern_type=PatternType.TASK,
                name=node.name,
                attributes={"class_attrs": list(class_attrs), "bases": list(base_names)},
                file_path=file_path,
                line_number=node.lineno,
                confidence=confidence,
                original_code=ast.get_source_segment(code, node) or ""
            )
        
        # Check for orchestrator pattern
        orch_match = class_attrs & self.ORCH_ATTRS
        method_match = class_methods & self.ORCH_METHODS
        if len(orch_match) >= 2 or (orch_match and method_match):
            confidence = (len(orch_match) + len(method_match)) / (len(self.ORCH_ATTRS) + len(self.ORCH_METHODS))
            
            return PatternInfo(
                pattern_type=PatternType.ORCHESTRATOR,
                name=node.name,
                attributes={"class_attrs": list(class_attrs), "methods": list(class_methods)},
                file_path=file_path,
                line_number=node.lineno,
                confidence=confidence,
                original_code=ast.get_source_segment(code, node) or ""
            )
        
        return None
    
    def _analyze_function(self, node, code: str, file_path: str) -> Optional[PatternInfo]:
        """Analyze a function definition for patterns."""
        import ast
        
        # Check decorators
        decorator_names = set()
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name):
                decorator_names.add(dec.id)
            elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
                decorator_names.add(dec.func.id)
        
        # Check for agent decorator
        if decorator_names & self.AGENT_DECORATORS:
            return PatternInfo(
                pattern_type=PatternType.AGENT,
                name=node.name,
                attributes={"decorators": list(decorator_names)},
                file_path=file_path,
                line_number=node.lineno,
                confidence=0.9,
                original_code=ast.get_source_segment(code, node) or ""
            )
        
        # Check for task decorator
        if decorator_names & self.TASK_DECORATORS:
            return PatternInfo(
                pattern_type=PatternType.TASK,
                name=node.name,
                attributes={"decorators": list(decorator_names)},
                file_path=file_path,
                line_number=node.lineno,
                confidence=0.9,
                original_code=ast.get_source_segment(code, node) or ""
            )
        
        return None
    
    def _analyze_assignment(self, node, code: str, file_path: str) -> Optional[PatternInfo]:
        """Analyze an assignment for patterns."""
        import ast
        
        if not isinstance(node.value, ast.Call):
            return None
        
        call = node.value
        func_name = ""
        
        if isinstance(call.func, ast.Name):
            func_name = call.func.id
        elif isinstance(call.func, ast.Attribute):
            func_name = call.func.attr
        
        # Check for Agent instantiation (CrewAI or Agno style)
        if func_name.lower() == "agent":
            kwargs = self._extract_call_kwargs(call)
            # CrewAI style: role, goal, backstory
            # Agno style: name, model, instructions
            is_crewai_style = "role" in kwargs or "goal" in kwargs
            is_agno_style = ("name" in kwargs and "instructions" in kwargs) or ("name" in kwargs and "model" in kwargs)
            
            if is_crewai_style or is_agno_style:
                target_name = ""
                if node.targets and isinstance(node.targets[0], ast.Name):
                    target_name = node.targets[0].id
                
                return PatternInfo(
                    pattern_type=PatternType.AGENT,
                    name=target_name,
                    attributes=kwargs,
                    file_path=file_path,
                    line_number=node.lineno,
                    confidence=0.95,
                    original_code=ast.get_source_segment(code, node) or ""
                )
        
        # Check for Task instantiation
        if func_name.lower() == "task":
            kwargs = self._extract_call_kwargs(call)
            if "description" in kwargs:
                target_name = ""
                if node.targets and isinstance(node.targets[0], ast.Name):
                    target_name = node.targets[0].id
                
                return PatternInfo(
                    pattern_type=PatternType.TASK,
                    name=target_name,
                    attributes=kwargs,
                    file_path=file_path,
                    line_number=node.lineno,
                    confidence=0.95,
                    original_code=ast.get_source_segment(code, node) or ""
                )
        
        # Check for orchestrator patterns (Crew, Team, Workflow, etc.)
        orch_names = {"crew", "team", "orchestrator", "pipeline", "workflow"}
        if func_name.lower() in orch_names:
            kwargs = self._extract_call_kwargs(call)
            target_name = ""
            if node.targets and isinstance(node.targets[0], ast.Name):
                target_name = node.targets[0].id
            
            # Determine if it's a workflow or team pattern
            pattern_type = PatternType.ORCHESTRATOR
            if func_name.lower() == "workflow":
                pattern_type = PatternType.WORKFLOW
            
            return PatternInfo(
                pattern_type=pattern_type,
                name=target_name,
                attributes=kwargs,
                file_path=file_path,
                line_number=node.lineno,
                confidence=0.9,
                original_code=ast.get_source_segment(code, node) or ""
            )
        
        # Check for Step pattern (Agno style)
        if func_name.lower() == "step":
            kwargs = self._extract_call_kwargs(call)
            target_name = ""
            if node.targets and isinstance(node.targets[0], ast.Name):
                target_name = node.targets[0].id
            
            return PatternInfo(
                pattern_type=PatternType.TASK,
                name=target_name,
                attributes=kwargs,
                file_path=file_path,
                line_number=node.lineno,
                confidence=0.9,
                original_code=ast.get_source_segment(code, node) or ""
            )
        
        return None
    
    def _analyze_call(self, node, code: str, file_path: str) -> Optional[PatternInfo]:
        """Analyze a function call for patterns."""
        # This handles standalone calls not in assignments
        # Most patterns are caught by _analyze_assignment
        return None
    
    def _extract_call_kwargs(self, call) -> Dict[str, Any]:
        """Extract keyword arguments from a Call node."""
        import ast
        
        kwargs = {}
        for kw in call.keywords:
            if kw.arg:
                # Try to get literal value
                if isinstance(kw.value, ast.Constant):
                    kwargs[kw.arg] = kw.value.value
                elif isinstance(kw.value, ast.List):
                    kwargs[kw.arg] = "[list]"
                elif isinstance(kw.value, ast.Name):
                    kwargs[kw.arg] = f"${kw.value.id}"
                else:
                    kwargs[kw.arg] = "[complex]"
        
        return kwargs


# =============================================================================
# Code Conversion
# =============================================================================

class CodeConverter:
    """Converts agent code patterns to PraisonAI format.
    
    Uses pattern detection to identify agent definitions and converts
    them to PraisonAI's Agent, Task, and AgentTeam classes.
    """
    
    def __init__(self):
        self.detector = PatternDetector()
    
    def analyze(self, path: str) -> AnalysisResult:
        """Analyze a file or directory for convertible patterns.
        
        Args:
            path: File or directory path
            
        Returns:
            Analysis result with detected patterns
        """
        result = AnalysisResult()
        
        if os.path.isfile(path):
            patterns = self._analyze_file(path)
            result.patterns.extend(patterns)
            result.files_scanned = 1
        elif os.path.isdir(path):
            files = self.scan_directory(path)
            result.files_scanned = len(files)
            for file_path in files:
                patterns = self._analyze_file(file_path)
                result.patterns.extend(patterns)
        else:
            result.warnings.append(f"Path not found: {path}")
        
        result.convertible_count = len([p for p in result.patterns 
                                        if p.pattern_type in (PatternType.AGENT, PatternType.TASK, PatternType.ORCHESTRATOR)])
        
        return result
    
    def _analyze_file(self, file_path: str) -> List[PatternInfo]:
        """Analyze a single file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()
            return self.detector.detect_patterns(code, file_path)
        except Exception as e:
            logger.warning(f"Error analyzing {file_path}: {e}")
            return []
    
    def scan_directory(self, path: str) -> List[str]:
        """Scan directory for Python files.
        
        Excludes venv, __pycache__, .git, etc.
        
        Args:
            path: Directory path
            
        Returns:
            List of Python file paths
        """
        exclude_dirs = {"venv", ".venv", "__pycache__", ".git", "node_modules", ".tox", "build", "dist", "*.egg-info"}
        files = []
        
        for root, dirs, filenames in os.walk(path):
            # Filter out excluded directories
            dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.endswith(".egg-info")]
            
            for filename in filenames:
                if filename.endswith(".py"):
                    files.append(os.path.join(root, filename))
        
        return files
    
    def convert_code(self, code: str, file_path: str = "") -> ConversionResult:
        """Convert code to PraisonAI format.
        
        Args:
            code: Source code
            file_path: Optional file path for context
            
        Returns:
            Conversion result
        """
        import ast
        import re
        
        result = ConversionResult(success=True)
        
        # Detect patterns
        patterns = self.detector.detect_patterns(code, file_path)
        result.patterns_found = patterns
        
        converted = code
        
        # Check if code has any framework imports that need conversion
        has_framework_imports = bool(re.search(
            r'from\s+(?:some_framework|crewai|agno|\w+\.(?:agent|team|workflow))',
            code
        ))
        
        if not patterns and not has_framework_imports:
            # No patterns and no framework imports to convert
            result.converted_code = code
            result.warnings.append("No convertible patterns found")
            return result
        
        # Track imports to add
        imports_to_add = set()
        
        # Convert imports first - handle various framework import patterns
        import_replacements = [
            # Full line import removals (must come first to avoid partial matches)
            (r'^from\s+some_framework\s+import\s+[^\n]+$', '', re.MULTILINE),
            (r'^from\s+some_framework\.\w+\s+import\s+[^\n]+$', '', re.MULTILINE),
            (r'^from\s+some_framework\.\w+\.\w+\s+import\s+[^\n]+$', '', re.MULTILINE),
            # Generic framework imports - remove full lines
            (r'^from\s+\w+\.models\.\w+\s+import\s+[^\n]+$', '', re.MULTILINE),
            (r'^from\s+\w+\.db\.\w+\s+import\s+[^\n]+$', '', re.MULTILINE),
            (r'^from\s+\w+\.team\.team\s+import\s+[^\n]+$', '', re.MULTILINE),
            (r'^from\s+\w+\.workflow\s+import\s+[^\n]+$', '', re.MULTILINE),
            # Agent imports from various frameworks - convert
            (r'^from\s+\w+\.agent\s+import\s+Agent\b.*$', 'from praisonaiagents import Agent', re.MULTILINE),
            (r'^from\s+\w+\s+import\s+Agent\b.*$', 'from praisonaiagents import Agent', re.MULTILINE),
            # Task imports
            (r'^from\s+\w+\s+import\s+Task\b.*$', 'from praisonaiagents import Task', re.MULTILINE),
            (r'^from\s+\w+\.task\s+import\s+Task\b.*$', 'from praisonaiagents import Task', re.MULTILINE),
        ]
        
        for item in import_replacements:
            if len(item) == 3:
                pattern, replacement, flags = item
            else:
                pattern, replacement = item
                flags = 0
            if re.search(pattern, converted, flags):
                converted = re.sub(pattern, replacement, converted, flags=flags)
                imports_to_add.add("from praisonaiagents import Agent, Task, AgentTeam")
        
        # Clean up empty lines from removed imports
        lines = converted.split('\n')
        cleaned_lines = []
        prev_empty = False
        for line in lines:
            is_empty = line.strip() == ''
            # Skip consecutive empty lines
            if is_empty and prev_empty:
                continue
            cleaned_lines.append(line)
            prev_empty = is_empty
        converted = '\n'.join(cleaned_lines)
        
        # Convert orchestrator patterns
        orch_replacements = [
            (r'\bCrew\s*\(', 'AgentTeam('),
            (r'\bTeam\s*\(', 'AgentTeam('),
            (r'\bWorkflow\s*\(', 'AgentTeam('),
            (r'\.kickoff\s*\(', '.start('),
            (r'\.print_response\s*\(', '.start('),
        ]
        
        for pattern, replacement in orch_replacements:
            if re.search(pattern, converted):
                converted = re.sub(pattern, replacement, converted)
                imports_to_add.add("from praisonaiagents import AgentTeam")
        
        # Convert Agno-specific patterns
        agno_replacements = [
            # Convert model parameter to llm
            (r'model\s*=\s*Gemini\s*\([^)]*\)', 'llm="gemini/gemini-2.0-flash"'),
            (r'model\s*=\s*OpenAI\s*\([^)]*\)', 'llm="gpt-4o-mini"'),
            # Convert members to agents
            (r'\bmembers\s*=', 'agents='),
            # Convert Step to Task-like
            (r'\bStep\s*\(', 'Task('),
            # Remove unsupported parameters
            (r',?\s*verbose\s*=\s*(?:True|False)', ''),  # Remove verbose param
            (r',?\s*markdown\s*=\s*(?:True|False)', ''),  # Remove markdown param
            (r',?\s*description\s*=\s*"[^"]*"', ''),  # Remove description param from AgentTeam
        ]
        
        for pattern, replacement in agno_replacements:
            if re.search(pattern, converted):
                converted = re.sub(pattern, replacement, converted)
        
        # Add imports if not already present
        if imports_to_add and "from praisonaiagents import" not in converted:
            import_line = "from praisonaiagents import Agent, Task, AgentTeam\n"
            # Add after any existing imports or at the top
            if "import " in converted:
                # Find last import line
                lines = converted.split("\n")
                last_import_idx = 0
                for i, line in enumerate(lines):
                    if line.strip().startswith("import ") or line.strip().startswith("from "):
                        last_import_idx = i
                lines.insert(last_import_idx + 1, import_line.strip())
                converted = "\n".join(lines)
            else:
                converted = import_line + converted
        
        result.converted_code = converted
        
        # Validate converted code
        try:
            ast.parse(converted)
        except SyntaxError as e:
            result.success = False
            result.errors.append(f"Converted code has syntax error: {e}")
        
        return result
    
    def convert_file(
        self,
        source: str,
        output: Optional[str] = None,
        dry_run: bool = True,
        backup: bool = True
    ) -> ConversionResult:
        """Convert a file to PraisonAI format.
        
        Args:
            source: Source file path
            output: Output file path (default: source_converted.py)
            dry_run: If True, don't write files
            backup: If True, create backup when overwriting
            
        Returns:
            Conversion result
        """
        if not os.path.exists(source):
            return ConversionResult(
                success=False,
                errors=[f"Source file not found: {source}"]
            )
        
        try:
            with open(source, "r", encoding="utf-8") as f:
                code = f.read()
        except Exception as e:
            return ConversionResult(
                success=False,
                errors=[f"Failed to read source: {e}"]
            )
        
        result = self.convert_code(code, source)
        
        if not dry_run and result.success:
            output_path = output or source.replace(".py", "_converted.py")
            
            # Create backup if overwriting
            if backup and output_path == source:
                backup_path = source + ".bak"
                try:
                    shutil.copy2(source, backup_path)
                except Exception as e:
                    result.warnings.append(f"Failed to create backup: {e}")
            
            try:
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(result.converted_code)
            except Exception as e:
                result.success = False
                result.errors.append(f"Failed to write output: {e}")
        
        return result
    
    def convert_directory(
        self,
        source: str,
        output: Optional[str] = None,
        dry_run: bool = True,
        backup: bool = True
    ) -> Dict[str, ConversionResult]:
        """Convert all Python files in a directory.
        
        Args:
            source: Source directory
            output: Output directory (default: in-place)
            dry_run: If True, don't write files
            backup: If True, create backups
            
        Returns:
            Dict mapping file paths to conversion results
        """
        results = {}
        files = self.scan_directory(source)
        
        for file_path in files:
            if output:
                rel_path = os.path.relpath(file_path, source)
                out_path = os.path.join(output, rel_path)
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
            else:
                out_path = file_path
            
            result = self.convert_file(file_path, out_path, dry_run, backup)
            results[file_path] = result
        
        return results


class ConfigMigrator:
    """Configuration migrator for PraisonAI."""
    
    def migrate(
        self,
        source: str,
        target: Optional[str] = None,
        source_format: Optional[str] = None,
        target_format: str = "praisonai",
    ) -> Dict[str, Any]:
        """Migrate configuration from one format to another.
        
        Args:
            source: Source configuration file path
            target: Target file path (optional)
            source_format: Source format (auto-detected if not provided)
            target_format: Target format (default: praisonai)
            
        Returns:
            Migration result
        """
        if not os.path.exists(source):
            return {"success": False, "error": f"Source file not found: {source}"}
        
        if not source_format:
            source_format = self._detect_format(source)
        
        try:
            config = self._load_config(source, source_format)
        except Exception as e:
            return {"success": False, "error": f"Failed to load source: {e}"}
        
        try:
            converted = self._convert_config(config, source_format, target_format)
        except Exception as e:
            return {"success": False, "error": f"Failed to convert: {e}"}
        
        if target:
            try:
                self._save_config(converted, target, target_format)
            except Exception as e:
                return {"success": False, "error": f"Failed to save: {e}"}
        
        return {
            "success": True,
            "source_format": source_format,
            "target_format": target_format,
            "config": converted,
            "target_file": target,
        }
    
    def _detect_format(self, path: str) -> str:
        """Detect configuration format from file."""
        import yaml
        
        with open(path, "r") as f:
            content = f.read()
        
        try:
            config = yaml.safe_load(content)
        except Exception:
            return "unknown"
        
        if not isinstance(config, dict):
            return "unknown"
        
        if "framework" in config and config.get("framework") == "praisonai":
            return "praisonai"
        if "agents" in config and "tasks" in config:
            return "crewai"
        if "config_list" in config or "llm_config" in config:
            return "autogen"
        if "agents" in config:
            return "praisonai"
        
        return "unknown"
    
    def _load_config(self, path: str, format: str) -> Dict[str, Any]:
        """Load configuration from file."""
        import yaml
        
        with open(path, "r") as f:
            return yaml.safe_load(f)
    
    def _convert_config(
        self,
        config: Dict[str, Any],
        source_format: str,
        target_format: str,
    ) -> Dict[str, Any]:
        """Convert configuration between formats."""
        if source_format == target_format:
            return config
        
        if source_format == "crewai" and target_format == "praisonai":
            return self._convert_crewai_to_praisonai(config)
        if source_format == "autogen" and target_format == "praisonai":
            return self._convert_autogen_to_praisonai(config)
        if source_format == "praisonai" and target_format == "crewai":
            return self._convert_praisonai_to_crewai(config)
        
        return config
    
    def _convert_crewai_to_praisonai(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Convert CrewAI config to PraisonAI format."""
        result = {
            "framework": "praisonai",
            "topic": config.get("topic", "Converted from CrewAI"),
            "agents": [],
            "steps": [],
        }
        
        for agent in config.get("agents", []):
            result["agents"].append({
                "name": agent.get("role", "agent").lower().replace(" ", "_"),
                "role": agent.get("role", "Agent"),
                "goal": agent.get("goal", ""),
                "backstory": agent.get("backstory", ""),
                "tools": agent.get("tools", []),
            })
        
        for i, task in enumerate(config.get("tasks", [])):
            agent_name = task.get("agent", "")
            if isinstance(agent_name, dict):
                agent_name = agent_name.get("role", "agent").lower().replace(" ", "_")
            
            result["steps"].append({
                "name": f"step_{i+1}",
                "agent": agent_name,
                "action": task.get("description", ""),
                "expected_output": task.get("expected_output", ""),
            })
        
        return result
    
    def _convert_autogen_to_praisonai(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Convert AutoGen config to PraisonAI format."""
        result = {
            "framework": "praisonai",
            "topic": "Converted from AutoGen",
            "agents": [],
            "steps": [],
        }
        
        llm_config = config.get("llm_config", {})
        model = "gpt-4o-mini"
        if "config_list" in llm_config:
            config_list = llm_config["config_list"]
            if config_list:
                model = config_list[0].get("model", model)
        
        for agent in config.get("agents", []):
            result["agents"].append({
                "name": agent.get("name", "agent"),
                "role": agent.get("name", "Agent"),
                "goal": agent.get("system_message", ""),
                "backstory": "",
                "llm": model,
            })
        
        return result
    
    def _convert_praisonai_to_crewai(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Convert PraisonAI config to CrewAI format."""
        result = {
            "agents": [],
            "tasks": [],
        }
        
        for agent in config.get("agents", []):
            result["agents"].append({
                "role": agent.get("role", agent.get("name", "Agent")),
                "goal": agent.get("goal", ""),
                "backstory": agent.get("backstory", ""),
                "tools": agent.get("tools", []),
            })
        
        for step in config.get("steps", []):
            result["tasks"].append({
                "description": step.get("action", ""),
                "expected_output": step.get("expected_output", ""),
                "agent": step.get("agent", ""),
            })
        
        return result
    
    def _save_config(self, config: Dict[str, Any], path: str, format: str) -> None:
        """Save configuration to file."""
        import yaml
        
        with open(path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def handle_migrate_command(args) -> None:
    """Handle migrate CLI command.
    
    Supports both Python code migration and YAML config migration.
    Uses pattern-based detection or AI-driven migration.
    """
    try:
        from rich.console import Console
    except ImportError:
        print("Error: Rich library required")
        return
    
    console = Console()
    
    source = getattr(args, "source", None)
    target = getattr(args, "target", None) or getattr(args, "output", None)
    dry_run = getattr(args, "dry_run", True)
    backup = getattr(args, "backup", True)
    source_format = getattr(args, "from_format", None)
    target_format = getattr(args, "to_format", "praisonai")
    use_ai = not getattr(args, "no_ai", False)  # AI is default
    max_retries = getattr(args, "max_retries", 3)
    llm = getattr(args, "llm", "gpt-4o-mini")
    
    if not source:
        console.print("[red]Error: Source file or directory required[/red]")
        return
    
    if not os.path.exists(source):
        console.print(f"[red]Error: Path not found: {source}[/red]")
        return
    
    # Use AI-driven migration if requested
    if use_ai:
        _handle_ai_migration(console, source, target, dry_run, max_retries, llm)
        return
    
    # Determine if this is Python code or YAML config
    is_python = source.endswith(".py") or (os.path.isdir(source) and not source.endswith((".yaml", ".yml")))
    is_yaml = source.endswith((".yaml", ".yml"))
    
    if is_python or os.path.isdir(source):
        # Python code migration
        _handle_code_migration(console, source, target, dry_run, backup)
    elif is_yaml:
        # YAML config migration
        _handle_config_migration(console, source, target, source_format, target_format)
    else:
        # Try to detect
        try:
            with open(source, "r") as f:
                content = f.read()
            if content.strip().startswith(("import ", "from ", "class ", "def ", "#")):
                _handle_code_migration(console, source, target, dry_run, backup)
            else:
                _handle_config_migration(console, source, target, source_format, target_format)
        except Exception:
            console.print("[yellow]Could not determine file type, trying config migration...[/yellow]")
            _handle_config_migration(console, source, target, source_format, target_format)


def _handle_ai_migration(console, source: str, target: Optional[str], dry_run: bool, max_retries: int, llm: str) -> None:
    """Handle AI-driven migration using AgentFlow."""
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    
    console.print("\n[bold cyan]🤖 AI-Driven Migration[/bold cyan]\n")
    console.print(f"   Source: {source}")
    console.print(f"   LLM: {llm}")
    console.print(f"   Max retries: {max_retries}")
    console.print(f"   Mode: {'dry-run' if dry_run else 'apply'}\n")
    
    try:
        from .migration_flow import MigrationFlow
    except ImportError as e:
        console.print(f"[red]Error importing MigrationFlow: {e}[/red]")
        return
    
    # Create and run the migration flow
    flow = MigrationFlow(
        source_path=source,
        output_path=target,
        max_retries=max_retries,
        llm=llm,
        dry_run=dry_run,
    )
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Running migration agents...", total=None)
        result = flow.run()
        progress.update(task, completed=True)
    
    # Display results
    if result.success:
        console.print(Panel.fit(
            f"[green]✅ Migration successful![/green]\n\n"
            f"Files converted: {result.files_converted}\n"
            f"Iterations: {result.iterations}\n"
            f"Evaluation score: {result.evaluation_score:.1f}/10",
            title="Migration Complete",
        ))
        
        if dry_run:
            console.print("\n[yellow]Dry-run mode: No files were written.[/yellow]")
            console.print("Run with [bold]--apply[/bold] to save converted files.\n")
            
            # Show preview of converted files
            if result.converted_files:
                console.print("[bold]Converted files preview:[/bold]")
                for filename, content in list(result.converted_files.items())[:3]:
                    console.print(f"\n[cyan]{filename}[/cyan]")
                    preview = content[:500] + "..." if len(content) > 500 else content
                    console.print(preview)
        else:
            console.print(f"\n[green]Files saved to: {target or source + '_converted'}[/green]")
    else:
        console.print(Panel.fit(
            f"[red]❌ Migration failed[/red]\n\n"
            f"Iterations attempted: {result.iterations}\n"
            f"Last score: {result.evaluation_score:.1f}/10",
            title="Migration Failed",
        ))
        
        if result.errors:
            console.print("\n[bold red]Errors:[/bold red]")
            for error in result.errors:
                console.print(f"  • {error}")
        
        if result.warnings:
            console.print("\n[bold yellow]Warnings:[/bold yellow]")
            for warning in result.warnings:
                console.print(f"  • {warning}")


def _handle_code_migration(console, source: str, target: Optional[str], dry_run: bool, backup: bool) -> None:
    """Handle Python code migration."""
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.table import Table
    
    converter = CodeConverter()
    
    # Analysis phase
    console.print("\n[bold cyan]🔍 Analyzing code patterns...[/bold cyan]\n")
    
    analysis = converter.analyze(source)
    
    if analysis.files_scanned == 0:
        console.print("[yellow]No Python files found to analyze.[/yellow]")
        return
    
    console.print(f"   Scanned [bold]{analysis.files_scanned}[/bold] Python file(s)")
    
    if not analysis.patterns:
        console.print("[yellow]   No convertible patterns found.[/yellow]")
        return
    
    # Count patterns by type
    pattern_counts = {}
    for p in analysis.patterns:
        ptype = p.pattern_type.value
        pattern_counts[ptype] = pattern_counts.get(ptype, 0) + 1
    
    pattern_summary = ", ".join(f"{count} {ptype}" for ptype, count in pattern_counts.items())
    console.print(f"   Found [bold green]{len(analysis.patterns)}[/bold green] patterns: {pattern_summary}")
    
    # Show patterns table
    if analysis.patterns:
        table = Table(title="Detected Patterns", show_header=True)
        table.add_column("Type", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("File", style="dim")
        table.add_column("Line", justify="right")
        table.add_column("Confidence", justify="right")
        
        for p in analysis.patterns[:20]:  # Limit to 20 rows
            file_display = os.path.basename(p.file_path) if p.file_path else "-"
            table.add_row(
                p.pattern_type.value,
                p.name or "-",
                file_display,
                str(p.line_number),
                f"{p.confidence:.0%}"
            )
        
        if len(analysis.patterns) > 20:
            table.add_row("...", f"({len(analysis.patterns) - 20} more)", "", "", "")
        
        console.print(table)
    
    # Conversion phase
    if dry_run:
        console.print("\n[bold yellow]📋 Conversion Preview (dry-run mode)[/bold yellow]")
        console.print("   Run with [bold]--apply[/bold] to execute conversion.\n")
    else:
        console.print("\n[bold green]🔄 Converting...[/bold green]\n")
    
    if os.path.isfile(source):
        result = converter.convert_file(source, target, dry_run, backup)
        
        if result.success:
            if dry_run:
                console.print(Panel.fit(
                    f"[green]Conversion preview successful![/green]\n\n"
                    f"Patterns found: {len(result.patterns_found)}\n"
                    f"Warnings: {len(result.warnings)}",
                    title="Migration Preview",
                ))
                
                if result.converted_code and result.converted_code != result.patterns_found:
                    console.print("\n[bold]Converted code preview:[/bold]")
                    console.print(Syntax(result.converted_code[:2000], "python", line_numbers=True))
                    if len(result.converted_code) > 2000:
                        console.print(f"... ({len(result.converted_code)} chars total)")
            else:
                console.print(f"[green]✓[/green] Converted: {source}")
                if target:
                    console.print(f"   Saved to: {target}")
        else:
            console.print(f"[red]✗[/red] Failed: {source}")
            for error in result.errors:
                console.print(f"   [red]{error}[/red]")
        
        for warning in result.warnings:
            console.print(f"   [yellow]⚠ {warning}[/yellow]")
    
    elif os.path.isdir(source):
        results = converter.convert_directory(source, target, dry_run, backup)
        
        success_count = sum(1 for r in results.values() if r.success)
        fail_count = len(results) - success_count
        
        console.print(f"\n[bold]Results:[/bold] {success_count} succeeded, {fail_count} failed")
        
        for file_path, result in results.items():
            if not result.success:
                console.print(f"[red]✗[/red] {file_path}")
                for error in result.errors:
                    console.print(f"   [red]{error}[/red]")


def _handle_config_migration(console, source: str, target: Optional[str], source_format: Optional[str], target_format: str) -> None:
    """Handle YAML config migration."""
    from rich.panel import Panel
    from rich.syntax import Syntax
    
    migrator = ConfigMigrator()
    
    result = migrator.migrate(
        source=source,
        target=target,
        source_format=source_format,
        target_format=target_format,
    )
    
    if not result["success"]:
        console.print(f"[red]Migration failed: {result['error']}[/red]")
        return
    
    # Use generic terminology in output
    source_desc = "detected format" if result['source_format'] != "praisonai" else "PraisonAI"
    
    console.print(Panel.fit(
        f"[green]Migration successful![/green]\n\n"
        f"Source: {source_desc}\n"
        f"Target: PraisonAI format",
        title="Config Migration",
    ))
    
    if target:
        console.print(f"\nSaved to: {target}")
    else:
        import yaml
        yaml_str = yaml.dump(result["config"], default_flow_style=False, sort_keys=False)
        console.print("\nConverted configuration:")
        console.print(Syntax(yaml_str, "yaml"))


def add_migrate_parser(subparsers) -> None:
    """Add migrate subparser to CLI.
    
    Supports both Python code migration and YAML config migration.
    Uses generic terminology to avoid exposing competitor framework names.
    """
    migrate_parser = subparsers.add_parser(
        "migrate",
        help="Migrate agent code and configurations to PraisonAI format",
        description="Convert agent definitions from various formats to PraisonAI. "
                    "Supports both Python code and YAML configurations. "
                    "Uses AI-driven pattern detection and conversion.",
    )
    migrate_parser.add_argument(
        "source",
        help="Source file or directory to migrate",
    )
    migrate_parser.add_argument(
        "--output", "-o",
        dest="target",
        help="Output file or directory (default: preview only)",
    )
    migrate_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview changes without writing files (default)",
    )
    migrate_parser.add_argument(
        "--apply",
        action="store_true",
        dest="apply_changes",
        help="Apply changes and write output files",
    )
    migrate_parser.add_argument(
        "--no-backup",
        action="store_false",
        dest="backup",
        default=True,
        help="Don't create backup files when overwriting",
    )
    migrate_parser.add_argument(
        "--from", dest="from_format",
        choices=["auto", "yaml", "python"],
        default="auto",
        help="Source format (default: auto-detect)",
    )
    migrate_parser.add_argument(
        "--to", dest="to_format",
        default="praisonai",
        help="Target format (default: praisonai)",
    )
    migrate_parser.add_argument(
        "--no-ai",
        action="store_true",
        dest="no_ai",
        help="Disable AI-driven migration, use pattern-based only",
    )
    migrate_parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum retry attempts for AI migration (default: 3)",
    )
    migrate_parser.add_argument(
        "--llm",
        default="gpt-4o-mini",
        help="LLM model for AI migration (default: gpt-4o-mini)",
    )
    migrate_parser.set_defaults(func=_migrate_command_wrapper)


def _migrate_command_wrapper(args) -> None:
    """Wrapper to handle --apply flag."""
    # If --apply is set, disable dry_run
    if getattr(args, "apply_changes", False):
        args.dry_run = False
    handle_migrate_command(args)
