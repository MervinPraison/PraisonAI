"""
Unit tests for Recipe Runtime Configuration.

Tests:
- RuntimeConfig parsing from dict
- Environment variable expansion
- Default values
- Schema validation
"""

import os
from unittest.mock import patch


class TestRuntimeConfig:
    """Tests for RuntimeConfig dataclass."""
    
    def test_empty_runtime_config(self):
        """Test creating RuntimeConfig with no data."""
        from praisonai.recipe.runtime import RuntimeConfig
        
        config = RuntimeConfig()
        
        assert config.background.enabled is False
        assert config.job.enabled is False
        assert config.schedule.enabled is False
    
    def test_runtime_config_from_dict(self):
        """Test creating RuntimeConfig from dictionary."""
        from praisonai.recipe.runtime import RuntimeConfig
        
        data = {
            'background': {
                'enabled': True,
                'max_concurrent': 10,
            },
            'job': {
                'enabled': True,
                'timeout_sec': 600,
                'webhook_url': 'https://example.com/webhook',
            },
            'schedule': {
                'enabled': True,
                'interval': 'daily',
                'max_retries': 5,
            },
        }
        
        config = RuntimeConfig.from_dict(data)
        
        assert config.background.enabled is True
        assert config.background.max_concurrent == 10
        assert config.job.enabled is True
        assert config.job.timeout_sec == 600
        assert config.job.webhook_url == 'https://example.com/webhook'
        assert config.schedule.enabled is True
        assert config.schedule.interval == 'daily'
        assert config.schedule.max_retries == 5
    
    def test_runtime_config_defaults(self):
        """Test that defaults are applied correctly."""
        from praisonai.recipe.runtime import (
            RuntimeConfig,
            DEFAULT_TIMEOUT_SEC,
            DEFAULT_MAX_COST_USD,
            DEFAULT_MAX_RETRIES,
            DEFAULT_MAX_CONCURRENT,
        )
        
        config = RuntimeConfig.from_dict({})
        
        assert config.background.max_concurrent == DEFAULT_MAX_CONCURRENT
        assert config.job.timeout_sec == DEFAULT_TIMEOUT_SEC
        assert config.schedule.max_retries == DEFAULT_MAX_RETRIES
        assert config.schedule.max_cost_usd == DEFAULT_MAX_COST_USD
    
    def test_runtime_config_to_dict(self):
        """Test converting RuntimeConfig to dictionary."""
        from praisonai.recipe.runtime import RuntimeConfig
        
        config = RuntimeConfig()
        data = config.to_dict()
        
        assert 'background' in data
        assert 'job' in data
        assert 'schedule' in data
        assert data['background']['enabled'] is False
        assert data['job']['enabled'] is False
        assert data['schedule']['enabled'] is False


class TestEnvVarExpansion:
    """Tests for environment variable expansion."""
    
    def test_expand_simple_env_var(self):
        """Test expanding a simple environment variable."""
        from praisonai.recipe.runtime import expand_env_vars
        
        with patch.dict(os.environ, {'MY_VAR': 'test_value'}):
            result = expand_env_vars('${MY_VAR}')
            assert result == 'test_value'
    
    def test_expand_env_var_in_string(self):
        """Test expanding env var embedded in string."""
        from praisonai.recipe.runtime import expand_env_vars
        
        with patch.dict(os.environ, {'API_KEY': 'secret123'}):
            result = expand_env_vars('Bearer ${API_KEY}')
            assert result == 'Bearer secret123'
    
    def test_expand_missing_env_var(self):
        """Test that missing env vars are kept as-is."""
        from praisonai.recipe.runtime import expand_env_vars
        
        result = expand_env_vars('${NONEXISTENT_VAR}')
        assert result == '${NONEXISTENT_VAR}'
    
    def test_expand_env_var_in_dict(self):
        """Test expanding env vars in nested dict."""
        from praisonai.recipe.runtime import expand_env_vars
        
        with patch.dict(os.environ, {'WEBHOOK': 'https://example.com'}):
            data = {
                'url': '${WEBHOOK}/callback',
                'nested': {
                    'value': '${WEBHOOK}/nested'
                }
            }
            result = expand_env_vars(data)
            
            assert result['url'] == 'https://example.com/callback'
            assert result['nested']['value'] == 'https://example.com/nested'
    
    def test_expand_env_var_in_list(self):
        """Test expanding env vars in list."""
        from praisonai.recipe.runtime import expand_env_vars
        
        with patch.dict(os.environ, {'VAL': 'expanded'}):
            data = ['${VAL}', 'static', '${VAL}_suffix']
            result = expand_env_vars(data)
            
            assert result == ['expanded', 'static', 'expanded_suffix']
    
    def test_no_expansion_for_non_string(self):
        """Test that non-string values are returned as-is."""
        from praisonai.recipe.runtime import expand_env_vars
        
        assert expand_env_vars(123) == 123
        assert expand_env_vars(True) is True
        assert expand_env_vars(None) is None


class TestParseRuntimeConfig:
    """Tests for parse_runtime_config function."""
    
    def test_parse_none(self):
        """Test parsing None returns default config."""
        from praisonai.recipe.runtime import parse_runtime_config, RuntimeConfig
        
        config = parse_runtime_config(None)
        
        assert isinstance(config, RuntimeConfig)
        assert config.background.enabled is False
    
    def test_parse_with_env_expansion(self):
        """Test parsing with environment variable expansion."""
        from praisonai.recipe.runtime import parse_runtime_config
        
        with patch.dict(os.environ, {'WEBHOOK_URL': 'https://hooks.example.com'}):
            data = {
                'job': {
                    'enabled': True,
                    'webhook_url': '${WEBHOOK_URL}/notify',
                }
            }
            config = parse_runtime_config(data, expand_env=True)
            
            assert config.job.webhook_url == 'https://hooks.example.com/notify'
    
    def test_parse_without_env_expansion(self):
        """Test parsing without environment variable expansion."""
        from praisonai.recipe.runtime import parse_runtime_config
        
        data = {
            'job': {
                'webhook_url': '${WEBHOOK_URL}',
            }
        }
        config = parse_runtime_config(data, expand_env=False)
        
        assert config.job.webhook_url == '${WEBHOOK_URL}'


class TestBackgroundRuntimeConfig:
    """Tests for BackgroundRuntimeConfig."""
    
    def test_from_dict_with_all_fields(self):
        """Test creating from dict with all fields."""
        from praisonai.recipe.runtime import BackgroundRuntimeConfig
        
        data = {
            'enabled': True,
            'max_concurrent': 20,
            'cleanup_delay_sec': 7200,
        }
        config = BackgroundRuntimeConfig.from_dict(data)
        
        assert config.enabled is True
        assert config.max_concurrent == 20
        assert config.cleanup_delay_sec == 7200
    
    def test_from_dict_partial(self):
        """Test creating from dict with partial fields."""
        from praisonai.recipe.runtime import BackgroundRuntimeConfig, DEFAULT_MAX_CONCURRENT
        
        data = {'enabled': True}
        config = BackgroundRuntimeConfig.from_dict(data)
        
        assert config.enabled is True
        assert config.max_concurrent == DEFAULT_MAX_CONCURRENT


class TestJobRuntimeConfig:
    """Tests for JobRuntimeConfig."""
    
    def test_from_dict_with_all_fields(self):
        """Test creating from dict with all fields."""
        from praisonai.recipe.runtime import JobRuntimeConfig
        
        data = {
            'enabled': True,
            'timeout_sec': 1800,
            'webhook_url': 'https://example.com',
            'idempotency_scope': 'global',
            'events': ['completed'],
        }
        config = JobRuntimeConfig.from_dict(data)
        
        assert config.enabled is True
        assert config.timeout_sec == 1800
        assert config.webhook_url == 'https://example.com'
        assert config.idempotency_scope == 'global'
        assert config.events == ['completed']
    
    def test_default_events(self):
        """Test default events list."""
        from praisonai.recipe.runtime import JobRuntimeConfig
        
        config = JobRuntimeConfig.from_dict({})
        
        assert config.events == ['completed', 'failed']


class TestScheduleRuntimeConfig:
    """Tests for ScheduleRuntimeConfig."""
    
    def test_from_dict_with_all_fields(self):
        """Test creating from dict with all fields."""
        from praisonai.recipe.runtime import ScheduleRuntimeConfig
        
        data = {
            'enabled': True,
            'interval': '*/30m',
            'max_retries': 5,
            'run_immediately': True,
            'timeout_sec': 600,
            'max_cost_usd': 2.50,
        }
        config = ScheduleRuntimeConfig.from_dict(data)
        
        assert config.enabled is True
        assert config.interval == '*/30m'
        assert config.max_retries == 5
        assert config.run_immediately is True
        assert config.timeout_sec == 600
        assert config.max_cost_usd == 2.50
    
    def test_default_interval(self):
        """Test default interval is hourly."""
        from praisonai.recipe.runtime import ScheduleRuntimeConfig
        
        config = ScheduleRuntimeConfig.from_dict({})
        
        assert config.interval == 'hourly'
