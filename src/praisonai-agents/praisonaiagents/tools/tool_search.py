"""
Tool Search - Progressive disclosure layer for MCP and non-core plugin tools.

Implements Hermes-parity bridge tools with lazy-loaded implementation:
- tool_search(query) → matches
- tool_describe(name) → full schema  
- tool_call(name, args) → unwrap → execute_tool(real_name)

Architecture invariants (ported from Hermes):
1. Core tools never defer - PRAISONAI_CORE_TOOLS
2. Unknown tools stay visible - never silently dropped
3. Stateless catalog - rebuilt every assembly from current tool-defs
4. skip_assembly for bridge dispatch - handlers read pre-assembly deferrable set
5. Session scoping - catalog = deferrable subset of agent's own tool list
6. Unwrap before trace/stream - hooks, approval, AG-UI show real tool name
7. Auto threshold - deferrable schema tokens ≥ threshold_pct * context_length
8. BM25 inlined - no new dependency; substring fallback on tool name
"""

import re
import math
from typing import Dict, List, Optional, Union, Protocol, Set, FrozenSet, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict

# Type definitions matching Hermes patterns
ToolDef = Dict[str, Any]  # OpenAI function schema
ToolDefList = List[ToolDef]

# Core tools that never defer (mirrors Hermes _HERMES_CORE_TOOLS)
PRAISONAI_CORE_TOOLS: FrozenSet[str] = frozenset({
    # File operations
    "read_file", "write_file", "list_files", "get_file_info", 
    "copy_file", "move_file", "delete_file",
    
    # Shell operations  
    "execute_command", "list_processes", "kill_process", "get_system_info",
    
    # Web operations
    "search_web", "web_search", "internet_search", "web_crawl", "crawl_web",
    
    # Schedule operations (agent-centric scheduling)
    "schedule_add", "schedule_list", "schedule_remove",
    
    # Memory operations (active memory)
    "store_memory", "search_memory",
    
    # Clarify tool (human-in-the-loop clarification)
    "clarify",
})

@dataclass
class ToolSearchConfig:
    """Configuration for Tool Search feature."""
    enabled: Union[bool, str] = "auto"  # auto | on | off | True | False
    threshold_pct: float = 10.0  # Percentage of context window for deferral threshold
    search_default_limit: int = 5  # Default number of search results
    max_search_limit: int = 20  # Maximum search results allowed
    core_tools: Optional[FrozenSet[str]] = None  # Override core tools set
    
    @classmethod
    def from_raw(cls, raw_config: Any) -> "ToolSearchConfig":
        """Create config from various input formats (bool, dict, ToolSearchConfig)."""
        if isinstance(raw_config, cls):
            return raw_config
        elif isinstance(raw_config, bool):
            return cls(enabled="on" if raw_config else "off")
        elif isinstance(raw_config, str):
            if raw_config.lower() in ("true", "on", "yes", "1"):
                return cls(enabled="on")
            elif raw_config.lower() in ("false", "off", "no", "0"):
                return cls(enabled="off") 
            elif raw_config.lower() == "auto":
                return cls(enabled="auto")
            else:
                raise ValueError(f"Invalid tool_search string value: {raw_config}")
        elif isinstance(raw_config, dict):
            return cls(**raw_config)
        else:
            raise TypeError(f"Invalid tool_search type: {type(raw_config)}")

class ToolSearchProtocol(Protocol):
    """Protocol for tool search implementations."""
    
    def search_catalog(self, query: str, limit: int = 5) -> List[Dict[str, str]]:
        """Search for tools matching the query."""
        ...
        
    def describe_tool(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get full schema for a specific tool."""
        ...
        
    def resolve_underlying_call(self, tool_name: str, tool_args: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Unwrap bridge call to real tool name and args."""
        ...

def classify_tools(tool_defs: ToolDefList, config: ToolSearchConfig) -> Tuple[ToolDefList, ToolDefList]:
    """
    Classify tools into core (never defer) vs deferrable.
    
    Args:
        tool_defs: List of OpenAI function schemas
        config: Tool search configuration
        
    Returns:
        Tuple of (core_tools, deferrable_tools)
    """
    core_tools = []
    deferrable_tools = []
    
    # Use configured core tools or default
    core_tool_names = config.core_tools or PRAISONAI_CORE_TOOLS
    
    for tool_def in tool_defs:
        tool_name = tool_def.get("function", {}).get("name", "")
        
        # Check if it's a core tool
        if tool_name in core_tool_names:
            core_tools.append(tool_def)
            continue
            
        # Check for deferrable marker from MCP or custom tools
        if _is_tool_deferrable(tool_def):
            deferrable_tools.append(tool_def)
        else:
            # Unknown tools stay visible (invariant #2)
            core_tools.append(tool_def)
    
    return core_tools, deferrable_tools

def _is_tool_deferrable(tool_def: ToolDef) -> bool:
    """Check if a tool should be deferred based on markers."""
    # Check for MCP deferrable marker
    if tool_def.get("__praisonai_deferrable__", False):
        return True
        
    # Check function metadata for deferrable flag
    function_def = tool_def.get("function", {})
    if function_def.get("deferrable", False):
        return True
        
    # Check tool name patterns for MCP tools
    tool_name = function_def.get("name", "")
    if tool_name.startswith("mcp_") or "mcp" in tool_name.lower():
        return True
        
    return False

def estimate_tool_schema_tokens(tool_defs: ToolDefList) -> int:
    """
    Estimate token count for tool schemas.
    
    Rough approximation: 1 token ≈ 4 characters for English text.
    Function schemas are structured JSON so may be more dense.
    """
    if not tool_defs:
        return 0
        
    # Convert to JSON and estimate
    import json
    total_chars = 0
    for tool_def in tool_defs:
        try:
            json_str = json.dumps(tool_def, separators=(',', ':'))
            total_chars += len(json_str)
        except (TypeError, ValueError):
            # Fallback estimation
            total_chars += len(str(tool_def))
    
    # Conservative estimate: 1 token per 3.5 characters for JSON
    return int(total_chars / 3.5)

def should_defer_tools(
    deferrable_tools: ToolDefList, 
    config: ToolSearchConfig,
    context_length: Optional[int] = None
) -> bool:
    """
    Determine if tools should be deferred based on auto threshold.
    
    Args:
        deferrable_tools: List of deferrable tool schemas
        config: Tool search configuration  
        context_length: Model context window size
        
    Returns:
        True if tools should be deferred
    """
    if config.enabled == "off" or config.enabled is False:
        return False
    elif config.enabled == "on" or config.enabled is True:
        return True
    elif config.enabled == "auto":
        # Auto mode: check threshold
        if not deferrable_tools:
            return False
            
        deferrable_tokens = estimate_tool_schema_tokens(deferrable_tools)
        
        # Use fallback if context length unknown
        context_limit = context_length or 20000
        threshold_tokens = int(context_limit * (config.threshold_pct / 100.0))
        
        return deferrable_tokens >= threshold_tokens
    else:
        return False

class BM25ToolSearcher:
    """
    Simple BM25 implementation for tool search.
    No external dependencies - inlined from Hermes approach.
    """
    
    def __init__(self, tool_catalog: List[Dict[str, str]]):
        """
        Initialize with tool catalog.
        
        Args:
            tool_catalog: List of dicts with 'name', 'description' keys
        """
        self.catalog = tool_catalog
        self.term_frequencies = []
        self.doc_frequencies = defaultdict(int)
        self.total_docs = len(tool_catalog)
        
        # Preprocess documents
        self._build_index()
    
    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization - lowercase, alphanumeric + underscores."""
        if not text:
            return []
        return re.findall(r'\b[a-zA-Z0-9_]+\b', text.lower())
    
    def _build_index(self):
        """Build BM25 index from catalog."""
        # Calculate term frequencies for each document
        for item in self.catalog:
            doc_text = f"{item['name']} {item['description']}"
            tokens = self._tokenize(doc_text)
            
            # Term frequency for this doc
            tf = defaultdict(int)
            for token in tokens:
                tf[token] += 1
                
            self.term_frequencies.append(dict(tf))
            
            # Document frequency (how many docs contain each term)
            unique_tokens = set(tokens)
            for token in unique_tokens:
                self.doc_frequencies[token] += 1
    
    def search(self, query: str, limit: int = 5) -> List[Dict[str, str]]:
        """
        Search using BM25 scoring.
        
        Args:
            query: Search query string
            limit: Maximum results to return
            
        Returns:
            List of matching tool items, sorted by relevance
        """
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []
        
        scores = []
        k1, b = 1.5, 0.75  # BM25 parameters
        
        for i, (item, tf) in enumerate(zip(self.catalog, self.term_frequencies)):
            score = 0.0
            doc_length = sum(tf.values())
            
            for token in query_tokens:
                if token in tf:
                    # BM25 formula
                    idf = math.log((self.total_docs - self.doc_frequencies[token] + 0.5) / 
                                 (self.doc_frequencies[token] + 0.5))
                    term_freq = tf[token]
                    score += idf * (term_freq * (k1 + 1)) / (
                        term_freq + k1 * (1 - b + b * (doc_length / self._avg_doc_length()))
                    )
            
            if score > 0:
                scores.append((score, item))
        
        # Sort by score descending and return top results
        scores.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scores[:limit]]
    
    def _avg_doc_length(self) -> float:
        """Calculate average document length."""
        if not self.term_frequencies:
            return 0.0
        total_length = sum(sum(tf.values()) for tf in self.term_frequencies)
        return total_length / len(self.term_frequencies)

def search_catalog(
    deferrable_tools: ToolDefList, 
    query: str, 
    limit: int = 5
) -> List[Dict[str, str]]:
    """
    Search deferrable tools catalog using BM25.
    
    Args:
        deferrable_tools: List of deferrable tool schemas
        query: Search query
        limit: Maximum results
        
    Returns:
        List of matching tools with name/description
    """
    if not deferrable_tools or not query.strip():
        return []
    
    # Build catalog for searching
    catalog = []
    for tool_def in deferrable_tools:
        function_def = tool_def.get("function", {})
        name = function_def.get("name", "")
        description = function_def.get("description", "")
        
        if name:  # Only include tools with names
            catalog.append({
                "name": name,
                "description": description
            })
    
    if not catalog:
        return []
    
    # Use BM25 search if query is substantial, otherwise substring fallback
    if len(query.strip()) >= 3:
        searcher = BM25ToolSearcher(catalog)
        results = searcher.search(query, limit)
        
        # If BM25 finds results, use them
        if results:
            return results
    
    # Fallback: simple substring matching on tool names
    query_lower = query.lower()
    matches = []
    for item in catalog:
        if query_lower in item["name"].lower() or query_lower in item["description"].lower():
            matches.append(item)
            if len(matches) >= limit:
                break
                
    return matches

def bridge_tool_schemas() -> ToolDefList:
    """
    Generate the three bridge tool schemas.
    
    Returns:
        List of OpenAI function schemas for bridge tools
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "tool_search",
                "description": "Search for available tools by name or functionality. Use this to discover what tools are available before using them.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query describing the tool functionality you need"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results to return",
                            "default": 5,
                            "minimum": 1,
                            "maximum": 20
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function", 
            "function": {
                "name": "tool_describe",
                "description": "Get the full schema and documentation for a specific tool. Use this after tool_search to understand how to use a tool.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tool_name": {
                            "type": "string",
                            "description": "Exact name of the tool to describe"
                        }
                    },
                    "required": ["tool_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "tool_call", 
                "description": "Execute a tool with the given arguments. Use this after tool_describe to actually run the tool.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tool_name": {
                            "type": "string",
                            "description": "Exact name of the tool to execute"
                        },
                        "tool_args": {
                            "type": "object", 
                            "description": "Arguments to pass to the tool",
                            "additionalProperties": True
                        }
                    },
                    "required": ["tool_name", "tool_args"]
                }
            }
        }
    ]

def assemble_tool_defs(
    tool_defs: ToolDefList,
    config: ToolSearchConfig, 
    context_length: Optional[int] = None
) -> Tuple[ToolDefList, Dict[str, Any]]:
    """
    Main assembly function - decide whether to use bridge mode or pass-through.
    
    Args:
        tool_defs: Original list of tool schemas
        config: Tool search configuration
        context_length: Model context window size
        
    Returns:
        Tuple of (assembled_tool_defs, metadata)
        metadata contains: {"bridge_mode": bool, "deferred_count": int, "catalog": List}
    """
    # Always return original tools if disabled
    if config.enabled == "off" or config.enabled is False:
        return tool_defs, {"bridge_mode": False, "deferred_count": 0, "catalog": []}
    
    # Classify tools
    core_tools, deferrable_tools = classify_tools(tool_defs, config)
    
    # Check if we should defer
    should_defer = should_defer_tools(deferrable_tools, config, context_length)
    
    if not should_defer or not deferrable_tools:
        # Pass-through mode - return original tools
        return tool_defs, {"bridge_mode": False, "deferred_count": 0, "catalog": []}
    
    # Bridge mode - replace deferrable tools with bridge schemas
    bridge_schemas = bridge_tool_schemas()
    assembled_tools = core_tools + bridge_schemas
    
    # Build catalog for search
    catalog = []
    for tool_def in deferrable_tools:
        function_def = tool_def.get("function", {})
        name = function_def.get("name", "")
        description = function_def.get("description", "")
        if name:
            catalog.append({"name": name, "description": description})
    
    metadata = {
        "bridge_mode": True,
        "deferred_count": len(deferrable_tools), 
        "catalog": catalog,
        "deferrable_tools": deferrable_tools  # Keep full schemas for describe/call
    }
    
    return assembled_tools, metadata

def dispatch_tool_search(
    query: str, 
    limit: Optional[int],
    deferrable_tools: ToolDefList,
    config: ToolSearchConfig
) -> Dict[str, Any]:
    """
    Handle tool_search bridge call.
    
    Returns:
        JSON response with search results
    """
    # Validate and clamp limit
    search_limit = limit or config.search_default_limit
    search_limit = min(search_limit, config.max_search_limit)
    search_limit = max(search_limit, 1)
    
    # Perform search
    results = search_catalog(deferrable_tools, query, search_limit)
    
    return {
        "query": query,
        "results": results,
        "total_available": len(deferrable_tools)
    }

def dispatch_tool_describe(
    tool_name: str,
    deferrable_tools: ToolDefList
) -> Dict[str, Any]:
    """
    Handle tool_describe bridge call.
    
    Returns:
        JSON response with full tool schema or error
    """
    # Find the tool
    for tool_def in deferrable_tools:
        function_def = tool_def.get("function", {})
        if function_def.get("name") == tool_name:
            return {
                "tool_name": tool_name,
                "schema": tool_def,
                "found": True
            }
    
    return {
        "tool_name": tool_name,
        "error": f"Tool '{tool_name}' not found in available tools",
        "found": False
    }

def resolve_underlying_call(tool_name: str, tool_args: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """
    Unwrap tool_call bridge to get real tool name and args.
    
    Args:
        tool_name: Should be "tool_call"
        tool_args: Dict with "tool_name" and "tool_args" keys
        
    Returns:
        Tuple of (real_tool_name, real_args)
    """
    if tool_name != "tool_call":
        # Not a bridge call, return as-is
        return tool_name, tool_args
    
    # Extract real tool call from bridge args
    real_tool_name = tool_args.get("tool_name", "")
    real_args = tool_args.get("tool_args", {})
    
    if not real_tool_name:
        raise ValueError("tool_call requires 'tool_name' parameter")
    
    return real_tool_name, real_args

def scoped_deferrable_names(agent_tool_list: List[str], deferrable_tools: ToolDefList) -> Set[str]:
    """
    Get names of deferrable tools that are in the agent's enabled tool list.
    Implements session scoping (invariant #5).
    
    Args:
        agent_tool_list: List of tool names available to this agent
        deferrable_tools: Full list of deferrable tool schemas
        
    Returns:
        Set of tool names that are both deferrable and enabled for this agent
    """
    agent_tool_set = set(agent_tool_list)
    deferrable_names = set()
    
    for tool_def in deferrable_tools:
        function_def = tool_def.get("function", {})
        tool_name = function_def.get("name", "")
        if tool_name and tool_name in agent_tool_set:
            deferrable_names.add(tool_name)
    
    return deferrable_names