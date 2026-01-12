"""
Code Intelligence Router for PraisonAI.

Routes code-related queries to LSP when available, with fallback to grep/file search.
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .interactive_runtime import InteractiveRuntime

logger = logging.getLogger(__name__)


class CodeIntent(Enum):
    """Classification of code-related intents."""
    LIST_SYMBOLS = "list_symbols"
    GO_TO_DEFINITION = "go_to_definition"
    FIND_REFERENCES = "find_references"
    GET_DIAGNOSTICS = "get_diagnostics"
    EXPLAIN_CODE = "explain_code"
    SEARCH_CODE = "search_code"
    UNKNOWN = "unknown"


@dataclass
class CodeQueryResult:
    """Result of a code intelligence query."""
    intent: CodeIntent
    success: bool
    lsp_used: bool
    data: Any = None
    citations: List[Dict[str, Any]] = None
    error: Optional[str] = None
    fallback_used: bool = False
    
    def __post_init__(self):
        if self.citations is None:
            self.citations = []
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent.value,
            "success": self.success,
            "lsp_used": self.lsp_used,
            "data": self.data,
            "citations": self.citations,
            "error": self.error,
            "fallback_used": self.fallback_used
        }


class CodeIntelligenceRouter:
    """
    Routes code intelligence queries to LSP or fallback mechanisms.
    
    LSP-first approach:
    - If LSP is available, use it for semantic queries
    - If LSP fails or unavailable, fall back to grep/file search
    - Always provide citations with file:line references
    """
    
    # Patterns for intent classification
    INTENT_PATTERNS = {
        CodeIntent.LIST_SYMBOLS: [
            r"list\s+(all\s+)?(functions?|classes?|methods?|symbols?)",
            r"what\s+(functions?|classes?|methods?)\s+(are|exist)",
            r"show\s+(me\s+)?(all\s+)?(functions?|classes?|symbols?)",
            r"find\s+(all\s+)?(functions?|classes?|methods?)",
        ],
        CodeIntent.GO_TO_DEFINITION: [
            r"(go\s+to|find|show|where\s+is)\s+(the\s+)?definition",
            r"where\s+is\s+(\w+)\s+defined",
            r"definition\s+of\s+(\w+)",
            r"(\w+)\s+is\s+defined\s+where",
        ],
        CodeIntent.FIND_REFERENCES: [
            r"(find|show|list)\s+(all\s+)?references",
            r"where\s+is\s+(\w+)\s+used",
            r"usages?\s+of\s+(\w+)",
            r"who\s+(calls?|uses?)\s+(\w+)",
        ],
        CodeIntent.GET_DIAGNOSTICS: [
            r"(show|list|get)\s+(all\s+)?(errors?|warnings?|diagnostics?|problems?)",
            r"what('s|\s+is)\s+wrong",
            r"any\s+(errors?|issues?|problems?)",
            r"check\s+(for\s+)?(errors?|issues?)",
        ],
        CodeIntent.EXPLAIN_CODE: [
            r"explain\s+(this|the)\s+code",
            r"what\s+does\s+(this|the)\s+code\s+do",
            r"how\s+does\s+(\w+)\s+work",
        ],
        CodeIntent.SEARCH_CODE: [
            r"search\s+(for\s+)?",
            r"find\s+(the\s+)?string",
            r"grep\s+",
        ],
    }
    
    def __init__(self, runtime: "InteractiveRuntime"):
        """Initialize with runtime reference."""
        self.runtime = runtime
    
    def classify_intent(self, query: str) -> CodeIntent:
        """Classify the intent of a code query."""
        query_lower = query.lower()
        
        for intent, patterns in self.INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    return intent
        
        return CodeIntent.UNKNOWN
    
    async def handle_query(self, query: str, file_path: str = None) -> CodeQueryResult:
        """
        Handle a code intelligence query.
        
        Args:
            query: The user's query
            file_path: Optional file path context
            
        Returns:
            CodeQueryResult with data and citations
        """
        intent = self.classify_intent(query)
        
        if intent == CodeIntent.LIST_SYMBOLS:
            return await self._handle_list_symbols(query, file_path)
        elif intent == CodeIntent.GO_TO_DEFINITION:
            return await self._handle_go_to_definition(query, file_path)
        elif intent == CodeIntent.FIND_REFERENCES:
            return await self._handle_find_references(query, file_path)
        elif intent == CodeIntent.GET_DIAGNOSTICS:
            return await self._handle_get_diagnostics(query, file_path)
        elif intent == CodeIntent.SEARCH_CODE:
            return await self._handle_search_code(query, file_path)
        else:
            return CodeQueryResult(
                intent=intent,
                success=False,
                lsp_used=False,
                error="Could not determine code query intent"
            )
    
    async def _handle_list_symbols(self, query: str, file_path: str = None) -> CodeQueryResult:
        """Handle list symbols query."""
        if not file_path:
            # Try to find a file from the query
            file_path = self._extract_file_from_query(query)
        
        if not file_path:
            return CodeQueryResult(
                intent=CodeIntent.LIST_SYMBOLS,
                success=False,
                lsp_used=False,
                error="No file specified. Please specify a file path."
            )
        
        # Try LSP first
        if self.runtime.lsp_ready:
            try:
                symbols = await self.runtime.lsp_get_symbols(file_path)
                if symbols:
                    citations = [
                        {"file": file_path, "type": "symbols", "count": len(symbols)}
                    ]
                    return CodeQueryResult(
                        intent=CodeIntent.LIST_SYMBOLS,
                        success=True,
                        lsp_used=True,
                        data=symbols,
                        citations=citations
                    )
            except Exception as e:
                logger.warning(f"LSP symbols failed: {e}")
        
        # Fallback to regex-based symbol extraction
        return await self._fallback_list_symbols(file_path)
    
    async def _fallback_list_symbols(self, file_path: str) -> CodeQueryResult:
        """Fallback symbol listing using regex."""
        try:
            path = Path(file_path)
            if not path.exists():
                path = Path(self.runtime.config.workspace) / file_path
            
            if not path.exists():
                return CodeQueryResult(
                    intent=CodeIntent.LIST_SYMBOLS,
                    success=False,
                    lsp_used=False,
                    fallback_used=True,
                    error=f"File not found: {file_path}"
                )
            
            content = path.read_text()
            symbols = []
            
            # Python patterns
            if path.suffix == ".py":
                # Functions
                for match in re.finditer(r'^(async\s+)?def\s+(\w+)\s*\(', content, re.MULTILINE):
                    line_num = content[:match.start()].count('\n') + 1
                    symbols.append({
                        "name": match.group(2),
                        "kind": "function",
                        "line": line_num
                    })
                # Classes
                for match in re.finditer(r'^class\s+(\w+)\s*[:\(]', content, re.MULTILINE):
                    line_num = content[:match.start()].count('\n') + 1
                    symbols.append({
                        "name": match.group(1),
                        "kind": "class",
                        "line": line_num
                    })
            
            # JavaScript/TypeScript patterns
            elif path.suffix in [".js", ".ts", ".jsx", ".tsx"]:
                # Functions
                for match in re.finditer(r'(?:async\s+)?function\s+(\w+)\s*\(', content):
                    line_num = content[:match.start()].count('\n') + 1
                    symbols.append({
                        "name": match.group(1),
                        "kind": "function",
                        "line": line_num
                    })
                # Arrow functions assigned to const/let/var
                for match in re.finditer(r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(', content):
                    line_num = content[:match.start()].count('\n') + 1
                    symbols.append({
                        "name": match.group(1),
                        "kind": "function",
                        "line": line_num
                    })
                # Classes
                for match in re.finditer(r'class\s+(\w+)\s*(?:extends|implements|{)', content):
                    line_num = content[:match.start()].count('\n') + 1
                    symbols.append({
                        "name": match.group(1),
                        "kind": "class",
                        "line": line_num
                    })
            
            citations = [
                {"file": str(path), "type": "symbols", "count": len(symbols)}
            ]
            
            return CodeQueryResult(
                intent=CodeIntent.LIST_SYMBOLS,
                success=True,
                lsp_used=False,
                fallback_used=True,
                data=symbols,
                citations=citations
            )
            
        except Exception as e:
            return CodeQueryResult(
                intent=CodeIntent.LIST_SYMBOLS,
                success=False,
                lsp_used=False,
                fallback_used=True,
                error=str(e)
            )
    
    async def _handle_go_to_definition(self, query: str, file_path: str = None) -> CodeQueryResult:
        """Handle go to definition query."""
        # Extract symbol name from query
        symbol = self._extract_symbol_from_query(query)
        
        if not symbol:
            return CodeQueryResult(
                intent=CodeIntent.GO_TO_DEFINITION,
                success=False,
                lsp_used=False,
                error="Could not identify symbol to find definition for"
            )
        
        if not file_path:
            file_path = self._extract_file_from_query(query)
        
        # Try LSP first
        if self.runtime.lsp_ready and file_path:
            try:
                # Need to find the symbol position first
                line, col = await self._find_symbol_position(file_path, symbol)
                if line is not None:
                    definitions = await self.runtime.lsp_get_definition(file_path, line, col)
                    if definitions:
                        citations = [
                            {"file": d.get("uri", "").replace("file://", ""), 
                             "line": d.get("range", {}).get("start", {}).get("line", 0) + 1,
                             "type": "definition"}
                            for d in definitions
                        ]
                        return CodeQueryResult(
                            intent=CodeIntent.GO_TO_DEFINITION,
                            success=True,
                            lsp_used=True,
                            data={"symbol": symbol, "definitions": definitions},
                            citations=citations
                        )
            except Exception as e:
                logger.warning(f"LSP definition failed: {e}")
        
        # Fallback to grep
        return await self._fallback_find_definition(symbol)
    
    async def _fallback_find_definition(self, symbol: str) -> CodeQueryResult:
        """Fallback definition finding using grep."""
        try:
            import subprocess
            workspace = self.runtime.config.workspace
            
            # Search for definition patterns
            patterns = [
                f"def {symbol}\\s*\\(",  # Python function
                f"class {symbol}\\s*[:\\(]",  # Python class
                f"function {symbol}\\s*\\(",  # JS function
                f"const {symbol}\\s*=",  # JS const
                f"let {symbol}\\s*=",  # JS let
            ]
            
            results = []
            for pattern in patterns:
                try:
                    result = subprocess.run(
                        ["grep", "-rn", "-E", pattern, workspace],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.stdout:
                        for line in result.stdout.strip().split('\n'):
                            if line:
                                parts = line.split(':', 2)
                                if len(parts) >= 2:
                                    results.append({
                                        "file": parts[0],
                                        "line": int(parts[1]),
                                        "content": parts[2] if len(parts) > 2 else ""
                                    })
                except subprocess.TimeoutExpired:
                    pass
            
            if results:
                citations = [
                    {"file": r["file"], "line": r["line"], "type": "definition"}
                    for r in results
                ]
                return CodeQueryResult(
                    intent=CodeIntent.GO_TO_DEFINITION,
                    success=True,
                    lsp_used=False,
                    fallback_used=True,
                    data={"symbol": symbol, "definitions": results},
                    citations=citations
                )
            
            return CodeQueryResult(
                intent=CodeIntent.GO_TO_DEFINITION,
                success=False,
                lsp_used=False,
                fallback_used=True,
                error=f"Definition for '{symbol}' not found"
            )
            
        except Exception as e:
            return CodeQueryResult(
                intent=CodeIntent.GO_TO_DEFINITION,
                success=False,
                lsp_used=False,
                fallback_used=True,
                error=str(e)
            )
    
    async def _handle_find_references(self, query: str, file_path: str = None) -> CodeQueryResult:
        """Handle find references query."""
        symbol = self._extract_symbol_from_query(query)
        
        if not symbol:
            return CodeQueryResult(
                intent=CodeIntent.FIND_REFERENCES,
                success=False,
                lsp_used=False,
                error="Could not identify symbol to find references for"
            )
        
        if not file_path:
            file_path = self._extract_file_from_query(query)
        
        # Try LSP first
        if self.runtime.lsp_ready and file_path:
            try:
                line, col = await self._find_symbol_position(file_path, symbol)
                if line is not None:
                    references = await self.runtime.lsp_get_references(file_path, line, col)
                    if references:
                        citations = [
                            {"file": r.get("uri", "").replace("file://", ""),
                             "line": r.get("range", {}).get("start", {}).get("line", 0) + 1,
                             "type": "reference"}
                            for r in references
                        ]
                        return CodeQueryResult(
                            intent=CodeIntent.FIND_REFERENCES,
                            success=True,
                            lsp_used=True,
                            data={"symbol": symbol, "references": references},
                            citations=citations
                        )
            except Exception as e:
                logger.warning(f"LSP references failed: {e}")
        
        # Fallback to grep
        return await self._fallback_find_references(symbol)
    
    async def _fallback_find_references(self, symbol: str) -> CodeQueryResult:
        """Fallback reference finding using grep."""
        try:
            import subprocess
            workspace = self.runtime.config.workspace
            
            result = subprocess.run(
                ["grep", "-rn", "-w", symbol, workspace],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            results = []
            if result.stdout:
                for line in result.stdout.strip().split('\n'):
                    if line:
                        parts = line.split(':', 2)
                        if len(parts) >= 2:
                            results.append({
                                "file": parts[0],
                                "line": int(parts[1]),
                                "content": parts[2] if len(parts) > 2 else ""
                            })
            
            if results:
                citations = [
                    {"file": r["file"], "line": r["line"], "type": "reference"}
                    for r in results
                ]
                return CodeQueryResult(
                    intent=CodeIntent.FIND_REFERENCES,
                    success=True,
                    lsp_used=False,
                    fallback_used=True,
                    data={"symbol": symbol, "references": results},
                    citations=citations
                )
            
            return CodeQueryResult(
                intent=CodeIntent.FIND_REFERENCES,
                success=False,
                lsp_used=False,
                fallback_used=True,
                error=f"No references found for '{symbol}'"
            )
            
        except Exception as e:
            return CodeQueryResult(
                intent=CodeIntent.FIND_REFERENCES,
                success=False,
                lsp_used=False,
                fallback_used=True,
                error=str(e)
            )
    
    async def _handle_get_diagnostics(self, query: str, file_path: str = None) -> CodeQueryResult:
        """Handle get diagnostics query."""
        if not file_path:
            file_path = self._extract_file_from_query(query)
        
        # Try LSP
        if self.runtime.lsp_ready:
            try:
                diagnostics = await self.runtime.lsp_get_diagnostics(file_path)
                citations = []
                if diagnostics:
                    for d in diagnostics:
                        if isinstance(d, dict):
                            citations.append({
                                "file": file_path or "workspace",
                                "line": d.get("range", {}).get("start", {}).get("line", 0) + 1,
                                "type": "diagnostic",
                                "severity": d.get("severity", "unknown")
                            })
                
                return CodeQueryResult(
                    intent=CodeIntent.GET_DIAGNOSTICS,
                    success=True,
                    lsp_used=True,
                    data=diagnostics,
                    citations=citations
                )
            except Exception as e:
                logger.warning(f"LSP diagnostics failed: {e}")
        
        return CodeQueryResult(
            intent=CodeIntent.GET_DIAGNOSTICS,
            success=False,
            lsp_used=False,
            error="LSP not available for diagnostics"
        )
    
    async def _handle_search_code(self, query: str, file_path: str = None) -> CodeQueryResult:
        """Handle code search query."""
        # Extract search term
        search_term = self._extract_search_term(query)
        
        if not search_term:
            return CodeQueryResult(
                intent=CodeIntent.SEARCH_CODE,
                success=False,
                lsp_used=False,
                error="Could not identify search term"
            )
        
        try:
            import subprocess
            workspace = self.runtime.config.workspace
            
            cmd = ["grep", "-rn", search_term]
            if file_path:
                cmd.append(file_path)
            else:
                cmd.append(workspace)
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            results = []
            if result.stdout:
                for line in result.stdout.strip().split('\n')[:50]:  # Limit results
                    if line:
                        parts = line.split(':', 2)
                        if len(parts) >= 2:
                            results.append({
                                "file": parts[0],
                                "line": int(parts[1]),
                                "content": parts[2] if len(parts) > 2 else ""
                            })
            
            citations = [
                {"file": r["file"], "line": r["line"], "type": "search_result"}
                for r in results
            ]
            
            return CodeQueryResult(
                intent=CodeIntent.SEARCH_CODE,
                success=True,
                lsp_used=False,
                data={"search_term": search_term, "results": results},
                citations=citations
            )
            
        except Exception as e:
            return CodeQueryResult(
                intent=CodeIntent.SEARCH_CODE,
                success=False,
                lsp_used=False,
                error=str(e)
            )
    
    def _extract_file_from_query(self, query: str) -> Optional[str]:
        """Extract file path from query."""
        # Look for file patterns
        patterns = [
            r'(?:in|from|file)\s+["\']?([^\s"\']+\.\w+)["\']?',
            r'([^\s]+\.(?:py|js|ts|tsx|jsx|go|rs|java|cpp|c|h))',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    def _extract_symbol_from_query(self, query: str) -> Optional[str]:
        """Extract symbol name from query."""
        # Common patterns for symbol extraction (order matters - more specific first)
        patterns = [
            # "find all references to X" - capture X after "to"
            r'references?\s+to\s+["\']?(\w+)["\']?',
            # "definition of X" - capture X after "of"
            r'definition\s+of\s+["\']?(\w+)["\']?',
            # "where is X defined/used"
            r'where\s+is\s+["\']?(\w+)["\']?\s+(?:defined|used)',
            # Quoted or backticked symbols
            r'["\'](\w+)["\']',
            r'`(\w+)`',
            # "X is defined/used"
            r'(\w+)\s+(?:is\s+)?(?:defined|used)',
            # Generic "find/show X" - but filter common words
            r'(?:find|show)\s+["\']?(\w+)["\']?',
        ]
        
        # Words to filter out
        filter_words = {'the', 'a', 'an', 'is', 'are', 'in', 'of', 'to', 'for', 
                       'all', 'any', 'some', 'this', 'that', 'where', 'what',
                       'definition', 'references', 'reference', 'symbol', 'symbols'}
        
        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                symbol = match.group(1)
                # Filter out common words
                if symbol.lower() not in filter_words:
                    return symbol
        
        return None
    
    def _extract_search_term(self, query: str) -> Optional[str]:
        """Extract search term from query."""
        patterns = [
            r'search\s+(?:for\s+)?["\']([^"\']+)["\']',
            r'find\s+["\']([^"\']+)["\']',
            r'grep\s+["\']?([^\s"\']+)["\']?',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    async def _find_symbol_position(self, file_path: str, symbol: str) -> tuple:
        """Find the position of a symbol in a file."""
        try:
            path = Path(file_path)
            if not path.exists():
                path = Path(self.runtime.config.workspace) / file_path
            
            if not path.exists():
                return None, None
            
            content = path.read_text()
            lines = content.split('\n')
            
            for i, line in enumerate(lines):
                col = line.find(symbol)
                if col >= 0:
                    return i, col
            
            return None, None
        except Exception:
            return None, None
