"""
Template Loader

Loads and materializes templates into Agent/Workflow configurations.
Handles TEMPLATE.yaml parsing, config merging, and skills integration.
"""

import os
import re
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from .resolver import ResolvedTemplate  # noqa: F401 - used by registry
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
    
    # Runtime configuration (background/job/schedule)
    runtime: Optional[Any] = None  # RuntimeConfig, lazy loaded
    
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
        """Parse TEMPLATE.yaml file, or extract metadata from agents.yaml if absent."""
        import yaml
        
        template_file = template_dir / self.TEMPLATE_FILE
        
        if not template_file.exists():
            # Try to extract metadata from agents.yaml (simplified 2-file structure)
            agents_file = template_dir / "agents.yaml"
            if agents_file.exists():
                return self._parse_agents_yaml_metadata(template_dir, agents_file)
            
            # Fallback to directory name
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
        
        # Handle workflow - can be inline dict or file reference string
        workflow = raw.get("workflow", "workflow.yaml")
        
        # Handle agents - can be inline list or file reference string
        agents = raw.get("agents", "agents.yaml")
        
        # Parse runtime configuration (lazy import to avoid circular deps)
        runtime = None
        if "runtime" in raw:
            from praisonai.recipe.runtime import parse_runtime_config
            runtime = parse_runtime_config(raw.get("runtime"), expand_env=True)
        
        return TemplateConfig(
            name=raw.get("name", template_dir.name),
            description=raw.get("description", ""),
            version=raw.get("version", "1.0.0"),
            author=raw.get("author"),
            license=raw.get("license"),
            tags=raw.get("tags", []),
            requires=requires,
            workflow_file=workflow,
            agents_file=agents,
            config_schema=raw.get("config", {}),
            defaults=raw.get("defaults", {}),
            skills=raw.get("skills", []),
            cli=raw.get("cli", {}),
            runtime=runtime,
            raw=raw,
            path=template_dir
        )
    
    def _parse_agents_yaml_metadata(
        self,
        template_dir: Path,
        agents_file: Path
    ) -> TemplateConfig:
        """
        Extract metadata from agents.yaml for simplified 2-file recipe structure.
        
        Supports optional 'metadata' block in agents.yaml:
        ```yaml
        metadata:
          name: my-recipe
          version: "1.0.0"
          description: What this recipe does
          author: author-name
          license: MIT
          tags: [tag1, tag2]
          requires:
            env: [API_KEY]
        
        framework: praisonai
        agents:
          ...
        ```
        
        Args:
            template_dir: Path to the template directory
            agents_file: Path to agents.yaml file
            
        Returns:
            TemplateConfig with metadata extracted from agents.yaml
        """
        import yaml
        
        with open(agents_file) as f:
            raw = yaml.safe_load(f) or {}
        
        # Extract metadata block if present
        metadata = raw.get("metadata", {})
        
        # Extract requires from metadata
        requires = metadata.get("requires", {})
        if isinstance(requires, list):
            requires = {"tools": requires}
        
        # Use agents.yaml as the workflow file (it contains agents and steps)
        workflow_file = "agents.yaml"
        agents_file_ref = "agents.yaml"
        
        # Build raw config for compatibility
        raw_config = {
            **raw,
            "name": metadata.get("name", template_dir.name),
            "version": metadata.get("version", "1.0.0"),
            "description": metadata.get("description", ""),
            "author": metadata.get("author"),
            "license": metadata.get("license"),
            "tags": metadata.get("tags", []),
            "requires": requires,
        }
        
        return TemplateConfig(
            name=metadata.get("name", template_dir.name),
            description=metadata.get("description", ""),
            version=metadata.get("version", "1.0.0"),
            author=metadata.get("author"),
            license=metadata.get("license"),
            tags=metadata.get("tags", []),
            requires=requires,
            workflow_file=workflow_file,
            agents_file=agents_file_ref,
            config_schema=metadata.get("config", {}),
            defaults=metadata.get("defaults", {}),
            skills=raw.get("skills", []),
            cli=metadata.get("cli", {}),
            runtime=None,
            raw=raw_config,
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
        
        Supports:
        - Inline workflow definition in TEMPLATE.yaml (workflow: {agents: [...], tasks: [...]})
        - Separate workflow file reference (workflow: "workflow.yaml")
        """
        import yaml
        
        # Check if workflow is inline (dict) or a file reference (string)
        if isinstance(template.workflow_file, dict):
            # Inline workflow definition
            config = template.workflow_file
        elif isinstance(template.workflow_file, str):
            # File reference
            workflow_file = template.path / template.workflow_file
            
            if not workflow_file.exists():
                # Check if workflow is in raw config
                if "workflow" in template.raw and isinstance(template.raw["workflow"], dict):
                    config = template.raw["workflow"]
                else:
                    raise ValueError(f"Workflow file not found: {workflow_file}")
            else:
                with open(workflow_file) as f:
                    config = yaml.safe_load(f) or {}
        else:
            raise ValueError(f"Invalid workflow configuration type: {type(template.workflow_file)}")
        
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
        """
        Recursively substitute variables in config with sentinel protection.
        
        This method implements a secure multi-phase substitution strategy:
        1. Generate a unique sentinel token for this render
        2. Protect user-provided variable values that contain {{...}} syntax
        3. Perform template variable substitution on the config
        4. Restore protected values
        
        This prevents user input containing {{variable}} syntax from being
        interpreted as template variables (injection protection).
        """
        if isinstance(config, str):
            # Generate per-render unique sentinel to prevent collision attacks
            sentinel_id = secrets.token_hex(8)
            sentinel_prefix = f"__PRAISONAI_SENTINEL_{sentinel_id}_"
            
            # Phase 1: Protect variable values that contain template syntax
            protected_values, safe_variables = self._protect_variable_values(
                variables, sentinel_prefix
            )
            
            # Phase 2: Perform substitution with safe values
            pattern = r'\{\{(\w+)\}\}'
            
            def replace(match):
                var_name = match.group(1)
                return str(safe_variables.get(var_name, match.group(0)))
            
            result = re.sub(pattern, replace, config)
            
            # Phase 3: Restore protected values
            result = self._restore_protected_values(result, protected_values)
            
            return result
        
        elif isinstance(config, dict):
            return {k: self._substitute_variables(v, variables) for k, v in config.items()}
        
        elif isinstance(config, list):
            return [self._substitute_variables(item, variables) for item in config]
        
        return config
    
    def _protect_variable_values(
        self,
        variables: Dict[str, Any],
        sentinel_prefix: str
    ) -> Tuple[Dict[str, str], Dict[str, Any]]:
        """
        Protect variable values that contain template syntax.
        
        Args:
            variables: Original variable dict
            sentinel_prefix: Unique prefix for this render
            
        Returns:
            Tuple of (protected_values mapping, safe_variables dict)
        """
        protected_values = {}  # sentinel -> original value
        safe_variables = {}
        
        template_pattern = re.compile(r'\{\{.*?\}\}')
        
        for key, value in variables.items():
            if isinstance(value, str) and template_pattern.search(value):
                # This value contains template syntax - protect it
                sentinel = f"{sentinel_prefix}{key}__"
                protected_values[sentinel] = value
                safe_variables[key] = sentinel
            else:
                safe_variables[key] = value
        
        return protected_values, safe_variables
    
    def _restore_protected_values(
        self,
        content: str,
        protected_values: Dict[str, str]
    ) -> str:
        """
        Restore protected values after substitution.
        
        Args:
            content: Content with sentinel tokens
            protected_values: Mapping of sentinel -> original value
            
        Returns:
            Content with sentinels replaced by original values
        """
        for sentinel, original in protected_values.items():
            content = content.replace(sentinel, original)
        return content
    
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
    Create a Agents team from a template.
    
    Args:
        uri: Template URI
        config: Optional config overrides
        offline: If True, only use cache
        **agents_kwargs: Additional Agents constructor arguments
        
    Returns:
        Configured Agents instance
    """
    loader = TemplateLoader(offline=offline)
    template = loader.load(uri, config=config, offline=offline)
    
    # Load workflow config (contains agents and tasks)
    workflow_config = loader.load_workflow_config(template)
    
    # Import Agents lazily
    from praisonaiagents import AgentManager
    
    # Merge with kwargs
    final_config = {**workflow_config, **agents_kwargs}
    
    return AgentManager(**final_config)
