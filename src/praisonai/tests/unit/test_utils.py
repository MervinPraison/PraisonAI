"""
Common test utilities and helpers for PraisonAI unit tests.

This module provides reusable test utilities, fixtures, and helper functions
to improve test consistency and reduce code duplication across the test suite.
"""
import asyncio
import json
from typing import Any, Dict, List, Optional, Callable, Union
from unittest.mock import Mock, AsyncMock, MagicMock
from pathlib import Path
import pytest


class TestDataBuilder:
    """Builder pattern for creating test data with sensible defaults."""
    
    @staticmethod
    def create_agent_config(
        name: str = "TestAgent",
        role: str = "Test Specialist", 
        goal: str = "Perform testing tasks",
        backstory: str = "An expert testing agent",
        model: str = "gpt-4o-mini",
        api_key: str = "test-api-key",
        **kwargs
    ) -> Dict[str, Any]:
        """Create agent configuration with defaults."""
        config = {
            'name': name,
            'role': role,
            'goal': goal,
            'backstory': backstory,
            'llm': {
                'model': model,
                'api_key': api_key
            }
        }
        config.update(kwargs)
        return config
    
    @staticmethod
    def create_task_config(
        name: str = "test_task",
        description: str = "A test task",
        expected_output: str = "Test output",
        **kwargs
    ) -> Dict[str, Any]:
        """Create task configuration with defaults."""
        config = {
            'name': name,
            'description': description,
            'expected_output': expected_output
        }
        config.update(kwargs)
        return config
    
    @staticmethod
    def create_tool_config(
        name: str = "test_tool",
        description: str = "A test tool",
        func: Optional[Callable] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Create tool configuration with defaults."""
        if func is None:
            func = lambda x: f"Processed: {x}"
        
        config = {
            'name': name,
            'description': description,
            'func': func
        }
        config.update(kwargs)
        return config


class MockResponseBuilder:
    """Builder for creating consistent mock responses."""
    
    @staticmethod
    def create_llm_response(
        content: str = "Test response",
        model: str = "gpt-4o-mini",
        total_tokens: int = 100,
        **kwargs
    ) -> Mock:
        """Create a mock LLM response."""
        response = Mock()
        response.choices = [
            Mock(
                message=Mock(content=content),
                index=0,
                finish_reason="stop"
            )
        ]
        response.usage = Mock(
            total_tokens=total_tokens,
            prompt_tokens=50,
            completion_tokens=50
        )
        response.model = model
        
        for key, value in kwargs.items():
            setattr(response, key, value)
        
        return response
    
    @staticmethod
    def create_streaming_response(
        chunks: List[str] = None,
        model: str = "gpt-4o-mini"
    ) -> List[Mock]:
        """Create a mock streaming response."""
        if chunks is None:
            chunks = ["Test ", "streaming ", "response"]
        
        responses = []
        for i, chunk in enumerate(chunks):
            response = Mock()
            response.choices = [
                Mock(
                    delta=Mock(content=chunk),
                    index=0,
                    finish_reason=None if i < len(chunks) - 1 else "stop"
                )
            ]
            response.model = model
            responses.append(response)
        
        return responses
    
    @staticmethod
    def create_error_response(
        error_type: type = Exception,
        error_message: str = "Test error",
        status_code: int = 500
    ) -> Mock:
        """Create a mock error response."""
        error = error_type(error_message)
        error.status_code = status_code
        return error


class AsyncTestHelper:
    """Helper for async test operations."""
    
    @staticmethod
    async def run_with_timeout(
        coro: Callable,
        timeout: float = 5.0,
        timeout_message: str = "Test timed out"
    ) -> Any:
        """Run an async operation with a timeout."""
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            pytest.fail(timeout_message)
    
    @staticmethod
    def create_async_mock(return_value: Any = None) -> AsyncMock:
        """Create an async mock with proper configuration."""
        mock = AsyncMock()
        if return_value is not None:
            mock.return_value = return_value
        return mock
    
    @staticmethod
    async def assert_async_called_with_retry(
        mock: AsyncMock,
        expected_args: tuple = None,
        expected_kwargs: dict = None,
        max_retries: int = 3,
        retry_delay: float = 0.1
    ) -> None:
        """Assert async mock was called with expected args, with retry logic."""
        for i in range(max_retries):
            try:
                if expected_args and expected_kwargs:
                    mock.assert_called_with(*expected_args, **expected_kwargs)
                elif expected_args:
                    mock.assert_called_with(*expected_args)
                elif expected_kwargs:
                    mock.assert_called_with(**expected_kwargs)
                else:
                    mock.assert_called()
                return
            except AssertionError:
                if i < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    raise


class FileSystemTestHelper:
    """Helper for file system operations in tests."""
    
    @staticmethod
    def create_test_file(
        path: Path,
        content: str = "Test content",
        encoding: str = "utf-8"
    ) -> Path:
        """Create a test file with content."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding=encoding)
        return path
    
    @staticmethod
    def create_test_json_file(
        path: Path,
        data: Dict[str, Any]
    ) -> Path:
        """Create a test JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        return path
    
    @staticmethod
    def assert_file_contains(
        path: Path,
        expected_content: str,
        encoding: str = "utf-8"
    ) -> None:
        """Assert a file contains expected content."""
        actual_content = path.read_text(encoding=encoding)
        assert expected_content in actual_content, \
            f"Expected '{expected_content}' not found in file {path}"


class MockFactories:
    """Factory methods for creating common mocks."""
    
    @staticmethod
    def create_mock_agent(
        name: str = "MockAgent",
        execute_return: Any = "Task executed"
    ) -> Mock:
        """Create a mock agent."""
        mock_agent = Mock()
        mock_agent.name = name
        mock_agent.execute = Mock(return_value=execute_return)
        mock_agent.aexecute = AsyncMock(return_value=execute_return)
        return mock_agent
    
    @staticmethod
    def create_mock_task(
        name: str = "mock_task",
        output: Any = "Task output"
    ) -> Mock:
        """Create a mock task."""
        mock_task = Mock()
        mock_task.name = name
        mock_task.output = output
        mock_task.status = "completed"
        return mock_task
    
    @staticmethod
    def create_mock_tool(
        name: str = "mock_tool",
        return_value: Any = "Tool result"
    ) -> Mock:
        """Create a mock tool."""
        mock_tool = Mock()
        mock_tool.name = name
        mock_tool.__name__ = name  # For function tools
        mock_tool.return_value = return_value
        mock_tool.description = f"Mock {name} tool"
        return mock_tool


def assert_no_hardcoded_secrets(
    content: str,
    patterns: List[str] = None
) -> None:
    """Assert that content doesn't contain hardcoded secrets."""
    if patterns is None:
        patterns = [
            'sk-',  # OpenAI API key prefix
            'AIza',  # Google API key prefix
            'ghp_',  # GitHub personal access token
            'ghs_',  # GitHub server token
            'password=',
            'secret=',
            'token=',
            'api_key=',
        ]
    
    for pattern in patterns:
        assert pattern not in content, \
            f"Potential secret found: pattern '{pattern}' detected in content"


def parametrize_providers(test_func: Callable) -> Callable:
    """Decorator to parametrize tests across different LLM providers."""
    providers = [
        ("openai", "gpt-4o-mini"),
        ("anthropic", "claude-3-sonnet"),
        ("google", "gemini-pro"),
        ("ollama", "llama2"),
    ]
    
    return pytest.mark.parametrize("provider,model", providers)(test_func)


class TestMetrics:
    """Helper for tracking test metrics and performance."""
    
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.memory_usage = []
    
    def start(self):
        """Start tracking metrics."""
        import time
        self.start_time = time.time()
    
    def end(self):
        """End tracking and return duration."""
        import time
        self.end_time = time.time()
        return self.end_time - self.start_time
    
    def assert_performance(
        self,
        max_duration: float,
        message: str = "Test exceeded performance threshold"
    ):
        """Assert test completed within duration limit."""
        duration = self.end()
        assert duration <= max_duration, \
            f"{message}: {duration:.2f}s > {max_duration}s"