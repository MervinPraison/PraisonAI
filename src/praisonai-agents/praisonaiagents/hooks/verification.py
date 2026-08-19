"""
Verification Hooks Protocol for PraisonAI Agents.

Provides protocols for verification hooks that can be used with Agent autonomy.
Verification hooks run after file writes or at configured checkpoints to
validate agent actions (e.g., run tests, lint, build).

Usage:
    from praisonaiagents.hooks import VerificationHook, VerificationResult
    
    class TestRunner(VerificationHook):
        name = "pytest"
        
        def run(self, context=None):
            # Run tests and return result
            return VerificationResult(
                success=True,
                output="All tests passed",
                details={"tests_run": 10, "passed": 10}
            )
    
    agent = Agent(
        instructions="...",
        autonomy=True,
        verification_hooks=[TestRunner()]
    )
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol, runtime_checkable


@dataclass
class VerificationResult:
    """Result of a verification hook execution.
    
    Attributes:
        success: Whether verification passed
        output: Human-readable output/summary
        details: Additional structured details
        error: Error message if failed
        duration_seconds: How long verification took
    """
    success: bool
    output: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    duration_seconds: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "output": self.output,
            "details": self.details,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
        }


@runtime_checkable
class VerificationHook(Protocol):
    """Protocol for verification hooks.
    
    Verification hooks are used by Agent autonomy to validate actions.
    They run after file writes or at configured checkpoints.
    
    Implementations must provide:
    - name: Unique identifier for the hook
    - run(): Execute verification and return result
    
    Example:
        class LintRunner:
            name = "ruff"
            
            def run(self, context=None):
                import subprocess
                result = subprocess.run(["ruff", "check", "."], capture_output=True)
                return VerificationResult(
                    success=result.returncode == 0,
                    output=result.stdout.decode()
                )
    """
    
    name: str
    
    def run(self, context: Optional[Dict[str, Any]] = None) -> VerificationResult:
        """Run the verification hook.
        
        Args:
            context: Optional context with information about what changed
                    (e.g., files modified, actions taken)
        
        Returns:
            VerificationResult with success status and output
        """
        ...


class BaseVerificationHook:
    """Base class for verification hooks.
    
    Provides common functionality for verification hooks.
    Subclass this to create custom verification hooks.
    
    Example:
        class MyTestRunner(BaseVerificationHook):
            name = "my_tests"
            
            def _execute(self, context):
                # Run your tests
                return VerificationResult(success=True, output="Tests passed")
    """
    
    name: str = "base"
    timeout_seconds: float = 60.0
    blocking: bool = True

    def __init__(
        self,
        name: Optional[str] = None,
        timeout: float = 60.0,
        blocking: bool = True,
    ):
        """Initialize the hook.
        
        Args:
            name: Override the hook name
            timeout: Timeout in seconds for execution
            blocking: When True (default), a failure of this hook blocks the
                autonomous loop from finalising with a success outcome.
        """
        if name:
            self.name = name
        self.timeout_seconds = timeout
        self.blocking = blocking
    
    def run(self, context: Optional[Dict[str, Any]] = None) -> VerificationResult:
        """Run the verification hook.
        
        Args:
            context: Optional context
            
        Returns:
            VerificationResult
        """
        import time
        start = time.time()
        
        try:
            result = self._execute(context)
            result.duration_seconds = time.time() - start
            return result
        except Exception as e:
            return VerificationResult(
                success=False,
                output=str(e),
                error=str(e),
                duration_seconds=time.time() - start,
            )
    
    def _execute(self, context: Optional[Dict[str, Any]] = None) -> VerificationResult:
        """Execute the verification logic.
        
        Override this method in subclasses.
        
        Args:
            context: Optional context
            
        Returns:
            VerificationResult
        """
        raise NotImplementedError("Subclasses must implement _execute()")


class CommandVerificationHook(BaseVerificationHook):
    """Verification hook that runs a shell command.
    
    Example:
        hook = CommandVerificationHook(
            name="pytest",
            command=["pytest", "-v", "--tb=short"]
        )
    """
    
    def __init__(
        self,
        name: str,
        command,
        cwd: Optional[str] = None,
        timeout: float = 60.0,
        blocking: bool = True,
    ):
        """Initialize command hook.
        
        Args:
            name: Hook name
            command: Command to run as a list (e.g., ["pytest", "-v"]) or a
                string (e.g., "python -m pytest -q"), which is shell-split.
            cwd: Working directory for command
            timeout: Timeout in seconds
            blocking: When True (default), a failure blocks completion.
        """
        super().__init__(name=name, timeout=timeout, blocking=blocking)
        if isinstance(command, str):
            import shlex
            command = shlex.split(command)
        self.command = command
        self.cwd = cwd
    
    def _execute(self, context: Optional[Dict[str, Any]] = None) -> VerificationResult:
        """Execute the command.
        
        Args:
            context: Optional context
            
        Returns:
            VerificationResult
        """
        import subprocess
        
        try:
            result = subprocess.run(
                self.command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                cwd=self.cwd,
            )
            
            return VerificationResult(
                success=result.returncode == 0,
                output=result.stdout + result.stderr,
                details={
                    "command": self.command,
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                },
            )
        except subprocess.TimeoutExpired:
            return VerificationResult(
                success=False,
                output=f"Command timed out after {self.timeout_seconds}s",
                error="timeout",
            )
        except Exception as e:
            return VerificationResult(
                success=False,
                output=str(e),
                error=str(e),
            )


def _get_dotted(data: Any, path: str) -> Any:
    """Access a dotted path (e.g. ``"a.b.c"``) in nested dicts/lists.

    Returns ``None`` if any segment is missing. List indices are supported
    via integer-looking segments.
    """
    value = data
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, (list, tuple)):
            try:
                value = value[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return value


class FileCheckHook(BaseVerificationHook):
    """Declarative file-assertion verification hook (no shell involved).

    Checks portable filesystem facts:
      - ``exists``    : the file exists (default True).
      - ``non_empty`` : the file has non-zero size.
      - ``contains``  : the file text contains a substring.
      - ``json_field``/``equals`` : the JSON value at a dotted path equals a value.

    Example:
        hook = FileCheckHook(name="changelog", path="CHANGELOG.md", non_empty=True)
        hook = FileCheckHook(name="cfg", path="out.json",
                             json_field="status.code", equals=0)
    """

    def __init__(
        self,
        name: str,
        path: str,
        exists: bool = True,
        non_empty: bool = False,
        contains: Optional[str] = None,
        json_field: Optional[str] = None,
        equals: Any = None,
        blocking: bool = True,
    ):
        super().__init__(name=name, blocking=blocking)
        self.path = path
        self.exists = exists
        self.non_empty = non_empty
        self.contains = contains
        self.json_field = json_field
        self.equals = equals

    def _execute(self, context: Optional[Dict[str, Any]] = None) -> VerificationResult:
        import os

        details: Dict[str, Any] = {"path": self.path}
        file_exists = os.path.isfile(self.path)
        details["exists"] = file_exists

        if self.exists and not file_exists:
            return VerificationResult(
                success=False,
                output=f"File not found: {self.path}",
                error="not_found",
                details=details,
            )
        if not self.exists:
            success = not file_exists
            return VerificationResult(
                success=success,
                output=(
                    f"File exists but was expected absent: {self.path}"
                    if not success else f"File absent as expected: {self.path}"
                ),
                details=details,
            )

        if self.non_empty:
            size = os.path.getsize(self.path)
            details["size"] = size
            if size == 0:
                return VerificationResult(
                    success=False,
                    output=f"File is empty: {self.path}",
                    error="empty",
                    details=details,
                )

        if self.contains is not None or self.json_field is not None:
            try:
                with open(self.path, "r", encoding="utf-8") as fh:
                    text = fh.read()
            except Exception as e:
                return VerificationResult(
                    success=False, output=str(e), error=str(e), details=details
                )

            if self.contains is not None and self.contains not in text:
                return VerificationResult(
                    success=False,
                    output=f"File {self.path} does not contain {self.contains!r}",
                    error="missing_substring",
                    details=details,
                )

            if self.json_field is not None:
                import json as _json

                try:
                    data = _json.loads(text)
                except Exception as e:
                    return VerificationResult(
                        success=False,
                        output=f"File {self.path} is not valid JSON: {e}",
                        error="invalid_json",
                        details=details,
                    )
                actual = _get_dotted(data, self.json_field)
                details["json_field"] = self.json_field
                details["actual"] = actual
                if actual != self.equals:
                    return VerificationResult(
                        success=False,
                        output=(
                            f"{self.path}:{self.json_field} = {actual!r}, "
                            f"expected {self.equals!r}"
                        ),
                        error="mismatch",
                        details=details,
                    )

        return VerificationResult(
            success=True,
            output=f"File check passed: {self.path}",
            details=details,
        )
