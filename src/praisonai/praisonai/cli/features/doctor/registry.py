"""
Check registry for the Doctor CLI module.

Manages registration and discovery of doctor checks.
"""

from typing import Callable, Dict, List, Optional, Set
from .models import CheckDefinition, CheckCategory, CheckSeverity, CheckResult


class CheckRegistry:
    """
    Registry for doctor checks.
    
    Manages check definitions and their implementations.
    """
    
    _instance: Optional["CheckRegistry"] = None
    
    def __new__(cls) -> "CheckRegistry":
        """Singleton pattern for global registry."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._checks: Dict[str, CheckDefinition] = {}
            cls._instance._implementations: Dict[str, Callable] = {}
            cls._instance._initialized = False
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> "CheckRegistry":
        """Get the singleton instance."""
        return cls()
    
    @classmethod
    def reset(cls) -> None:
        """Reset the registry (for testing)."""
        cls._instance = None
    
    def register(
        self,
        id: str,
        title: str,
        description: str,
        category: CheckCategory,
        implementation: Callable,
        severity: CheckSeverity = CheckSeverity.MEDIUM,
        requires_deep: bool = False,
        dependencies: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        """
        Register a doctor check.
        
        Args:
            id: Unique identifier (snake_case)
            title: Human-readable title
            description: Short description of what the check does
            category: Check category
            implementation: Callable that performs the check
            severity: Severity level
            requires_deep: Whether this check requires --deep mode
            dependencies: List of check IDs this check depends on
            tags: Optional tags for filtering
        """
        definition = CheckDefinition(
            id=id,
            title=title,
            description=description,
            category=category,
            severity=severity,
            requires_deep=requires_deep,
            dependencies=dependencies or [],
            tags=tags or [],
        )
        self._checks[id] = definition
        self._implementations[id] = implementation
    
    def get_check(self, id: str) -> Optional[CheckDefinition]:
        """Get a check definition by ID."""
        return self._checks.get(id)
    
    def get_implementation(self, id: str) -> Optional[Callable]:
        """Get a check implementation by ID."""
        return self._implementations.get(id)
    
    def get_all_checks(self) -> List[CheckDefinition]:
        """Get all registered checks."""
        return list(self._checks.values())
    
    def get_check_ids(self) -> List[str]:
        """Get all registered check IDs."""
        return list(self._checks.keys())
    
    def get_checks_by_category(self, category: CheckCategory) -> List[CheckDefinition]:
        """Get all checks in a category."""
        return [c for c in self._checks.values() if c.category == category]
    
    def get_checks_by_tag(self, tag: str) -> List[CheckDefinition]:
        """Get all checks with a specific tag."""
        return [c for c in self._checks.values() if tag in c.tags]
    
    def filter_checks(
        self,
        only: Optional[List[str]] = None,
        skip: Optional[List[str]] = None,
        categories: Optional[List[CheckCategory]] = None,
        deep_mode: bool = False,
    ) -> List[CheckDefinition]:
        """
        Filter checks based on criteria.
        
        Args:
            only: Only include these check IDs
            skip: Skip these check IDs
            categories: Only include checks in these categories
            deep_mode: Include checks that require deep mode
            
        Returns:
            Filtered list of check definitions
        """
        checks = list(self._checks.values())
        
        # Filter by only
        if only:
            only_set = set(only)
            checks = [c for c in checks if c.id in only_set]
        
        # Filter by skip
        if skip:
            skip_set = set(skip)
            checks = [c for c in checks if c.id not in skip_set]
        
        # Filter by categories
        if categories:
            checks = [c for c in checks if c.category in categories]
        
        # Filter by deep mode
        if not deep_mode:
            checks = [c for c in checks if not c.requires_deep]
        
        return checks
    
    def resolve_dependencies(self, check_ids: List[str]) -> List[str]:
        """
        Resolve check dependencies and return ordered list.
        
        Args:
            check_ids: List of check IDs to resolve
            
        Returns:
            Ordered list of check IDs with dependencies first
        """
        resolved: List[str] = []
        seen: Set[str] = set()
        
        def resolve(id: str) -> None:
            if id in seen:
                return
            seen.add(id)
            
            check = self._checks.get(id)
            if check:
                for dep in check.dependencies:
                    resolve(dep)
                resolved.append(id)
        
        for id in check_ids:
            resolve(id)
        
        return resolved
    
    def list_checks_text(self) -> str:
        """Generate text listing of all checks."""
        lines = ["Available Doctor Checks:", ""]
        
        # Group by category
        by_category: Dict[CheckCategory, List[CheckDefinition]] = {}
        for check in self._checks.values():
            if check.category not in by_category:
                by_category[check.category] = []
            by_category[check.category].append(check)
        
        for category in CheckCategory:
            if category in by_category:
                lines.append(f"  {category.value.upper()}:")
                for check in sorted(by_category[category], key=lambda c: c.id):
                    deep_marker = " [deep]" if check.requires_deep else ""
                    lines.append(f"    {check.id:<30} {check.description}{deep_marker}")
                lines.append("")
        
        return "\n".join(lines)


# Global registry instance
_registry = CheckRegistry()


def register_check(
    id: str,
    title: str,
    description: str,
    category: CheckCategory,
    severity: CheckSeverity = CheckSeverity.MEDIUM,
    requires_deep: bool = False,
    dependencies: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
):
    """
    Decorator to register a doctor check.
    
    Usage:
        @register_check(
            id="python_version",
            title="Python Version",
            description="Check Python version is 3.9+",
            category=CheckCategory.ENVIRONMENT,
        )
        def check_python_version(config: DoctorConfig) -> CheckResult:
            ...
    """
    def decorator(func: Callable) -> Callable:
        _registry.register(
            id=id,
            title=title,
            description=description,
            category=category,
            implementation=func,
            severity=severity,
            requires_deep=requires_deep,
            dependencies=dependencies,
            tags=tags,
        )
        return func
    return decorator


def get_registry() -> CheckRegistry:
    """Get the global check registry."""
    return _registry
