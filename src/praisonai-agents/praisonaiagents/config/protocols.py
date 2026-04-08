"""
Configuration Schema Protocols for PraisonAI Agents.

Core protocols for unified configuration schema validation and mapping.
These protocols define the contract for configuration schema providers
without heavy implementations (following protocol-driven architecture).
"""

from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable
from dataclasses import dataclass


@dataclass
class ValidationResult:
    """
    Result of configuration validation.
    
    Attributes:
        is_valid: Whether the configuration is valid
        errors: List of validation error messages
        warnings: List of validation warning messages
        normalized: Normalized configuration (after applying defaults, etc.)
    """
    is_valid: bool
    errors: List[str]
    warnings: List[str] = None
    normalized: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


@dataclass
class CliMapping:
    """
    Mapping between configuration field and CLI flag.
    
    Attributes:
        field_name: Name of the configuration field
        cli_flag: CLI flag name (without --)
        description: Help text for CLI flag
        type_hint: Python type for CLI argument parsing
        default: Default value if not provided
        choices: Valid choices for enum/choice fields
        env_var: Environment variable name (optional)
    """
    field_name: str
    cli_flag: str
    description: str
    type_hint: type
    default: Any = None
    choices: Optional[List[str]] = None
    env_var: Optional[str] = None


@dataclass
class PrecedenceChain:
    """
    Documented precedence chain for configuration resolution.
    
    Attributes:
        chain: List of source names in precedence order (highest to lowest)
        descriptions: Dict mapping source names to descriptions
    """
    chain: List[str]
    descriptions: Dict[str, str]
    
    def __post_init__(self):
        # Validate chain is non-empty
        if not self.chain:
            raise ValueError("Precedence chain cannot be empty")
        
        # Ensure all chain items have descriptions
        for source in self.chain:
            if source not in self.descriptions:
                self.descriptions[source] = f"Configuration from {source}"


@runtime_checkable
class ConfigSchemaProtocol(Protocol):
    """
    Protocol for configuration schema providers.
    
    Defines the interface for configuration schema validation, CLI mapping,
    and precedence chain documentation. Implementations should provide
    concrete schema validation and mapping logic.
    
    This protocol enables:
    - Schema-driven CLI generation
    - Guaranteed CLI/YAML/Python mapping
    - Single documented precedence chain
    - Strong validation with user-friendly errors
    """
    
    def validate(self, config: Dict[str, Any]) -> ValidationResult:
        """
        Validate configuration against schema.
        
        Args:
            config: Configuration dictionary to validate
            
        Returns:
            ValidationResult with validation status and any errors/warnings
        """
        ...
    
    def get_cli_mapping(self) -> List[CliMapping]:
        """
        Get CLI flag mappings derived from schema.
        
        Returns:
            List of CliMapping objects defining CLI flags
        """
        ...
    
    def get_precedence_chain(self) -> PrecedenceChain:
        """
        Get documented precedence chain for configuration resolution.
        
        Returns:
            PrecedenceChain defining resolution order and descriptions
        """
        ...
    
    def normalize_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize configuration by applying defaults and transformations.
        
        Args:
            config: Raw configuration dictionary
            
        Returns:
            Normalized configuration dictionary
        """
        ...
    
    def get_schema_info(self) -> Dict[str, Any]:
        """
        Get schema metadata for documentation and introspection.
        
        Returns:
            Dict containing schema information (fields, types, descriptions, etc.)
        """
        ...


@runtime_checkable
class ConfigMappingProtocol(Protocol):
    """
    Protocol for configuration field mapping and transformation.
    
    Handles mapping between different configuration interfaces:
    - YAML field names (e.g., 'role', 'backstory') 
    - Python API field names (e.g., 'name', 'instructions')
    - CLI flag names (e.g., '--agent-role', '--agent-backstory')
    """
    
    def yaml_to_python(self, yaml_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map YAML configuration to Python API format.
        
        Args:
            yaml_config: Configuration from YAML file
            
        Returns:
            Configuration mapped to Python API field names
        """
        ...
    
    def python_to_yaml(self, python_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map Python API configuration to YAML format.
        
        Args:
            python_config: Configuration from Python API
            
        Returns:
            Configuration mapped to YAML field names
        """
        ...
    
    def cli_to_python(self, cli_args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map CLI arguments to Python API format.
        
        Args:
            cli_args: Parsed CLI arguments
            
        Returns:
            Configuration mapped to Python API field names
        """
        ...
    
    def get_field_aliases(self) -> Dict[str, List[str]]:
        """
        Get field name aliases for backward compatibility.
        
        Returns:
            Dict mapping canonical field names to lists of aliases
        """
        ...


@runtime_checkable  
class ConfigValidatorProtocol(Protocol):
    """
    Protocol for configuration validation with helpful error messages.
    
    Provides detailed validation with suggestions for fixing common mistakes.
    """
    
    def validate_with_suggestions(self, config: Dict[str, Any]) -> ValidationResult:
        """
        Validate configuration with suggestions for fixing errors.
        
        Args:
            config: Configuration to validate
            
        Returns:
            ValidationResult with detailed error messages and suggestions
        """
        ...
    
    def suggest_corrections(self, field_name: str, invalid_value: Any) -> List[str]:
        """
        Suggest corrections for invalid field values.
        
        Args:
            field_name: Name of the invalid field
            invalid_value: The invalid value provided
            
        Returns:
            List of suggested corrections
        """
        ...
    
    def check_field_conflicts(self, config: Dict[str, Any]) -> List[str]:
        """
        Check for conflicting configuration fields.
        
        Args:
            config: Configuration to check
            
        Returns:
            List of conflict error messages
        """
        ...


@runtime_checkable
class ConfigMergerProtocol(Protocol):
    """
    Protocol for merging configurations from multiple sources with precedence.
    
    Implements the single documented precedence chain for config resolution.
    """
    
    def merge_configs(
        self, 
        sources: Dict[str, Dict[str, Any]],
        precedence_chain: List[str]
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Merge configurations from multiple sources with precedence.
        
        Args:
            sources: Dict mapping source names to configuration dicts
            precedence_chain: List of source names in precedence order (highest to lowest)
            
        Returns:
            Tuple of (merged_config, resolution_log)
        """
        ...
    
    def resolve_conflicts(
        self,
        field_name: str,
        values: Dict[str, Any]
    ) -> Tuple[Any, str]:
        """
        Resolve conflicts between multiple values for a field.
        
        Args:
            field_name: Name of the conflicting field
            values: Dict mapping source names to values
            
        Returns:
            Tuple of (resolved_value, resolution_reason)
        """
        ...