"""
Shared configuration loader for PraisonAI CLI commands.

Implements strict precedence:
1. CLI flags (highest priority)
2. Environment variables
3. Config file (YAML)
4. Defaults (lowest priority)

This module is DRY - used by both knowledge and rag commands.
"""

import os
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RAGCliConfig:
    """
    Configuration for RAG/Knowledge CLI commands.
    
    Supports loading from multiple sources with proper precedence.
    """
    # Collection settings
    collection: str = "default"
    
    # Retrieval settings
    top_k: int = 5
    hybrid: bool = False
    rerank: bool = False
    min_score: float = 0.0
    
    # RAG settings
    include_citations: bool = True
    max_context_tokens: int = 4000
    
    # Vector store settings
    vector_store_provider: str = "chroma"
    vector_store_path: Optional[str] = None
    
    # Server settings (for serve command)
    host: str = "127.0.0.1"
    port: int = 8080
    openai_compat: bool = False
    
    # LLM settings
    model: Optional[str] = None
    
    # Misc
    verbose: bool = False
    
    def to_knowledge_config(self) -> Dict[str, Any]:
        """Convert to knowledge config dict."""
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
    
    def to_rag_config_dict(self) -> Dict[str, Any]:
        """Convert to RAGConfig dict."""
        config = {
            "top_k": self.top_k,
            "include_citations": self.include_citations,
            "max_context_tokens": self.max_context_tokens,
            "min_score": self.min_score,
            "rerank": self.rerank,
        }
        
        if self.hybrid:
            config["retrieval_strategy"] = "hybrid"
        
        if self.model:
            config["model"] = self.model
        
        return config


# Environment variable mappings
ENV_MAPPINGS = {
    "PRAISONAI_COLLECTION": "collection",
    "PRAISONAI_TOP_K": ("top_k", int),
    "PRAISONAI_HYBRID": ("hybrid", lambda x: x.lower() in ("true", "1", "yes")),
    "PRAISONAI_RERANK": ("rerank", lambda x: x.lower() in ("true", "1", "yes")),
    "PRAISONAI_MIN_SCORE": ("min_score", float),
    "PRAISONAI_CITATIONS": ("include_citations", lambda x: x.lower() in ("true", "1", "yes")),
    "PRAISONAI_MAX_CONTEXT_TOKENS": ("max_context_tokens", int),
    "PRAISONAI_VECTOR_STORE": "vector_store_provider",
    "PRAISONAI_VECTOR_STORE_PATH": "vector_store_path",
    "PRAISONAI_HOST": "host",
    "PRAISONAI_PORT": ("port", int),
    "PRAISONAI_OPENAI_COMPAT": ("openai_compat", lambda x: x.lower() in ("true", "1", "yes")),
    "PRAISONAI_MODEL": "model",
    "PRAISONAI_VERBOSE": ("verbose", lambda x: x.lower() in ("true", "1", "yes")),
}


def load_config_file(config_path: Path) -> Dict[str, Any]:
    """
    Load configuration from a YAML file.
    
    Args:
        config_path: Path to the YAML config file
        
    Returns:
        Dict with configuration values
    """
    if not config_path.exists():
        logger.warning(f"Config file not found: {config_path}")
        return {}
    
    try:
        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
        return config
    except Exception as e:
        logger.error(f"Failed to load config file: {e}")
        return {}


def load_from_env() -> Dict[str, Any]:
    """
    Load configuration from environment variables.
    
    Returns:
        Dict with configuration values from environment
    """
    config = {}
    
    for env_var, mapping in ENV_MAPPINGS.items():
        value = os.environ.get(env_var)
        if value is not None:
            if isinstance(mapping, tuple):
                attr_name, converter = mapping
                try:
                    config[attr_name] = converter(value)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid value for {env_var}: {e}")
            else:
                config[mapping] = value
    
    return config


def merge_configs(
    defaults: Dict[str, Any],
    file_config: Dict[str, Any],
    env_config: Dict[str, Any],
    cli_config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Merge configurations with proper precedence.
    
    Precedence (highest to lowest):
    1. CLI flags
    2. Environment variables
    3. Config file
    4. Defaults
    
    Args:
        defaults: Default configuration values
        file_config: Configuration from YAML file
        env_config: Configuration from environment variables
        cli_config: Configuration from CLI flags
        
    Returns:
        Merged configuration dict
    """
    result = defaults.copy()
    
    # Apply file config (lowest priority after defaults)
    for key, value in file_config.items():
        if value is not None:
            result[key] = value
    
    # Apply env config (higher priority)
    for key, value in env_config.items():
        if value is not None:
            result[key] = value
    
    # Apply CLI config (highest priority)
    for key, value in cli_config.items():
        if value is not None:
            result[key] = value
    
    return result


def load_cli_config(
    config_file: Optional[Path] = None,
    cli_overrides: Optional[Dict[str, Any]] = None,
) -> RAGCliConfig:
    """
    Load CLI configuration with proper precedence.
    
    Args:
        config_file: Optional path to YAML config file
        cli_overrides: Dict of CLI flag values (only non-None values)
        
    Returns:
        RAGCliConfig instance with merged configuration
    """
    # Start with defaults
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
    
    # Load from config file
    file_config = {}
    if config_file:
        raw_config = load_config_file(config_file)
        # Flatten nested config
        if "knowledge" in raw_config:
            file_config.update(raw_config["knowledge"])
        if "rag" in raw_config:
            file_config.update(raw_config["rag"])
        if "retrieval" in raw_config:
            file_config.update(raw_config["retrieval"])
        # Also check for top-level keys
        for key in defaults.keys():
            if key in raw_config:
                file_config[key] = raw_config[key]
    
    # Load from environment
    env_config = load_from_env()
    
    # CLI overrides (filter out None values)
    cli_config = {k: v for k, v in (cli_overrides or {}).items() if v is not None}
    
    # Merge with precedence
    merged = merge_configs(defaults, file_config, env_config, cli_config)
    
    # Create config object
    return RAGCliConfig(**{k: v for k, v in merged.items() if k in RAGCliConfig.__dataclass_fields__})


def get_config_schema() -> Dict[str, Any]:
    """
    Get the configuration schema for documentation.
    
    Returns:
        Dict describing the configuration schema
    """
    return {
        "knowledge": {
            "collection": "Collection/index name (default: 'default')",
            "vector_store_provider": "Vector store provider (default: 'chroma')",
            "vector_store_path": "Path to vector store (default: './.praison/knowledge/{collection}')",
        },
        "retrieval": {
            "top_k": "Number of results to retrieve (default: 5)",
            "hybrid": "Enable hybrid retrieval (default: false)",
            "rerank": "Enable reranking (default: false)",
            "min_score": "Minimum relevance score (default: 0.0)",
        },
        "rag": {
            "include_citations": "Include citations in response (default: true)",
            "max_context_tokens": "Maximum context tokens (default: 4000)",
            "model": "LLM model to use (default: gpt-4o-mini)",
        },
        "server": {
            "host": "Server host (default: '127.0.0.1')",
            "port": "Server port (default: 8080)",
            "openai_compat": "Enable OpenAI-compatible endpoint (default: false)",
        },
    }
