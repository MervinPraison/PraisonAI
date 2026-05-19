"""
Security pre-checks for sandbox code execution.

Provides pre-execution analysis of code for potentially dangerous patterns.
Note: These are warnings only - the sandbox provides the real isolation.
"""

import re
import ast
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass 
class SecurityWarning:
    """A security warning from code analysis."""
    
    pattern: str
    message: str
    severity: str  # "low", "medium", "high", "critical"
    line_number: Optional[int] = None
    context: Optional[str] = None


# Dangerous patterns to detect in code
DANGEROUS_PATTERNS = [
    # System/OS access
    (r"import\s+os\s*;?\s*os\.system", "Direct system command execution via os.system", "high"),
    (r"subprocess\.call.*shell\s*=\s*True", "Shell injection risk with subprocess", "high"),
    (r"subprocess\.run.*shell\s*=\s*True", "Shell injection risk with subprocess", "high"),
    (r"subprocess\.Popen.*shell\s*=\s*True", "Shell injection risk with subprocess", "high"),
    (r"__import__\(['\"]os['\"]\)", "Dynamic import of os module", "medium"),
    (r"eval\s*\(", "Dynamic code execution with eval()", "critical"),
    (r"exec\s*\(", "Dynamic code execution with exec()", "critical"),
    (r"compile\s*\(.*exec", "Code compilation for execution", "high"),
    
    # File system access
    (r"open\s*\(.*['\"]\/etc", "Access to system configuration files", "medium"),
    (r"open\s*\(.*['\"]\/root", "Access to root directory", "high"),
    (r"open\s*\(.*['\"]\/home", "Access to user directories", "medium"),
    (r"shutil\.rmtree", "Recursive directory deletion", "high"),
    (r"os\.remove\s*\(", "File deletion", "medium"),
    (r"os\.unlink\s*\(", "File deletion", "medium"),
    (r"pathlib\.Path.*unlink", "File deletion via pathlib", "medium"),
    
    # Network access
    (r"socket\.socket", "Direct socket creation", "medium"),
    (r"urllib\.request", "HTTP requests via urllib", "low"),
    (r"requests\.", "HTTP requests via requests library", "low"),
    (r"http\.client", "HTTP client usage", "low"),
    
    # Process manipulation
    (r"os\.fork\s*\(", "Process forking", "high"),
    (r"multiprocessing\.", "Multiprocessing usage", "medium"),
    (r"threading\.Thread", "Thread creation", "low"),
    
    # Potentially dangerous builtins
    (r"getattr\s*\(.*__", "Dynamic attribute access to dunder methods", "medium"),
    (r"setattr\s*\(.*__", "Dynamic attribute setting of dunder methods", "medium"),
    (r"hasattr\s*\(.*__", "Dynamic attribute checking of dunder methods", "low"),
    (r"globals\s*\(\)", "Access to global namespace", "medium"),
    (r"locals\s*\(\)", "Access to local namespace", "low"),
    (r"vars\s*\(", "Variable inspection", "low"),
    (r"dir\s*\(", "Object inspection", "low"),
    
    # Code modification
    (r"sys\.modules", "Module manipulation", "high"),
    (r"importlib\.", "Dynamic import manipulation", "medium"),
    (r"__builtins__", "Access to builtin functions", "high"),
    
    # Memory/performance
    (r"while\s+True:", "Infinite loop (potential DoS)", "medium"),
    (r"for.*in.*range\s*\(\s*[0-9]{6,}", "Large range iteration", "low"),
    (r"list\s*\(\s*range\s*\(\s*[0-9]{6,}", "Large list creation", "low"),
    (r"\*\s*[0-9]{6,}", "Large data multiplication", "low"),
]


def check_code_safety(code: str, language: str = "python") -> List[SecurityWarning]:
    """Analyze code for potentially dangerous patterns.
    
    Args:
        code: Code to analyze
        language: Programming language (currently only 'python' supported)
        
    Returns:
        List of security warnings found
        
    Note:
        These are warnings only. The sandbox provides real isolation.
        This is a best-effort static analysis for user awareness.
    """
    warnings = []
    
    if language == "python":
        warnings.extend(_check_python_patterns(code))
        warnings.extend(_check_python_ast(code))
    elif language == "bash":
        warnings.extend(_check_bash_patterns(code))
    else:
        # Fall back to basic pattern matching
        warnings.extend(_check_generic_patterns(code))
    
    return warnings


def _check_python_patterns(code: str) -> List[SecurityWarning]:
    """Check Python code using regex patterns."""
    warnings = []
    lines = code.split('\n')
    
    for i, line in enumerate(lines, 1):
        for pattern, message, severity in DANGEROUS_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                warnings.append(SecurityWarning(
                    pattern=pattern,
                    message=message,
                    severity=severity,
                    line_number=i,
                    context=line.strip(),
                ))
    
    return warnings


def _check_python_ast(code: str) -> List[SecurityWarning]:
    """Check Python code using AST analysis."""
    warnings = []
    
    try:
        tree = ast.parse(code)
        visitor = DangerousASTVisitor()
        visitor.visit(tree)
        warnings.extend(visitor.warnings)
    except SyntaxError:
        # Invalid Python syntax - let the sandbox handle it
        pass
    except Exception as e:
        logger.debug(f"AST analysis failed: {e}")
    
    return warnings


def _check_bash_patterns(code: str) -> List[SecurityWarning]:
    """Check bash/shell code for dangerous patterns."""
    warnings = []
    lines = code.split('\n')
    
    bash_patterns = [
        (r"rm\s+-rf\s+\/", "Recursive deletion of root directory", "critical"),
        (r"rm\s+-rf\s+\*", "Recursive deletion with wildcard", "high"),
        (r">\s*\/dev\/sd[a-z]", "Direct disk device access", "critical"),
        (r"dd\s+if=.*of=", "Low-level disk operations", "high"),
        (r"mkfs\.", "Filesystem creation", "critical"),
        (r"fdisk", "Disk partitioning", "critical"),
        (r"shutdown", "System shutdown", "high"),
        (r"reboot", "System reboot", "high"),
        (r"halt", "System halt", "high"),
        (r"init\s+[0-6]", "System runlevel change", "high"),
        (r"chmod\s+777", "Overly permissive file permissions", "medium"),
        (r"curl.*\|\s*bash", "Piped execution from network", "high"),
        (r"wget.*\|\s*bash", "Piped execution from network", "high"),
        (r"\$\(.*\)", "Command substitution", "medium"),
        (r"`.*`", "Command substitution (backticks)", "medium"),
    ]
    
    for i, line in enumerate(lines, 1):
        for pattern, message, severity in bash_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                warnings.append(SecurityWarning(
                    pattern=pattern,
                    message=message,
                    severity=severity,
                    line_number=i,
                    context=line.strip(),
                ))
    
    return warnings


def _check_generic_patterns(code: str) -> List[SecurityWarning]:
    """Check code using generic patterns."""
    warnings = []
    lines = code.split('\n')
    
    generic_patterns = [
        (r"eval\s*\(", "Dynamic code execution", "critical"),
        (r"exec\s*\(", "Dynamic code execution", "critical"),
        (r"system\s*\(", "System command execution", "high"),
        (r"shell\s*\(", "Shell command execution", "high"),
    ]
    
    for i, line in enumerate(lines, 1):
        for pattern, message, severity in generic_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                warnings.append(SecurityWarning(
                    pattern=pattern,
                    message=message,
                    severity=severity,
                    line_number=i,
                    context=line.strip(),
                ))
    
    return warnings


class DangerousASTVisitor(ast.NodeVisitor):
    """AST visitor to detect dangerous Python constructs."""
    
    def __init__(self):
        self.warnings = []
    
    def visit_Call(self, node):
        """Visit function calls."""
        # Check for dangerous function calls
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in ("eval", "exec", "compile"):
                self.warnings.append(SecurityWarning(
                    pattern=f"{func_name}()",
                    message=f"Dynamic code execution with {func_name}()",
                    severity="critical",
                    line_number=node.lineno,
                ))
        
        # Check for attribute calls like os.system
        elif isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                module = node.func.value.id
                func = node.func.attr
                
                if module == "os" and func == "system":
                    self.warnings.append(SecurityWarning(
                        pattern="os.system()",
                        message="Direct system command execution",
                        severity="high",
                        line_number=node.lineno,
                    ))
                elif module == "subprocess" and func in ("call", "run", "Popen"):
                    # Check if shell=True is used
                    for keyword in node.keywords:
                        if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant):
                            if keyword.value.value is True:
                                self.warnings.append(SecurityWarning(
                                    pattern=f"subprocess.{func}(..., shell=True)",
                                    message="Shell injection risk with subprocess",
                                    severity="high",
                                    line_number=node.lineno,
                                ))
        
        self.generic_visit(node)
    
    def visit_Import(self, node):
        """Visit import statements."""
        for alias in node.names:
            if alias.name in ("os", "subprocess", "sys"):
                self.warnings.append(SecurityWarning(
                    pattern=f"import {alias.name}",
                    message=f"Import of potentially dangerous module: {alias.name}",
                    severity="low",
                    line_number=node.lineno,
                ))
        
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node):
        """Visit from ... import statements."""
        if node.module in ("os", "subprocess", "sys"):
            for alias in node.names:
                if alias.name in ("system", "call", "run", "Popen", "modules"):
                    self.warnings.append(SecurityWarning(
                        pattern=f"from {node.module} import {alias.name}",
                        message=f"Import of dangerous function: {alias.name}",
                        severity="medium",
                        line_number=node.lineno,
                    ))
        
        self.generic_visit(node)


def format_warnings(warnings: List[SecurityWarning]) -> str:
    """Format security warnings for display.
    
    Args:
        warnings: List of security warnings
        
    Returns:
        Formatted string of warnings
    """
    if not warnings:
        return "No security issues detected."
    
    # Group by severity
    by_severity = {"critical": [], "high": [], "medium": [], "low": []}
    for warning in warnings:
        by_severity[warning.severity].append(warning)
    
    lines = []
    lines.append(f"Security analysis found {len(warnings)} potential issue(s):")
    lines.append("")
    
    for severity in ["critical", "high", "medium", "low"]:
        if by_severity[severity]:
            lines.append(f"{severity.upper()} RISK:")
            for warning in by_severity[severity]:
                line_info = f" (line {warning.line_number})" if warning.line_number else ""
                context_info = f"\n  Context: {warning.context}" if warning.context else ""
                lines.append(f"  - {warning.message}{line_info}{context_info}")
            lines.append("")
    
    lines.append("Note: These are warnings only. The sandbox provides real isolation.")
    return "\n".join(lines)


def get_security_summary(warnings: List[SecurityWarning]) -> Dict[str, Any]:
    """Get security analysis summary.
    
    Args:
        warnings: List of security warnings
        
    Returns:
        Dictionary with summary statistics
    """
    by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for warning in warnings:
        by_severity[warning.severity] += 1
    
    max_severity = "low"
    if by_severity["critical"] > 0:
        max_severity = "critical"
    elif by_severity["high"] > 0:
        max_severity = "high"  
    elif by_severity["medium"] > 0:
        max_severity = "medium"
    
    return {
        "total_warnings": len(warnings),
        "by_severity": by_severity,
        "max_severity": max_severity,
        "is_safe": len(warnings) == 0,
        "has_critical": by_severity["critical"] > 0,
    }