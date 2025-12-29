"""
Tests for lazy import behavior in praisonaiagents.

These tests verify that heavy dependencies like litellm are NOT loaded
at package import time, ensuring fast startup.
"""
import sys
import pytest


def clear_modules():
    """Clear all praisonai and litellm related modules from cache."""
    to_remove = [m for m in list(sys.modules.keys()) 
                 if 'praison' in m or 'litellm' in m]
    for mod in to_remove:
        del sys.modules[mod]


class TestLazyImports:
    """Test that heavy dependencies are lazily loaded."""
    
    def setup_method(self):
        """Clear module cache before each test."""
        clear_modules()
    
    def teardown_method(self):
        """Clean up after each test."""
        clear_modules()
    
    def test_litellm_not_loaded_on_import(self):
        """litellm should NOT be loaded when importing praisonaiagents."""
        import praisonaiagents  # noqa: F401
        
        assert 'litellm' not in sys.modules, \
            "litellm should not be loaded at import time"
    
    def test_requests_not_loaded_on_import(self):
        """requests should NOT be loaded when importing praisonaiagents."""
        import praisonaiagents  # noqa: F401
        
        assert 'requests' not in sys.modules, \
            "requests should not be loaded at import time"
    
    def test_chromadb_not_loaded_on_import(self):
        """chromadb should NOT be loaded when importing praisonaiagents."""
        import praisonaiagents  # noqa: F401
        
        assert 'chromadb' not in sys.modules, \
            "chromadb should not be loaded at import time"
    
    def test_agent_available_via_getattr(self):
        """Agent should be available via lazy loading."""
        import praisonaiagents
        
        # Access Agent - this triggers lazy loading
        Agent = praisonaiagents.Agent
        
        assert Agent is not None
        assert hasattr(Agent, 'chat')
    
    def test_session_available_via_getattr(self):
        """Session should be available via lazy loading."""
        import praisonaiagents
        
        # Access Session - this triggers lazy loading
        Session = praisonaiagents.Session
        
        assert Session is not None
    
    def test_knowledge_available_via_getattr(self):
        """Knowledge should be available via lazy loading."""
        import praisonaiagents
        
        # Access Knowledge - this triggers lazy loading
        Knowledge = praisonaiagents.Knowledge
        
        assert Knowledge is not None
    
    def test_memory_available_via_getattr(self):
        """Memory should be available via lazy loading."""
        import praisonaiagents
        
        # Access Memory - this triggers lazy loading
        Memory = praisonaiagents.Memory
        
        assert Memory is not None
    
    def test_tools_loaded_eagerly(self):
        """Tools should be available immediately (lightweight)."""
        import praisonaiagents
        
        # Tools is lightweight and should be available
        assert hasattr(praisonaiagents, 'Tools')
        assert praisonaiagents.Tools is not None
    
    def test_all_exports_accessible(self):
        """All items in __all__ should be accessible."""
        import praisonaiagents
        
        for name in praisonaiagents.__all__:
            # Some items may be None if optional deps not installed
            try:
                attr = getattr(praisonaiagents, name)
                # Just verify it's accessible, may be None
            except AttributeError:
                pytest.fail(f"'{name}' in __all__ but not accessible")


class TestLitePackage:
    """Test the lite subpackage."""
    
    def setup_method(self):
        """Clear module cache before each test."""
        clear_modules()
    
    def test_lite_import_fast(self):
        """Lite package should import quickly without heavy deps."""
        import time
        
        start = time.perf_counter()
        from praisonaiagents.lite import LiteAgent  # noqa: F401
        end = time.perf_counter()
        
        import_time_ms = (end - start) * 1000
        
        # Lite should import in under 200ms (allowing for system variance)
        assert import_time_ms < 200, \
            f"Lite import took {import_time_ms:.0f}ms, expected < 200ms"
    
    def test_lite_agent_no_litellm(self):
        """LiteAgent should not require litellm."""
        from praisonaiagents.lite import LiteAgent
        
        # Create agent without LLM function
        agent = LiteAgent(name="Test")
        
        assert agent.name == "Test"
        assert 'litellm' not in sys.modules
    
    def test_lite_agent_with_custom_llm(self):
        """LiteAgent should work with custom LLM function."""
        from praisonaiagents.lite import LiteAgent
        
        # Create a mock LLM function
        def mock_llm(messages):
            return "Hello from mock LLM!"
        
        agent = LiteAgent(
            name="TestAgent",
            llm_fn=mock_llm,
            instructions="You are a test agent."
        )
        
        response = agent.chat("Hi")
        
        assert response == "Hello from mock LLM!"
        assert len(agent.chat_history) == 2  # user + assistant


class TestTelemetryConfig:
    """Test telemetry configuration."""
    
    def setup_method(self):
        """Clear module cache and env vars before each test."""
        clear_modules()
        import os
        # Save original env vars
        self._orig_env = {}
        for key in ['PRAISONAI_TELEMETRY_ENABLED', 'PRAISONAI_TELEMETRY_DISABLED', 
                    'DO_NOT_TRACK', 'PRAISONAI_DISABLE_TELEMETRY']:
            self._orig_env[key] = os.environ.get(key)
            if key in os.environ:
                del os.environ[key]
    
    def teardown_method(self):
        """Restore env vars after each test."""
        import os
        for key, value in self._orig_env.items():
            if value is None:
                if key in os.environ:
                    del os.environ[key]
            else:
                os.environ[key] = value
        clear_modules()
    
    def test_telemetry_disabled_by_default(self):
        """Telemetry should be disabled by default (opt-in model)."""
        from praisonaiagents._config import TELEMETRY_ENABLED
        
        assert TELEMETRY_ENABLED is False, \
            "Telemetry should be disabled by default"
    
    def test_telemetry_enabled_via_env(self):
        """Telemetry can be enabled via environment variable."""
        import os
        os.environ['PRAISONAI_TELEMETRY_ENABLED'] = 'true'
        
        # Re-import to pick up new env var
        clear_modules()
        from praisonaiagents._config import _get_telemetry_enabled
        
        assert _get_telemetry_enabled() is True
    
    def test_do_not_track_takes_precedence(self):
        """DO_NOT_TRACK should disable telemetry even if enabled."""
        import os
        os.environ['PRAISONAI_TELEMETRY_ENABLED'] = 'true'
        os.environ['DO_NOT_TRACK'] = 'true'
        
        clear_modules()
        from praisonaiagents._config import _get_telemetry_enabled
        
        assert _get_telemetry_enabled() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
