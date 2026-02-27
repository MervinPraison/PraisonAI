"""
AST-Grep Tool for PraisonAI Agents.

Provides AST-based structural code search and rewrite capabilities
using the ast-grep (sg) CLI tool. Gracefully handles cases where
ast-grep is not installed.

Features:
- Structural code search using AST patterns
- Structural code rewrite (dry-run by default)
- YAML rule scanning
- Graceful fallback when not installed
- Zero performance impact when not used (lazy loading)

Installation:
    pip install ast-grep-cli

Usage:
    from praisonaiagents import Agent
    from praisonaiagents.tools import ast_grep_search
    
    agent = Agent(
        name="coder",
        tools=[ast_grep_search],
    )
"""

import shutil
import subprocess
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)

# Availability cache for performance (checked once per process)
_availability_cache: Optional[bool] = None


def is_ast_grep_available() -> bool:
    """Check if ast-grep (sg) CLI is available.
    
    Returns:
        True if sg binary is found in PATH, False otherwise.
        
    Note:
        Result is cached for performance. First call checks PATH,
        subsequent calls return cached result.
    """
    global _availability_cache
    
    if _availability_cache is not None:
        return _availability_cache
    
    # Check if sg binary is in PATH
    sg_path = shutil.which('sg')
    _availability_cache = sg_path is not None
    
    if _availability_cache:
        logger.debug(f"ast-grep found at: {sg_path}")
    else:
        logger.debug("ast-grep (sg) not found in PATH")
    
    return _availability_cache


def _get_not_installed_message() -> str:
    """Get helpful error message when ast-grep is not installed."""
    return (
        "ast-grep is not installed or not available in PATH.\n\n"
        "To install ast-grep, run:\n"
        "  pip install ast-grep-cli\n\n"
        "Or install via npm:\n"
        "  npm install -g @ast-grep/cli\n\n"
        "For more information, visit: https://ast-grep.github.io/"
    )


def ast_grep_search(
    pattern: str,
    lang: str,
    path: str = ".",
    json_output: bool = True,
) -> str:
    """Search code using AST patterns.
    
    Performs structural code search using ast-grep's pattern matching.
    Unlike regex, this understands code structure and won't match
    patterns in comments or strings.
    
    Args:
        pattern: AST pattern to search for. Use $VAR for single nodes,
            $$$ for multiple nodes. Example: "def $FN($$$)" matches
            all Python function definitions.
        lang: Programming language (python, javascript, typescript,
            rust, go, java, c, cpp, etc.)
        path: Directory or file to search in. Defaults to current directory.
        json_output: Whether to return JSON format. Defaults to True.
        
    Returns:
        Search results as JSON string (if json_output=True) or plain text.
        Returns error message if ast-grep is not installed.
        
    Example:
        # Find all function definitions
        result = ast_grep_search("def $FN($$$)", lang="python", path="./src")
        
        # Find all console.log calls
        result = ast_grep_search("console.log($$$)", lang="javascript")
        
        # Find all async functions
        result = ast_grep_search("async def $FN($$$)", lang="python")
    """
    if not is_ast_grep_available():
        return _get_not_installed_message()
    
    if not pattern:
        return "Error: Pattern cannot be empty"
    
    try:
        cmd = ['sg', '--pattern', pattern, '--lang', lang]
        
        if json_output:
            cmd.append('--json')
        
        cmd.append(path)
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        if result.returncode != 0 and result.stderr:
            return f"Error: {result.stderr}"
        
        output = result.stdout.strip()
        if not output:
            return "No matches found"
        
        return output
        
    except subprocess.TimeoutExpired:
        return "Error: Search timed out after 60 seconds"
    except subprocess.SubprocessError as e:
        return f"Error executing ast-grep: {e}"
    except Exception as e:
        logger.exception("Unexpected error in ast_grep_search")
        return f"Error: {e}"


def ast_grep_rewrite(
    pattern: str,
    replacement: str,
    lang: str,
    path: str = ".",
    dry_run: bool = True,
) -> str:
    """Rewrite code using AST patterns.
    
    Performs structural code transformation using ast-grep's pattern
    matching and rewriting. By default, runs in dry-run mode to show
    what would be changed without modifying files.
    
    Args:
        pattern: AST pattern to match. Use $VAR for single nodes,
            $$$ for multiple nodes.
        replacement: Replacement pattern. Can reference captured
            variables from the pattern.
        lang: Programming language (python, javascript, typescript,
            rust, go, java, c, cpp, etc.)
        path: Directory or file to rewrite. Defaults to current directory.
        dry_run: If True (default), show changes without modifying files.
            Set to False to actually modify files.
            
    Returns:
        Rewrite preview/results as string.
        Returns error message if ast-grep is not installed.
        
    Example:
        # Preview renaming a function (dry run)
        result = ast_grep_rewrite(
            "def old_name($$$)",
            "def new_name($$$)",
            lang="python",
            path="./src"
        )
        
        # Actually apply the rewrite
        result = ast_grep_rewrite(
            "console.log($MSG)",
            "logger.info($MSG)",
            lang="javascript",
            dry_run=False
        )
    """
    if not is_ast_grep_available():
        return _get_not_installed_message()
    
    if not pattern:
        return "Error: Pattern cannot be empty"
    
    if not replacement:
        return "Error: Replacement cannot be empty"
    
    try:
        cmd = [
            'sg', '--pattern', pattern,
            '--rewrite', replacement,
            '--lang', lang,
        ]
        
        if not dry_run:
            cmd.append('--update-all')
        
        cmd.append(path)
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        
        if result.returncode != 0 and result.stderr:
            return f"Error: {result.stderr}"
        
        output = result.stdout.strip()
        if not output:
            if dry_run:
                return "No matches found for rewrite"
            else:
                return "No changes made"
        
        prefix = "[DRY RUN] " if dry_run else ""
        return f"{prefix}{output}"
        
    except subprocess.TimeoutExpired:
        return "Error: Rewrite timed out after 120 seconds"
    except subprocess.SubprocessError as e:
        return f"Error executing ast-grep: {e}"
    except Exception as e:
        logger.exception("Unexpected error in ast_grep_rewrite")
        return f"Error: {e}"


def ast_grep_scan(
    path: str = ".",
    rule_file: Optional[str] = None,
) -> str:
    """Scan code using YAML lint rules.
    
    Runs ast-grep's rule-based scanning to find code patterns
    defined in YAML rule files. Useful for enforcing coding
    standards and finding anti-patterns.
    
    Args:
        path: Directory or file to scan. Defaults to current directory.
        rule_file: Optional path to a specific YAML rule file.
            If not provided, looks for sgconfig.yml in the path.
            
    Returns:
        Scan results as string.
        Returns error message if ast-grep is not installed.
        
    Example:
        # Scan with default rules
        result = ast_grep_scan(path="./src")
        
        # Scan with specific rule file
        result = ast_grep_scan(
            path="./src",
            rule_file="./rules/security.yml"
        )
    """
    if not is_ast_grep_available():
        return _get_not_installed_message()
    
    try:
        cmd = ['sg', 'scan']
        
        if rule_file:
            cmd.extend(['--rule', rule_file])
        
        cmd.append(path)
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        
        # scan returns non-zero if issues found, which is expected
        output = result.stdout.strip()
        if result.stderr and not output:
            return f"Error: {result.stderr}"
        
        if not output:
            return "No issues found"
        
        return output
        
    except subprocess.TimeoutExpired:
        return "Error: Scan timed out after 120 seconds"
    except subprocess.SubprocessError as e:
        return f"Error executing ast-grep: {e}"
    except Exception as e:
        logger.exception("Unexpected error in ast_grep_scan")
        return f"Error: {e}"


# Convenience function to get all ast-grep tools
def get_ast_grep_tools() -> List:
    """Get all ast-grep tools as a list.
    
    Returns:
        List of ast-grep tool functions.
        
    Example:
        from praisonaiagents import Agent
        from praisonaiagents.tools.ast_grep_tool import get_ast_grep_tools
        
        agent = Agent(
            name="coder",
            tools=get_ast_grep_tools(),
        )
    """
    return [ast_grep_search, ast_grep_rewrite, ast_grep_scan]


__all__ = [
    'is_ast_grep_available',
    'ast_grep_search',
    'ast_grep_rewrite',
    'ast_grep_scan',
    'get_ast_grep_tools',
]
