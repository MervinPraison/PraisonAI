"""
Template Loader

Loads and materializes templates into Agent/Workflow configurations.
Handles TEMPLATE.yaml parsing, config merging, and skills integration.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from .resolver import ResolvedTemplate, TemplateSource
from .cache import TemplateCache
from .registry import TemplateRegistry
from .security import TemplateSecurity


@dataclass
class TemplateConfig:
    """Parsed template configuration."""
    name: str
    description: str = ""
    version: str = "1.0.0"
    author: Optional[str] = None
    license: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    
    # Dependencies
    requires: Dict[str, Any] = field(default_factory=dict)
    
    # Entry points
    workflow_file: str = "workflow.yaml"
    agents_file: str = "agents.yaml"
    
    # Configuration schema
    config_schema: Dict[str, Any] = field(default_factory=dict)
    
    # Default configuration values
    defaults: Dict[str, Any] = field(default_factory=dict)
    
    # Skills to load
    skills: List[str] = field(default_factory=list)
    
    # CLI integration
    cli: Dict[str, Any] = field(default_factory=dict)
    
    # Raw config dict
    raw: Dict[str, Any] = field(default_factory=dict)
    
    # Source path
    path: Optional[Path] = None


class TemplateLoader:
    """
    Loads templates and materializes them into usable configurations.
    
    Supports:
    - TEMPLATE.yaml parsing
    - Config override merging
    - Skills integration
    - Workflow/Agent file loading
    """
    
    TEMPLATE_FILE = "TEMPLATE.yaml"
    
    def __init__(
        self,
        cache: Optional[TemplateCache] = None,
        registry: Optional[TemplateRegistry] = None,
        security: Optional[TemplateSecurity] = None,
        offline: bool = False
    ):
        """
        Initialize the loader.
        
        Args:
            cache: Template cache instance
            registry: Template registry instance
            security: Security handler instance
            offline: If True, only use cached templates
        """
        self.cache = cache or TemplateCache()
        self.registry = registry or TemplateRegistry(cache=self.cache, offline=offline)
        self.security = security or TemplateSecurity()
        self.offline = offline
    
    def load(
        self,
        uri: str,
        config: Optional[Dict[str, Any]] = None,
        offline: bool = False
    ) -> TemplateConfig:
        """
        Load a template by URI.
        
        Args:
            uri: Template URI
            config: Optional config overrides
            offline: If True, only use cache
            
        Returns:
            TemplateConfig with parsed configuration
            
        Raises:
            ValueError: If template not found or invalid
            SecurityError: If template fails security checks
        """
        # Security check
        if not self.security.is_source_allowed(uri):
            raise ValueError(f"Template source not allowed: {uri}")
        
        # Get template (from cache or remote)
        use_offline = offline or self.offline
        cached = self.registry.get_template(uri, offline=use_offline)
        
        # Validate security
        errors = self.security.validate_template_directory(cached.path)
        if errors:
            raise ValueError("Template security validation failed:\n" + "\n".join(errors))
        
        # Parse TEMPLATE.yaml
        template_config = self._parse_template_file(cached.path)
        template_config.path = cached.path
        
        # Merge config overrides
        if config:
            template_config = self._merge_config(template_config, config)
        
        return template_config
    
    def _parse_template_file(self, template_dir: Path) -> TemplateConfig:
        """Parse TEMPLATE.yaml file."""
        import yaml
        
        template_file = template_dir / self.TEMPLATE_FILE
        
        if not template_file.exists():
            # Try to infer from directory name
            return TemplateConfig(
                name=template_dir.name,
                path=template_dir
            )
        
        with open(template_file) as f:
            raw = yaml.safe_load(f) or {}
        
        # Sanitize config
        raw = self.security.sanitize_template_config(raw)
        
        # Extract requires
        requires = raw.get("requires", {})
        if isinstance(requires, list):
            requires = {"tools": requires}
        
        return TemplateConfig(
            name=raw.get("name", template_dir.name),
            description=raw.get("description", ""),
            version=raw.get("version", "1.0.0"),
            author=raw.get("author"),
            license=raw.get("license"),
            tags=raw.get("tags", []),
            requires=requires,
            workflow_file=raw.get("workflow", "workflow.yaml"),
            agents_file=raw.get("agents", "agents.yaml"),
            config_schema=raw.get("config", {}),
            defaults=raw.get("defaults", {}),
            skills=raw.get("skills", []),
            cli=raw.get("cli", {}),
            raw=raw,
            path=template_dir
        )
    
    def _merge_config(
        self,
        template: TemplateConfig,
        overrides: Dict[str, Any]
    ) -> TemplateConfig:
        """Merge config overrides into template config."""
        # Start with defaults
        merged = dict(template.defaults)
        
        # Apply overrides
        merged.update(overrides)
        
        # Update template
        template.defaults = merged
        
        return template
    
    def load_workflow_config(
        self,
        template: TemplateConfig
    ) -> Dict[str, Any]:
        """
        Load workflow configuration from template.
        
        Args:
            template: Parsed template config
            
        Returns:
            Workflow configuration dict
        """
        import yaml
        
        workflow_file = template.path / template.workflow_file
        
        if not workflow_file.exists():
            raise ValueError(f"Workflow file not found: {workflow_file}")
        
        with open(workflow_file) as f:
            config = yaml.safe_load(f) or {}
        
        # Substitute variables from template config
        config = self._substitute_variables(config, template.defaults)
        
        return config
    
    def load_agents_config(
        self,
        template: TemplateConfig
    ) -> Dict[str, Any]:
        """
        Load agents configuration from template.
        
        Args:
            template: Parsed template config
            
        Returns:
            Agents configuration dict
        """
        import yaml
        
        agents_file = template.path / template.agents_file
        
        if not agents_file.exists():
            # Try workflow file for inline agents
            return {}
        
        with open(agents_file) as f:
            config = yaml.safe_load(f) or {}
        
        # Substitute variables
        config = self._substitute_variables(config, template.defaults)
        
        return config
    
    def _substitute_variables(
        self,
        config: Any,
        variables: Dict[str, Any]
    ) -> Any:
        """Recursively substitute variables in config."""
        if isinstance(config, str):
            # Replace {{variable}} patterns
            import re
            pattern = r'\{\{(\w+)\}\}'
            
            def replace(match):
                var_name = match.group(1)
                return str(variables.get(var_name, match.group(0)))
            
            return re.sub(pattern, replace, config)
        
        elif isinstance(config, dict):
            return {k: self._substitute_variables(v, variables) for k, v in config.items()}
        
        elif isinstance(config, list):
            return [self._substitute_variables(item, variables) for item in config]
        
        return config
    
    def get_required_tools(self, template: TemplateConfig) -> List[str]:
        """Get list of required tools for a template."""
        tools = template.requires.get("tools", [])
        if isinstance(tools, str):
            tools = [tools]
        return tools
    
    def get_required_packages(self, template: TemplateConfig) -> List[str]:
        """Get list of required Python packages for a template."""
        packages = template.requires.get("packages", [])
        if isinstance(packages, str):
            packages = [packages]
        return packages
    
    def get_required_env(self, template: TemplateConfig) -> List[str]:
        """Get list of required environment variables for a template."""
        env = template.requires.get("env", [])
        if isinstance(env, str):
            env = [env]
        return env
    
    def check_requirements(
        self,
        template: TemplateConfig
    ) -> Dict[str, List[str]]:
        """
        Check if template requirements are satisfied.
        
        Returns:
            Dict with 'missing_packages', 'missing_env', 'missing_tools' lists
        """
        result = {
            "missing_packages": [],
            "missing_env": [],
            "missing_tools": []
        }
        
        # Check packages
        for package in self.get_required_packages(template):
            try:
                __import__(package.replace("-", "_"))
            except ImportError:
                result["missing_packages"].append(package)
        
        # Check environment variables
        for env_var in self.get_required_env(template):
            if not os.environ.get(env_var):
                result["missing_env"].append(env_var)
        
        return result


def load_template(
    uri: str,
    config: Optional[Dict[str, Any]] = None,
    offline: bool = False
) -> TemplateConfig:
    """
    Convenience function to load a template.
    
    Args:
        uri: Template URI
        config: Optional config overrides
        offline: If True, only use cache
        
    Returns:
        TemplateConfig with parsed configuration
    """
    loader = TemplateLoader(offline=offline)
    return loader.load(uri, config=config, offline=offline)


def create_agent_from_template(
    uri: str,
    config: Optional[Dict[str, Any]] = None,
    offline: bool = False,
    **agent_kwargs
):
    """
    Create an Agent from a template.
    
    Args:
        uri: Template URI
        config: Optional config overrides
        offline: If True, only use cache
        **agent_kwargs: Additional Agent constructor arguments
        
    Returns:
        Configured Agent instance
    """
    loader = TemplateLoader(offline=offline)
    template = loader.load(uri, config=config, offline=offline)
    
    # Load agents config
    agents_config = loader.load_agents_config(template)
    
    # Get first agent or use template defaults
    if agents_config and "agents" in agents_config:
        agent_list = list(agents_config["agents"].values())
        if agent_list:
            agent_config = agent_list[0]
        else:
            agent_config = {}
    else:
        agent_config = {}
    
    # Merge with kwargs
    final_config = {**agent_config, **agent_kwargs}
    
    # Import Agent lazily
    from praisonaiagents import Agent
    
    # Handle skills
    if template.skills:
        final_config["skills"] = template.skills
    
    return Agent(**final_config)


def create_workflow_from_template(
    uri: str,
    config: Optional[Dict[str, Any]] = None,
    offline: bool = False,
    **workflow_kwargs
):
    """
    Create a Workflow from a template.
    
    Args:
        uri: Template URI
        config: Optional config overrides
        offline: If True, only use cache
        **workflow_kwargs: Additional Workflow constructor arguments
        
    Returns:
        Configured Workflow instance
    """
    loader = TemplateLoader(offline=offline)
    template = loader.load(uri, config=config, offline=offline)
    
    # Load workflow config
    workflow_config = loader.load_workflow_config(template)
    
    # Merge with kwargs
    final_config = {**workflow_config, **workflow_kwargs}
    
    # Import Workflow lazily
    from praisonaiagents import Workflow
    
    return Workflow(**final_config)


def create_agents_from_template(
    uri: str,
    config: Optional[Dict[str, Any]] = None,
    offline: bool = False,
    **agents_kwargs
):
    """
    Create a PraisonAIAgents team from a template.
    
    Args:
        uri: Template URI
        config: Optional config overrides
        offline: If True, only use cache
        **agents_kwargs: Additional PraisonAIAgents constructor arguments
        
    Returns:
        Configured PraisonAIAgents instance
    """
    loader = TemplateLoader(offline=offline)
    template = loader.load(uri, config=config, offline=offline)
    
    # Load workflow config (contains agents and tasks)
    workflow_config = loader.load_workflow_config(template)
    
    # Import PraisonAIAgents lazily
    from praisonaiagents import PraisonAIAgents
    
    # Merge with kwargs
    final_config = {**workflow_config, **agents_kwargs}
    
    return PraisonAIAgents(**final_config)
