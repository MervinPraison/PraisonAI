"""
Tests for CLI config loader with precedence.

Tests that config loading follows: CLI > ENV > File > Defaults
"""

import os
import tempfile
from pathlib import Path


class TestRAGCliConfig:
    """Tests for RAGCliConfig dataclass."""
    
    def test_rag_cli_config_defaults(self):
        """Test RAGCliConfig has correct defaults."""
        from praisonai.cli.config_loader import RAGCliConfig
        
        config = RAGCliConfig()
        
        assert config.collection == "default"
        assert config.top_k == 5
        assert config.hybrid is False
        assert config.rerank is False
        assert config.include_citations is True
    
    def test_rag_cli_config_to_knowledge_config(self):
        """Test conversion to knowledge config dict."""
        from praisonai.cli.config_loader import RAGCliConfig
        
        config = RAGCliConfig(collection="test", hybrid=True)
        knowledge_config = config.to_knowledge_config()
        
        assert knowledge_config["vector_store"]["config"]["collection_name"] == "test"
        assert "retrieval" in knowledge_config
        assert knowledge_config["retrieval"]["strategy"] == "hybrid"
    
    def test_rag_cli_config_to_rag_config_dict(self):
        """Test conversion to RAGConfig dict."""
        from praisonai.cli.config_loader import RAGCliConfig
        
        config = RAGCliConfig(top_k=10, rerank=True, hybrid=True)
        rag_config = config.to_rag_config_dict()
        
        assert rag_config["top_k"] == 10
        assert rag_config["rerank"] is True
        assert rag_config["retrieval_strategy"] == "hybrid"


class TestLoadFromEnv:
    """Tests for loading config from environment variables."""
    
    def test_load_from_env_collection(self):
        """Test loading collection from env."""
        from praisonai.cli.config_loader import load_from_env
        
        os.environ["PRAISONAI_COLLECTION"] = "test_collection"
        try:
            config = load_from_env()
            assert config.get("collection") == "test_collection"
        finally:
            del os.environ["PRAISONAI_COLLECTION"]
    
    def test_load_from_env_top_k(self):
        """Test loading top_k from env with type conversion."""
        from praisonai.cli.config_loader import load_from_env
        
        os.environ["PRAISONAI_TOP_K"] = "10"
        try:
            config = load_from_env()
            assert config.get("top_k") == 10
            assert isinstance(config.get("top_k"), int)
        finally:
            del os.environ["PRAISONAI_TOP_K"]
    
    def test_load_from_env_hybrid_bool(self):
        """Test loading hybrid bool from env."""
        from praisonai.cli.config_loader import load_from_env
        
        os.environ["PRAISONAI_HYBRID"] = "true"
        try:
            config = load_from_env()
            assert config.get("hybrid") is True
        finally:
            del os.environ["PRAISONAI_HYBRID"]
    
    def test_load_from_env_hybrid_bool_false(self):
        """Test loading hybrid=false from env."""
        from praisonai.cli.config_loader import load_from_env
        
        os.environ["PRAISONAI_HYBRID"] = "false"
        try:
            config = load_from_env()
            assert config.get("hybrid") is False
        finally:
            del os.environ["PRAISONAI_HYBRID"]


class TestLoadConfigFile:
    """Tests for loading config from YAML file."""
    
    def test_load_config_file_basic(self):
        """Test loading basic config from file."""
        from praisonai.cli.config_loader import load_config_file
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
collection: file_collection
top_k: 15
hybrid: true
""")
            f.flush()
            
            config = load_config_file(Path(f.name))
            
            assert config.get("collection") == "file_collection"
            assert config.get("top_k") == 15
            assert config.get("hybrid") is True
        
        os.unlink(f.name)
    
    def test_load_config_file_nested(self):
        """Test loading nested config from file."""
        from praisonai.cli.config_loader import load_config_file
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
knowledge:
  collection: nested_collection
rag:
  top_k: 20
  rerank: true
retrieval:
  hybrid: true
""")
            f.flush()
            
            config = load_config_file(Path(f.name))
            
            assert config.get("knowledge", {}).get("collection") == "nested_collection"
            assert config.get("rag", {}).get("top_k") == 20
            assert config.get("retrieval", {}).get("hybrid") is True
        
        os.unlink(f.name)
    
    def test_load_config_file_not_found(self):
        """Test loading non-existent config file returns empty dict."""
        from praisonai.cli.config_loader import load_config_file
        
        config = load_config_file(Path("/nonexistent/path.yaml"))
        
        assert config == {}


class TestMergeConfigs:
    """Tests for config merging with precedence."""
    
    def test_merge_configs_cli_wins(self):
        """Test that CLI config has highest precedence."""
        from praisonai.cli.config_loader import merge_configs
        
        defaults = {"collection": "default", "top_k": 5}
        file_config = {"collection": "file", "top_k": 10}
        env_config = {"collection": "env", "top_k": 15}
        cli_config = {"collection": "cli"}
        
        result = merge_configs(defaults, file_config, env_config, cli_config)
        
        assert result["collection"] == "cli"
        assert result["top_k"] == 15  # From env (CLI didn't override)
    
    def test_merge_configs_env_over_file(self):
        """Test that env config beats file config."""
        from praisonai.cli.config_loader import merge_configs
        
        defaults = {"collection": "default"}
        file_config = {"collection": "file"}
        env_config = {"collection": "env"}
        cli_config = {}
        
        result = merge_configs(defaults, file_config, env_config, cli_config)
        
        assert result["collection"] == "env"
    
    def test_merge_configs_file_over_defaults(self):
        """Test that file config beats defaults."""
        from praisonai.cli.config_loader import merge_configs
        
        defaults = {"collection": "default", "top_k": 5}
        file_config = {"collection": "file"}
        env_config = {}
        cli_config = {}
        
        result = merge_configs(defaults, file_config, env_config, cli_config)
        
        assert result["collection"] == "file"
        assert result["top_k"] == 5  # From defaults


class TestLoadCliConfig:
    """Tests for the main load_cli_config function."""
    
    def test_load_cli_config_defaults(self):
        """Test loading with only defaults."""
        from praisonai.cli.config_loader import load_cli_config
        
        config = load_cli_config()
        
        assert config.collection == "default"
        assert config.top_k == 5
        assert config.hybrid is False
    
    def test_load_cli_config_with_cli_overrides(self):
        """Test loading with CLI overrides."""
        from praisonai.cli.config_loader import load_cli_config
        
        config = load_cli_config(cli_overrides={
            "collection": "cli_collection",
            "hybrid": True,
            "top_k": 20,
        })
        
        assert config.collection == "cli_collection"
        assert config.hybrid is True
        assert config.top_k == 20
    
    def test_load_cli_config_with_file(self):
        """Test loading with config file."""
        from praisonai.cli.config_loader import load_cli_config
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
collection: file_collection
top_k: 15
""")
            f.flush()
            
            config = load_cli_config(config_file=Path(f.name))
            
            assert config.collection == "file_collection"
            assert config.top_k == 15
        
        os.unlink(f.name)
    
    def test_load_cli_config_precedence(self):
        """Test full precedence chain: CLI > ENV > File > Defaults."""
        from praisonai.cli.config_loader import load_cli_config
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
collection: file_collection
top_k: 10
hybrid: false
rerank: true
""")
            f.flush()
            
            os.environ["PRAISONAI_TOP_K"] = "15"
            os.environ["PRAISONAI_HYBRID"] = "true"
            
            try:
                config = load_cli_config(
                    config_file=Path(f.name),
                    cli_overrides={"collection": "cli_collection"}
                )
                
                # CLI wins for collection
                assert config.collection == "cli_collection"
                # ENV wins for top_k and hybrid
                assert config.top_k == 15
                assert config.hybrid is True
                # File wins for rerank (no ENV or CLI override)
                assert config.rerank is True
            finally:
                del os.environ["PRAISONAI_TOP_K"]
                del os.environ["PRAISONAI_HYBRID"]
        
        os.unlink(f.name)


class TestGetConfigSchema:
    """Tests for config schema documentation."""
    
    def test_get_config_schema_has_sections(self):
        """Test that schema has all sections."""
        from praisonai.cli.config_loader import get_config_schema
        
        schema = get_config_schema()
        
        assert "knowledge" in schema
        assert "retrieval" in schema
        assert "rag" in schema
        assert "server" in schema
    
    def test_get_config_schema_has_hybrid(self):
        """Test that schema documents hybrid option."""
        from praisonai.cli.config_loader import get_config_schema
        
        schema = get_config_schema()
        
        assert "hybrid" in schema["retrieval"]
