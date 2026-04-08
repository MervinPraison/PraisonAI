"""
Fallback unified schema implementation without Pydantic dependency.

Provides basic configuration schema functionality for environments
where Pydantic is not available.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from praisonaiagents.config.protocols import (
    ConfigSchemaProtocol,
    ValidationResult,
    CliMapping, 
    PrecedenceChain,
)


@dataclass
class BasicRAGSchema:
    """
    Basic RAG schema using dataclasses as fallback.
    
    Provides the same fields as UnifiedRAGSchema but with simpler validation.
    """
    collection: str = "default"
    top_k: int = 5
    hybrid: bool = False
    rerank: bool = False
    min_score: float = 0.0
    include_citations: bool = True
    max_context_tokens: int = 4000
    vector_store_provider: str = "chroma"
    vector_store_path: Optional[str] = None
    host: str = "127.0.0.1"
    port: int = 8080
    openai_compat: bool = False
    model: Optional[str] = None
    verbose: bool = False


class BasicRAGSchemaProvider:
    """
    Basic schema provider without Pydantic dependency.
    
    Provides core functionality for configuration validation and mapping.
    """
    
    def __init__(self):
        self.schema_class = BasicRAGSchema
        
        # Field mappings
        self.yaml_to_python_map = {
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
        
        # Environment variables
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
        """Basic validation without Pydantic."""
        errors = []
        warnings = []
        
        # Check for unknown fields first
        known_fields = {
            "collection", "top_k", "hybrid", "rerank", "min_score", 
            "include_citations", "max_context_tokens", "vector_store_provider",
            "vector_store_path", "host", "port", "openai_compat", "model", "verbose"
        }
        unknown_fields = set(config.keys()) - known_fields
        if unknown_fields:
            for field in unknown_fields:
                errors.append(f"Unknown field '{field}'. Valid fields: {', '.join(sorted(known_fields))}")
        
        # Check required fields
        if "collection" not in config:
            errors.append("collection is required")
        
        # Check value ranges
        if "top_k" in config:
            if not isinstance(config["top_k"], int) or config["top_k"] <= 0 or config["top_k"] > 100:
                errors.append("top_k must be an integer between 1 and 100")
        
        if "min_score" in config:
            if not isinstance(config["min_score"], (int, float)) or config["min_score"] < 0 or config["min_score"] > 1:
                errors.append("min_score must be a number between 0 and 1")
        
        if "port" in config:
            if not isinstance(config["port"], int) or config["port"] < 1000 or config["port"] > 65535:
                errors.append("port must be an integer between 1000 and 65535")
        
        if "vector_store_provider" in config:
            valid_providers = ["chroma", "pinecone", "weaviate", "qdrant"]
            if config["vector_store_provider"] not in valid_providers:
                errors.append(f"vector_store_provider must be one of: {valid_providers}")
        
        # Type checking
        bool_fields = ["hybrid", "rerank", "include_citations", "openai_compat", "verbose"]
        for field in bool_fields:
            if field in config and not isinstance(config[field], bool):
                errors.append(f"{field} must be a boolean (true/false)")
        
        is_valid = len(errors) == 0
        normalized = self.normalize_config(config) if is_valid else None
        
        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            normalized=normalized
        )
    
    def get_cli_mapping(self) -> List[CliMapping]:
        """Generate CLI mappings from schema."""
        mappings = [
            CliMapping(
                field_name="collection",
                cli_flag="collection", 
                description="Collection/index name for vector storage",
                type_hint=str,
                default="default",
                env_var="PRAISONAI_COLLECTION"
            ),
            CliMapping(
                field_name="top_k",
                cli_flag="top-k",
                description="Number of documents to retrieve", 
                type_hint=int,
                default=5,
                env_var="PRAISONAI_TOP_K"
            ),
            CliMapping(
                field_name="hybrid",
                cli_flag="hybrid",
                description="Enable hybrid retrieval (dense + sparse)",
                type_hint=bool,
                default=False,
                env_var="PRAISONAI_HYBRID"
            ),
            CliMapping(
                field_name="rerank",
                cli_flag="rerank",
                description="Enable reranking of retrieved results",
                type_hint=bool,
                default=False,
                env_var="PRAISONAI_RERANK"
            ),
            CliMapping(
                field_name="min_score", 
                cli_flag="min-score",
                description="Minimum relevance score threshold",
                type_hint=float,
                default=0.0,
                env_var="PRAISONAI_MIN_SCORE"
            ),
            CliMapping(
                field_name="include_citations",
                cli_flag="citations",
                description="Include source citations in responses",
                type_hint=bool,
                default=True,
                env_var="PRAISONAI_CITATIONS"
            ),
            CliMapping(
                field_name="max_context_tokens",
                cli_flag="max-context",
                description="Maximum tokens for context window",
                type_hint=int,
                default=4000,
                env_var="PRAISONAI_MAX_CONTEXT_TOKENS"
            ),
            CliMapping(
                field_name="vector_store_provider",
                cli_flag="vector-store",
                description="Vector store provider (chroma, pinecone, etc.)",
                type_hint=str,
                default="chroma",
                env_var="PRAISONAI_VECTOR_STORE"
            ),
            CliMapping(
                field_name="vector_store_path",
                cli_flag="vector-path",
                description="Path to vector store data",
                type_hint=str,
                default=None,
                env_var="PRAISONAI_VECTOR_STORE_PATH"
            ),
            CliMapping(
                field_name="host",
                cli_flag="host",
                description="Server host address",
                type_hint=str,
                default="127.0.0.1",
                env_var="PRAISONAI_HOST"
            ),
            CliMapping(
                field_name="port",
                cli_flag="port", 
                description="Server port number",
                type_hint=int,
                default=8080,
                env_var="PRAISONAI_PORT"
            ),
            CliMapping(
                field_name="openai_compat",
                cli_flag="openai-compat",
                description="Enable OpenAI-compatible API endpoint",
                type_hint=bool,
                default=False,
                env_var="PRAISONAI_OPENAI_COMPAT"
            ),
            CliMapping(
                field_name="model",
                cli_flag="model",
                description="LLM model to use (defaults to gpt-4o-mini)",
                type_hint=str,
                default=None,
                env_var="PRAISONAI_MODEL"
            ),
            CliMapping(
                field_name="verbose",
                cli_flag="verbose",
                description="Enable verbose output",
                type_hint=bool,
                default=False,
                env_var="PRAISONAI_VERBOSE"
            ),
        ]
        
        return mappings
    
    def get_precedence_chain(self) -> PrecedenceChain:
        """Get documented precedence chain."""
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
        """Normalize config by applying defaults."""
        defaults = {
            "collection": "default",
            "top_k": 5,
            "hybrid": False,
            "rerank": False,
            "min_score": 0.0,
            "include_citations": True,
            "max_context_tokens": 4000,
            "vector_store_provider": "chroma",
            "vector_store_path": None,
            "host": "127.0.0.1",
            "port": 8080,
            "openai_compat": False,
            "model": None,
            "verbose": False,
        }
        
        result = defaults.copy()
        result.update(config)
        return result
    
    def get_schema_info(self) -> Dict[str, Any]:
        """Get schema metadata."""
        return {
            "name": "BasicRAGSchema",
            "description": "Basic unified schema for RAG configuration (fallback)",
            "fields": {
                "collection": {"type": "str", "description": "Collection name", "default": "default"},
                "top_k": {"type": "int", "description": "Number of results", "default": 5},
                "hybrid": {"type": "bool", "description": "Hybrid retrieval", "default": False},
                "rerank": {"type": "bool", "description": "Enable reranking", "default": False},
                "min_score": {"type": "float", "description": "Min score", "default": 0.0},
                "include_citations": {"type": "bool", "description": "Include citations", "default": True},
                "max_context_tokens": {"type": "int", "description": "Max context", "default": 4000},
                "vector_store_provider": {"type": "str", "description": "Vector store", "default": "chroma"},
                "host": {"type": "str", "description": "Host", "default": "127.0.0.1"},
                "port": {"type": "int", "description": "Port", "default": 8080},
                "model": {"type": "str", "description": "LLM model", "default": None},
                "verbose": {"type": "bool", "description": "Verbose", "default": False},
            },
            "precedence": ["cli_flags", "env_vars", "config_file", "defaults"],
        }
    
    def yaml_to_python(self, yaml_config: Dict[str, Any]) -> Dict[str, Any]:
        """Map YAML field names to Python format."""
        result = yaml_config.copy()
        for yaml_name, python_name in self.yaml_to_python_map.items():
            if yaml_name in result:
                result[python_name] = result.pop(yaml_name)
        return result
    
    def cli_to_python(self, cli_args: Dict[str, Any]) -> Dict[str, Any]:
        """Map CLI arguments to Python format."""
        python_config = {}
        for cli_flag, python_field in self.cli_flag_map.items():
            cli_key = cli_flag.replace("-", "_")
            if cli_key in cli_args and cli_args[cli_key] is not None:
                python_config[python_field] = cli_args[cli_key]
        return python_config
    
    def merge_with_precedence(self, cli_config: Dict[str, Any], env_config: Dict[str, Any], 
                            file_config: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
        """Merge configs following precedence."""
        result = defaults.copy()
        for config in [file_config, env_config, cli_config]:
            for key, value in config.items():
                if value is not None:
                    result[key] = value
        return result
    
    def load_env_config(self) -> Dict[str, Any]:
        """Load from environment variables."""
        import os
        env_config = {}
        
        for env_var, field_name in self.env_var_map.items():
            value = os.environ.get(env_var)
            if value is not None:
                env_config[field_name] = self._convert_env_value(field_name, value)
        
        return env_config
    
    def _convert_env_value(self, field_name: str, value: str) -> Any:
        """Convert env var string to appropriate type."""
        if field_name in ["hybrid", "rerank", "include_citations", "openai_compat", "verbose"]:
            return value.lower() in ("true", "1", "yes", "on")
        
        if field_name in ["top_k", "max_context_tokens", "port"]:
            try:
                return int(value)
            except ValueError:
                return value
        
        if field_name in ["min_score"]:
            try:
                return float(value)
            except ValueError:
                return value
        
        return value


# Create the fallback provider
basic_rag_schema_provider = BasicRAGSchemaProvider()