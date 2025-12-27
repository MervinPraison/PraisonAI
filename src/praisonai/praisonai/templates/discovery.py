"""
Template Discovery

Discovers templates from multiple directories with precedence support.
Supports custom user directories, built-in templates, and package templates.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class DiscoveredTemplate:
    """Information about a discovered template."""
    name: str
    path: Path
    source: str  # 'custom', 'builtin', 'package'
    priority: int  # Lower = higher priority
    
    # Optional metadata (loaded lazily)
    description: Optional[str] = None
    version: Optional[str] = None
    author: Optional[str] = None


class TemplateDiscovery:
    """
    Discovers templates from multiple directories with precedence.
    
    Search order (highest to lowest priority):
    1. User custom directory (~/.praison/templates)
    2. XDG config directory (~/.config/praison/templates)
    3. Project local directory (./.praison/templates)
    4. Built-in package templates (agent_recipes)
    
    Templates in higher priority directories override those in lower priority.
    """
    
    # Default search paths (in priority order)
    DEFAULT_SEARCH_PATHS = [
        ("~/.praison/templates", "custom", 1),
        ("~/.config/praison/templates", "custom", 2),
        ("./.praison/templates", "project", 3),
    ]
    
    TEMPLATE_FILE = "TEMPLATE.yaml"
    
    def __init__(
        self,
        custom_dirs: Optional[List[str]] = None,
        include_package: bool = True,
        include_defaults: bool = True
    ):
        """
        Initialize template discovery.
        
        Args:
            custom_dirs: Additional custom directories to search (highest priority)
            include_package: Whether to include package templates (agent_recipes)
            include_defaults: Whether to include default search paths
        """
        self.search_paths: List[Tuple[Path, str, int]] = []
        
        # Add custom directories first (highest priority)
        if custom_dirs:
            for i, dir_path in enumerate(custom_dirs):
                expanded = Path(os.path.expanduser(dir_path))
                self.search_paths.append((expanded, "custom", i))
        
        # Add default search paths
        if include_defaults:
            base_priority = len(custom_dirs) if custom_dirs else 0
            for path, source, priority in self.DEFAULT_SEARCH_PATHS:
                expanded = Path(os.path.expanduser(path))
                self.search_paths.append((expanded, source, base_priority + priority))
        
        self.include_package = include_package
        self._package_path: Optional[Path] = None
    
    @property
    def package_templates_path(self) -> Optional[Path]:
        """Get path to package templates (lazy loaded)."""
        if self._package_path is None and self.include_package:
            try:
                import importlib.resources
                try:
                    # Python 3.9+
                    ref = importlib.resources.files("agent_recipes") / "templates"
                    self._package_path = Path(str(ref))
                except (TypeError, AttributeError):
                    # Fallback for older Python
                    import agent_recipes
                    self._package_path = Path(agent_recipes.__file__).parent / "templates"
            except ImportError:
                pass
        return self._package_path
    
    def discover_all(self) -> Dict[str, DiscoveredTemplate]:
        """
        Discover all templates from all search paths.
        
        Returns:
            Dict mapping template name to DiscoveredTemplate.
            When duplicates exist, higher priority wins.
        """
        templates: Dict[str, DiscoveredTemplate] = {}
        
        # Scan search paths in reverse priority order (lowest first)
        # so that higher priority overwrites lower
        all_paths = list(self.search_paths)
        
        # Add package templates with lowest priority
        if self.include_package and self.package_templates_path:
            max_priority = max((p[2] for p in all_paths), default=0) + 1
            all_paths.append((self.package_templates_path, "package", max_priority))
        
        # Sort by priority descending (lowest priority first)
        all_paths.sort(key=lambda x: x[2], reverse=True)
        
        for dir_path, source, priority in all_paths:
            if dir_path.exists() and dir_path.is_dir():
                discovered = self._scan_directory(dir_path, source, priority)
                # Higher priority overwrites lower
                templates.update(discovered)
        
        return templates
    
    def _scan_directory(
        self,
        directory: Path,
        source: str,
        priority: int
    ) -> Dict[str, DiscoveredTemplate]:
        """
        Scan a directory for templates (shallow scan).
        
        Only looks at direct subdirectories containing TEMPLATE.yaml.
        Does NOT recursively scan nested directories.
        
        Args:
            directory: Directory to scan
            source: Source identifier ('custom', 'builtin', 'package')
            priority: Priority level
            
        Returns:
            Dict mapping template name to DiscoveredTemplate
        """
        templates = {}
        
        try:
            for item in directory.iterdir():
                if item.is_dir():
                    template_file = item / self.TEMPLATE_FILE
                    workflow_file = item / "workflow.yaml"
                    
                    # A valid template has TEMPLATE.yaml or workflow.yaml
                    if template_file.exists() or workflow_file.exists():
                        template = DiscoveredTemplate(
                            name=item.name,
                            path=item,
                            source=source,
                            priority=priority
                        )
                        
                        # Load basic metadata if TEMPLATE.yaml exists
                        if template_file.exists():
                            self._load_template_metadata(template, template_file)
                        
                        templates[item.name] = template
        except PermissionError:
            pass  # Skip directories we can't read
        
        return templates
    
    def _load_template_metadata(
        self,
        template: DiscoveredTemplate,
        template_file: Path
    ) -> None:
        """Load basic metadata from TEMPLATE.yaml."""
        try:
            import yaml
            with open(template_file) as f:
                data = yaml.safe_load(f) or {}
            
            template.description = data.get("description", "")
            template.version = data.get("version", "1.0.0")
            template.author = data.get("author")
        except Exception:
            pass  # Metadata loading is optional
    
    def find_template(self, name: str) -> Optional[DiscoveredTemplate]:
        """
        Find a template by name.
        
        Searches all directories in priority order and returns the
        highest priority match.
        
        Args:
            name: Template name to find
            
        Returns:
            DiscoveredTemplate if found, None otherwise
        """
        all_templates = self.discover_all()
        return all_templates.get(name)
    
    def resolve_template_path(self, name: str) -> Optional[Path]:
        """
        Resolve a template name to its path.
        
        Args:
            name: Template name
            
        Returns:
            Path to template directory, or None if not found
        """
        template = self.find_template(name)
        return template.path if template else None
    
    def list_templates(
        self,
        source_filter: Optional[str] = None
    ) -> List[DiscoveredTemplate]:
        """
        List all discovered templates.
        
        Args:
            source_filter: Optional filter by source ('custom', 'package', etc.)
            
        Returns:
            List of DiscoveredTemplate objects
        """
        templates = self.discover_all()
        
        if source_filter:
            return [t for t in templates.values() if t.source == source_filter]
        
        return list(templates.values())
    
    def get_search_paths(self) -> List[Tuple[str, str, bool]]:
        """
        Get all search paths with their status.
        
        Returns:
            List of (path, source, exists) tuples
        """
        paths = []
        
        for dir_path, source, _ in self.search_paths:
            paths.append((str(dir_path), source, dir_path.exists()))
        
        if self.include_package and self.package_templates_path:
            paths.append((
                str(self.package_templates_path),
                "package",
                self.package_templates_path.exists()
            ))
        
        return paths


# Convenience functions
def discover_templates(
    custom_dirs: Optional[List[str]] = None
) -> Dict[str, DiscoveredTemplate]:
    """
    Discover all templates from default and custom directories.
    
    Args:
        custom_dirs: Additional custom directories to search
        
    Returns:
        Dict mapping template name to DiscoveredTemplate
    """
    discovery = TemplateDiscovery(custom_dirs=custom_dirs)
    return discovery.discover_all()


def find_template_path(
    name: str,
    custom_dirs: Optional[List[str]] = None
) -> Optional[Path]:
    """
    Find a template by name and return its path.
    
    Args:
        name: Template name
        custom_dirs: Additional custom directories to search
        
    Returns:
        Path to template directory, or None if not found
    """
    discovery = TemplateDiscovery(custom_dirs=custom_dirs)
    return discovery.resolve_template_path(name)
