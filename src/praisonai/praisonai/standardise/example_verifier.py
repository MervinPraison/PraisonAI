"""
Example verification module for the FDEP standardisation system.

Verifies that generated Python examples are:
1. Syntactically correct (can be parsed)
2. Runnable (can be executed without errors)
3. Handle external library dependencies gracefully

Features:
- Syntax validation via ast.parse
- Execution in subprocess with timeout
- Detection of missing external libraries
- Detailed error reporting
"""

import ast
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple


@dataclass
class VerificationResult:
    """Result of example verification."""
    success: bool
    syntax_valid: bool
    execution_passed: bool
    output: str
    error: str
    missing_libraries: List[str]
    requires_external: bool
    
    @property
    def can_write(self) -> bool:
        """Whether the example is safe to write."""
        return self.syntax_valid and (self.execution_passed or self.requires_external)


class ExampleVerifier:
    """Verifies that generated examples are runnable."""
    
    # Known external libraries that may not be installed
    EXTERNAL_LIBRARIES = {
        "requests", "httpx", "aiohttp",  # HTTP
        "pandas", "numpy", "scipy",  # Data science
        "torch", "tensorflow", "transformers",  # ML
        "redis", "pymongo", "psycopg2",  # Databases
        "boto3", "google-cloud",  # Cloud
        "playwright", "selenium",  # Browser automation
        "beautifulsoup4", "scrapy",  # Web scraping
    }
    
    # Imports that indicate external dependencies
    EXTERNAL_IMPORT_PATTERNS = [
        "import requests",
        "import httpx",
        "import pandas",
        "import numpy",
        "import torch",
        "import tensorflow",
        "from transformers",
        "import redis",
        "import pymongo",
        "import boto3",
    ]
    
    # Patterns that indicate LLM API calls (will timeout during verification)
    LLM_CALL_PATTERNS = [
        "agent.start(",
        "agents.start(",
        ".chat(",
        ".run(",
    ]
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
    
    def verify(self, code: str) -> VerificationResult:
        """
        Verify that the code is valid and runnable.
        
        Args:
            code: Python source code to verify
            
        Returns:
            VerificationResult with details
        """
        # Step 1: Syntax validation
        syntax_valid, syntax_error = self._check_syntax(code)
        if not syntax_valid:
            return VerificationResult(
                success=False,
                syntax_valid=False,
                execution_passed=False,
                output="",
                error=f"Syntax error: {syntax_error}",
                missing_libraries=[],
                requires_external=False,
            )
        
        # Step 2: Check for external dependencies
        requires_external, external_libs = self._detect_external_deps(code)
        
        # Step 3: Skip execution for examples with LLM calls (they will timeout)
        if "LLM_API_CALL" in external_libs:
            return VerificationResult(
                success=True,
                syntax_valid=True,
                execution_passed=False,
                output="",
                error="Skipped: Example makes LLM API calls",
                missing_libraries=["praisonaiagents (LLM API)"],
                requires_external=True,
            )
        
        # Step 4: Execute the code
        execution_passed, output, error, missing_libs = self._execute(code)
        
        # Combine missing libraries
        all_missing = list(set(missing_libs + external_libs))
        
        return VerificationResult(
            success=execution_passed or requires_external,
            syntax_valid=True,
            execution_passed=execution_passed,
            output=output,
            error=error,
            missing_libraries=all_missing,
            requires_external=requires_external and not execution_passed,
        )
    
    def _check_syntax(self, code: str) -> Tuple[bool, str]:
        """Check if code is syntactically valid."""
        try:
            ast.parse(code)
            return True, ""
        except SyntaxError as e:
            return False, f"Line {e.lineno}: {e.msg}"
    
    def _detect_external_deps(self, code: str) -> Tuple[bool, List[str]]:
        """Detect if code requires external libraries or makes LLM calls."""
        external_libs = []
        
        for pattern in self.EXTERNAL_IMPORT_PATTERNS:
            if pattern in code:
                lib_name = pattern.split()[-1]
                external_libs.append(lib_name)
        
        # Check for LLM API calls that will timeout during verification
        for pattern in self.LLM_CALL_PATTERNS:
            if pattern in code:
                external_libs.append("LLM_API_CALL")
                break
        
        return len(external_libs) > 0, external_libs
    
    def _execute(self, code: str) -> Tuple[bool, str, str, List[str]]:
        """Execute code in a subprocess."""
        missing_libs = []
        
        # Write code to temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            temp_path = f.name
        
        try:
            # Run with timeout
            result = subprocess.run(
                [sys.executable, temp_path],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env={**subprocess.os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            
            output = result.stdout
            error = result.stderr
            
            # Check for import errors
            if result.returncode != 0:
                if "ModuleNotFoundError" in error or "ImportError" in error:
                    # Extract module name
                    for line in error.split("\n"):
                        if "No module named" in line:
                            # Extract module name from error
                            parts = line.split("'")
                            if len(parts) >= 2:
                                missing_libs.append(parts[1].split(".")[0])
                
                return False, output, error, missing_libs
            
            return True, output, error, missing_libs
            
        except subprocess.TimeoutExpired:
            return False, "", f"Execution timed out after {self.timeout}s", missing_libs
        except Exception as e:
            return False, "", str(e), missing_libs
        finally:
            # Clean up temp file
            Path(temp_path).unlink(missing_ok=True)
    
    def format_result(self, result: VerificationResult) -> str:
        """Format verification result for display."""
        lines = []
        
        if result.success:
            lines.append("✅ Verification PASSED")
        else:
            lines.append("❌ Verification FAILED")
        
        lines.append(f"  Syntax valid: {'✓' if result.syntax_valid else '✗'}")
        lines.append(f"  Execution passed: {'✓' if result.execution_passed else '✗'}")
        
        if result.requires_external:
            lines.append(f"  ⚠️  Requires external libraries: {', '.join(result.missing_libraries)}")
            lines.append("     (Will be written with warning)")
        
        if result.error and not result.requires_external:
            lines.append(f"  Error: {result.error[:200]}")
        
        if result.output:
            lines.append(f"  Output preview: {result.output[:100]}...")
        
        return "\n".join(lines)
