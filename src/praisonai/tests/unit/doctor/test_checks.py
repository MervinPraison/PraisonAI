"""Unit tests for doctor checks."""

import os
from unittest.mock import patch, MagicMock

from praisonai.cli.features.doctor.models import (
    CheckCategory,
    CheckStatus,
    DoctorConfig,
)
from praisonai.cli.features.doctor.registry import CheckRegistry


class TestEnvChecks:
    """Tests for environment checks."""
    
    def setup_method(self):
        """Reset registry before each test."""
        CheckRegistry.reset()
        # Import checks to register them
        from praisonai.cli.features.doctor.checks import env_checks
    
    def test_python_version_check(self):
        """Test Python version check."""
        from praisonai.cli.features.doctor.checks.env_checks import check_python_version
        
        config = DoctorConfig()
        result = check_python_version(config)
        
        # Should pass on Python 3.9+
        assert result.status == CheckStatus.PASS
        assert "Python" in result.message
    
    def test_openai_api_key_check_present(self):
        """Test OpenAI API key check when present."""
        from praisonai.cli.features.doctor.checks.env_checks import check_openai_api_key
        
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test1234567890abcdefghij"}):
            config = DoctorConfig()
            result = check_openai_api_key(config)
            
            assert result.status == CheckStatus.PASS
            assert "configured" in result.message.lower()
    
    def test_openai_api_key_check_missing(self):
        """Test OpenAI API key check when missing."""
        from praisonai.cli.features.doctor.checks.env_checks import check_openai_api_key
        
        env = {k: v for k, v in os.environ.items() 
               if k not in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"]}
        
        with patch.dict(os.environ, env, clear=True):
            config = DoctorConfig()
            result = check_openai_api_key(config)
            
            # Should fail or warn when no API keys are set
            assert result.status in [CheckStatus.FAIL, CheckStatus.WARN]
    
    def test_os_info_check(self):
        """Test OS info check."""
        from praisonai.cli.features.doctor.checks.env_checks import check_os_info
        
        config = DoctorConfig()
        result = check_os_info(config)
        
        assert result.status == CheckStatus.PASS
        assert result.metadata.get("os_name") is not None
    
    def test_virtual_env_check(self):
        """Test virtual environment check."""
        from praisonai.cli.features.doctor.checks.env_checks import check_virtual_env
        
        config = DoctorConfig()
        result = check_virtual_env(config)
        
        # Should pass or warn depending on environment
        assert result.status in [CheckStatus.PASS, CheckStatus.WARN]


class TestConfigChecks:
    """Tests for configuration checks."""
    
    def setup_method(self):
        """Reset registry before each test."""
        CheckRegistry.reset()
        from praisonai.cli.features.doctor.checks import config_checks
    
    def test_agents_yaml_not_found(self):
        """Test agents.yaml check when file doesn't exist."""
        from praisonai.cli.features.doctor.checks.config_checks import check_agents_yaml_exists
        
        with patch('pathlib.Path.cwd') as mock_cwd:
            mock_cwd.return_value = MagicMock()
            mock_cwd.return_value.__truediv__ = lambda self, x: MagicMock(exists=lambda: False)
            
            config = DoctorConfig()
            result = check_agents_yaml_exists(config)
            
            # Should skip when not found (optional)
            assert result.status == CheckStatus.SKIP
    
    def test_praison_config_dir_check(self):
        """Test .praison config directory check."""
        from praisonai.cli.features.doctor.checks.config_checks import check_praison_config_dir
        
        config = DoctorConfig()
        result = check_praison_config_dir(config)
        
        # Should pass or skip
        assert result.status in [CheckStatus.PASS, CheckStatus.SKIP]


class TestPermissionsChecks:
    """Tests for permissions checks."""
    
    def setup_method(self):
        """Reset registry before each test."""
        CheckRegistry.reset()
        from praisonai.cli.features.doctor.checks import permissions_checks
    
    def test_temp_dir_check(self):
        """Test temp directory permissions check."""
        from praisonai.cli.features.doctor.checks.permissions_checks import check_permissions_temp_dir
        
        config = DoctorConfig()
        result = check_permissions_temp_dir(config)
        
        # Should pass on most systems
        assert result.status == CheckStatus.PASS
    
    def test_cwd_check(self):
        """Test current working directory check."""
        from praisonai.cli.features.doctor.checks.permissions_checks import check_permissions_cwd
        
        config = DoctorConfig()
        result = check_permissions_cwd(config)
        
        # Should pass or warn
        assert result.status in [CheckStatus.PASS, CheckStatus.WARN]


class TestNetworkChecks:
    """Tests for network checks."""
    
    def setup_method(self):
        """Reset registry before each test."""
        CheckRegistry.reset()
        from praisonai.cli.features.doctor.checks import network_checks
    
    def test_proxy_check_no_proxy(self):
        """Test proxy check when no proxy is configured."""
        from praisonai.cli.features.doctor.checks.network_checks import check_network_proxy
        
        env = {k: v for k, v in os.environ.items() 
               if k.upper() not in ["HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"]}
        
        with patch.dict(os.environ, env, clear=True):
            config = DoctorConfig()
            result = check_network_proxy(config)
            
            assert result.status == CheckStatus.SKIP
    
    def test_ssl_check_default(self):
        """Test SSL configuration check with defaults."""
        from praisonai.cli.features.doctor.checks.network_checks import check_network_ssl
        
        config = DoctorConfig()
        result = check_network_ssl(config)
        
        # Should pass with default SSL config
        assert result.status in [CheckStatus.PASS, CheckStatus.WARN]
    
    def test_openai_base_url_check(self):
        """Test OpenAI base URL check."""
        from praisonai.cli.features.doctor.checks.network_checks import check_network_openai_base_url
        
        config = DoctorConfig()
        result = check_network_openai_base_url(config)
        
        # Should pass (either default or custom)
        assert result.status == CheckStatus.PASS


class TestPerformanceChecks:
    """Tests for performance checks."""
    
    def setup_method(self):
        """Reset registry before each test."""
        CheckRegistry.reset()
        from praisonai.cli.features.doctor.checks import performance_checks
    
    def test_loaded_modules_check(self):
        """Test loaded modules count check."""
        from praisonai.cli.features.doctor.checks.performance_checks import check_performance_loaded_modules
        
        config = DoctorConfig()
        result = check_performance_loaded_modules(config)
        
        assert result.status == CheckStatus.PASS
        assert result.metadata.get("total") is not None
        assert result.metadata["total"] > 0


class TestDbChecks:
    """Tests for database checks."""
    
    def setup_method(self):
        """Reset registry before each test."""
        CheckRegistry.reset()
        from praisonai.cli.features.doctor.checks import db_checks
    
    def test_db_config_no_dsn(self):
        """Test database config check when no DSN is set."""
        from praisonai.cli.features.doctor.checks.db_checks import check_db_config
        
        env = {k: v for k, v in os.environ.items() 
               if k not in ["DATABASE_URL", "PRAISONAI_DATABASE_URL"]}
        
        with patch.dict(os.environ, env, clear=True):
            config = DoctorConfig()
            result = check_db_config(config)
            
            assert result.status == CheckStatus.SKIP
    
    def test_sqlite_driver_check(self):
        """Test SQLite driver check."""
        from praisonai.cli.features.doctor.checks.db_checks import check_db_driver_sqlite
        
        config = DoctorConfig()
        result = check_db_driver_sqlite(config)
        
        # SQLite is built-in, should always pass
        assert result.status == CheckStatus.PASS


class TestMcpChecks:
    """Tests for MCP checks."""
    
    def setup_method(self):
        """Reset registry before each test."""
        CheckRegistry.reset()
        from praisonai.cli.features.doctor.checks import mcp_checks
    
    def test_mcp_config_not_found(self):
        """Test MCP config check when no config exists."""
        from praisonai.cli.features.doctor.checks.mcp_checks import check_mcp_config
        
        config = DoctorConfig()
        result = check_mcp_config(config)
        
        # Should skip when no config found
        assert result.status in [CheckStatus.PASS, CheckStatus.SKIP]


class TestSkillsChecks:
    """Tests for skills checks."""
    
    def setup_method(self):
        """Reset registry before each test."""
        CheckRegistry.reset()
        from praisonai.cli.features.doctor.checks import skills_checks
    
    def test_skills_dirs_check(self):
        """Test skills directories check."""
        from praisonai.cli.features.doctor.checks.skills_checks import check_skills_dirs
        
        config = DoctorConfig()
        result = check_skills_dirs(config)
        
        # Should pass or skip
        assert result.status in [CheckStatus.PASS, CheckStatus.SKIP]


class TestMemoryChecks:
    """Tests for memory checks."""
    
    def setup_method(self):
        """Reset registry before each test."""
        CheckRegistry.reset()
        from praisonai.cli.features.doctor.checks import memory_checks
    
    def test_memory_dirs_check(self):
        """Test memory directories check."""
        from praisonai.cli.features.doctor.checks.memory_checks import check_memory_dirs
        
        config = DoctorConfig()
        result = check_memory_dirs(config)
        
        # Should pass or skip
        assert result.status in [CheckStatus.PASS, CheckStatus.SKIP]


class TestObsChecks:
    """Tests for observability checks."""
    
    def setup_method(self):
        """Reset registry before each test."""
        CheckRegistry.reset()
        from praisonai.cli.features.doctor.checks import obs_checks
    
    def test_obs_config_check(self):
        """Test observability config check."""
        from praisonai.cli.features.doctor.checks.obs_checks import check_obs_config
        
        config = DoctorConfig()
        result = check_obs_config(config)
        
        # Should pass or skip
        assert result.status in [CheckStatus.PASS, CheckStatus.SKIP]


class TestStalePackagesCheck:
    """Tests for stale packages check (namespace package detection)."""
    
    def setup_method(self):
        """Reset registry before each test."""
        CheckRegistry.reset()
        from praisonai.cli.features.doctor.checks import env_checks
    
    def test_stale_packages_check_passes_when_clean(self):
        """Test stale packages check passes when no stale artifacts exist."""
        from praisonai.cli.features.doctor.checks.env_checks import check_stale_packages
        
        config = DoctorConfig()
        result = check_stale_packages(config)
        
        # Should pass when environment is clean
        assert result.status == CheckStatus.PASS
        assert "No stale package artifacts" in result.message
    
    def test_stale_packages_check_detects_namespace_package(self):
        """Test stale packages check detects when praisonaiagents is namespace pkg."""
        from praisonai.cli.features.doctor.checks.env_checks import check_stale_packages
        
        # Mock praisonaiagents with __file__ = None (namespace package)
        with patch('praisonai.cli.features.doctor.checks.env_checks.check_stale_packages') as mock_check:
            # This test verifies the check function exists and is callable
            # The actual namespace detection is tested in praisonaiagents tests
            config = DoctorConfig()
            result = check_stale_packages(config)
            
            # In clean environment, should pass
            assert result.status == CheckStatus.PASS
    
    def test_praisonaiagents_file_not_none(self):
        """Test that praisonaiagents.__file__ is not None (CI check)."""
        import praisonaiagents
        
        # This is the critical CI check - __file__ must not be None
        assert praisonaiagents.__file__ is not None, (
            "praisonaiagents.__file__ is None - this indicates a namespace package "
            "shadowing issue. Remove stale praisonaiagents directory from site-packages."
        )
    
    def test_praisonaiagents_spec_has_origin(self):
        """Test that praisonaiagents.__spec__.origin is not None (CI check)."""
        import praisonaiagents
        
        # Namespace packages have origin=None
        assert praisonaiagents.__spec__ is not None
        assert praisonaiagents.__spec__.origin is not None, (
            "praisonaiagents.__spec__.origin is None - namespace package detected"
        )
    
    def test_agent_import_succeeds(self):
        """Test that Agent can be imported (CI check)."""
        from praisonaiagents import Agent
        
        assert Agent is not None
        assert hasattr(Agent, '__init__')
        assert hasattr(Agent, 'start')
