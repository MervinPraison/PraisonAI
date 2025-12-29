"""
Tools checks for the Doctor CLI module.

Validates tool availability, dependencies, and API keys.
"""

import os

from ..models import (
    CheckCategory,
    CheckResult,
    CheckStatus,
    CheckSeverity,
    DoctorConfig,
)
from ..registry import register_check


# Tool categories and their requirements
TOOL_CATEGORIES = {
    "web_search": {
        "tools": ["internet_search", "duckduckgo", "tavily_search", "exa_search", "searxng_search"],
        "description": "Web search tools",
    },
    "file_ops": {
        "tools": ["read_file", "write_file", "list_files", "file_tools"],
        "description": "File operation tools",
    },
    "data": {
        "tools": ["csv_tools", "json_tools", "excel_tools", "xml_tools", "yaml_tools", "pandas_tools"],
        "description": "Data processing tools",
    },
    "database": {
        "tools": ["duckdb_tools", "mongodb_tools"],
        "description": "Database tools",
    },
    "code": {
        "tools": ["python_tools", "shell_tools", "execute_code"],
        "description": "Code execution tools",
    },
    "web_crawl": {
        "tools": ["crawl4ai", "spider_tools", "newspaper_tools"],
        "description": "Web crawling tools",
    },
    "knowledge": {
        "tools": ["wiki_search", "arxiv_tools", "wikipedia_tools"],
        "description": "Knowledge/research tools",
    },
    "finance": {
        "tools": ["yfinance", "get_stock_price", "get_stock_info"],
        "description": "Financial data tools",
    },
}

# Tools that require API keys
TOOLS_REQUIRING_API_KEYS = {
    "tavily_search": "TAVILY_API_KEY",
    "tavily": "TAVILY_API_KEY",
    "exa_search": "EXA_API_KEY",
    "exa": "EXA_API_KEY",
    "ydc_search": "YDC_API_KEY",
    "ydc": "YDC_API_KEY",
}

# Tools that require optional dependencies
TOOLS_REQUIRING_DEPS = {
    "crawl4ai": "crawl4ai",
    "tavily_search": "tavily",
    "tavily": "tavily",
    "pandas_tools": "pandas",
    "excel_tools": "openpyxl",
    "yfinance": "yfinance",
    "duckdb_tools": "duckdb",
    "mongodb_tools": "pymongo",
    "newspaper_tools": "newspaper3k",
    "arxiv_tools": "arxiv",
}


@register_check(
    id="tools_registry",
    title="Tools Registry",
    description="Check tool registry is accessible",
    category=CheckCategory.TOOLS,
    severity=CheckSeverity.MEDIUM,
)
def check_tools_registry(config: DoctorConfig) -> CheckResult:
    """Check tool registry is accessible."""
    try:
        from praisonaiagents.tools import TOOL_MAPPINGS
        tool_count = len(TOOL_MAPPINGS)
        
        return CheckResult(
            id="tools_registry",
            title="Tools Registry",
            category=CheckCategory.TOOLS,
            status=CheckStatus.PASS,
            message=f"Tool registry accessible with {tool_count} tools",
            metadata={"tool_count": tool_count},
        )
    except ImportError as e:
        return CheckResult(
            id="tools_registry",
            title="Tools Registry",
            category=CheckCategory.TOOLS,
            status=CheckStatus.FAIL,
            message="Cannot access tool registry",
            details=str(e),
            remediation="Ensure praisonaiagents is properly installed",
            severity=CheckSeverity.HIGH,
        )


@register_check(
    id="tools_web_search",
    title="Web Search Tools",
    description="Check web search tool availability",
    category=CheckCategory.TOOLS,
    severity=CheckSeverity.MEDIUM,
)
def check_tools_web_search(config: DoctorConfig) -> CheckResult:
    """Check web search tool availability."""
    available = []
    missing = []
    
    # Check DuckDuckGo (no API key required)
    try:
        from praisonaiagents.tools import internet_search
        available.append("internet_search (DuckDuckGo)")
    except ImportError:
        missing.append("internet_search")
    
    # Check Tavily
    if os.environ.get("TAVILY_API_KEY"):
        try:
            from praisonaiagents.tools import tavily_search
            available.append("tavily_search")
        except ImportError:
            missing.append("tavily_search (missing tavily package)")
    else:
        missing.append("tavily_search (TAVILY_API_KEY not set)")
    
    # Check Exa
    if os.environ.get("EXA_API_KEY"):
        try:
            from praisonaiagents.tools import exa_search
            available.append("exa_search")
        except ImportError:
            missing.append("exa_search (missing exa package)")
    else:
        missing.append("exa_search (EXA_API_KEY not set)")
    
    if available:
        return CheckResult(
            id="tools_web_search",
            title="Web Search Tools",
            category=CheckCategory.TOOLS,
            status=CheckStatus.PASS,
            message=f"{len(available)} web search tool(s) available",
            details=", ".join(available),
            metadata={"available": available, "missing": missing},
        )
    else:
        return CheckResult(
            id="tools_web_search",
            title="Web Search Tools",
            category=CheckCategory.TOOLS,
            status=CheckStatus.WARN,
            message="No web search tools available",
            details=", ".join(missing),
            remediation="Install duckduckgo-search or set TAVILY_API_KEY",
        )


@register_check(
    id="tools_file_ops",
    title="File Operation Tools",
    description="Check file operation tool availability",
    category=CheckCategory.TOOLS,
    severity=CheckSeverity.LOW,
)
def check_tools_file_ops(config: DoctorConfig) -> CheckResult:
    """Check file operation tool availability."""
    try:
        from praisonaiagents.tools import read_file, write_file, list_files
        return CheckResult(
            id="tools_file_ops",
            title="File Operation Tools",
            category=CheckCategory.TOOLS,
            status=CheckStatus.PASS,
            message="File operation tools available (read_file, write_file, list_files)",
        )
    except ImportError as e:
        return CheckResult(
            id="tools_file_ops",
            title="File Operation Tools",
            category=CheckCategory.TOOLS,
            status=CheckStatus.WARN,
            message="Some file operation tools not available",
            details=str(e),
        )


@register_check(
    id="tools_code_execution",
    title="Code Execution Tools",
    description="Check code execution tool availability",
    category=CheckCategory.TOOLS,
    severity=CheckSeverity.LOW,
)
def check_tools_code_execution(config: DoctorConfig) -> CheckResult:
    """Check code execution tool availability."""
    available = []
    
    try:
        from praisonaiagents.tools import execute_code
        available.append("execute_code")
    except ImportError:
        pass
    
    try:
        from praisonaiagents.tools import execute_command
        available.append("execute_command")
    except ImportError:
        pass
    
    if available:
        return CheckResult(
            id="tools_code_execution",
            title="Code Execution Tools",
            category=CheckCategory.TOOLS,
            status=CheckStatus.PASS,
            message=f"Code execution tools available: {', '.join(available)}",
            metadata={"available": available},
        )
    else:
        return CheckResult(
            id="tools_code_execution",
            title="Code Execution Tools",
            category=CheckCategory.TOOLS,
            status=CheckStatus.SKIP,
            message="Code execution tools not loaded (optional)",
        )


@register_check(
    id="tools_api_keys",
    title="Tool API Keys",
    description="Check API keys for tools that require them",
    category=CheckCategory.TOOLS,
    severity=CheckSeverity.INFO,
)
def check_tools_api_keys(config: DoctorConfig) -> CheckResult:
    """Check API keys for tools that require them."""
    configured = []
    missing = []
    
    api_keys = {
        "TAVILY_API_KEY": "Tavily search",
        "EXA_API_KEY": "Exa search",
        "YDC_API_KEY": "You.com search",
        "SPIDER_API_KEY": "Spider web crawling",
    }
    
    for key, description in api_keys.items():
        if os.environ.get(key):
            configured.append(description)
        else:
            missing.append(f"{description} ({key})")
    
    if configured:
        return CheckResult(
            id="tools_api_keys",
            title="Tool API Keys",
            category=CheckCategory.TOOLS,
            status=CheckStatus.PASS,
            message=f"{len(configured)} tool API key(s) configured",
            details=f"Configured: {', '.join(configured)}",
            metadata={"configured": configured, "missing": missing},
        )
    else:
        return CheckResult(
            id="tools_api_keys",
            title="Tool API Keys",
            category=CheckCategory.TOOLS,
            status=CheckStatus.SKIP,
            message="No optional tool API keys configured",
            details="Tools like Tavily, Exa require API keys for enhanced functionality",
        )


@register_check(
    id="tools_optional_deps",
    title="Tool Optional Dependencies",
    description="Check optional dependencies for tools",
    category=CheckCategory.TOOLS,
    severity=CheckSeverity.INFO,
    requires_deep=True,
)
def check_tools_optional_deps(config: DoctorConfig) -> CheckResult:
    """Check optional dependencies for tools."""
    available = []
    missing = []
    
    deps_to_check = [
        ("crawl4ai", "Crawl4AI web crawling"),
        ("tavily", "Tavily search"),
        ("pandas", "Pandas data tools"),
        ("openpyxl", "Excel tools"),
        ("yfinance", "Yahoo Finance tools"),
        ("duckdb", "DuckDB tools"),
        ("pymongo", "MongoDB tools"),
        ("arxiv", "arXiv tools"),
    ]
    
    for package, description in deps_to_check:
        try:
            __import__(package)
            available.append(description)
        except ImportError:
            missing.append(f"{description} ({package})")
    
    total = len(deps_to_check)
    
    return CheckResult(
        id="tools_optional_deps",
        title="Tool Optional Dependencies",
        category=CheckCategory.TOOLS,
        status=CheckStatus.PASS,
        message=f"{len(available)}/{total} optional tool dependencies installed",
        details=f"Missing: {', '.join(missing[:3])}{'...' if len(missing) > 3 else ''}" if missing else "All installed",
        metadata={"available": available, "missing": missing},
    )


@register_check(
    id="tools_summary",
    title="Tools Summary",
    description="Summary of tool availability by category",
    category=CheckCategory.TOOLS,
    severity=CheckSeverity.INFO,
)
def check_tools_summary(config: DoctorConfig) -> CheckResult:
    """Summary of tool availability by category."""
    try:
        from praisonaiagents.tools import TOOL_MAPPINGS
        
        category_counts = {}
        for cat_name, cat_info in TOOL_CATEGORIES.items():
            available = sum(1 for t in cat_info["tools"] if t in TOOL_MAPPINGS)
            total = len(cat_info["tools"])
            category_counts[cat_name] = f"{available}/{total}"
        
        summary = ", ".join(f"{k}: {v}" for k, v in category_counts.items())
        
        return CheckResult(
            id="tools_summary",
            title="Tools Summary",
            category=CheckCategory.TOOLS,
            status=CheckStatus.PASS,
            message=f"Tool categories: {summary}",
            metadata={"categories": category_counts},
        )
    except ImportError:
        return CheckResult(
            id="tools_summary",
            title="Tools Summary",
            category=CheckCategory.TOOLS,
            status=CheckStatus.SKIP,
            message="Cannot generate tools summary",
        )
