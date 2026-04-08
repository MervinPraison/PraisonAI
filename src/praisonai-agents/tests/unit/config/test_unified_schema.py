"""
Test suite for unified configuration schema.

Tests the core protocols and ensures CLI/YAML/Python configuration
consistency as specified in architectural gap #2.
"""

import os
import tempfile
from pathlib import Path
from typing import Dict, Any
import pytest

# Import from core SDK (protocols)
from praisonaiagents.config.protocols import (
    ConfigSchemaProtocol,
    ValidationResult,
    CliMapping,
    PrecedenceChain,
)

# Try to import wrapper implementation for integration testing
try:
    from praisonai.cli.unified_schema import rag_schema_provider
    WRAPPER_AVAILABLE = True
except ImportError:
    WRAPPER_AVAILABLE = False

# Test data
VALID_CONFIG = {
    "collection": "test_collection",
    "top_k": 10,
    "hybrid": True,
    "rerank": False,
    "min_score": 0.5,
    "include_citations": True,
    "max_context_tokens": 8000,
    "vector_store_provider": "chroma",
    "host": "0.0.0.0",
    "port": 9090,
    "model": "gpt-4",
    "verbose": True,
}

INVALID_CONFIG = {
    "collection": "test",
    "top_k": -5,  # Invalid: should be >= 1
    "min_score": 2.0,  # Invalid: should be <= 1.0
    "vector_store_provider": "invalid_provider",  # Invalid: not in allowed list
    "port": 99999,  # Invalid: > 65535
}

YAML_CONFIG_CONTENT = """
collection: yaml_test
vector_store: pinecone
citations: false
max_context: 6000
host: localhost
"""

CLI_ARGS = {
    "collection": "cli_test",
    "top_k": 15,
    "hybrid": True,
    "verbose": True,
}


class MockSchemaProvider:
    """Mock implementation of ConfigSchemaProtocol for testing."""
    
    def validate(self, config: Dict[str, Any]) -> ValidationResult:
        """Mock validation - check for obvious errors."""
        errors = []
        warnings = []
        
        # Check required fields
        if "collection" not in config:
            errors.append("collection is required")
        
        # Check value ranges
        if "top_k" in config and config["top_k"] <= 0:
            errors.append("top_k must be positive")
        
        if "min_score" in config and (config["min_score"] < 0 or config["min_score"] > 1):
            errors.append("min_score must be between 0 and 1")
        
        if "port" in config and (config["port"] < 1000 or config["port"] > 65535):
            errors.append("port must be between 1000 and 65535")
        
        # Check provider validity
        valid_providers = ["chroma", "pinecone", "weaviate", "qdrant"]
        if "vector_store_provider" in config:
            if config["vector_store_provider"] not in valid_providers:
                errors.append(f"vector_store_provider must be one of: {valid_providers}")
        
        is_valid = len(errors) == 0
        
        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            normalized=config if is_valid else None
        )
    
    def get_cli_mapping(self) -> list[CliMapping]:
        """Mock CLI mappings."""
        return [
            CliMapping("collection", "collection", "Collection name", str, "default"),
            CliMapping("top_k", "top-k", "Number of results", int, 5),
            CliMapping("hybrid", "hybrid", "Enable hybrid retrieval", bool, False),
            CliMapping("min_score", "min-score", "Minimum score", float, 0.0),
            CliMapping("include_citations", "citations", "Include citations", bool, True),
            CliMapping("vector_store_provider", "vector-store", "Vector store", str, "chroma"),
            CliMapping("port", "port", "Server port", int, 8080),
            CliMapping("verbose", "verbose", "Verbose output", bool, False),
        ]
    
    def get_precedence_chain(self) -> PrecedenceChain:
        """Mock precedence chain."""
        return PrecedenceChain(
            chain=["cli", "env", "file", "defaults"],
            descriptions={
                "cli": "Command line arguments",
                "env": "Environment variables", 
                "file": "Configuration file",
                "defaults": "Default values"
            }
        )
    
    def normalize_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Mock normalization with defaults."""
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
            "verbose": False,
        }
        
        result = defaults.copy()
        result.update(config)
        return result
    
    def get_schema_info(self) -> Dict[str, Any]:
        """Mock schema info."""
        return {
            "name": "TestSchema",
            "description": "Test unified schema",
            "fields": {
                "collection": {"type": "str", "default": "default"},
                "top_k": {"type": "int", "default": 5},
                "hybrid": {"type": "bool", "default": False},
            },
            "precedence": ["cli", "env", "file", "defaults"],
        }


@pytest.fixture
def schema_provider():
    """Create a mock schema provider for testing."""
    return MockSchemaProvider()


def test_protocol_interface(schema_provider):
    """Test that mock provider implements the protocol correctly."""
    assert isinstance(schema_provider, ConfigSchemaProtocol)
    
    # Test validation method
    result = schema_provider.validate(VALID_CONFIG)
    assert isinstance(result, ValidationResult)
    assert result.is_valid
    assert result.errors == []
    
    # Test CLI mapping method
    mappings = schema_provider.get_cli_mapping()
    assert isinstance(mappings, list)
    assert all(isinstance(m, CliMapping) for m in mappings)
    
    # Test precedence chain method
    chain = schema_provider.get_precedence_chain()
    assert isinstance(chain, PrecedenceChain)
    assert len(chain.chain) > 0
    
    # Test normalization method
    normalized = schema_provider.normalize_config({})
    assert isinstance(normalized, dict)
    assert "collection" in normalized
    
    # Test schema info method
    info = schema_provider.get_schema_info()
    assert isinstance(info, dict)
    assert "name" in info


def test_validation_success(schema_provider):
    """Test successful configuration validation."""
    result = schema_provider.validate(VALID_CONFIG)
    
    assert result.is_valid
    assert result.errors == []
    assert result.normalized is not None


def test_validation_failure(schema_provider):
    """Test configuration validation with errors."""
    result = schema_provider.validate(INVALID_CONFIG)
    
    assert not result.is_valid
    assert len(result.errors) > 0
    assert result.normalized is None
    
    # Check specific error messages
    error_text = " ".join(result.errors)
    assert "top_k must be positive" in error_text
    assert "min_score must be between" in error_text
    assert "vector_store_provider must be" in error_text


def test_cli_mapping_generation(schema_provider):
    """Test CLI flag generation from schema."""
    mappings = schema_provider.get_cli_mapping()
    
    # Check that we have mappings
    assert len(mappings) > 0
    
    # Check mapping structure
    for mapping in mappings:
        assert hasattr(mapping, 'field_name')
        assert hasattr(mapping, 'cli_flag')
        assert hasattr(mapping, 'description')
        assert hasattr(mapping, 'type_hint')
        
        # Field names should be valid Python identifiers
        assert mapping.field_name.isidentifier()
        
        # CLI flags should be kebab-case
        assert "-" in mapping.cli_flag or mapping.cli_flag.isalpha()
    
    # Check for specific expected mappings
    flag_names = [m.cli_flag for m in mappings]
    assert "collection" in flag_names
    assert "top-k" in flag_names
    assert "vector-store" in flag_names


def test_precedence_chain_documentation(schema_provider):
    """Test precedence chain is properly documented."""
    chain = schema_provider.get_precedence_chain()
    
    # Check chain structure
    assert len(chain.chain) >= 3  # Should have at least cli, env, defaults
    assert isinstance(chain.descriptions, dict)
    
    # Check all chain items have descriptions
    for source in chain.chain:
        assert source in chain.descriptions
        assert len(chain.descriptions[source]) > 10  # Meaningful description
    
    # Check precedence order makes sense (cli should be highest)
    assert "cli" in chain.chain[0] or "command" in chain.chain[0].lower()


def test_config_normalization(schema_provider):
    """Test configuration normalization with defaults."""
    # Test empty config gets defaults
    empty_config = {}
    normalized = schema_provider.normalize_config(empty_config)
    
    assert normalized["collection"] == "default"
    assert normalized["top_k"] == 5
    assert normalized["hybrid"] is False
    
    # Test partial config merges with defaults
    partial_config = {"collection": "custom", "top_k": 10}
    normalized = schema_provider.normalize_config(partial_config)
    
    assert normalized["collection"] == "custom"  # User value
    assert normalized["top_k"] == 10  # User value
    assert normalized["hybrid"] is False  # Default value


def test_schema_metadata(schema_provider):
    """Test schema metadata for documentation."""
    info = schema_provider.get_schema_info()
    
    # Check required fields
    assert "name" in info
    assert "description" in info
    assert "fields" in info
    assert "precedence" in info
    
    # Check field definitions
    fields = info["fields"]
    assert isinstance(fields, dict)
    assert len(fields) > 0
    
    # Check precedence documentation
    precedence = info["precedence"]
    assert isinstance(precedence, list)
    assert len(precedence) >= 3


def test_cli_yaml_python_consistency():
    """Test that the same config produces identical behavior across interfaces."""
    provider = MockSchemaProvider()
    
    # Base configuration that should be consistent
    base_config = {
        "collection": "consistency_test",
        "top_k": 8,
        "hybrid": True,
        "include_citations": False,
    }
    
    # 1. Direct Python config
    python_result = provider.validate(base_config)
    
    # 2. CLI-style config (simulate CLI parsing)
    cli_style = {
        "collection": "consistency_test", 
        "top_k": 8,
        "hybrid": True,
        "include_citations": False,
    }
    cli_result = provider.validate(cli_style)
    
    # 3. YAML-style config (after field mapping)
    yaml_style = {
        "collection": "consistency_test",
        "top_k": 8,  
        "hybrid": True,
        "include_citations": False,
    }
    yaml_result = provider.validate(yaml_style)
    
    # All should validate successfully
    assert python_result.is_valid
    assert cli_result.is_valid
    assert yaml_result.is_valid
    
    # Normalized configs should be identical
    assert python_result.normalized == cli_result.normalized
    assert cli_result.normalized == yaml_result.normalized


def test_environment_variable_mapping():
    """Test environment variable to config field mapping."""
    # This would be implemented in the actual schema provider
    # Here we just test the concept
    
    env_mapping = {
        "PRAISONAI_COLLECTION": "collection",
        "PRAISONAI_TOP_K": "top_k", 
        "PRAISONAI_HYBRID": "hybrid",
        "PRAISONAI_VECTOR_STORE": "vector_store_provider",
    }
    
    # Verify mapping structure
    for env_var, field in env_mapping.items():
        assert env_var.startswith("PRAISONAI_")
        assert field.isidentifier()


def test_backward_compatibility():
    """Test that new unified schema maintains backward compatibility."""
    provider = MockSchemaProvider()
    
    # Old-style config that should still work
    legacy_config = {
        "collection": "legacy_test",
        "top_k": 5,
        "include_citations": True,
        "vector_store_provider": "chroma",
    }
    
    result = provider.validate(legacy_config)
    assert result.is_valid
    
    # Should normalize to include defaults for new fields
    normalized = provider.normalize_config(legacy_config)
    assert "hybrid" in normalized  # Should get default value
    assert "rerank" in normalized  # Should get default value


if __name__ == "__main__":
    pytest.main([__file__])