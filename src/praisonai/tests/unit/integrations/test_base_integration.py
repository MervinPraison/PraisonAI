"""
Tests for BaseCLIIntegration class.

TDD approach: Write tests first, then implement.
"""

import pytest
import asyncio
import json
from unittest.mock import patch, MagicMock, AsyncMock
import sys
import os

# Add the praisonai package to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))


class TestBaseCLIIntegration:
    """Tests for the BaseCLIIntegration abstract base class."""
    
    def test_import_base_integration(self):
        """Test that BaseCLIIntegration can be imported."""
        from praisonai.integrations.base import BaseCLIIntegration
        assert BaseCLIIntegration is not None
    
    def test_base_integration_is_abstract(self):
        """Test that BaseCLIIntegration cannot be instantiated directly."""
        from praisonai.integrations.base import BaseCLIIntegration
        with pytest.raises(TypeError):
            BaseCLIIntegration()
    
    def test_concrete_implementation_requires_cli_command(self):
        """Test that concrete implementations must define cli_command."""
        from praisonai.integrations.base import BaseCLIIntegration
        
        class IncompleteIntegration(BaseCLIIntegration):
            pass
        
        with pytest.raises(TypeError):
            IncompleteIntegration()
    
    def test_is_available_returns_false_for_missing_cli(self):
        """Test is_available returns False when CLI is not installed."""
        from praisonai.integrations.base import BaseCLIIntegration
        
        class TestIntegration(BaseCLIIntegration):
            @property
            def cli_command(self) -> str:
                return "nonexistent_cli_tool_12345"
            
            async def execute(self, prompt: str, **options) -> str:
                return ""
            
            async def stream(self, prompt: str, **options):
                yield {}
        
        integration = TestIntegration()
        assert integration.is_available is False
    
    def test_is_available_caches_result(self):
        """Test that is_available caches the availability check."""
        from praisonai.integrations.base import BaseCLIIntegration
        
        class TestIntegration(BaseCLIIntegration):
            @property
            def cli_command(self) -> str:
                return "nonexistent_cli_12345"
            
            async def execute(self, prompt: str, **options) -> str:
                return ""
            
            async def stream(self, prompt: str, **options):
                yield {}
        
        integration = TestIntegration()
        # First call
        result1 = integration.is_available
        # Second call should use cache
        result2 = integration.is_available
        assert result1 == result2
    
    def test_workspace_default_is_current_dir(self):
        """Test that default workspace is current directory."""
        from praisonai.integrations.base import BaseCLIIntegration
        
        class TestIntegration(BaseCLIIntegration):
            @property
            def cli_command(self) -> str:
                return "test"
            
            async def execute(self, prompt: str, **options) -> str:
                return ""
            
            async def stream(self, prompt: str, **options):
                yield {}
        
        integration = TestIntegration()
        assert integration.workspace == "."
    
    def test_workspace_can_be_set(self):
        """Test that workspace can be set during initialization."""
        from praisonai.integrations.base import BaseCLIIntegration
        
        class TestIntegration(BaseCLIIntegration):
            @property
            def cli_command(self) -> str:
                return "test"
            
            async def execute(self, prompt: str, **options) -> str:
                return ""
            
            async def stream(self, prompt: str, **options):
                yield {}
        
        integration = TestIntegration(workspace="/custom/path")
        assert integration.workspace == "/custom/path"
    
    def test_timeout_default_is_300(self):
        """Test that default timeout is 300 seconds."""
        from praisonai.integrations.base import BaseCLIIntegration
        
        class TestIntegration(BaseCLIIntegration):
            @property
            def cli_command(self) -> str:
                return "test"
            
            async def execute(self, prompt: str, **options) -> str:
                return ""
            
            async def stream(self, prompt: str, **options):
                yield {}
        
        integration = TestIntegration()
        assert integration.timeout == 300
    
    def test_as_tool_returns_callable(self):
        """Test that as_tool returns a callable function."""
        from praisonai.integrations.base import BaseCLIIntegration
        
        class TestIntegration(BaseCLIIntegration):
            @property
            def cli_command(self) -> str:
                return "test"
            
            async def execute(self, prompt: str, **options) -> str:
                return "test result"
            
            async def stream(self, prompt: str, **options):
                yield {}
        
        integration = TestIntegration()
        tool = integration.as_tool()
        assert callable(tool)
    
    def test_as_tool_has_correct_name(self):
        """Test that the tool function has the correct name."""
        from praisonai.integrations.base import BaseCLIIntegration
        
        class TestIntegration(BaseCLIIntegration):
            @property
            def cli_command(self) -> str:
                return "my_cli"
            
            async def execute(self, prompt: str, **options) -> str:
                return ""
            
            async def stream(self, prompt: str, **options):
                yield {}
        
        integration = TestIntegration()
        tool = integration.as_tool()
        assert tool.__name__ == "my_cli_tool"
    
    def test_as_tool_has_docstring(self):
        """Test that the tool function has a docstring."""
        from praisonai.integrations.base import BaseCLIIntegration
        
        class TestIntegration(BaseCLIIntegration):
            @property
            def cli_command(self) -> str:
                return "test"
            
            async def execute(self, prompt: str, **options) -> str:
                return ""
            
            async def stream(self, prompt: str, **options):
                yield {}
        
        integration = TestIntegration()
        tool = integration.as_tool()
        assert tool.__doc__ is not None
        assert "test" in tool.__doc__


class TestBaseCLIIntegrationAsync:
    """Async tests for BaseCLIIntegration."""
    
    @pytest.mark.asyncio
    async def test_execute_async_runs_command(self):
        """Test that execute_async runs a command."""
        from praisonai.integrations.base import BaseCLIIntegration
        
        class TestIntegration(BaseCLIIntegration):
            @property
            def cli_command(self) -> str:
                return "echo"
            
            async def execute(self, prompt: str, **options) -> str:
                return await self.execute_async(["echo", prompt])
            
            async def stream(self, prompt: str, **options):
                yield {}
        
        integration = TestIntegration()
        result = await integration.execute("hello")
        assert "hello" in result
    
    @pytest.mark.asyncio
    async def test_execute_async_handles_timeout(self):
        """Test that execute_async handles timeout."""
        from praisonai.integrations.base import BaseCLIIntegration
        
        class TestIntegration(BaseCLIIntegration):
            @property
            def cli_command(self) -> str:
                return "sleep"
            
            async def execute(self, prompt: str, **options) -> str:
                return await self.execute_async(["sleep", "10"], timeout=0.1)
            
            async def stream(self, prompt: str, **options):
                yield {}
        
        integration = TestIntegration()
        with pytest.raises(TimeoutError):
            await integration.execute("test")
    
    @pytest.mark.asyncio
    async def test_execute_async_captures_stderr(self):
        """Test that execute_async captures stderr."""
        from praisonai.integrations.base import BaseCLIIntegration
        
        class TestIntegration(BaseCLIIntegration):
            @property
            def cli_command(self) -> str:
                return "bash"
            
            async def execute(self, prompt: str, **options) -> str:
                stdout, stderr = await self.execute_async_with_stderr(
                    ["bash", "-c", "echo error >&2"]
                )
                return stderr
            
            async def stream(self, prompt: str, **options):
                yield {}
        
        integration = TestIntegration()
        result = await integration.execute("test")
        assert "error" in result


class TestAvailabilityCache:
    """Tests for the availability caching mechanism."""
    
    def test_availability_cache_is_class_level(self):
        """Test that availability cache is shared across instances."""
        from praisonai.integrations.base import BaseCLIIntegration
        
        class TestIntegration(BaseCLIIntegration):
            @property
            def cli_command(self) -> str:
                return "shared_test_cli"
            
            async def execute(self, prompt: str, **options) -> str:
                return ""
            
            async def stream(self, prompt: str, **options):
                yield {}
        
        integration1 = TestIntegration()
        integration2 = TestIntegration()
        
        # Access is_available on first instance
        _ = integration1.is_available
        
        # Second instance should use cached value
        assert "shared_test_cli" in BaseCLIIntegration._availability_cache
    
    def test_clear_availability_cache(self):
        """Test that availability cache can be cleared."""
        from praisonai.integrations.base import BaseCLIIntegration
        
        # Clear cache
        BaseCLIIntegration._availability_cache.clear()
        assert len(BaseCLIIntegration._availability_cache) == 0
