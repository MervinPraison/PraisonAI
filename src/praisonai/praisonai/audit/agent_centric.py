"""
Agent-Centric Compliance Auditor Implementation.

Provides scanning, detection, and fixing capabilities for ensuring
Python examples and documentation follow agent-centric principles.
"""

import ast
import os
import re
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any


class ComplianceStatus(Enum):
    """Compliance status for a file."""
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    SKIPPED = "skipped"
    ERROR = "error"


class NonComplianceReason(Enum):
    """Categories for non-compliance."""
    NO_AGENT_IMPORT = "A_no_agent_import"
    IMPORT_NO_INSTANTIATION = "B_import_no_instantiation"
    LOW_LEVEL_FIRST = "C_low_level_first"
    TOO_ADVANCED = "D_too_advanced"
    WRONG_FOLDER = "E_wrong_folder"
    OUTDATED_API = "F_outdated_api"
    NON_RUNNABLE = "G_non_runnable"
    DUPLICATE_QUICKSTART = "H_duplicate_quickstart"
    INSTANTIATION_TOO_LATE = "I_instantiation_too_late"


@dataclass
class ComplianceResult:
    """Result of compliance check for a single file."""
    file_path: str
    status: ComplianceStatus
    reason: Optional[NonComplianceReason] = None
    details: str = ""
    line_of_import: int = 0
    line_of_instantiation: int = 0
    detection_methods: Dict[str, bool] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "status": self.status.value,
            "reason": self.reason.value if self.reason else None,
            "details": self.details,
            "line_of_import": self.line_of_import,
            "line_of_instantiation": self.line_of_instantiation,
            "detection_methods": self.detection_methods
        }


@dataclass
class AuditReport:
    """Complete audit report."""
    total_files: int = 0
    compliant: int = 0
    non_compliant: int = 0
    skipped: int = 0
    errors: int = 0
    results: List[ComplianceResult] = field(default_factory=list)
    by_reason: Dict[str, int] = field(default_factory=dict)
    
    def compliance_rate(self) -> float:
        checkable = self.total_files - self.skipped
        if checkable == 0:
            return 100.0
        return (self.compliant / checkable) * 100


# Agent-centric import patterns
AGENT_IMPORTS = [
    r"from\s+praisonaiagents\s+import\s+.*\bAgent\b",
    r"from\s+praisonaiagents\s+import\s+.*\bPraisonAIAgents\b",
    r"from\s+praisonaiagents\s+import\s+.*\bWorkflow\b",
    r"from\s+praisonaiagents\.agent\s+import\s+Agent",
    r"from\s+praisonaiagents\.agents\s+import\s+PraisonAIAgents",
    r"from\s+praisonaiagents\.workflow\s+import\s+Workflow",
]

# Instantiation patterns
INSTANTIATION_PATTERNS = [
    r"\bAgent\s*\(",
    r"\bPraisonAIAgents\s*\(",
    r"\bWorkflow\s*\(",
]

# Low-level imports that should come AFTER agent-centric code
LOW_LEVEL_IMPORTS = [
    r"from\s+praisonaiagents\.(memory|knowledge|tools|context)",
    r"from\s+praisonaiagents\.mcp",
    r"from\s+praisonaiagents\.hooks",
    r"from\s+praisonaiagents\.middleware",
]

# Files/folders to skip
SKIP_PATTERNS = [
    r"__pycache__",
    r"\.pyc$",
    r"__init__\.py$",
    r"conftest\.py$",
    r"test_.*\.py$",
    r".*_test\.py$",
]

# Definition-only folders (tools, utilities, not runnable examples)
DEFINITION_FOLDERS = [
    "tool_definitions",
    "utils",
    "helpers",
    "lib",
]


class AgentCentricAuditor:
    """
    Auditor for agent-centric compliance.
    
    Usage:
        auditor = AgentCentricAuditor(line_limit=40)
        report = auditor.scan("/path/to/examples")
        auditor.fix_file("/path/to/file.py")
    """
    
    def __init__(
        self,
        line_limit: int = 40,
        timeout: int = 30,
        verbose: bool = False
    ):
        self.line_limit = line_limit
        self.timeout = timeout
        self.verbose = verbose
        self._import_patterns = [re.compile(p, re.MULTILINE) for p in AGENT_IMPORTS]
        self._instantiation_patterns = [re.compile(p) for p in INSTANTIATION_PATTERNS]
        self._low_level_patterns = [re.compile(p, re.MULTILINE) for p in LOW_LEVEL_IMPORTS]
        self._skip_patterns = [re.compile(p) for p in SKIP_PATTERNS]
    
    def should_skip(self, file_path: str) -> Tuple[bool, str]:
        """Check if file should be skipped."""
        path = Path(file_path)
        
        # Skip patterns
        for pattern in self._skip_patterns:
            if pattern.search(str(path)):
                return True, f"matches skip pattern: {pattern.pattern}"
        
        # Skip definition folders
        for folder in DEFINITION_FOLDERS:
            if folder in path.parts:
                return True, f"in definition folder: {folder}"
        
        # Skip non-Python files
        if path.suffix != ".py":
            return True, "not a Python file"
        
        return False, ""
    
    def _get_first_n_lines(self, content: str, n: int) -> str:
        """Get first N lines of content."""
        lines = content.split('\n')
        return '\n'.join(lines[:n])
    
    def _find_line_number(self, content: str, pattern: re.Pattern) -> int:
        """Find line number of first match."""
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if pattern.search(line):
                return i
        return 0
    
    def _method_1_heuristic_header_scan(self, content: str) -> Tuple[bool, str]:
        """Method 1: Heuristic header scan (first N lines)."""
        header = self._get_first_n_lines(content, self.line_limit)
        
        has_import = any(p.search(header) for p in self._import_patterns)
        has_instantiation = any(p.search(header) for p in self._instantiation_patterns)
        
        if has_import and has_instantiation:
            return True, "import and instantiation found in header"
        elif has_import:
            return False, "import found but no instantiation in header"
        else:
            return False, "no agent import in header"
    
    def _method_2_ast_import_detector(self, content: str) -> Tuple[bool, str]:
        """Method 2: AST-based import detector."""
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            return False, f"syntax error: {e}"
        
        agent_imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and "praisonaiagents" in node.module:
                    for alias in node.names:
                        if alias.name in ("Agent", "PraisonAIAgents", "Workflow"):
                            agent_imports.append((node.lineno, alias.name))
        
        if agent_imports:
            first_import = agent_imports[0]
            if first_import[0] <= self.line_limit:
                return True, f"{first_import[1]} imported at line {first_import[0]}"
            return False, f"{first_import[1]} imported too late at line {first_import[0]}"
        return False, "no agent imports found via AST"
    
    def _method_3_regex_first_import(self, content: str) -> Tuple[bool, str]:
        """Method 3: Regex first meaningful import."""
        # Skip comments and docstrings
        lines = content.split('\n')
        in_docstring = False
        
        for i, line in enumerate(lines[:self.line_limit], 1):
            stripped = line.strip()
            
            # Handle docstrings
            if '"""' in stripped or "'''" in stripped:
                count = stripped.count('"""') + stripped.count("'''")
                if count == 1:
                    in_docstring = not in_docstring
                continue
            
            if in_docstring:
                continue
            
            # Skip comments
            if stripped.startswith('#'):
                continue
            
            # Check for agent import
            for pattern in self._import_patterns:
                if pattern.search(line):
                    return True, f"agent import at line {i}"
        
        return False, "no agent import in first meaningful lines"
    
    def _method_4_docstring_quickstart(self, content: str) -> Tuple[bool, str]:
        """Method 4: Docstring Quickstart validation."""
        # Check if file has a docstring mentioning it's low-level/advanced
        docstring_match = re.search(r'^"""(.*?)"""', content, re.DOTALL)
        if docstring_match:
            docstring = docstring_match.group(1).lower()
            if any(kw in docstring for kw in ["low-level", "advanced", "internal", "utility"]):
                return True, "marked as low-level/advanced in docstring"
        return False, "no low-level marker in docstring"
    
    def _method_5_check_duplicate_quickstart(self, content: str) -> Tuple[bool, str]:
        """Method 5: Check for duplicate quickstart blocks."""
        quickstart_pattern = r"#\s*Agent-centric quickstart"
        matches = re.findall(quickstart_pattern, content, re.IGNORECASE)
        if len(matches) > 1:
            return False, f"found {len(matches)} duplicate quickstart blocks"
        return True, "no duplicate quickstart blocks"
    
    def _method_6_low_level_first_check(self, content: str) -> Tuple[bool, str]:
        """Method 6: Check if low-level imports come before agent-centric."""
        header = self._get_first_n_lines(content, self.line_limit)
        
        # Find first agent import line
        agent_line = 0
        for pattern in self._import_patterns:
            line = self._find_line_number(header, pattern)
            if line > 0 and (agent_line == 0 or line < agent_line):
                agent_line = line
        
        # Find first low-level import line
        low_level_line = 0
        for pattern in self._low_level_patterns:
            line = self._find_line_number(header, pattern)
            if line > 0 and (low_level_line == 0 or line < low_level_line):
                low_level_line = line
        
        if low_level_line > 0 and agent_line == 0:
            return False, f"low-level import at line {low_level_line} with no agent import"
        if low_level_line > 0 and low_level_line < agent_line:
            return False, f"low-level import at line {low_level_line} before agent import at {agent_line}"
        
        return True, "agent imports come before low-level imports"
    
    def _method_7_folder_intent(self, file_path: str) -> Tuple[bool, str]:
        """Method 7: Folder intent rules."""
        path = Path(file_path)
        
        # Check if in a definition-only folder
        for folder in DEFINITION_FOLDERS:
            if folder in path.parts:
                return True, f"definition folder: {folder}"
        
        # Check for test folders
        if "test" in str(path).lower() or "tests" in path.parts:
            return True, "test folder"
        
        return False, "runnable example folder"
    
    def _method_8_runnability_check(self, content: str) -> Tuple[bool, str]:
        """Method 8: Check if file is runnable."""
        has_main_guard = 'if __name__ == "__main__"' in content or "if __name__ == '__main__'" in content
        has_top_level_call = any(p.search(content) for p in [
            re.compile(r"^\w+\.start\(", re.MULTILINE),
            re.compile(r"^\w+\.run\(", re.MULTILINE),
            re.compile(r"^\w+\.chat\(", re.MULTILINE),
            re.compile(r"^print\(", re.MULTILINE),
        ])
        
        if has_main_guard or has_top_level_call:
            return True, "runnable (has main guard or top-level execution)"
        return False, "may not be runnable"
    
    def _method_9_instantiation_check(self, content: str) -> Tuple[bool, str]:
        """Method 9: Check for actual instantiation within line limit."""
        header = self._get_first_n_lines(content, self.line_limit)
        
        for pattern in self._instantiation_patterns:
            if pattern.search(header):
                line = self._find_line_number(header, pattern)
                return True, f"instantiation found at line {line}"
        
        # Check full file
        for pattern in self._instantiation_patterns:
            if pattern.search(content):
                line = self._find_line_number(content, pattern)
                return False, f"instantiation at line {line} (beyond limit {self.line_limit})"
        
        return False, "no instantiation found"
    
    def check_file(self, file_path: str) -> ComplianceResult:
        """Check a single file for compliance."""
        result = ComplianceResult(file_path=file_path, status=ComplianceStatus.COMPLIANT)
        
        # Check if should skip
        should_skip, skip_reason = self.should_skip(file_path)
        if should_skip:
            result.status = ComplianceStatus.SKIPPED
            result.details = skip_reason
            return result
        
        # Read file
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            result.status = ComplianceStatus.ERROR
            result.details = str(e)
            return result
        
        # Run all detection methods
        methods = {
            "heuristic_header": self._method_1_heuristic_header_scan,
            "ast_import": self._method_2_ast_import_detector,
            "regex_import": self._method_3_regex_first_import,
            "docstring_marker": self._method_4_docstring_quickstart,
            "duplicate_check": self._method_5_check_duplicate_quickstart,
            "low_level_order": self._method_6_low_level_first_check,
            "instantiation": self._method_9_instantiation_check,
        }
        
        for name, method in methods.items():
            try:
                passed, detail = method(content)
                result.detection_methods[name] = passed
                if self.verbose:
                    print(f"  {name}: {'✓' if passed else '✗'} - {detail}")
            except Exception as e:
                result.detection_methods[name] = False
                if self.verbose:
                    print(f"  {name}: ERROR - {e}")
        
        # Check folder intent
        is_definition, folder_detail = self._method_7_folder_intent(file_path)
        result.detection_methods["folder_intent"] = is_definition
        
        # Check runnability
        is_runnable, run_detail = self._method_8_runnability_check(content)
        result.detection_methods["runnability"] = is_runnable
        
        # Determine compliance
        if is_definition:
            result.status = ComplianceStatus.SKIPPED
            result.details = folder_detail
            return result
        
        # Check for duplicate quickstart (corruption)
        if not result.detection_methods.get("duplicate_check", True):
            result.status = ComplianceStatus.NON_COMPLIANT
            result.reason = NonComplianceReason.DUPLICATE_QUICKSTART
            result.details = "duplicate quickstart blocks found"
            return result
        
        # Check for agent import
        has_import = result.detection_methods.get("heuristic_header", False) or \
                     result.detection_methods.get("ast_import", False) or \
                     result.detection_methods.get("regex_import", False)
        
        has_instantiation = result.detection_methods.get("instantiation", False)
        
        if not has_import:
            # Check if it's a low-level file that should be skipped
            if result.detection_methods.get("docstring_marker", False):
                result.status = ComplianceStatus.SKIPPED
                result.details = "marked as low-level/advanced"
                return result
            
            result.status = ComplianceStatus.NON_COMPLIANT
            result.reason = NonComplianceReason.NO_AGENT_IMPORT
            result.details = "no agent import found in header"
            return result
        
        if not has_instantiation:
            result.status = ComplianceStatus.NON_COMPLIANT
            result.reason = NonComplianceReason.IMPORT_NO_INSTANTIATION
            result.details = "import found but no instantiation in header"
            return result
        
        if not result.detection_methods.get("low_level_order", True):
            result.status = ComplianceStatus.NON_COMPLIANT
            result.reason = NonComplianceReason.LOW_LEVEL_FIRST
            result.details = "low-level imports before agent-centric code"
            return result
        
        result.status = ComplianceStatus.COMPLIANT
        result.details = "all checks passed"
        return result
    
    def scan(self, path: str, recursive: bool = True) -> AuditReport:
        """Scan a directory for compliance."""
        report = AuditReport()
        path_obj = Path(path)
        
        if path_obj.is_file():
            files = [path_obj]
        elif recursive:
            files = list(path_obj.rglob("*.py"))
        else:
            files = list(path_obj.glob("*.py"))
        
        for file_path in files:
            result = self.check_file(str(file_path))
            report.results.append(result)
            report.total_files += 1
            
            if result.status == ComplianceStatus.COMPLIANT:
                report.compliant += 1
            elif result.status == ComplianceStatus.NON_COMPLIANT:
                report.non_compliant += 1
                if result.reason:
                    key = result.reason.value
                    report.by_reason[key] = report.by_reason.get(key, 0) + 1
            elif result.status == ComplianceStatus.SKIPPED:
                report.skipped += 1
            else:
                report.errors += 1
        
        return report
    
    def generate_quickstart_block(self, feature_name: str = "Demo") -> str:
        """Generate a standard quickstart block."""
        return f'''from praisonaiagents import Agent

# Agent-centric quickstart
agent = Agent(
    name="{feature_name}Agent",
    instructions="You are a helpful assistant."
)

'''
    
    def fix_file(self, file_path: str, dry_run: bool = False) -> Tuple[bool, str]:
        """Fix a non-compliant file by adding agent-centric quickstart."""
        result = self.check_file(file_path)
        
        if result.status == ComplianceStatus.COMPLIANT:
            return True, "already compliant"
        
        if result.status == ComplianceStatus.SKIPPED:
            return True, f"skipped: {result.details}"
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            return False, f"read error: {e}"
        
        # Handle duplicate quickstart blocks
        if result.reason == NonComplianceReason.DUPLICATE_QUICKSTART:
            # Remove all but first quickstart block
            pattern = r"(#\s*Agent-centric quickstart.*?agent\s*=\s*Agent\([^)]+\)\s*\n)"
            matches = list(re.finditer(pattern, content, re.DOTALL | re.IGNORECASE))
            if len(matches) > 1:
                # Keep first, remove rest
                for match in reversed(matches[1:]):
                    content = content[:match.start()] + content[match.end():]
                
                if not dry_run:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                return True, f"removed {len(matches)-1} duplicate quickstart blocks"
        
        # Find insertion point (after docstring and imports)
        lines = content.split('\n')
        insert_line = 0
        in_docstring = False
        found_import = False
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Track docstrings
            if '"""' in stripped or "'''" in stripped:
                count = stripped.count('"""') + stripped.count("'''")
                if count == 1:
                    in_docstring = not in_docstring
                elif count >= 2:
                    pass  # Single-line docstring
                continue
            
            if in_docstring:
                continue
            
            # Track imports
            if stripped.startswith(('import ', 'from ')):
                found_import = True
                insert_line = i + 1
                continue
            
            # After imports, find first non-empty, non-comment line
            if found_import and stripped and not stripped.startswith('#'):
                insert_line = i
                break
        
        # Check if already has agent import
        has_agent_import = any(p.search(content) for p in self._import_patterns)
        
        # Generate feature name from file
        feature_name = Path(file_path).stem.replace('_', ' ').title().replace(' ', '')
        
        if has_agent_import:
            # Just need to add instantiation
            quickstart = f'''
# Agent-centric quickstart
agent = Agent(
    name="{feature_name}Agent",
    instructions="You are a helpful assistant."
)

'''
        else:
            quickstart = self.generate_quickstart_block(feature_name)
        
        # Insert quickstart
        lines.insert(insert_line, quickstart)
        new_content = '\n'.join(lines)
        
        if not dry_run:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
        
        return True, f"added quickstart at line {insert_line}"
    
    def to_json(self, report: AuditReport) -> str:
        """Convert report to JSON."""
        return json.dumps({
            "total_files": report.total_files,
            "compliant": report.compliant,
            "non_compliant": report.non_compliant,
            "skipped": report.skipped,
            "errors": report.errors,
            "compliance_rate": report.compliance_rate(),
            "by_reason": report.by_reason,
            "results": [r.to_dict() for r in report.results]
        }, indent=2)
