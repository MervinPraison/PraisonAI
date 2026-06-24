"""
Configuration validator with fail-fast validation and aggregated error reporting.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import ValidationError

from .schema import YAMLConfig, ValidationResult
from ..tool_resolver import ToolResolver


class ConfigValidator:
    """Validator for YAML configuration with schema and cross-reference validation."""
    
    def __init__(self, tool_resolver: Optional[ToolResolver] = None):
        """Initialize validator with optional tool resolver.
        
        Args:
            tool_resolver: Tool resolver for validating tool references
        """
        self.tool_resolver = tool_resolver
        if not self.tool_resolver:
            # Create a default tool resolver
            self.tool_resolver = ToolResolver()
    
    def validate_yaml_string(self, yaml_content: str, strict: bool = False) -> ValidationResult:
        """Validate YAML configuration from string.
        
        Args:
            yaml_content: YAML configuration as string
            strict: If True, treat warnings as errors
            
        Returns:
            ValidationResult with errors and warnings
        """
        try:
            config_dict = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            return ValidationResult(
                valid=False,
                errors=[f"YAML syntax error: {e}"]
            )
        
        return self.validate_config(config_dict, strict=strict)
    
    def validate_yaml_file(self, file_path: str, strict: bool = False) -> ValidationResult:
        """Validate YAML configuration from file.
        
        Args:
            file_path: Path to YAML file
            strict: If True, treat warnings as errors
            
        Returns:
            ValidationResult with errors and warnings
        """
        path = Path(file_path)
        
        if not path.exists():
            return ValidationResult(
                valid=False,
                errors=[f"File not found: {file_path}"]
            )
        
        try:
            with open(path, 'r') as f:
                config_dict = yaml.safe_load(f)
        except yaml.YAMLError as e:
            return ValidationResult(
                valid=False,
                errors=[f"YAML syntax error in {file_path}: {e}"]
            )
        except Exception as e:
            return ValidationResult(
                valid=False,
                errors=[f"Error reading file {file_path}: {e}"]
            )
        
        return self.validate_config(config_dict, strict=strict, file_path=file_path)
    
    def validate_config(self, config: Dict[str, Any], strict: bool = False, file_path: Optional[str] = None) -> ValidationResult:
        """Validate configuration dictionary.
        
        Args:
            config: Configuration dictionary
            strict: If True, treat warnings as errors
            file_path: Optional file path for better error messages
            
        Returns:
            ValidationResult with errors and warnings
        """
        errors = []
        warnings = []
        file_prefix = f"{file_path}: " if file_path else ""
        
        if config is None:
            return ValidationResult(
                valid=False,
                errors=[f"{file_prefix}Configuration is empty. Expected a YAML mapping at the root."]
            )
        if not isinstance(config, dict):
            return ValidationResult(
                valid=False,
                errors=[f"{file_prefix}Invalid root type '{type(config).__name__}'. Expected a YAML mapping/object."]
            )
        
        # Validate against schema
        try:
            yaml_config = YAMLConfig(**config)
        except ValidationError as e:
            # Parse Pydantic errors into readable messages
            for error in e.errors():
                field_path = '.'.join(str(x) for x in error['loc'])
                msg = f"{file_prefix}{field_path}: {error['msg']}"
                
                # Add context for common errors
                if error['type'] == 'missing':
                    msg += f" (required field)"
                elif error['type'] == 'type_error':
                    msg += f" (expected {error.get('ctx', {}).get('expected_type', 'different type')})"
                elif error['type'] == 'value_error':
                    if 'ctx' in error and 'error' in error['ctx']:
                        msg = f"{file_prefix}{field_path}: {error['ctx']['error']}"
                
                errors.append(msg)
            
            return ValidationResult(valid=False, errors=errors, warnings=warnings)
        
        # Validate cross-references
        cross_ref_errors = yaml_config.validate_cross_references()
        for error in cross_ref_errors:
            errors.append(f"{file_prefix}{error}")
        
        # Validate tool references
        tool_errors, tool_warnings = self._validate_tools(yaml_config, file_prefix)
        errors.extend(tool_errors)
        warnings.extend(tool_warnings)
        
        # Check for unknown fields (as warnings)
        unknown_warnings = self._check_unknown_fields(config, file_prefix)
        warnings.extend(unknown_warnings)
        
        # In strict mode, treat warnings as errors
        if strict and warnings:
            errors.extend([f"[strict mode] {w}" for w in warnings])
            warnings = []
        
        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    def _validate_tools(self, config: YAMLConfig, file_prefix: str = "") -> tuple[List[str], List[str]]:
        """Validate tool references in configuration.
        
        Args:
            config: Validated YAML configuration
            file_prefix: File path prefix for error messages
            
        Returns:
            Tuple of (errors, warnings)
        """
        errors = []
        warnings = []
        
        # Collect all tool references
        tool_refs = set()
        
        # Global tools
        if config.tools:
            tool_refs.update(config.tools)
        if config.toolsets:
            tool_refs.update(config.toolsets)
        
        # Agent tools
        for agents_dict in [config.roles, config.agents]:
            if agents_dict:
                for agent_name, agent in agents_dict.items():
                    if agent.tools:
                        tool_refs.update(agent.tools)
                    if agent.toolsets:
                        tool_refs.update(agent.toolsets)
                    if agent.planning_tools:
                        tool_refs.update(agent.planning_tools)
        
        # Task tools
        if config.tasks:
            for task in config.tasks:
                if task.tools:
                    tool_refs.update(task.tools)
        
        # Validate each tool reference
        for tool_name in tool_refs:
            try:
                # Try to resolve the tool
                resolved = self.tool_resolver.resolve_tool(tool_name)
                if resolved is None:
                    # Check if it might be a valid tool that's not installed
                    if self._is_known_optional_tool(tool_name):
                        warnings.append(
                            f"{file_prefix}Tool '{tool_name}' requires additional dependencies. "
                            f"Install with: pip install 'praisonai[tools]' or the specific tool package."
                        )
                    else:
                        errors.append(
                            f"{file_prefix}Unknown tool '{tool_name}'. "
                            f"Ensure it's properly installed or defined in your configuration."
                        )
            except Exception as e:
                # Tool resolution failed
                warnings.append(
                    f"{file_prefix}Could not validate tool '{tool_name}': {e}"
                )
        
        return errors, warnings
    
    def _is_known_optional_tool(self, tool_name: str) -> bool:
        """Check if a tool name is a known optional tool.
        
        Args:
            tool_name: Tool name to check
            
        Returns:
            True if it's a known optional tool
        """
        # List of known optional tools that require extra dependencies
        known_optional = {
            # Database tools
            'PostgreSQLTool', 'MySQLTool', 'SQLiteTool', 'MongoDBTool', 'RedisTool',
            'SurrealDBTool', 'CassandraTool', 'ElasticsearchTool',
            
            # Web/API tools
            'SlackTool', 'DiscordTool', 'TelegramTool', 'EmailTool',
            'TwitterTool', 'LinkedInTool', 'GitHubTool',
            
            # Cloud tools
            'AWSTool', 'AzureTool', 'GCPTool', 'S3Tool',
            
            # AI/ML tools
            'HuggingFaceTool', 'OpenAITool', 'AnthropicTool',
            
            # Data tools
            'PandasTool', 'NumpyTool', 'ScipyTool',
            
            # Other
            'BrowserTool', 'SeleniumTool', 'PlaywrightTool',
            'KubernetesTool', 'DockerTool', 'TerraformTool',
        }
        
        return tool_name in known_optional
    
    def _check_unknown_fields(self, config: Dict[str, Any], file_prefix: str = "") -> List[str]:
        """Check for unknown fields in configuration.
        
        Args:
            config: Raw configuration dictionary
            file_prefix: File path prefix for messages
            
        Returns:
            List of warnings about unknown fields
        """
        warnings = []
        
        # Known top-level fields
        known_top_level = {
            'name', 'description', 'framework', 'process', 'type',
            'roles', 'agents', 'tasks', 'workflow', 'steps',
            'input', 'topic', 'tools', 'toolsets',
            'config', 'llm', 'models', 'providers',
            'deploy',  # Deployment configuration
            'dependencies',  # Task dependency declarations
        }
        
        # Known agent/role fields
        known_agent_fields = {
            'role', 'goal', 'instructions', 'backstory', 'tools', 'toolsets', 'tasks', 'llm',
            'function_calling_llm', 'allow_delegation', 'max_iter', 'max_rpm',
            'max_execution_time', 'verbose', 'cache', 'system_template',
            'prompt_template', 'response_template', 'tool_timeout', 'tool_retry_policy',
            'planning_tools', 'planning', 'autonomy', 'guardrails', 'streaming', 'stream',
            'approval', 'skills', 'cli_backend', 'runtime', 'reflection', 'handoff',
            'web', 'web_fetch', 'name',  # Sometimes used as alias
        }
        
        # Check top-level unknown fields
        for field in config:
            if field not in known_top_level:
                warnings.append(
                    f"{file_prefix}Unknown top-level field '{field}'. "
                    f"This field will be ignored."
                )
        
        # Check agent/role fields
        for section in ['agents', 'roles']:
            if section in config and isinstance(config[section], dict):
                for agent_name, agent_config in config[section].items():
                    if isinstance(agent_config, dict):
                        for field in agent_config:
                            if field not in known_agent_fields:
                                warnings.append(
                                    f"{file_prefix}{section}.{agent_name}: Unknown field '{field}'. "
                                    f"This field will be ignored."
                                )
        
        return warnings