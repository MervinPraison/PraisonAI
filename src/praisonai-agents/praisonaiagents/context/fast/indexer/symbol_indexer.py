"""
Symbol Indexer for Fast Context.

Extracts code symbols from source files:
- Python: functions, classes, imports
- JavaScript/TypeScript: functions, classes, imports, exports
- Go: functions, types, imports
- Rust: functions, structs, impl blocks, use statements
- Java: classes, methods, imports
"""

import os
import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)


class SymbolType(Enum):
    """Types of code symbols."""
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    IMPORT = "import"
    EXPORT = "export"
    VARIABLE = "variable"
    CONSTANT = "constant"
    TYPE = "type"
    STRUCT = "struct"
    INTERFACE = "interface"
    MODULE = "module"


@dataclass
class Symbol:
    """Represents a code symbol.
    
    Attributes:
        name: Symbol name
        symbol_type: Type of symbol
        file_path: File containing the symbol
        line_number: Line number (1-indexed)
        end_line: End line number (for multi-line symbols)
        signature: Full signature (for functions/methods)
        parent: Parent symbol name (for methods)
        docstring: Documentation string if available
    """
    name: str
    symbol_type: SymbolType
    file_path: str
    line_number: int
    end_line: Optional[int] = None
    signature: Optional[str] = None
    parent: Optional[str] = None
    docstring: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "type": self.symbol_type.value,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "end_line": self.end_line,
            "signature": self.signature,
            "parent": self.parent,
            "docstring": self.docstring
        }


class LanguageParser:
    """Base class for language-specific parsers."""
    
    def parse(self, content: str, file_path: str) -> List[Symbol]:
        """Parse content and extract symbols.
        
        Args:
            content: File content
            file_path: Path to the file
            
        Returns:
            List of extracted symbols
        """
        raise NotImplementedError


class PythonParser(LanguageParser):
    """Parser for Python files."""
    
    # Regex patterns for Python
    FUNCTION_PATTERN = re.compile(
        r'^(\s*)def\s+(\w+)\s*\((.*?)\)\s*(?:->.*?)?:',
        re.MULTILINE
    )
    CLASS_PATTERN = re.compile(
        r'^(\s*)class\s+(\w+)\s*(?:\((.*?)\))?:',
        re.MULTILINE
    )
    IMPORT_PATTERN = re.compile(
        r'^(?:from\s+(\S+)\s+)?import\s+(.+)$',
        re.MULTILINE
    )
    ASYNC_FUNCTION_PATTERN = re.compile(
        r'^(\s*)async\s+def\s+(\w+)\s*\((.*?)\)\s*(?:->.*?)?:',
        re.MULTILINE
    )
    
    def parse(self, content: str, file_path: str) -> List[Symbol]:
        symbols = []
        lines = content.split('\n')
        
        # Track class context for methods
        current_class = None
        class_indent = 0
        
        # Parse classes
        for match in self.CLASS_PATTERN.finditer(content):
            indent = len(match.group(1))
            name = match.group(2)
            bases = match.group(3) or ""
            line_num = content[:match.start()].count('\n') + 1
            
            symbols.append(Symbol(
                name=name,
                symbol_type=SymbolType.CLASS,
                file_path=file_path,
                line_number=line_num,
                signature=f"class {name}({bases})" if bases else f"class {name}"
            ))
        
        # Parse functions (including async)
        for pattern in [self.FUNCTION_PATTERN, self.ASYNC_FUNCTION_PATTERN]:
            for match in pattern.finditer(content):
                indent = len(match.group(1))
                name = match.group(2)
                params = match.group(3)
                line_num = content[:match.start()].count('\n') + 1
                
                # Determine if it's a method (inside a class)
                is_method = indent > 0
                parent = None
                
                if is_method:
                    # Find parent class
                    for sym in symbols:
                        if sym.symbol_type == SymbolType.CLASS:
                            if sym.line_number < line_num:
                                parent = sym.name
                
                symbol_type = SymbolType.METHOD if is_method else SymbolType.FUNCTION
                is_async = "async" in match.group(0)
                prefix = "async def" if is_async else "def"
                
                symbols.append(Symbol(
                    name=name,
                    symbol_type=symbol_type,
                    file_path=file_path,
                    line_number=line_num,
                    signature=f"{prefix} {name}({params})",
                    parent=parent
                ))
        
        # Parse imports
        for match in self.IMPORT_PATTERN.finditer(content):
            from_module = match.group(1)
            imports = match.group(2)
            line_num = content[:match.start()].count('\n') + 1
            
            if from_module:
                sig = f"from {from_module} import {imports}"
            else:
                sig = f"import {imports}"
            
            symbols.append(Symbol(
                name=imports.split(',')[0].strip().split(' ')[0],
                symbol_type=SymbolType.IMPORT,
                file_path=file_path,
                line_number=line_num,
                signature=sig
            ))
        
        return symbols


class JavaScriptParser(LanguageParser):
    """Parser for JavaScript/TypeScript files."""
    
    FUNCTION_PATTERN = re.compile(
        r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\((.*?)\)',
        re.MULTILINE
    )
    ARROW_FUNCTION_PATTERN = re.compile(
        r'(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\((.*?)\)\s*=>',
        re.MULTILINE
    )
    CLASS_PATTERN = re.compile(
        r'(?:export\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?',
        re.MULTILINE
    )
    IMPORT_PATTERN = re.compile(
        r'import\s+(?:{([^}]+)}|(\w+))\s+from\s+[\'"]([^\'"]+)[\'"]',
        re.MULTILINE
    )
    EXPORT_PATTERN = re.compile(
        r'export\s+(?:default\s+)?(?:const|let|var|function|class)\s+(\w+)',
        re.MULTILINE
    )
    
    def parse(self, content: str, file_path: str) -> List[Symbol]:
        symbols = []
        
        # Parse functions
        for match in self.FUNCTION_PATTERN.finditer(content):
            name = match.group(1)
            params = match.group(2)
            line_num = content[:match.start()].count('\n') + 1
            
            symbols.append(Symbol(
                name=name,
                symbol_type=SymbolType.FUNCTION,
                file_path=file_path,
                line_number=line_num,
                signature=f"function {name}({params})"
            ))
        
        # Parse arrow functions
        for match in self.ARROW_FUNCTION_PATTERN.finditer(content):
            name = match.group(1)
            params = match.group(2)
            line_num = content[:match.start()].count('\n') + 1
            
            symbols.append(Symbol(
                name=name,
                symbol_type=SymbolType.FUNCTION,
                file_path=file_path,
                line_number=line_num,
                signature=f"const {name} = ({params}) =>"
            ))
        
        # Parse classes
        for match in self.CLASS_PATTERN.finditer(content):
            name = match.group(1)
            extends = match.group(2)
            line_num = content[:match.start()].count('\n') + 1
            
            sig = f"class {name}"
            if extends:
                sig += f" extends {extends}"
            
            symbols.append(Symbol(
                name=name,
                symbol_type=SymbolType.CLASS,
                file_path=file_path,
                line_number=line_num,
                signature=sig
            ))
        
        # Parse imports
        for match in self.IMPORT_PATTERN.finditer(content):
            named = match.group(1)
            default = match.group(2)
            module = match.group(3)
            line_num = content[:match.start()].count('\n') + 1
            
            name = default or (named.split(',')[0].strip() if named else module)
            
            symbols.append(Symbol(
                name=name,
                symbol_type=SymbolType.IMPORT,
                file_path=file_path,
                line_number=line_num,
                signature=f"import from '{module}'"
            ))
        
        # Parse exports
        for match in self.EXPORT_PATTERN.finditer(content):
            name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            
            symbols.append(Symbol(
                name=name,
                symbol_type=SymbolType.EXPORT,
                file_path=file_path,
                line_number=line_num,
                signature=f"export {name}"
            ))
        
        return symbols


class GoParser(LanguageParser):
    """Parser for Go files."""
    
    FUNCTION_PATTERN = re.compile(
        r'^func\s+(?:\((\w+)\s+\*?(\w+)\)\s+)?(\w+)\s*\((.*?)\)',
        re.MULTILINE
    )
    TYPE_PATTERN = re.compile(
        r'^type\s+(\w+)\s+(struct|interface)',
        re.MULTILINE
    )
    IMPORT_PATTERN = re.compile(
        r'import\s+(?:\(\s*([\s\S]*?)\s*\)|"([^"]+)")',
        re.MULTILINE
    )
    
    def parse(self, content: str, file_path: str) -> List[Symbol]:
        symbols = []
        
        # Parse functions
        for match in self.FUNCTION_PATTERN.finditer(content):
            receiver_name = match.group(1)
            receiver_type = match.group(2)
            name = match.group(3)
            params = match.group(4)
            line_num = content[:match.start()].count('\n') + 1
            
            if receiver_type:
                # Method
                symbols.append(Symbol(
                    name=name,
                    symbol_type=SymbolType.METHOD,
                    file_path=file_path,
                    line_number=line_num,
                    signature=f"func ({receiver_name} {receiver_type}) {name}({params})",
                    parent=receiver_type
                ))
            else:
                # Function
                symbols.append(Symbol(
                    name=name,
                    symbol_type=SymbolType.FUNCTION,
                    file_path=file_path,
                    line_number=line_num,
                    signature=f"func {name}({params})"
                ))
        
        # Parse types
        for match in self.TYPE_PATTERN.finditer(content):
            name = match.group(1)
            kind = match.group(2)
            line_num = content[:match.start()].count('\n') + 1
            
            symbol_type = SymbolType.STRUCT if kind == "struct" else SymbolType.INTERFACE
            
            symbols.append(Symbol(
                name=name,
                symbol_type=symbol_type,
                file_path=file_path,
                line_number=line_num,
                signature=f"type {name} {kind}"
            ))
        
        return symbols


class RustParser(LanguageParser):
    """Parser for Rust files."""
    
    FUNCTION_PATTERN = re.compile(
        r'^(\s*)(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*(?:<[^>]*>)?\s*\((.*?)\)',
        re.MULTILINE
    )
    STRUCT_PATTERN = re.compile(
        r'^(?:pub\s+)?struct\s+(\w+)',
        re.MULTILINE
    )
    IMPL_PATTERN = re.compile(
        r'^impl(?:<[^>]*>)?\s+(?:(\w+)\s+for\s+)?(\w+)',
        re.MULTILINE
    )
    USE_PATTERN = re.compile(
        r'^use\s+(.+);',
        re.MULTILINE
    )
    
    def parse(self, content: str, file_path: str) -> List[Symbol]:
        symbols = []
        
        # Parse functions
        for match in self.FUNCTION_PATTERN.finditer(content):
            indent = len(match.group(1))
            name = match.group(2)
            params = match.group(3)
            line_num = content[:match.start()].count('\n') + 1
            
            is_method = indent > 0
            symbol_type = SymbolType.METHOD if is_method else SymbolType.FUNCTION
            
            symbols.append(Symbol(
                name=name,
                symbol_type=symbol_type,
                file_path=file_path,
                line_number=line_num,
                signature=f"fn {name}({params})"
            ))
        
        # Parse structs
        for match in self.STRUCT_PATTERN.finditer(content):
            name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            
            symbols.append(Symbol(
                name=name,
                symbol_type=SymbolType.STRUCT,
                file_path=file_path,
                line_number=line_num,
                signature=f"struct {name}"
            ))
        
        # Parse impl blocks
        for match in self.IMPL_PATTERN.finditer(content):
            trait_name = match.group(1)
            type_name = match.group(2)
            line_num = content[:match.start()].count('\n') + 1
            
            if trait_name:
                sig = f"impl {trait_name} for {type_name}"
            else:
                sig = f"impl {type_name}"
            
            symbols.append(Symbol(
                name=type_name,
                symbol_type=SymbolType.TYPE,
                file_path=file_path,
                line_number=line_num,
                signature=sig
            ))
        
        return symbols


class JavaParser(LanguageParser):
    """Parser for Java files."""
    
    CLASS_PATTERN = re.compile(
        r'(?:public\s+)?(?:abstract\s+)?(?:final\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+([^{]+))?',
        re.MULTILINE
    )
    METHOD_PATTERN = re.compile(
        r'(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?(?:\w+(?:<[^>]+>)?)\s+(\w+)\s*\((.*?)\)',
        re.MULTILINE
    )
    IMPORT_PATTERN = re.compile(
        r'^import\s+(?:static\s+)?([^;]+);',
        re.MULTILINE
    )
    
    def parse(self, content: str, file_path: str) -> List[Symbol]:
        symbols = []
        
        # Parse classes
        for match in self.CLASS_PATTERN.finditer(content):
            name = match.group(1)
            extends = match.group(2)
            implements = match.group(3)
            line_num = content[:match.start()].count('\n') + 1
            
            sig = f"class {name}"
            if extends:
                sig += f" extends {extends}"
            if implements:
                sig += f" implements {implements.strip()}"
            
            symbols.append(Symbol(
                name=name,
                symbol_type=SymbolType.CLASS,
                file_path=file_path,
                line_number=line_num,
                signature=sig
            ))
        
        # Parse methods
        for match in self.METHOD_PATTERN.finditer(content):
            name = match.group(1)
            params = match.group(2)
            line_num = content[:match.start()].count('\n') + 1
            
            # Skip constructors and common keywords
            if name in ('if', 'while', 'for', 'switch', 'catch'):
                continue
            
            symbols.append(Symbol(
                name=name,
                symbol_type=SymbolType.METHOD,
                file_path=file_path,
                line_number=line_num,
                signature=f"{name}({params})"
            ))
        
        # Parse imports
        for match in self.IMPORT_PATTERN.finditer(content):
            import_path = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            
            # Get the last part of the import
            name = import_path.split('.')[-1]
            
            symbols.append(Symbol(
                name=name,
                symbol_type=SymbolType.IMPORT,
                file_path=file_path,
                line_number=line_num,
                signature=f"import {import_path}"
            ))
        
        return symbols


class SymbolIndexer:
    """Indexes code symbols from source files.
    
    Supports multiple languages:
    - Python (.py)
    - JavaScript (.js, .jsx)
    - TypeScript (.ts, .tsx)
    - Go (.go)
    - Rust (.rs)
    - Java (.java)
    """
    
    # Map file extensions to parsers
    PARSERS = {
        '.py': PythonParser,
        '.js': JavaScriptParser,
        '.jsx': JavaScriptParser,
        '.ts': JavaScriptParser,
        '.tsx': JavaScriptParser,
        '.go': GoParser,
        '.rs': RustParser,
        '.java': JavaParser,
    }
    
    def __init__(self, workspace_path: str):
        """Initialize symbol indexer.
        
        Args:
            workspace_path: Root directory to index
        """
        self.workspace_path = os.path.abspath(workspace_path)
        self.symbols: Dict[str, List[Symbol]] = {}  # file_path -> symbols
        self.by_name: Dict[str, List[Symbol]] = {}  # symbol_name -> symbols
        self.by_type: Dict[SymbolType, List[Symbol]] = {}  # type -> symbols
        
        # Initialize parsers
        self._parsers = {ext: parser() for ext, parser in self.PARSERS.items()}
    
    def index_file(self, file_path: str) -> List[Symbol]:
        """Index symbols from a single file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            List of extracted symbols
        """
        ext = os.path.splitext(file_path)[1].lower()
        parser = self._parsers.get(ext)
        
        if not parser:
            return []
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            rel_path = os.path.relpath(file_path, self.workspace_path)
            symbols = parser.parse(content, rel_path)
            
            # Store in indexes
            self.symbols[rel_path] = symbols
            
            for sym in symbols:
                # By name
                if sym.name not in self.by_name:
                    self.by_name[sym.name] = []
                self.by_name[sym.name].append(sym)
                
                # By type
                if sym.symbol_type not in self.by_type:
                    self.by_type[sym.symbol_type] = []
                self.by_type[sym.symbol_type].append(sym)
            
            return symbols
        except Exception as e:
            logger.debug(f"Error indexing {file_path}: {e}")
            return []
    
    def index(self) -> int:
        """Index all supported files in workspace.
        
        Returns:
            Total number of symbols indexed
        """
        total_symbols = 0
        
        for root, dirs, files in os.walk(self.workspace_path):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for filename in files:
                ext = os.path.splitext(filename)[1].lower()
                if ext in self.PARSERS:
                    file_path = os.path.join(root, filename)
                    symbols = self.index_file(file_path)
                    total_symbols += len(symbols)
        
        logger.info(f"Indexed {total_symbols} symbols from {len(self.symbols)} files")
        return total_symbols
    
    def find_by_name(self, name: str, exact: bool = False) -> List[Symbol]:
        """Find symbols by name.
        
        Args:
            name: Symbol name to search
            exact: If True, match exact name
            
        Returns:
            List of matching symbols
        """
        if exact:
            return self.by_name.get(name, [])
        
        results = []
        name_lower = name.lower()
        for sym_name, symbols in self.by_name.items():
            if name_lower in sym_name.lower():
                results.extend(symbols)
        return results
    
    def find_by_type(self, symbol_type: SymbolType) -> List[Symbol]:
        """Find symbols by type.
        
        Args:
            symbol_type: Type of symbol
            
        Returns:
            List of matching symbols
        """
        return self.by_type.get(symbol_type, [])
    
    def find_in_file(self, file_path: str) -> List[Symbol]:
        """Find all symbols in a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            List of symbols in the file
        """
        return self.symbols.get(file_path, [])
    
    def get_stats(self) -> Dict[str, Any]:
        """Get indexer statistics.
        
        Returns:
            Dictionary with stats
        """
        type_counts = {t.value: len(syms) for t, syms in self.by_type.items()}
        
        return {
            "total_files": len(self.symbols),
            "total_symbols": sum(len(s) for s in self.symbols.values()),
            "by_type": type_counts
        }
