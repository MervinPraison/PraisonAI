"""
Repository Map System for PraisonAI CLI.

Inspired by Aider's RepoMap using tree-sitter for code parsing.
Provides intelligent codebase context for LLM interactions.

Architecture:
- RepoMap: Main class for building repository maps
- SymbolExtractor: Extracts symbols using tree-sitter or regex fallback
- SymbolRanker: Ranks symbols by importance using graph analysis
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from pathlib import Path
from collections import defaultdict
import logging
import re

logger = logging.getLogger(__name__)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class Symbol:
    """
    Represents a code symbol (class, function, method, variable).
    """
    name: str
    kind: str  # class, function, method, variable, import
    file_path: str
    line_number: int
    signature: str = ""  # Full signature for functions/methods
    parent: Optional[str] = None  # Parent class for methods
    references: int = 0  # Number of references in codebase
    
    @property
    def qualified_name(self) -> str:
        """Get fully qualified name."""
        if self.parent:
            return f"{self.parent}.{self.name}"
        return self.name
    
    def __hash__(self):
        return hash((self.name, self.kind, self.file_path, self.line_number))


@dataclass
class FileMap:
    """
    Map of symbols in a single file.
    """
    file_path: str
    symbols: List[Symbol] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    
    def add_symbol(self, symbol: Symbol) -> None:
        """Add a symbol to the file map."""
        self.symbols.append(symbol)
    
    def get_summary(self, max_symbols: int = 10) -> str:
        """Get a summary of the file's symbols."""
        lines = [f"{self.file_path}:"]
        
        # Sort by importance (references) and take top symbols
        sorted_symbols = sorted(
            self.symbols,
            key=lambda s: (s.references, s.kind == "class"),
            reverse=True
        )[:max_symbols]
        
        for symbol in sorted_symbols:
            if symbol.signature:
                lines.append(f"  {symbol.signature}")
            else:
                lines.append(f"  {symbol.kind} {symbol.name}")
        
        return "\n".join(lines)


@dataclass
class RepoMapConfig:
    """Configuration for repository mapping."""
    max_tokens: int = 1024
    max_files: int = 50
    max_symbols_per_file: int = 20
    include_imports: bool = True
    include_docstrings: bool = False
    file_extensions: Set[str] = field(default_factory=lambda: {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
        ".cpp", ".c", ".h", ".hpp", ".rb", ".php", ".swift", ".kt"
    })
    exclude_patterns: Set[str] = field(default_factory=lambda: {
        "__pycache__", "node_modules", ".git", ".venv", "venv",
        "build", "dist", ".egg-info", "__init__.py"
    })


# ============================================================================
# Symbol Extraction
# ============================================================================

class SymbolExtractor:
    """
    Extracts symbols from source code.
    
    Uses tree-sitter when available, falls back to regex patterns.
    """
    
    def __init__(self, use_tree_sitter: bool = True):
        self.use_tree_sitter = use_tree_sitter
        self._tree_sitter_available = False
        self._parsers: Dict[str, Any] = {}
        
        if use_tree_sitter:
            self._init_tree_sitter()
    
    def _init_tree_sitter(self) -> None:
        """Initialize tree-sitter if available."""
        try:
            # Try to import tree-sitter-languages (pip installable)
            import tree_sitter_languages
            self._tree_sitter_available = True
            self._ts_languages = tree_sitter_languages
            logger.debug("tree-sitter-languages available")
        except ImportError:
            try:
                # Fallback to tree-sitter with manual language setup
                import tree_sitter
                self._tree_sitter_available = True
                self._tree_sitter = tree_sitter
                logger.debug("tree-sitter available (manual setup required)")
            except ImportError:
                logger.debug("tree-sitter not available, using regex fallback")
                self._tree_sitter_available = False
    
    def extract_symbols(self, file_path: str, content: str) -> List[Symbol]:
        """
        Extract symbols from file content.
        
        Args:
            file_path: Path to the file
            content: File content
            
        Returns:
            List of extracted symbols
        """
        ext = Path(file_path).suffix.lower()
        
        if self._tree_sitter_available:
            try:
                return self._extract_with_tree_sitter(file_path, content, ext)
            except Exception as e:
                logger.debug(f"tree-sitter extraction failed: {e}")
        
        # Fallback to regex
        return self._extract_with_regex(file_path, content, ext)
    
    def _extract_with_tree_sitter(
        self, file_path: str, content: str, ext: str
    ) -> List[Symbol]:
        """Extract symbols using tree-sitter."""
        symbols = []
        
        # Map extension to language
        lang_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".rb": "ruby",
            ".cpp": "cpp",
            ".c": "c",
            ".h": "c",
        }
        
        lang = lang_map.get(ext)
        if not lang:
            return self._extract_with_regex(file_path, content, ext)
        
        try:
            parser = self._ts_languages.get_parser(lang)
            tree = parser.parse(content.encode())
            
            # Extract based on language
            if lang == "python":
                symbols = self._extract_python_symbols(file_path, tree, content)
            else:
                # Generic extraction for other languages
                symbols = self._extract_generic_symbols(file_path, tree, content, lang)
        except Exception as e:
            logger.debug(f"tree-sitter parsing failed for {lang}: {e}")
            return self._extract_with_regex(file_path, content, ext)
        
        return symbols
    
    def _extract_python_symbols(
        self, file_path: str, tree: Any, content: str
    ) -> List[Symbol]:
        """Extract Python symbols from tree-sitter AST."""
        symbols = []
        lines = content.split("\n")
        
        def visit_node(node, parent_class=None):
            if node.type == "class_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    class_name = content[name_node.start_byte:name_node.end_byte]
                    line_num = node.start_point[0] + 1
                    
                    # Get class signature
                    sig_end = node.children[0].end_byte if node.children else node.start_byte + 50
                    signature = content[node.start_byte:sig_end].split("\n")[0]
                    
                    symbols.append(Symbol(
                        name=class_name,
                        kind="class",
                        file_path=file_path,
                        line_number=line_num,
                        signature=signature.strip()
                    ))
                    
                    # Visit children with class context
                    for child in node.children:
                        visit_node(child, class_name)
                    return
            
            elif node.type == "function_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    func_name = content[name_node.start_byte:name_node.end_byte]
                    line_num = node.start_point[0] + 1
                    
                    # Get function signature
                    sig_line = lines[line_num - 1] if line_num <= len(lines) else ""
                    
                    kind = "method" if parent_class else "function"
                    symbols.append(Symbol(
                        name=func_name,
                        kind=kind,
                        file_path=file_path,
                        line_number=line_num,
                        signature=sig_line.strip(),
                        parent=parent_class
                    ))
            
            # Visit children
            for child in node.children:
                visit_node(child, parent_class)
        
        visit_node(tree.root_node)
        return symbols
    
    def _extract_generic_symbols(
        self, file_path: str, tree: Any, content: str, lang: str
    ) -> List[Symbol]:
        """Generic symbol extraction for other languages."""
        symbols = []
        
        # Node types for different languages
        class_types = {"class_definition", "class_declaration", "struct_definition"}
        func_types = {"function_definition", "function_declaration", "method_definition"}
        
        def visit_node(node, parent=None):
            if node.type in class_types:
                name = self._get_node_name(node, content)
                if name:
                    symbols.append(Symbol(
                        name=name,
                        kind="class",
                        file_path=file_path,
                        line_number=node.start_point[0] + 1
                    ))
                    for child in node.children:
                        visit_node(child, name)
                    return
            
            elif node.type in func_types:
                name = self._get_node_name(node, content)
                if name:
                    symbols.append(Symbol(
                        name=name,
                        kind="method" if parent else "function",
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                        parent=parent
                    ))
            
            for child in node.children:
                visit_node(child, parent)
        
        visit_node(tree.root_node)
        return symbols
    
    def _get_node_name(self, node: Any, content: str) -> Optional[str]:
        """Get name from a tree-sitter node."""
        name_node = node.child_by_field_name("name")
        if name_node:
            return content[name_node.start_byte:name_node.end_byte]
        return None
    
    def _extract_with_regex(
        self, file_path: str, content: str, ext: str
    ) -> List[Symbol]:
        """Extract symbols using regex patterns (fallback)."""
        symbols = []
        lines = content.split("\n")
        
        if ext == ".py":
            symbols = self._extract_python_regex(file_path, lines)
        elif ext in {".js", ".ts", ".jsx", ".tsx"}:
            symbols = self._extract_js_regex(file_path, lines)
        elif ext in {".java", ".kt"}:
            symbols = self._extract_java_regex(file_path, lines)
        elif ext == ".go":
            symbols = self._extract_go_regex(file_path, lines)
        elif ext == ".rs":
            symbols = self._extract_rust_regex(file_path, lines)
        else:
            # Generic extraction
            symbols = self._extract_generic_regex(file_path, lines)
        
        return symbols
    
    def _extract_python_regex(self, file_path: str, lines: List[str]) -> List[Symbol]:
        """Extract Python symbols using regex."""
        symbols = []
        current_class = None
        
        class_pattern = re.compile(r'^class\s+(\w+)')
        func_pattern = re.compile(r'^(\s*)def\s+(\w+)\s*\(([^)]*)\)')
        
        for i, line in enumerate(lines):
            line_num = i + 1
            
            # Check for class
            class_match = class_pattern.match(line)
            if class_match:
                current_class = class_match.group(1)
                symbols.append(Symbol(
                    name=current_class,
                    kind="class",
                    file_path=file_path,
                    line_number=line_num,
                    signature=line.strip()
                ))
                continue
            
            # Check for function/method
            func_match = func_pattern.match(line)
            if func_match:
                indent = len(func_match.group(1))
                func_name = func_match.group(2)
                
                # If indented, it's a method
                if indent > 0 and current_class:
                    symbols.append(Symbol(
                        name=func_name,
                        kind="method",
                        file_path=file_path,
                        line_number=line_num,
                        signature=line.strip(),
                        parent=current_class
                    ))
                else:
                    current_class = None  # Reset class context
                    symbols.append(Symbol(
                        name=func_name,
                        kind="function",
                        file_path=file_path,
                        line_number=line_num,
                        signature=line.strip()
                    ))
        
        return symbols
    
    def _extract_js_regex(self, file_path: str, lines: List[str]) -> List[Symbol]:
        """Extract JavaScript/TypeScript symbols using regex."""
        symbols = []
        
        class_pattern = re.compile(r'(?:export\s+)?class\s+(\w+)')
        func_pattern = re.compile(
            r'(?:export\s+)?(?:async\s+)?function\s+(\w+)|'
            r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>'
        )
        
        for i, line in enumerate(lines):
            line_num = i + 1
            
            class_match = class_pattern.search(line)
            if class_match:
                symbols.append(Symbol(
                    name=class_match.group(1),
                    kind="class",
                    file_path=file_path,
                    line_number=line_num,
                    signature=line.strip()[:80]
                ))
            
            func_match = func_pattern.search(line)
            if func_match:
                name = func_match.group(1) or func_match.group(2)
                if name:
                    symbols.append(Symbol(
                        name=name,
                        kind="function",
                        file_path=file_path,
                        line_number=line_num,
                        signature=line.strip()[:80]
                    ))
        
        return symbols
    
    def _extract_java_regex(self, file_path: str, lines: List[str]) -> List[Symbol]:
        """Extract Java/Kotlin symbols using regex."""
        symbols = []
        
        class_pattern = re.compile(
            r'(?:public|private|protected)?\s*(?:static\s+)?'
            r'(?:class|interface|enum)\s+(\w+)'
        )
        method_pattern = re.compile(
            r'(?:public|private|protected)?\s*(?:static\s+)?'
            r'(?:\w+(?:<[^>]+>)?)\s+(\w+)\s*\('
        )
        
        for i, line in enumerate(lines):
            line_num = i + 1
            
            class_match = class_pattern.search(line)
            if class_match:
                symbols.append(Symbol(
                    name=class_match.group(1),
                    kind="class",
                    file_path=file_path,
                    line_number=line_num
                ))
            
            method_match = method_pattern.search(line)
            if method_match and not class_match:
                symbols.append(Symbol(
                    name=method_match.group(1),
                    kind="method",
                    file_path=file_path,
                    line_number=line_num
                ))
        
        return symbols
    
    def _extract_go_regex(self, file_path: str, lines: List[str]) -> List[Symbol]:
        """Extract Go symbols using regex."""
        symbols = []
        
        func_pattern = re.compile(r'^func\s+(?:\([^)]+\)\s+)?(\w+)')
        type_pattern = re.compile(r'^type\s+(\w+)\s+(?:struct|interface)')
        
        for i, line in enumerate(lines):
            line_num = i + 1
            
            type_match = type_pattern.match(line)
            if type_match:
                symbols.append(Symbol(
                    name=type_match.group(1),
                    kind="class",
                    file_path=file_path,
                    line_number=line_num
                ))
            
            func_match = func_pattern.match(line)
            if func_match:
                symbols.append(Symbol(
                    name=func_match.group(1),
                    kind="function",
                    file_path=file_path,
                    line_number=line_num
                ))
        
        return symbols
    
    def _extract_rust_regex(self, file_path: str, lines: List[str]) -> List[Symbol]:
        """Extract Rust symbols using regex."""
        symbols = []
        
        fn_pattern = re.compile(r'(?:pub\s+)?(?:async\s+)?fn\s+(\w+)')
        struct_pattern = re.compile(r'(?:pub\s+)?struct\s+(\w+)')
        
        for i, line in enumerate(lines):
            line_num = i + 1
            
            struct_match = struct_pattern.match(line)
            if struct_match:
                symbols.append(Symbol(
                    name=struct_match.group(1),
                    kind="class",
                    file_path=file_path,
                    line_number=line_num
                ))
            
            fn_match = fn_pattern.search(line)
            if fn_match:
                symbols.append(Symbol(
                    name=fn_match.group(1),
                    kind="function",
                    file_path=file_path,
                    line_number=line_num
                ))
        
        return symbols
    
    def _extract_generic_regex(self, file_path: str, lines: List[str]) -> List[Symbol]:
        """Generic symbol extraction for unknown languages."""
        symbols = []
        
        # Very basic patterns
        class_pattern = re.compile(r'(?:class|struct|interface)\s+(\w+)')
        func_pattern = re.compile(r'(?:function|def|fn|func)\s+(\w+)')
        
        for i, line in enumerate(lines):
            line_num = i + 1
            
            class_match = class_pattern.search(line)
            if class_match:
                symbols.append(Symbol(
                    name=class_match.group(1),
                    kind="class",
                    file_path=file_path,
                    line_number=line_num
                ))
            
            func_match = func_pattern.search(line)
            if func_match:
                symbols.append(Symbol(
                    name=func_match.group(1),
                    kind="function",
                    file_path=file_path,
                    line_number=line_num
                ))
        
        return symbols


# ============================================================================
# Symbol Ranking
# ============================================================================

class SymbolRanker:
    """
    Ranks symbols by importance using reference counting and graph analysis.
    """
    
    def __init__(self):
        self.symbol_refs: Dict[str, int] = defaultdict(int)
        self.file_refs: Dict[str, Set[str]] = defaultdict(set)
    
    def analyze_references(
        self, file_maps: Dict[str, FileMap], all_content: Dict[str, str]
    ) -> None:
        """
        Analyze references between symbols across files.
        
        Args:
            file_maps: Map of file path to FileMap
            all_content: Map of file path to content
        """
        # Build symbol name set
        all_symbols = set()
        for file_map in file_maps.values():
            for symbol in file_map.symbols:
                all_symbols.add(symbol.name)
        
        # Count references
        for file_path, content in all_content.items():
            for symbol_name in all_symbols:
                # Simple word boundary match
                pattern = rf'\b{re.escape(symbol_name)}\b'
                matches = len(re.findall(pattern, content))
                if matches > 0:
                    self.symbol_refs[symbol_name] += matches
                    self.file_refs[file_path].add(symbol_name)
        
        # Update symbol reference counts
        for file_map in file_maps.values():
            for symbol in file_map.symbols:
                symbol.references = self.symbol_refs.get(symbol.name, 0)
    
    def get_top_symbols(
        self, file_maps: Dict[str, FileMap], max_symbols: int = 50
    ) -> List[Symbol]:
        """Get the most important symbols across the codebase."""
        all_symbols = []
        for file_map in file_maps.values():
            all_symbols.extend(file_map.symbols)
        
        # Sort by references and kind priority
        kind_priority = {"class": 3, "function": 2, "method": 1, "variable": 0}
        
        sorted_symbols = sorted(
            all_symbols,
            key=lambda s: (s.references, kind_priority.get(s.kind, 0)),
            reverse=True
        )
        
        return sorted_symbols[:max_symbols]


# ============================================================================
# Repository Map
# ============================================================================

class RepoMap:
    """
    Main class for building repository maps.
    
    Provides intelligent codebase context for LLM interactions.
    """
    
    def __init__(
        self,
        root: Optional[str] = None,
        config: Optional[RepoMapConfig] = None,
        verbose: bool = False
    ):
        self.root = Path(root) if root else Path.cwd()
        self.config = config or RepoMapConfig()
        self.verbose = verbose
        
        self.extractor = SymbolExtractor()
        self.ranker = SymbolRanker()
        
        self._file_maps: Dict[str, FileMap] = {}
        self._all_content: Dict[str, str] = {}
        self._last_map: Optional[str] = None
    
    def scan(self, paths: Optional[List[str]] = None) -> None:
        """
        Scan the repository for symbols.
        
        Args:
            paths: Optional list of specific paths to scan
        """
        if paths:
            files_to_scan = [Path(p) for p in paths]
        else:
            files_to_scan = self._find_files()
        
        for file_path in files_to_scan:
            try:
                self._scan_file(file_path)
            except Exception as e:
                logger.debug(f"Error scanning {file_path}: {e}")
        
        # Analyze references
        self.ranker.analyze_references(self._file_maps, self._all_content)
        
        if self.verbose:
            logger.info(f"Scanned {len(self._file_maps)} files")
    
    def _find_files(self) -> List[Path]:
        """Find all relevant source files in the repository."""
        files = []
        
        for ext in self.config.file_extensions:
            for file_path in self.root.rglob(f"*{ext}"):
                # Check exclusions
                if any(excl in str(file_path) for excl in self.config.exclude_patterns):
                    continue
                files.append(file_path)
        
        return files[:self.config.max_files]
    
    def _scan_file(self, file_path: Path) -> None:
        """Scan a single file for symbols."""
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.debug(f"Could not read {file_path}: {e}")
            return
        
        rel_path = str(file_path.relative_to(self.root))
        self._all_content[rel_path] = content
        
        symbols = self.extractor.extract_symbols(rel_path, content)
        
        file_map = FileMap(file_path=rel_path)
        for symbol in symbols[:self.config.max_symbols_per_file]:
            file_map.add_symbol(symbol)
        
        self._file_maps[rel_path] = file_map
    
    def get_map(
        self,
        focus_files: Optional[List[str]] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Get the repository map as a string.
        
        Args:
            focus_files: Files to prioritize in the map
            max_tokens: Maximum tokens for the map
            
        Returns:
            Formatted repository map string
        """
        if not self._file_maps:
            self.scan()
        
        max_tokens = max_tokens or self.config.max_tokens
        
        # Get top symbols
        top_symbols = self.ranker.get_top_symbols(self._file_maps)
        
        # Group by file
        file_symbols: Dict[str, List[Symbol]] = defaultdict(list)
        for symbol in top_symbols:
            file_symbols[symbol.file_path].append(symbol)
        
        # Prioritize focus files
        if focus_files:
            focus_set = set(focus_files)
            sorted_files = sorted(
                file_symbols.keys(),
                key=lambda f: (f not in focus_set, f)
            )
        else:
            sorted_files = sorted(file_symbols.keys())
        
        # Build map
        lines = []
        estimated_tokens = 0
        
        for file_path in sorted_files:
            symbols = file_symbols[file_path]
            
            file_lines = [f"{file_path}:"]
            for symbol in symbols:
                if symbol.signature:
                    file_lines.append(f"  │{symbol.signature}")
                else:
                    file_lines.append(f"  │{symbol.kind} {symbol.name}")
            file_lines.append("  ⋮...")
            
            file_text = "\n".join(file_lines)
            file_tokens = len(file_text) // 4  # Rough token estimate
            
            if estimated_tokens + file_tokens > max_tokens:
                break
            
            lines.extend(file_lines)
            estimated_tokens += file_tokens
        
        self._last_map = "\n".join(lines)
        return self._last_map
    
    def get_file_symbols(self, file_path: str) -> List[Symbol]:
        """Get symbols for a specific file."""
        if file_path in self._file_maps:
            return self._file_maps[file_path].symbols
        return []
    
    def get_symbol_context(self, symbol_name: str) -> Optional[str]:
        """Get context around a specific symbol."""
        for file_path, file_map in self._file_maps.items():
            for symbol in file_map.symbols:
                if symbol.name == symbol_name:
                    content = self._all_content.get(file_path, "")
                    lines = content.split("\n")
                    
                    # Get lines around the symbol
                    start = max(0, symbol.line_number - 3)
                    end = min(len(lines), symbol.line_number + 10)
                    
                    context_lines = lines[start:end]
                    return f"{file_path}:{symbol.line_number}\n" + "\n".join(context_lines)
        
        return None
    
    def refresh(self) -> None:
        """Refresh the repository map."""
        self._file_maps.clear()
        self._all_content.clear()
        self.ranker = SymbolRanker()
        self.scan()


# ============================================================================
# CLI Integration Handler
# ============================================================================

class RepoMapHandler:
    """
    Handler for integrating RepoMap with PraisonAI CLI.
    """
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._repo_map: Optional[RepoMap] = None
    
    @property
    def feature_name(self) -> str:
        return "repo_map"
    
    def initialize(
        self,
        root: Optional[str] = None,
        config: Optional[RepoMapConfig] = None
    ) -> RepoMap:
        """Initialize the repository map."""
        self._repo_map = RepoMap(
            root=root,
            config=config,
            verbose=self.verbose
        )
        
        if self.verbose:
            from rich import print as rprint
            rprint(f"[cyan]RepoMap initialized for: {self._repo_map.root}[/cyan]")
        
        return self._repo_map
    
    def get_map(self, focus_files: Optional[List[str]] = None) -> str:
        """Get the repository map."""
        if not self._repo_map:
            self._repo_map = self.initialize()
        
        return self._repo_map.get_map(focus_files=focus_files)
    
    def get_context(self, symbol_name: str) -> Optional[str]:
        """Get context for a symbol."""
        if not self._repo_map:
            self._repo_map = self.initialize()
        
        return self._repo_map.get_symbol_context(symbol_name)
    
    def refresh(self) -> None:
        """Refresh the map."""
        if self._repo_map:
            self._repo_map.refresh()
    
    def print_map(self) -> None:
        """Print the repository map."""
        from rich.console import Console
        from rich.panel import Panel
        from rich.syntax import Syntax
        
        console = Console()
        map_str = self.get_map()
        
        console.print(Panel(
            Syntax(map_str, "text", theme="monokai"),
            title="📁 Repository Map",
            border_style="blue"
        ))
