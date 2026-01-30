"""
API Markdown Generator for PraisonAI.

Generates a comprehensive api.md file documenting all public API surfaces:
- Python Core SDK (praisonaiagents)
- Python Wrapper/Integrations (praisonai)
- CLI commands
- TypeScript package (praisonai-ts)

Uses AST-based static analysis to avoid importing heavy dependencies.

Example output format (OpenAI SDK style):

# Agents

Types:
```python
from praisonaiagents import Agent, AgentConfig
from praisonaiagents.types import RunResult
```

Methods:
* <code title="class Agent">Agent.<a href="./src/praisonai-agents/praisonaiagents/agent.py">start</a>(prompt: str, **kwargs) -> RunResult</code>

Usage:
    python -m praisonai._dev.api_md --write
    python -m praisonai._dev.api_md --check
    python -m praisonai._dev.api_md --stdout
"""

import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class SymbolInfo:
    """Information about a discovered symbol."""
    name: str
    kind: str  # 'class', 'function', 'type', 'constant'
    module_path: str  # e.g., 'praisonaiagents.agent.agent'
    file_path: str  # relative to repo root
    line_number: int
    signature: Optional[str] = None
    return_type: Optional[str] = None
    methods: List["MethodInfo"] = field(default_factory=list)
    docstring: Optional[str] = None


@dataclass
class MethodInfo:
    """Information about a class method."""
    name: str
    signature: str
    return_type: Optional[str]
    line_number: int


@dataclass
class CLICommand:
    """Information about a CLI command."""
    command_path: str  # e.g., 'praisonai docs api-md'
    help_text: Optional[str]
    file_path: str
    line_number: int


@dataclass
class TSExport:
    """Information about a TypeScript export."""
    name: str
    kind: str  # 'class', 'function', 'type', 'const'
    source_file: str
    is_type: bool = False


class ApiMdGenerator:
    """
    Generates api.md from source code using AST analysis.
    
    Design principles:
    - AST-first: Never import modules that may have heavy dependencies
    - Deterministic: Stable ordering for reproducible output
    - Comprehensive: Cover all public exports
    """
    
    # Section groupings for organizing exports
    SECTION_GROUPS = {
        'Shared Types': ['TaskOutput', 'ReflectionOutput', 'ToolResult', 'ToolValidationError',
                         'GuardrailResult', 'StepResult', 'WorkflowContext', 'HandoffResult',
                         'HandoffInputData', 'HandoffConfig', 'ContextPolicy', 'HandoffError',
                         'HandoffCycleError', 'HandoffDepthError', 'HandoffTimeoutError'],
        'Agents': ['Agent', 'Agents', 'PraisonAIAgents', 'ImageAgent', 'ContextAgent',
                   'DeepResearchAgent', 'QueryRewriterAgent', 'PromptExpanderAgent',
                   'AutoAgents', 'AutoRagAgent', 'PlanningAgent', 'create_context_agent'],
        'Tools': ['Tools', 'BaseTool', 'tool', 'FunctionTool', 'ToolRegistry',
                  'get_registry', 'register_tool', 'get_tool', 'validate_tool'],
        'Workflows': ['Workflow', 'Task', 'Pipeline', 'Route', 'Parallel',
                      'Loop', 'Repeat', 'route', 'parallel', 'loop', 'repeat'],
        'DB': ['db', 'DbAdapter', 'AsyncDbAdapter'],
        'Memory': ['Memory', 'MemoryConfig', 'MemoryBackend'],
        'Knowledge': ['Knowledge', 'Chunking', 'ChunkingStrategy', 'KnowledgeConfig'],
        'RAG': ['RAG', 'RAGConfig', 'RAGResult', 'RAGCitation', 'RetrievalConfig',
                'RetrievalPolicy', 'CitationsMode', 'ContextPack'],
        'Handoff': ['Handoff', 'handoff', 'handoff_filters', 'RECOMMENDED_PROMPT_PREFIX',
                    'prompt_with_handoff_instructions'],
        'Guardrails': ['LLMGuardrail', 'GuardrailConfig', 'GuardrailAction', 'GUARDRAIL_PRESETS'],
        'Planning': ['Plan', 'PlanStep', 'TodoList', 'TodoItem', 'PlanStorage',
                     'ApprovalCallback', 'READ_ONLY_TOOLS', 'RESTRICTED_TOOLS', 'PlanningConfig'],
        'Skills': ['SkillManager', 'SkillProperties', 'SkillMetadata', 'SkillLoader', 'SkillsConfig'],
        'Session': ['Session'],
        'MCP': ['MCP'],
        'Telemetry': ['get_telemetry', 'enable_telemetry', 'disable_telemetry',
                      'enable_performance_mode', 'disable_performance_mode',
                      'cleanup_telemetry_resources', 'MinimalTelemetry', 'TelemetryCollector'],
        'Observability': ['obs', 'FlowDisplay', 'track_workflow'],
        'Context': ['FastContext', 'FastContextResult', 'FileMatch', 'LineRange',
                    'ContextManager', 'ManagerConfig'],
        'UI': ['AGUI', 'A2A'],
        'Config': ['MemoryConfig', 'KnowledgeConfig', 'PlanningConfig', 'ReflectionConfig',
                   'GuardrailConfig', 'WebConfig', 'OutputConfig', 'ExecutionConfig',
                   'TemplateConfig', 'CachingConfig', 'HooksConfig', 'SkillsConfig',
                   'AutonomyConfig', 'OutputPreset', 'ExecutionPreset', 'AutonomyLevel',
                   'WebSearchProvider', 'MultiAgentHooksConfig', 'MultiAgentOutputConfig',
                   'MultiAgentExecutionConfig', 'MultiAgentPlanningConfig', 'MultiAgentMemoryConfig'],
        'Display': ['display_interaction', 'display_self_reflection', 'display_instruction',
                    'display_tool_call', 'display_error', 'display_generating',
                    'clean_triple_backticks', 'error_logs', 'register_display_callback',
                    'sync_display_callbacks', 'async_display_callbacks'],
        'Utilities': ['resolve', 'ArrayMode', 'resolve_memory', 'resolve_knowledge',
                      'resolve_output', 'resolve_execution', 'resolve_web', 'resolve_planning',
                      'resolve_reflection', 'resolve_context', 'resolve_autonomy',
                      'resolve_caching', 'resolve_hooks', 'resolve_skills', 'resolve_routing',
                      'resolve_guardrails', 'resolve_guardrail_policies', 'is_policy_string',
                      'parse_policy_string'],
    }
    
    def __init__(self, repo_root: Optional[Path] = None):
        """Initialize the generator with repository root path."""
        if repo_root is None:
            # Auto-detect repo root
            repo_root = self._find_repo_root()
        self.repo_root = Path(repo_root).resolve()
        
        # Package paths
        self.agents_pkg = self.repo_root / "src" / "praisonai-agents" / "praisonaiagents"
        self.wrapper_pkg = self.repo_root / "src" / "praisonai" / "praisonai"
        self.ts_pkg = self.repo_root / "src" / "praisonai-ts"
        
        # Discovered symbols
        self.agents_symbols: Dict[str, SymbolInfo] = {}
        self.wrapper_symbols: Dict[str, SymbolInfo] = {}
        self.cli_commands: List[CLICommand] = []
        self.ts_exports: List[TSExport] = []
        
    def _find_repo_root(self) -> Path:
        """Find repository root by looking for .git directory."""
        current = Path.cwd()
        while current != current.parent:
            if (current / ".git").exists():
                return current
            current = current.parent
        # Fallback to expected location
        return Path("/Users/praison/praisonai-package")
    
    def discover_all(self) -> None:
        """Discover all public API symbols."""
        self._discover_python_exports(self.agents_pkg, "praisonaiagents", self.agents_symbols)
        self._discover_python_exports(self.wrapper_pkg, "praisonai", self.wrapper_symbols)
        self._discover_cli_commands()
        self._discover_ts_exports()
    
    def _discover_python_exports(
        self, 
        pkg_path: Path, 
        pkg_name: str,
        symbols: Dict[str, SymbolInfo]
    ) -> None:
        """Discover Python exports from __init__.py using AST."""
        init_file = pkg_path / "__init__.py"
        if not init_file.exists():
            return
        
        try:
            with open(init_file, 'r', encoding='utf-8') as f:
                source = f.read()
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            return
        
        # Extract __all__ if present
        all_exports: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == '__all__':
                        if isinstance(node.value, ast.List):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    all_exports.add(elt.value)
        
        # Track imports to find source files
        import_sources: Dict[str, Tuple[str, str]] = {}  # name -> (module, original_name)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    name = alias.asname if alias.asname else alias.name
                    import_sources[name] = (node.module, alias.name)
        
        # Parse __getattr__ for lazy-loaded symbols
        lazy_sources = self._parse_getattr_lazy_imports(tree)
        import_sources.update(lazy_sources)
        
        # Parse _LAZY_IMPORTS dictionary pattern
        dict_sources = self._parse_lazy_imports_dict(tree)
        import_sources.update(dict_sources)
        
        # Also include symbols from SECTION_GROUPS that exist in lazy imports
        # This ensures lazy-loaded classes like Workflow appear in api.md
        # even if they're not in __all__ (which is kept minimal for IDE experience)
        section_symbols = set()
        for symbol_list in self.SECTION_GROUPS.values():
            section_symbols.update(symbol_list)
        
        # Merge: __all__ exports + section group symbols that exist in lazy imports
        exports_to_process = all_exports | (section_symbols & set(import_sources.keys()))
        
        # For each export, find its definition
        for export_name in sorted(exports_to_process):
            if export_name in import_sources:
                module_path, original_name = import_sources[export_name]
                # Resolve to file
                symbol_info = self._resolve_symbol(
                    pkg_path, pkg_name, module_path, original_name, export_name
                )
                if symbol_info:
                    symbols[export_name] = symbol_info
            else:
                # Defined in __init__.py itself
                symbol_info = self._find_symbol_in_file(
                    init_file, export_name, pkg_name
                )
                if symbol_info:
                    symbols[export_name] = symbol_info
    
    def _parse_getattr_lazy_imports(self, tree: ast.Module) -> Dict[str, Tuple[str, str]]:
        """
        Parse __getattr__ function to extract lazy-loaded imports.
        
        Looks for patterns like:
            if name == "Agent":
                from .agent.agent import Agent
                return Agent
        """
        lazy_sources: Dict[str, Tuple[str, str]] = {}
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == '__getattr__':
                # Walk through ALL nodes in the function to find if statements
                for stmt in ast.walk(node):
                    if isinstance(stmt, ast.If):
                        # Check if this is `if name == "SomeName":` or `if name in ("A", "B"):`
                        symbol_names = self._extract_name_comparisons(stmt.test)
                        if symbol_names:
                            # Look for import statement in the body
                            for inner_stmt in stmt.body:
                                if isinstance(inner_stmt, ast.ImportFrom) and inner_stmt.module:
                                    for alias in inner_stmt.names:
                                        imported_name = alias.name
                                        for symbol_name in symbol_names:
                                            lazy_sources[symbol_name] = (inner_stmt.module, imported_name)
                                    break
                                elif isinstance(inner_stmt, ast.Assign):
                                    # Handle: value = lazy_import('path', 'attr', cache)
                                    if isinstance(inner_stmt.value, ast.Call) and getattr(inner_stmt.value.func, 'id', '') == 'lazy_import':
                                        if len(inner_stmt.value.args) >= 2:
                                            mod_arg = inner_stmt.value.args[0]
                                            attr_arg = inner_stmt.value.args[1]
                                            if (isinstance(mod_arg, ast.Constant) and isinstance(mod_arg.value, str) and
                                                isinstance(attr_arg, ast.Constant) and isinstance(attr_arg.value, str)):
                                                for symbol_name in symbol_names:
                                                    lazy_sources[symbol_name] = (mod_arg.value, attr_arg.value)
                                        break
        
        return lazy_sources

    def _parse_lazy_imports_dict(self, tree: ast.Module) -> Dict[str, Tuple[str, str]]:
        """Parse _LAZY_IMPORTS dictionary definition."""
        lazy_sources: Dict[str, Tuple[str, str]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == '_LAZY_IMPORTS':
                        if isinstance(node.value, ast.Dict):
                            for k, v in zip(node.value.keys, node.value.values):
                                if k and isinstance(k, ast.Constant) and isinstance(k.value, str):
                                    if isinstance(v, ast.Tuple) and len(v.elts) >= 2:
                                        module_elt = v.elts[0]
                                        attr_elt = v.elts[1]
                                        if (isinstance(module_elt, ast.Constant) and isinstance(module_elt.value, str) and
                                            isinstance(attr_elt, ast.Constant) and isinstance(attr_elt.value, str)):
                                            lazy_sources[k.value] = (module_elt.value, attr_elt.value)
        return lazy_sources
    
    def _extract_name_comparisons(self, test: ast.expr) -> List[str]:
        """
        Extract the string values from comparisons like `name == "Agent"`
        or `name in ("A", "B", "C")`.
        """
        names = []
        if isinstance(test, ast.Compare):
            # Handle: name == "Agent"
            if (len(test.ops) == 1 and 
                isinstance(test.ops[0], ast.Eq) and
                isinstance(test.left, ast.Name) and test.left.id == 'name'):
                if len(test.comparators) == 1:
                    comp = test.comparators[0]
                    if isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                        names.append(comp.value)
            # Handle: name in ("A", "B", "C")
            if (len(test.ops) == 1 and
                isinstance(test.ops[0], ast.In) and
                isinstance(test.left, ast.Name) and test.left.id == 'name'):
                if len(test.comparators) == 1:
                    comp = test.comparators[0]
                    if isinstance(comp, ast.Tuple):
                        for elt in comp.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                names.append(elt.value)
        return names
    
    def _resolve_symbol(
        self,
        pkg_path: Path,
        pkg_name: str,
        module_path: str,
        original_name: str,
        export_name: str
    ) -> Optional[SymbolInfo]:
        """Resolve a symbol to its definition file."""
        file_path = None
        
        # Handle relative imports (starting with .)
        if module_path.startswith('.'):
            # Convert relative to absolute
            parts = module_path.lstrip('.').split('.')
            rel_depth = len(module_path) - len(module_path.lstrip('.'))
            if rel_depth == 1:
                # Same package
                file_path = pkg_path
            else:
                file_path = pkg_path.parent
                for _ in range(rel_depth - 1):
                    file_path = file_path.parent
            for part in parts:
                if part:
                    file_path = file_path / part
        # Handle absolute imports starting with package name
        elif module_path.startswith(pkg_name + '.') or module_path == pkg_name:
            rel_path = module_path[len(pkg_name):].lstrip('.')
            parts = rel_path.split('.') if rel_path else []
            file_path = pkg_path
            for part in parts:
                file_path = file_path / part
        else:
            # Treat as relative import within package (e.g., 'agent.agent' -> pkg_path/agent/agent.py)
            # This handles lazy imports in __getattr__ that use implicit relative paths
            parts = module_path.split('.')
            file_path = pkg_path
            for part in parts:
                file_path = file_path / part
        
        if file_path is None:
            return None
        
        # Try as directory with __init__.py or as .py file
        if file_path.is_dir():
            init_file = file_path / "__init__.py"
            if init_file.exists():
                return self._find_symbol_in_file(init_file, original_name, pkg_name, export_name)
        
        py_file = file_path.with_suffix('.py')
        if py_file.exists():
            return self._find_symbol_in_file(py_file, original_name, pkg_name, export_name)
        
        return None
    
    def _find_symbol_in_file(
        self,
        file_path: Path,
        symbol_name: str,
        pkg_name: str,
        export_name: Optional[str] = None
    ) -> Optional[SymbolInfo]:
        """Find a symbol definition in a Python file."""
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            return None
        
        rel_path = self._get_relative_path(file_path)
        module_path = self._file_to_module(file_path, pkg_name)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == symbol_name:
                methods = self._extract_methods(node)
                return SymbolInfo(
                    name=export_name or symbol_name,
                    kind='class',
                    module_path=module_path,
                    file_path=rel_path,
                    line_number=node.lineno,
                    signature=self._extract_class_signature(node),
                    methods=methods,
                    docstring=ast.get_docstring(node)
                )
            elif isinstance(node, ast.FunctionDef) and node.name == symbol_name:
                return SymbolInfo(
                    name=export_name or symbol_name,
                    kind='function',
                    module_path=module_path,
                    file_path=rel_path,
                    line_number=node.lineno,
                    signature=self._extract_function_signature(node),
                    return_type=self._extract_return_type(node),
                    docstring=ast.get_docstring(node)
                )
            elif isinstance(node, ast.AsyncFunctionDef) and node.name == symbol_name:
                return SymbolInfo(
                    name=export_name or symbol_name,
                    kind='function',
                    module_path=module_path,
                    file_path=rel_path,
                    line_number=node.lineno,
                    signature=self._extract_function_signature(node),
                    return_type=self._extract_return_type(node),
                    docstring=ast.get_docstring(node)
                )
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == symbol_name:
                        return SymbolInfo(
                            name=export_name or symbol_name,
                            kind='constant',
                            module_path=module_path,
                            file_path=rel_path,
                            line_number=node.lineno
                        )
        
        # Check for re-exports in __init__.py
        if file_path.name == "__init__.py":
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    for alias in node.names:
                        name = alias.asname if alias.asname else alias.name
                        if name == symbol_name:
                            # Recursively resolve
                            return self._resolve_symbol(
                                file_path.parent, pkg_name,
                                '.' + node.module if not node.module.startswith('.') else node.module,
                                alias.name, export_name or symbol_name
                            )
        
        return None
    
    def _extract_methods(self, class_node: ast.ClassDef) -> List[MethodInfo]:
        """Extract public methods from a class."""
        methods = []
        for node in class_node.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith('_') or node.name in ('__init__', '__call__'):
                    methods.append(MethodInfo(
                        name=node.name,
                        signature=self._extract_function_signature(node),
                        return_type=self._extract_return_type(node),
                        line_number=node.lineno
                    ))
        return sorted(methods, key=lambda m: m.name)
    
    def _extract_function_signature(self, node: ast.FunctionDef) -> str:
        """Extract function signature as string."""
        args = []
        
        # Regular args
        defaults_offset = len(node.args.args) - len(node.args.defaults)
        for i, arg in enumerate(node.args.args):
            if arg.arg == 'self' or arg.arg == 'cls':
                continue
            arg_str = arg.arg
            if arg.annotation:
                arg_str += f": {self._annotation_to_str(arg.annotation)}"
            if i >= defaults_offset:
                default = node.args.defaults[i - defaults_offset]
                arg_str += f" = {self._default_to_str(default)}"
            args.append(arg_str)
        
        # *args
        if node.args.vararg:
            arg_str = f"*{node.args.vararg.arg}"
            if node.args.vararg.annotation:
                arg_str += f": {self._annotation_to_str(node.args.vararg.annotation)}"
            args.append(arg_str)
        
        # **kwargs
        if node.args.kwarg:
            arg_str = f"**{node.args.kwarg.arg}"
            if node.args.kwarg.annotation:
                arg_str += f": {self._annotation_to_str(node.args.kwarg.annotation)}"
            args.append(arg_str)
        
        return f"({', '.join(args)})"
    
    def _extract_class_signature(self, node: ast.ClassDef) -> str:
        """Extract class __init__ signature."""
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                return self._extract_function_signature(item)
        return "()"
    
    def _extract_return_type(self, node: ast.FunctionDef) -> Optional[str]:
        """Extract return type annotation."""
        if node.returns:
            return self._annotation_to_str(node.returns)
        return None
    
    def _annotation_to_str(self, node: ast.expr) -> str:
        """Convert AST annotation to string."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.Subscript):
            value = self._annotation_to_str(node.value)
            slice_val = self._annotation_to_str(node.slice)
            return f"{value}[{slice_val}]"
        elif isinstance(node, ast.Attribute):
            return f"{self._annotation_to_str(node.value)}.{node.attr}"
        elif isinstance(node, ast.Tuple):
            elts = ', '.join(self._annotation_to_str(e) for e in node.elts)
            return elts
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            left = self._annotation_to_str(node.left)
            right = self._annotation_to_str(node.right)
            return f"{left} | {right}"
        elif isinstance(node, ast.List):
            elts = ', '.join(self._annotation_to_str(e) for e in node.elts)
            return f"[{elts}]"
        return "Any"
    
    def _default_to_str(self, node: ast.expr) -> str:
        """Convert default value to string."""
        if isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.List):
            return "[]"
        elif isinstance(node, ast.Dict):
            return "{}"
        elif isinstance(node, ast.Call):
            return "..."
        return "..."
    
    def _get_relative_path(self, file_path: Path) -> str:
        """Get path relative to repo root."""
        try:
            return "./" + str(file_path.relative_to(self.repo_root))
        except ValueError:
            return str(file_path)
    
    def _file_to_module(self, file_path: Path, pkg_name: str) -> str:
        """Convert file path to module path."""
        try:
            if pkg_name == "praisonaiagents":
                rel = file_path.relative_to(self.agents_pkg.parent)
            else:
                rel = file_path.relative_to(self.wrapper_pkg.parent)
            parts = list(rel.parts)
            if parts[-1] == "__init__.py":
                parts = parts[:-1]
            elif parts[-1].endswith('.py'):
                parts[-1] = parts[-1][:-3]
            return '.'.join(parts)
        except ValueError:
            return pkg_name
    
    def _discover_cli_commands(self) -> None:
        """Discover CLI commands from Typer apps."""
        commands_dir = self.wrapper_pkg / "cli" / "commands"
        if not commands_dir.exists():
            return
        
        for py_file in sorted(commands_dir.glob("*.py")):
            if py_file.name.startswith('_'):
                continue
            self._parse_typer_commands(py_file)
        
        # Also check main.py for argparse commands
        main_py = self.wrapper_pkg / "cli" / "main.py"
        if main_py.exists():
            self._parse_main_commands(main_py)
    
    def _parse_typer_commands(self, file_path: Path) -> None:
        """Parse Typer command definitions from a file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            return
        
        rel_path = self._get_relative_path(file_path)
        command_name = file_path.stem
        
        # Find @app.command() decorators
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for decorator in node.decorator_list:
                    if self._is_command_decorator(decorator):
                        cmd_name = self._extract_command_name(decorator, node.name)
                        help_text = ast.get_docstring(node)
                        self.cli_commands.append(CLICommand(
                            command_path=f"praisonai {command_name} {cmd_name}".strip(),
                            help_text=help_text[:100] if help_text else None,
                            file_path=rel_path,
                            line_number=node.lineno
                        ))
    
    def _is_command_decorator(self, decorator: ast.expr) -> bool:
        """Check if decorator is @app.command() or similar."""
        if isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Attribute):
                return decorator.func.attr in ('command', 'callback')
        elif isinstance(decorator, ast.Attribute):
            return decorator.attr in ('command', 'callback')
        return False
    
    def _extract_command_name(self, decorator: ast.expr, func_name: str) -> str:
        """Extract command name from decorator or function name."""
        if isinstance(decorator, ast.Call):
            for arg in decorator.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    return arg.value
            for kw in decorator.keywords:
                if kw.arg == 'name' and isinstance(kw.value, ast.Constant):
                    return kw.value.value
        # Convert function name: some_command -> some-command
        return func_name.replace('_', '-')
    
    def _parse_main_commands(self, file_path: Path) -> None:
        """Parse main CLI commands from argparse in main.py."""
        # Add base commands that are handled in main.py
        rel_path = self._get_relative_path(file_path)
        base_commands = [
            ("praisonai", "Main CLI entry point"),
            ("praisonai run", "Run agents from YAML file"),
            ("praisonai chat", "Terminal chat interface"),
            ("praisonai code", "Terminal code assistant"),
        ]
        for cmd, help_text in base_commands:
            self.cli_commands.append(CLICommand(
                command_path=cmd,
                help_text=help_text,
                file_path=rel_path,
                line_number=1
            ))
    
    def _discover_ts_exports(self) -> None:
        """Discover TypeScript exports from index.ts."""
        index_file = self.ts_pkg / "src" / "index.ts"
        if not index_file.exists():
            return
        
        try:
            with open(index_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except (IOError, UnicodeDecodeError):
            return
        
        # Parse export statements using regex
        # export { Name1, Name2 } from './path'
        export_pattern = r"export\s*\{([^}]+)\}\s*from\s*['\"]([^'\"]+)['\"]"
        type_export_pattern = r"export\s+type\s*\{([^}]+)\}\s*from\s*['\"]([^'\"]+)['\"]"
        
        for match in re.finditer(export_pattern, content):
            names = match.group(1)
            source = match.group(2)
            for name in names.split(','):
                name = name.strip()
                if ' as ' in name:
                    name = name.split(' as ')[1].strip()
                if name and not name.startswith('type '):
                    self.ts_exports.append(TSExport(
                        name=name,
                        kind='export',
                        source_file=source,
                        is_type=False
                    ))
        
        for match in re.finditer(type_export_pattern, content):
            names = match.group(1)
            source = match.group(2)
            for name in names.split(','):
                name = name.strip()
                if ' as ' in name:
                    name = name.split(' as ')[1].strip()
                if name:
                    self.ts_exports.append(TSExport(
                        name=name,
                        kind='type',
                        source_file=source,
                        is_type=True
                    ))
    
    def generate(self) -> str:
        """Generate the api.md content."""
        self.discover_all()
        
        lines = [
            "# PraisonAI API Reference",
            "",
            "This file is auto-generated. Do not edit manually.",
            "Regenerate with: `praisonai docs api-md --write`",
            "",
        ]
        
        # Group symbols by section
        sections = self._group_symbols_by_section()
        
        # Generate each section
        section_order = [
            'Shared Types', 'Agents', 'Tools', 'Workflows', 'DB', 'Memory',
            'Knowledge', 'RAG', 'Handoff', 'Guardrails', 'Planning', 'Skills',
            'Session', 'MCP', 'Telemetry', 'Observability', 'Context', 'UI',
            'Config', 'Display', 'Utilities'
        ]
        
        for section_name in section_order:
            if section_name in sections and sections[section_name]:
                lines.extend(self._generate_section(section_name, sections[section_name]))
        
        # Handle remaining symbols not in predefined sections
        remaining = self._get_remaining_symbols(sections)
        if remaining:
            lines.extend(self._generate_section('Other', remaining))
        
        # Wrapper package exports
        if self.wrapper_symbols:
            lines.extend(self._generate_wrapper_section())
        
        # CLI section
        if self.cli_commands:
            lines.extend(self._generate_cli_section())
        
        # TypeScript section
        if self.ts_exports:
            lines.extend(self._generate_ts_section())
        
        # Optional Plugins section
        lines.extend(self._generate_plugins_section())
        
        return '\n'.join(lines)
    
    def _group_symbols_by_section(self) -> Dict[str, List[SymbolInfo]]:
        """Group symbols by their section."""
        sections: Dict[str, List[SymbolInfo]] = {}
        
        for section_name, symbol_names in self.SECTION_GROUPS.items():
            section_symbols = []
            for name in symbol_names:
                if name in self.agents_symbols:
                    section_symbols.append(self.agents_symbols[name])
            if section_symbols:
                sections[section_name] = sorted(section_symbols, key=lambda s: s.name)
        
        return sections
    
    def _get_remaining_symbols(self, sections: Dict[str, List[SymbolInfo]]) -> List[SymbolInfo]:
        """Get symbols not in any predefined section."""
        used_names = set()
        for symbol_list in sections.values():
            for symbol in symbol_list:
                used_names.add(symbol.name)
        
        remaining = []
        for name, symbol in self.agents_symbols.items():
            if name not in used_names:
                remaining.append(symbol)
        
        return sorted(remaining, key=lambda s: s.name)
    
    def _generate_section(self, section_name: str, symbols: List[SymbolInfo]) -> List[str]:
        """Generate a section of the API documentation."""
        lines = [
            f"# {section_name}",
            "",
        ]
        
        # Types block
        imports = []
        for symbol in symbols:
            if symbol.module_path.startswith('praisonaiagents'):
                imports.append(symbol.name)
        
        if imports:
            lines.append("Types:")
            lines.append("```python")
            # Group imports by module
            lines.append(f"from praisonaiagents import {', '.join(sorted(imports))}")
            lines.append("```")
            lines.append("")
        
        # Methods block
        methods_lines = []
        for symbol in symbols:
            if symbol.kind == 'class' and symbol.methods:
                for method in symbol.methods:
                    if method.name == '__init__':
                        continue
                    ret_type = f" -> {method.return_type}" if method.return_type else ""
                    methods_lines.append(
                        f'* <code title="class {symbol.name}">{symbol.name}.'
                        f'<a href="{symbol.file_path}">{method.name}</a>'
                        f'{method.signature}{ret_type}</code>'
                    )
            elif symbol.kind == 'function':
                ret_type = f" -> {symbol.return_type}" if symbol.return_type else ""
                module_prefix = symbol.module_path.split('.')[0]
                methods_lines.append(
                    f'* <code title="function">{module_prefix}.'
                    f'<a href="{symbol.file_path}">{symbol.name}</a>'
                    f'{symbol.signature or "()"}{ret_type}</code>'
                )
        
        if methods_lines:
            lines.append("Methods:")
            lines.append("")
            lines.extend(methods_lines)
            lines.append("")
        
        return lines
    
    def _generate_wrapper_section(self) -> List[str]:
        """Generate section for praisonai wrapper package."""
        lines = [
            "# Wrapper (praisonai)",
            "",
            "Types:",
            "```python",
        ]
        
        imports = sorted(self.wrapper_symbols.keys())
        lines.append(f"from praisonai import {', '.join(imports)}")
        lines.append("```")
        lines.append("")
        
        return lines
    
    def _generate_cli_section(self) -> List[str]:
        """Generate CLI commands section."""
        lines = [
            "# CLI",
            "",
            "Methods:",
            "",
        ]
        
        # Sort and deduplicate commands
        seen = set()
        for cmd in sorted(self.cli_commands, key=lambda c: c.command_path):
            if cmd.command_path in seen:
                continue
            seen.add(cmd.command_path)
            lines.append(
                f'* <code title="cli">{cmd.command_path} '
                f'<a href="{cmd.file_path}">--help</a></code>'
            )
        
        lines.append("")
        return lines
    
    def _generate_ts_section(self) -> List[str]:
        """Generate TypeScript exports section."""
        lines = [
            "# TypeScript",
            "",
            "Types/Exports:",
            "```ts",
        ]
        
        # Group by source file
        by_source: Dict[str, List[TSExport]] = {}
        for export in self.ts_exports:
            if export.source_file not in by_source:
                by_source[export.source_file] = []
            by_source[export.source_file].append(export)
        
        for source in sorted(by_source.keys()):
            exports = by_source[source]
            regular = [e.name for e in exports if not e.is_type]
            types = [e.name for e in exports if e.is_type]
            
            if regular:
                lines.append(f'export {{ {", ".join(sorted(regular))} }} from "{source}";')
            if types:
                lines.append(f'export type {{ {", ".join(sorted(types))} }} from "{source}";')
        
        lines.append("```")
        lines.append("")
        return lines
    
    def _generate_plugins_section(self) -> List[str]:
        """Generate optional plugins section."""
        return [
            "# Optional Plugins",
            "",
            "External tools are available via `praisonai-tools` package:",
            "",
            "```bash",
            "pip install praisonai-tools",
            "```",
            "",
            "See [PraisonAI-tools](https://github.com/MervinPraison/PraisonAI-tools) for available tools.",
            "",
        ]


def generate_api_md(
    repo_root: Optional[Path] = None,
    output_path: Optional[Path] = None,
    check: bool = False,
    stdout: bool = False
) -> int:
    """
    Generate api.md file.
    
    Args:
        repo_root: Repository root path (auto-detected if None)
        output_path: Output file path (defaults to repo_root/api.md)
        check: If True, check if existing file matches (exit 1 if different)
        stdout: If True, print to stdout instead of writing file
    
    Returns:
        Exit code (0 for success, 1 for check failure)
    """
    generator = ApiMdGenerator(repo_root)
    content = generator.generate()
    
    if stdout:
        print(content)
        return 0
    
    if output_path is None:
        output_path = generator.repo_root / "api.md"
    
    if check:
        if output_path.exists():
            with open(output_path, 'r', encoding='utf-8') as f:
                existing = f.read()
            if existing == content:
                print(f"✓ {output_path} is up to date")
                return 0
            else:
                print(f"✗ {output_path} is out of date")
                print("Run `praisonai docs api-md --write` to regenerate")
                return 1
        else:
            print(f"✗ {output_path} does not exist")
            print("Run `praisonai docs api-md --write` to generate")
            return 1
    
    # Write the file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✓ Generated {output_path}")
    return 0


def main():
    """CLI entry point for the generator."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Generate api.md for PraisonAI"
    )
    parser.add_argument(
        '--write', action='store_true', default=True,
        help='Write api.md file (default)'
    )
    parser.add_argument(
        '--check', action='store_true',
        help='Check if api.md is up to date (exit 1 if not)'
    )
    parser.add_argument(
        '--stdout', action='store_true',
        help='Print to stdout instead of writing file'
    )
    parser.add_argument(
        '--output', '-o', type=Path,
        help='Output file path (default: repo_root/api.md)'
    )
    
    args = parser.parse_args()
    
    exit_code = generate_api_md(
        output_path=args.output,
        check=args.check,
        stdout=args.stdout
    )
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
