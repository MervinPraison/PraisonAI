"""
Unified Configuration Schema for PraisonAI CLI/YAML/Python interfaces.

Implements the ConfigSchemaProtocol to provide a single source of truth
for configuration validation, CLI generation, and field mapping across
all three interface modes (CLI, YAML, Python).

This is the heavy implementation in the wrapper layer that builds on
the lightweight protocols from the core SDK.
"""

import os
import re
from dataclasses import asdict, fields, is_dataclass
from typing import Any, Dict, List, Optional, Set, Type, Union
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

try:
    from pydantic import BaseModel, Field, ValidationError
    try:
        # Pydantic V2
        from pydantic import field_validator
        PYDANTIC_V2 = True
    except ImportError:
        # Pydantic V1  
        from pydantic import validator as field_validator
        PYDANTIC_V2 = False
except ImportError:
    BaseModel = None
    Field = None
    ValidationError = None
    field_validator = None
    PYDANTIC_V2 = False

try:
    from praisonaiagents.config.protocols import (
        ConfigSchemaProtocol,
        ConfigMappingProtocol,
        ValidationResult,
        CliMapping,
        PrecedenceChain,
    )
    from praisonaiagents.rag.models import RAGConfig, RetrievalStrategy
except ImportError:
    # Fallback when praisonaiagents not available
    from dataclasses import dataclass
    from typing import Protocol, runtime_checkable
    from enum import Enum
    
    @dataclass
    class ValidationResult:
        is_valid: bool
        errors: List[str]
        warnings: List[str]
        normalized: Optional[Dict[str, Any]]
    
    @dataclass
    class CliMapping:
        field_name: str
        cli_flag: str
        description: str
        type_hint: type
        default: Any = None
        choices: Optional[List[str]] = None
        env_var: Optional[str] = None
    
    @dataclass
    class PrecedenceChain:
        chain: List[str]
        descriptions: Dict[str, str]
    
    @runtime_checkable
    class ConfigSchemaProtocol(Protocol):
        def validate(self, config: Dict[str, Any]) -> ValidationResult: ...
        def get_cli_mapping(self) -> List[CliMapping]: ...
        def get_precedence_chain(self) -> PrecedenceChain: ...
        def normalize_config(self, config: Dict[str, Any]) -> Dict[str, Any]: ...
    
    @runtime_checkable
    class ConfigMappingProtocol(Protocol):
        def cli_to_python(self, cli_config: Dict[str, Any]) -> Dict[str, Any]: ...
        def yaml_to_python(self, yaml_config: Dict[str, Any]) -> Dict[str, Any]: ...
    
    # Lightweight enum fallbacks
    class RetrievalStrategy(Enum):
        semantic = "semantic"
        keyword = "keyword"
        hybrid = "hybrid"
    
    # Placeholder for RAGConfig
    @dataclass
    class RAGConfig:
        collection: str = "default"


if BaseModel:
    class UnifiedRAGSchema(BaseModel):
        """
        Unified RAG schema that serves as single source of truth.
        
        This Pydantic model provides:
        - Schema validation for all three interfaces
        - Auto-generation of CLI flags from field annotations
        - Field mapping between CLI/YAML/Python naming conventions
        - Strong validation with user-friendly error messages
        """
        
        # Collection settings
        collection: str = Field(
            default="default",
            description="Collection/index name for vector storage"
        )
        
        # Retrieval settings
        top_k: int = Field(
            default=5,
            ge=1,
            le=100,
            description="Number of documents to retrieve"
        )
        
        hybrid: bool = Field(
            default=False,
            description="Enable hybrid retrieval (dense + sparse)"
        )
        
        rerank: bool = Field(
            default=False,
            description="Enable reranking of retrieved results"
        )
        
        min_score: float = Field(
            default=0.0,
            ge=0.0,
            le=1.0,
            description="Minimum relevance score threshold"
        )
        
        # RAG settings
        include_citations: bool = Field(
            default=True,
            description="Include source citations in responses"
        )
        
        max_context_tokens: int = Field(
            default=4000,
            ge=100,
            le=100000,
            description="Maximum tokens for context window"
        )
        
        # Vector store settings
        vector_store_provider: str = Field(
            default="chroma",
            description="Vector store provider (chroma, pinecone, etc.)"
        )
        
        vector_store_path: Optional[str] = Field(
            default=None,
            description="Path to vector store data"
        )
        
        # Server settings
        host: str = Field(
            default="127.0.0.1",
            description="Server host address"
        )
        
        port: int = Field(
            default=8080,
            ge=1000,
            le=65535,
            description="Server port number"
        )
        
        openai_compat: bool = Field(
            default=False,
            description="Enable OpenAI-compatible API endpoint"
        )
        
        # LLM settings
        model: Optional[str] = Field(
            default=None,
            description="LLM model to use (defaults to gpt-4o-mini)"
        )
        
        # Misc
        verbose: bool = Field(
            default=False,
            description="Enable verbose output"
        )
        
        if PYDANTIC_V2:
            @field_validator('vector_store_provider')
            @classmethod
            def validate_provider(cls, v):
                valid_providers = ['chroma', 'pinecone', 'weaviate', 'qdrant']
                if v not in valid_providers:
                    raise ValueError(f"Invalid provider '{v}'. Valid options: {', '.join(valid_providers)}")
                return v
            
            @field_validator('model')
            @classmethod  
            def validate_model(cls, v):
                if v is not None and not isinstance(v, str):
                    raise ValueError("Model must be a string")
                return v
        else:
            @field_validator('vector_store_provider')
            def validate_provider(cls, v):
                valid_providers = ['chroma', 'pinecone', 'weaviate', 'qdrant']
                if v not in valid_providers:
                    raise ValueError(f"Invalid provider '{v}'. Valid options: {', '.join(valid_providers)}")
                return v
            
            @field_validator('model')
            def validate_model(cls, v):
                if v is not None and not isinstance(v, str):
                    raise ValueError("Model must be a string")
                return v
        
        def to_rag_config(self) -> 'RAGConfig':
            """Convert to core SDK RAGConfig."""
            # Map unified schema to core SDK format
            strategy = RetrievalStrategy.HYBRID if self.hybrid else RetrievalStrategy.BASIC
            
            return RAGConfig(
                top_k=self.top_k,
                min_score=self.min_score,
                max_context_tokens=self.max_context_tokens,
                include_citations=self.include_citations,
                retrieval_strategy=strategy,
                rerank=self.rerank,
                model=self.model,
            )
        
        def to_knowledge_config(self) -> Dict[str, Any]:
            """Convert to knowledge config format."""
            path = self.vector_store_path or f"./.praison/knowledge/{self.collection}"
            
            config = {
                "vector_store": {
                    "provider": self.vector_store_provider,
                    "config": {
                        "collection_name": self.collection,
                        "path": path,
                    }
                }
            }
            
            if self.hybrid:
                config["retrieval"] = {
                    "strategy": "hybrid",
                }
            
            return config


class RAGSchemaProvider:
    """
    Schema provider implementing ConfigSchemaProtocol for RAG configuration.
    
    Provides unified configuration validation, CLI mapping, and field mapping
    across CLI, YAML, and Python interfaces.
    """
    
    def __init__(self):
        self.schema_class = UnifiedRAGSchema if BaseModel else None
        
        # Field name mappings between interfaces
        self.yaml_to_python_map = {
            # Keep most fields the same, but handle special cases
            "vector_store": "vector_store_provider",
            "vector_path": "vector_store_path",
            "citations": "include_citations",
        }
        
        # CLI flag mappings - these will be derived from schema when possible
        self._cli_flag_map = {
            "collection": "collection",
            "top-k": "top_k", 
            "hybrid": "hybrid",
            "rerank": "rerank",
            "min-score": "min_score",
            "citations": "include_citations",
            "max-context": "max_context_tokens",
            "vector-store": "vector_store_provider",
            "vector-path": "vector_store_path",
            "host": "host",
            "port": "port", 
            "openai-compat": "openai_compat",
            "model": "model",
            "verbose": "verbose",
        }
        
        # Environment variable mappings
        self.env_var_map = {
            "PRAISONAI_COLLECTION": "collection",
            "PRAISONAI_TOP_K": "top_k",
            "PRAISONAI_HYBRID": "hybrid", 
            "PRAISONAI_RERANK": "rerank",
            "PRAISONAI_MIN_SCORE": "min_score",
            "PRAISONAI_CITATIONS": "include_citations",
            "PRAISONAI_MAX_CONTEXT_TOKENS": "max_context_tokens",
            "PRAISONAI_VECTOR_STORE": "vector_store_provider",
            "PRAISONAI_VECTOR_STORE_PATH": "vector_store_path",
            "PRAISONAI_HOST": "host",
            "PRAISONAI_PORT": "port",
            "PRAISONAI_OPENAI_COMPAT": "openai_compat",
            "PRAISONAI_MODEL": "model",
            "PRAISONAI_VERBOSE": "verbose",
        }
    
    def validate(self, config: Dict[str, Any]) -> ValidationResult:
        """Validate configuration using Pydantic schema."""
        if not BaseModel:
            # Fallback validation without Pydantic
            return ValidationResult(
                is_valid=True,
                errors=[],
                warnings=["Pydantic not available - validation limited"],
                normalized=config
            )
        
        # Check for unknown fields first
        known_fields = set()
        if PYDANTIC_V2:
            known_fields = set(self.schema_class.model_fields.keys())
        else:
            known_fields = set(self.schema_class.__fields__.keys())
            
        unknown_fields = set(config.keys()) - known_fields
        if unknown_fields:
            return ValidationResult(
                is_valid=False,
                errors=[f"Unknown field '{field}'. Valid fields: {', '.join(sorted(known_fields))}" for field in unknown_fields],
                warnings=[],
                normalized=None
            )
        
        try:
            # Create schema instance to validate
            schema_instance = self.schema_class(**config)
            # Use model_dump for V2, dict() for V1
            if PYDANTIC_V2:
                normalized = schema_instance.model_dump()
            else:
                normalized = schema_instance.dict()
            
            return ValidationResult(
                is_valid=True,
                errors=[],
                warnings=[],
                normalized=normalized
            )
            
        except ValidationError as e:
            errors = []
            for error in e.errors():
                field_path = ".".join(str(p) for p in error["loc"])
                msg = error["msg"]
                errors.append(f"{field_path}: {msg}")
            
            return ValidationResult(
                is_valid=False,
                errors=errors,
                warnings=[],
                normalized=None
            )
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                errors=[f"Validation failed: {str(e)}"],
                warnings=[],
                normalized=None
            )
    
    def get_cli_mapping(self) -> List[CliMapping]:
        """Generate CLI mappings derived from schema fields."""
        mappings = []
        
        if not BaseModel:
            # Fallback without Pydantic
            return self._get_fallback_cli_mapping()
        
        # Get field info - compatible with both Pydantic V1 and V2
        if PYDANTIC_V2:
            field_dict = self.schema_class.model_fields
        else:
            field_dict = self.schema_class.__fields__
            
        for field_name, field_info in field_dict.items():
            cli_flag = self._field_to_cli_flag(field_name)
            env_var = self._field_to_env_var(field_name)
            try:
                from pydantic_core import PydanticUndefinedType
                default = field_info.default
                if isinstance(default, PydanticUndefinedType):
                    default = None
            except ImportError:
                default = field_info.default if hasattr(field_info, 'default') else None
            
            mapping = CliMapping(
                field_name=field_name,
                cli_flag=cli_flag,
                description=field_info.description or f"Set {field_name}",
                type_hint=self._get_python_type(field_info),
                default=None,  # Use None for argparse - don't override precedence
                env_var=env_var
            )
            
            mappings.append(mapping)
        
        return mappings
    
    def get_precedence_chain(self) -> PrecedenceChain:
        """Get the documented precedence chain."""
        return PrecedenceChain(
            chain=["cli_flags", "env_vars", "config_file", "defaults"],
            descriptions={
                "cli_flags": "Command line arguments (highest priority)",
                "env_vars": "Environment variables (PRAISONAI_*)",
                "config_file": "YAML configuration file",
                "defaults": "Built-in default values (lowest priority)"
            }
        )
    
    def normalize_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize config by applying defaults and transformations."""
        # Apply field mappings
        normalized = self._apply_field_mappings(config)
        
        # Apply defaults
        if BaseModel:
            try:
                schema_instance = self.schema_class(**normalized)
                # Use model_dump for V2, dict() for V1
                if PYDANTIC_V2:
                    return schema_instance.model_dump()
                else:
                    return schema_instance.dict()
            except ValidationError:
                pass  # Fall through to manual defaults
        
        # Manual defaults as fallback
        defaults = {
            "collection": "default",
            "top_k": 5,
            "hybrid": False,
            "rerank": False,
            "min_score": 0.0,
            "include_citations": True,
            "max_context_tokens": 4000,
            "vector_store_provider": "chroma",
            "host": "127.0.0.1",
            "port": 8080,
            "openai_compat": False,
            "verbose": False,
        }
        
        result = defaults.copy()
        result.update(normalized)
        return result
    
    def get_schema_info(self) -> Dict[str, Any]:
        """Get schema metadata for documentation."""
        info = {
            "name": "RAGSchema",
            "description": "Unified schema for RAG/Knowledge configuration",
            "fields": {},
            "precedence": self.get_precedence_chain().chain,
            "cli_mappings": {},
            "env_mappings": self.env_var_map,
        }
        
        if BaseModel:
            # Get field info - compatible with both Pydantic V1 and V2
            if PYDANTIC_V2:
                field_dict = self.schema_class.model_fields
            else:
                field_dict = self.schema_class.__fields__
                
            for field_name, field_info in field_dict.items():
                # Handle field type - different between V1 and V2
                if PYDANTIC_V2:
                    field_type = str(field_info.annotation)
                    field_default = field_info.default
                else:
                    field_type = str(field_info.type_)
                    field_default = field_info.default
                    
                info["fields"][field_name] = {
                    "type": field_type,
                    "description": field_info.description,
                    "default": field_default,
                }
                info["cli_mappings"][self._field_to_cli_flag(field_name)] = field_name
        
        return info
    
    def yaml_to_python(self, yaml_config: Dict[str, Any]) -> Dict[str, Any]:
        """Map YAML field names to Python API format."""
        return self._apply_field_mappings(yaml_config, self.yaml_to_python_map)
    
    def cli_to_python(self, cli_args: Dict[str, Any]) -> Dict[str, Any]:
        """Map CLI arguments to Python API format.""" 
        python_config = {}
        
        for cli_flag, python_field in self._cli_flag_map.items():
            cli_key = cli_flag.replace("-", "_")  # argparse converts dashes to underscores
            if cli_key in cli_args and cli_args[cli_key] is not None:
                python_config[python_field] = cli_args[cli_key]
        
        return python_config
    
    def merge_with_precedence(
        self,
        cli_config: Dict[str, Any],
        env_config: Dict[str, Any], 
        file_config: Dict[str, Any],
        defaults: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Merge configurations following documented precedence: CLI > ENV > YAML > defaults."""
        result = defaults.copy()
        
        # Apply in precedence order (lowest to highest)
        for config in [file_config, env_config, cli_config]:
            for key, value in config.items():
                if value is not None:
                    result[key] = value
        
        return result
    
    def load_env_config(self) -> Dict[str, Any]:
        """Load configuration from environment variables."""
        env_config = {}
        
        for env_var, field_name in self.env_var_map.items():
            value = os.environ.get(env_var)
            if value is not None:
                # Type conversion based on field type
                env_config[field_name] = self._convert_env_value(field_name, value)
        
        return env_config
    
    def _field_to_cli_flag(self, field_name: str) -> str:
        """Convert field name to CLI flag format."""
        # Find mapping in predefined mappings
        for cli_flag, python_field in self._cli_flag_map.items():
            if python_field == field_name:
                return cli_flag
        
        # Fallback: convert snake_case to kebab-case
        return field_name.replace("_", "-")
    
    def _field_to_env_var(self, field_name: str) -> Optional[str]:
        """Convert field name to environment variable."""
        for env_var, python_field in self.env_var_map.items():
            if python_field == field_name:
                return env_var
        return None
    
    def _get_python_type(self, field_info) -> type:
        """Extract Python type from Pydantic v2 field info."""
        if not BaseModel:
            return str
            
        # Handle field type - different between V1 and V2
        if PYDANTIC_V2:
            if hasattr(field_info, 'annotation'):
                field_type = field_info.annotation
                if hasattr(field_type, '__origin__'):
                    # Handle Union types (like Optional)
                    if field_type.__origin__ is Union:
                        args = field_type.__args__
                        # Return first non-None type
                        for arg in args:
                            if arg is not type(None):
                                return arg
                return field_type
        else:
            if hasattr(field_info, 'type_'):
                field_type = field_info.type_
                if hasattr(field_type, '__origin__'):
                    # Handle Union types (like Optional)
                    if field_type.__origin__ is Union:
                        args = field_type.__args__
                        # Return first non-None type
                        for arg in args:
                            if arg is not type(None):
                                return arg
                return field_type
        return str
    
    def _apply_field_mappings(self, config: Dict[str, Any], mapping: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Apply field name mappings."""
        if not mapping:
            mapping = self.yaml_to_python_map
            
        result = config.copy()
        
        for old_name, new_name in mapping.items():
            if old_name in result:
                result[new_name] = result.pop(old_name)
        
        return result
    
    def _convert_env_value(self, field_name: str, value: str) -> Any:
        """Convert environment variable string to appropriate type."""
        # Boolean fields
        if field_name in ["hybrid", "rerank", "include_citations", "openai_compat", "verbose"]:
            return value.lower() in ("true", "1", "yes", "on")
        
        # Integer fields  
        if field_name in ["top_k", "max_context_tokens", "port"]:
            try:
                return int(value)
            except ValueError:
                return value
        
        # Float fields
        if field_name in ["min_score"]:
            try:
                return float(value)
            except ValueError:
                return value
        
        # String fields (default)
        return value
    
    def _get_fallback_cli_mapping(self) -> List[CliMapping]:
        """Fallback CLI mapping without Pydantic."""
        return [
            CliMapping("collection", "collection", "Collection name", str, None),
            CliMapping("top_k", "top-k", "Number of results", int, None),
            CliMapping("hybrid", "hybrid", "Enable hybrid retrieval", bool, None),
            CliMapping("rerank", "rerank", "Enable reranking", bool, None),
            CliMapping("min_score", "min-score", "Minimum relevance score", float, None),
            CliMapping("include_citations", "citations", "Include citations", bool, None),
            CliMapping("max_context_tokens", "max-context", "Max context tokens", int, None),
            CliMapping("vector_store_provider", "vector-store", "Vector store provider", str, None),
            CliMapping("host", "host", "Server host", str, None),
            CliMapping("port", "port", "Server port", int, None),
            CliMapping("model", "model", "LLM model", str, None),
            CliMapping("verbose", "verbose", "Verbose output", bool, None),
        ]


# Create global instance
rag_schema_provider = RAGSchemaProvider()