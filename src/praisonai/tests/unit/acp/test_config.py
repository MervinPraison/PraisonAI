"""Unit tests for ACP configuration."""

import os
import tempfile
from pathlib import Path

from praisonai.acp.config import ACPConfig


class TestACPConfig:
    """Tests for ACPConfig class."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = ACPConfig()
        
        assert config.workspace == Path.cwd()
        assert config.agent == "default"
        assert config.agents_config is None
        assert config.router_enabled is False
        assert config.model is None
        assert config.resume_session is None
        assert config.resume_last is False
        assert config.read_only is True
        assert config.allow_write is False
        assert config.allow_shell is False
        assert config.allow_network is False
        assert config.approval_mode == "manual"
        assert config.debug is False
        assert config.profile is None
    
    def test_workspace_normalization(self):
        """Test workspace path normalization."""
        config = ACPConfig(workspace=".")
        assert config.workspace == Path.cwd()
        
        config = ACPConfig(workspace="/tmp")
        # Use resolve() to handle macOS symlinks (/tmp -> /private/tmp)
        assert config.workspace == Path("/tmp").resolve()
    
    def test_allowed_paths_default(self):
        """Test default allowed paths."""
        config = ACPConfig()
        
        assert config.workspace in config.allowed_paths
        assert Path.home() / ".praison" in config.allowed_paths
    
    def test_is_path_allowed(self):
        """Test path allowlist checking."""
        config = ACPConfig(workspace="/tmp/test_workspace")
        
        # Workspace itself should be allowed
        assert config.is_path_allowed(Path("/tmp/test_workspace"))
        
        # Subdirectories should be allowed
        assert config.is_path_allowed(Path("/tmp/test_workspace/subdir"))
        
        # Parent directories should NOT be allowed
        assert not config.is_path_allowed(Path("/tmp"))
        
        # Unrelated paths should NOT be allowed
        assert not config.is_path_allowed(Path("/var/log"))
    
    def test_can_write(self):
        """Test write permission checking."""
        # Read-only mode
        config = ACPConfig(read_only=True, allow_write=False)
        assert not config.can_write()
        
        # Allow write overrides read-only
        config = ACPConfig(read_only=True, allow_write=True)
        assert config.can_write()
        
        # Not read-only
        config = ACPConfig(read_only=False)
        assert config.can_write()
    
    def test_can_execute_shell(self):
        """Test shell execution permission checking."""
        config = ACPConfig(allow_shell=False)
        assert not config.can_execute_shell()
        
        config = ACPConfig(allow_shell=True)
        assert config.can_execute_shell()
    
    def test_from_env(self, monkeypatch):
        """Test configuration from environment variables."""
        monkeypatch.setenv("PRAISONAI_WORKSPACE", "/tmp/env_workspace")
        monkeypatch.setenv("PRAISONAI_AGENT", "test_agent")
        monkeypatch.setenv("PRAISONAI_MODEL", "gpt-4")
        monkeypatch.setenv("PRAISONAI_DEBUG", "true")
        monkeypatch.setenv("PRAISONAI_READ_ONLY", "false")
        monkeypatch.setenv("PRAISONAI_APPROVAL_MODE", "auto")
        
        config = ACPConfig.from_env()
        
        # Use resolve() to handle macOS symlinks
        assert config.workspace == Path("/tmp/env_workspace").resolve()
        assert config.agent == "test_agent"
        assert config.model == "gpt-4"
        assert config.debug is True
        assert config.read_only is False
        assert config.approval_mode == "auto"
    
    def test_from_file(self):
        """Test configuration from YAML file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
acp:
  workspace: /tmp/file_workspace
  agent: file_agent
  model: gpt-3.5-turbo
  debug: true
  read_only: false
  approval_mode: scoped
""")
            f.flush()
            
            config = ACPConfig.from_file(Path(f.name))
            
            # Use resolve() to handle macOS symlinks
            assert config.workspace == Path("/tmp/file_workspace").resolve()
            assert config.agent == "file_agent"
            assert config.model == "gpt-3.5-turbo"
            assert config.debug is True
            assert config.read_only is False
            assert config.approval_mode == "scoped"
        
        os.unlink(f.name)
    
    def test_from_file_missing(self):
        """Test configuration from non-existent file."""
        config = ACPConfig.from_file(Path("/nonexistent/config.yaml"))
        
        # Should return default config
        assert config.agent == "default"
        assert config.debug is False
    
    def test_to_dict(self):
        """Test configuration serialization."""
        config = ACPConfig(
            workspace="/tmp/test",
            agent="test_agent",
            model="gpt-4",
            debug=True,
        )
        
        data = config.to_dict()
        
        # Use resolve() to handle macOS symlinks
        assert data["workspace"] == str(Path("/tmp/test").resolve())
        assert data["agent"] == "test_agent"
        assert data["model"] == "gpt-4"
        assert data["debug"] is True
    
    def test_merge(self):
        """Test configuration merging."""
        config1 = ACPConfig(agent="agent1", model="model1")
        config2 = ACPConfig(agent="agent2", debug=True)
        
        merged = ACPConfig.merge(config1, config2)
        
        # Later config overrides
        assert merged.agent == "agent2"
        assert merged.model == "model1"  # Not overridden
        assert merged.debug is True
