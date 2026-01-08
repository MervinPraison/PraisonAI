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
    
    def __init__(self, name: Optional[str] = None, timeout: float = 60.0):
        """Initialize the hook.
        
        Args:
            name: Override the hook name
            timeout: Timeout in seconds for execution
        """
        if name:
            self.name = name
        self.timeout_seconds = timeout
    
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
        command: list,
        cwd: Optional[str] = None,
        timeout: float = 60.0,
    ):
        """Initialize command hook.
        
        Args:
            name: Hook name
            command: Command to run as list (e.g., ["pytest", "-v"])
            cwd: Working directory for command
            timeout: Timeout in seconds
        """
        super().__init__(name=name, timeout=timeout)
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
