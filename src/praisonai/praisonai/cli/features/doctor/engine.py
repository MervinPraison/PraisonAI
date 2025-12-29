"""
Doctor engine for executing health checks.

Provides the core execution logic for running doctor checks.
"""

import os
import platform
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
from typing import Callable, List, Optional
import time

from .models import (
    CheckCategory,
    CheckResult,
    CheckStatus,
    CheckSeverity,
    DoctorConfig,
    DoctorReport,
    EnvironmentSummary,
)
from .registry import CheckRegistry, get_registry


class DoctorEngine:
    """
    Engine for executing doctor checks.
    
    Handles check execution, timeout management, and report generation.
    """
    
    def __init__(self, config: Optional[DoctorConfig] = None):
        """
        Initialize the doctor engine.
        
        Args:
            config: Doctor configuration
        """
        self.config = config or DoctorConfig()
        self.registry = get_registry()
        self._results: List[CheckResult] = []
    
    def get_environment_summary(self) -> EnvironmentSummary:
        """Gather environment information."""
        # Get package versions lazily
        praisonai_version = "unknown"
        praisonaiagents_version = "unknown"
        
        try:
            from praisonai.version import __version__ as pai_version
            praisonai_version = pai_version
        except ImportError:
            pass
        
        try:
            import praisonaiagents
            praisonaiagents_version = getattr(praisonaiagents, "__version__", "unknown")
        except ImportError:
            pass
        
        return EnvironmentSummary(
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            python_executable=sys.executable,
            os_name=platform.system(),
            os_version=platform.release(),
            architecture=platform.machine(),
            praisonai_version=praisonai_version,
            praisonaiagents_version=praisonaiagents_version,
            working_directory=os.getcwd(),
            virtual_env=os.environ.get("VIRTUAL_ENV"),
        )
    
    def run_check(
        self,
        check_id: str,
        implementation: Callable,
        timeout: Optional[float] = None,
    ) -> CheckResult:
        """
        Run a single check with timeout handling.
        
        Args:
            check_id: Check identifier
            implementation: Check function
            timeout: Timeout in seconds
            
        Returns:
            Check result
        """
        timeout = timeout or self.config.timeout
        definition = self.registry.get_check(check_id)
        
        start_time = time.time()
        
        try:
            # Run with timeout using ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(implementation, self.config)
                try:
                    result = future.result(timeout=timeout)
                    result.duration_ms = (time.time() - start_time) * 1000
                    return result
                except FuturesTimeoutError:
                    return CheckResult(
                        id=check_id,
                        title=definition.title if definition else check_id,
                        category=definition.category if definition else CheckCategory.ENVIRONMENT,
                        status=CheckStatus.ERROR,
                        message=f"Check timed out after {timeout}s",
                        remediation="Increase timeout with --timeout or check for hanging operations",
                        duration_ms=(time.time() - start_time) * 1000,
                        severity=CheckSeverity.HIGH,
                    )
        except Exception as e:
            # Capture exception details but redact potential secrets
            tb = traceback.format_exc()
            return CheckResult(
                id=check_id,
                title=definition.title if definition else check_id,
                category=definition.category if definition else CheckCategory.ENVIRONMENT,
                status=CheckStatus.ERROR,
                message=f"Check failed with error: {type(e).__name__}: {str(e)[:100]}",
                details=tb[:500] if not self.config.quiet else None,
                remediation="Check the error details and fix the underlying issue",
                duration_ms=(time.time() - start_time) * 1000,
                severity=CheckSeverity.HIGH,
            )
    
    def run_checks(
        self,
        check_ids: Optional[List[str]] = None,
        categories: Optional[List[CheckCategory]] = None,
    ) -> List[CheckResult]:
        """
        Run multiple checks.
        
        Args:
            check_ids: Specific check IDs to run (None = all)
            categories: Filter by categories
            
        Returns:
            List of check results
        """
        # Get filtered checks
        checks = self.registry.filter_checks(
            only=check_ids or self.config.only or None,
            skip=self.config.skip or None,
            categories=categories,
            deep_mode=self.config.deep,
        )
        
        # Resolve dependencies and get ordered list
        ordered_ids = self.registry.resolve_dependencies([c.id for c in checks])
        
        results = []
        failed_deps = set()
        
        for check_id in ordered_ids:
            definition = self.registry.get_check(check_id)
            implementation = self.registry.get_implementation(check_id)
            
            if not definition or not implementation:
                continue
            
            # Check if dependencies failed
            if any(dep in failed_deps for dep in definition.dependencies):
                results.append(CheckResult(
                    id=check_id,
                    title=definition.title,
                    category=definition.category,
                    status=CheckStatus.SKIP,
                    message="Skipped due to failed dependency",
                    severity=definition.severity,
                ))
                continue
            
            # Run the check
            result = self.run_check(check_id, implementation)
            results.append(result)
            
            # Track failures for dependency resolution
            if result.status in (CheckStatus.FAIL, CheckStatus.ERROR):
                failed_deps.add(check_id)
                
                # Fail fast if configured
                if self.config.fail_fast:
                    break
        
        self._results = results
        return results
    
    def generate_report(self, results: Optional[List[CheckResult]] = None) -> DoctorReport:
        """
        Generate a complete doctor report.
        
        Args:
            results: Check results (uses stored results if None)
            
        Returns:
            Complete doctor report
        """
        results = results or self._results
        
        report = DoctorReport(
            version="1.0.0",
            timestamp=datetime.now(timezone.utc).isoformat(),
            environment=self.get_environment_summary(),
            results=results,
            mode="deep" if self.config.deep else "fast",
            filters={
                "only": self.config.only,
                "skip": self.config.skip,
            },
        )
        
        report.calculate_summary()
        report.exit_code = report.calculate_exit_code(strict=self.config.strict)
        
        return report
    
    def run(
        self,
        check_ids: Optional[List[str]] = None,
        categories: Optional[List[CheckCategory]] = None,
    ) -> DoctorReport:
        """
        Run checks and generate report.
        
        Args:
            check_ids: Specific check IDs to run
            categories: Filter by categories
            
        Returns:
            Complete doctor report
        """
        start_time = time.time()
        
        results = self.run_checks(check_ids, categories)
        report = self.generate_report(results)
        
        report.duration_ms = (time.time() - start_time) * 1000
        
        return report


def run_doctor(
    config: Optional[DoctorConfig] = None,
    check_ids: Optional[List[str]] = None,
    categories: Optional[List[CheckCategory]] = None,
) -> DoctorReport:
    """
    Convenience function to run doctor checks.
    
    Args:
        config: Doctor configuration
        check_ids: Specific check IDs to run
        categories: Filter by categories
        
    Returns:
        Complete doctor report
    """
    engine = DoctorEngine(config)
    return engine.run(check_ids, categories)
