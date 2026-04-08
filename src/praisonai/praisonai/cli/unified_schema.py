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
    from pydantic import BaseModel, Field, ValidationError, field_validator
except ImportError:
    BaseModel = None
    Field = None
    ValidationError = None
    field_validator = None

from praisonaiagents.config.protocols import (
    ConfigSchemaProtocol,
    ConfigMappingProtocol,
    ValidationResult,
    CliMapping,
    PrecedenceChain,
)
from praisonaiagents.rag.models import RAGConfig, RetrievalStrategy



if BaseModel is not None:
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
        
        def to_rag_config(self) -> 'RAGConfig':
            """Convert to core SDK RAGConfig."""
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
else:
    UnifiedRAGSchema = None


class RAGSchemaProvider:
    """
    Schema provider implementing ConfigSchemaProtocol for RAG configuration.
    
    Provides unified configuration validation, CLI mapping, and field mapping
    across CLI, YAML, and Python interfaces.
    """
    
    def __init__(self):
        self.schema_class = UnifiedRAGSchema
        
        # Field name mappings between interfaces
        self.yaml_to_python_map = {
            # Keep most fields the same, but handle special cases
            "vector_store": "vector_store_provider",
            "vector_path": "vector_store_path",
            "citations": "include_citations",
        }
        
        self.cli_flag_map = {
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
        
        try:
            # Create schema instance to validate
            schema_instance = self.schema_class(**config)
            normalized = schema_instance.model_dump()
            
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
        """Generate CLI mappings from schema fields."""
        mappings = []
        
        if not BaseModel:
            # Fallback without Pydantic
            return self._get_fallback_cli_mapping()
        
        for field_name, field_info in self.schema_class.model_fields.items():
            cli_flag = self._field_to_cli_flag(field_name)
            env_var = self._field_to_env_var(field_name)
            from pydantic_core import PydanticUndefinedType
            default = field_info.default
            if isinstance(default, PydanticUndefinedType):
                default = None
            
            mapping = CliMapping(
                field_name=field_name,
                cli_flag=cli_flag,
                description=field_info.description or f"Set {field_name}",
                type_hint=self._get_python_type(field_info),
                default=default,
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
                return schema_instance.model_dump()
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
            from pydantic_core import PydanticUndefinedType
            for field_name, field_info in self.schema_class.model_fields.items():
                default = field_info.default
                if isinstance(default, PydanticUndefinedType):
                    default = None
                info["fields"][field_name] = {
                    "type": str(field_info.annotation),
                    "description": field_info.description,
                    "default": default,
                }
                info["cli_mappings"][self._field_to_cli_flag(field_name)] = field_name
        
        return info
    
    def yaml_to_python(self, yaml_config: Dict[str, Any]) -> Dict[str, Any]:
        """Map YAML field names to Python API format."""
        return self._apply_field_mappings(yaml_config, self.yaml_to_python_map)
    
    def cli_to_python(self, cli_args: Dict[str, Any]) -> Dict[str, Any]:
        """Map CLI arguments to Python API format.""" 
        python_config = {}
        
        for cli_flag, python_field in self.cli_flag_map.items():
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
        """Merge configurations following documented precedence."""
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
        # Convert snake_case to kebab-case and find mapping
        for cli_flag, python_field in self.cli_flag_map.items():
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
        
        annotation = getattr(field_info, 'annotation', None)
        if annotation is None:
            return str
        
        origin = getattr(annotation, '__origin__', None)
        if origin is Union:
            # Handle Optional types (Union[X, None])
            args = annotation.__args__
            for arg in args:
                if arg is not type(None):
                    return arg
        return annotation
    
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
            CliMapping("collection", "collection", "Collection name", str, "default"),
            CliMapping("top_k", "top-k", "Number of results", int, 5),
            CliMapping("hybrid", "hybrid", "Enable hybrid retrieval", bool, False),
            CliMapping("rerank", "rerank", "Enable reranking", bool, False),
            CliMapping("min_score", "min-score", "Minimum relevance score", float, 0.0),
            CliMapping("include_citations", "citations", "Include citations", bool, True),
            CliMapping("max_context_tokens", "max-context", "Max context tokens", int, 4000),
            CliMapping("vector_store_provider", "vector-store", "Vector store provider", str, "chroma"),
            CliMapping("host", "host", "Server host", str, "127.0.0.1"),
            CliMapping("port", "port", "Server port", int, 8080),
            CliMapping("model", "model", "LLM model", str, None),
            CliMapping("verbose", "verbose", "Verbose output", bool, False),
        ]


# Create global instance
rag_schema_provider = RAGSchemaProvider()