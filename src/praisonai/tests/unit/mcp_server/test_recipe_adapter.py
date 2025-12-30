"""
Unit tests for Recipe MCP Adapter

Tests for the RecipeMCPAdapter and RecipeMCPConfig classes.
"""

from unittest.mock import MagicMock, patch


class TestRecipeMCPConfig:
    """Tests for RecipeMCPConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        from praisonai.mcp_server.recipe_adapter import RecipeMCPConfig
        
        config = RecipeMCPConfig(recipe_name="test-recipe")
        
        assert config.recipe_name == "test-recipe"
        assert config.expose_agent_tools is True
        assert config.expose_run_tool is True
        assert config.tool_namespace == "prefixed"
        assert config.expose_config is True
        assert config.expose_outputs is True
        assert config.expose_prompts is True
        assert config.safe_mode is True
        assert config.server_name == "test-recipe"
        assert config.server_version == "1.0.0"
        assert config.session_ttl == 3600
        assert config.max_concurrent_runs == 5
    
    def test_custom_config(self):
        """Test custom configuration values."""
        from praisonai.mcp_server.recipe_adapter import RecipeMCPConfig
        
        config = RecipeMCPConfig(
            recipe_name="my-recipe",
            safe_mode=False,
            tool_namespace="flat",
            server_name="custom-server",
            session_ttl=7200,
        )
        
        assert config.recipe_name == "my-recipe"
        assert config.safe_mode is False
        assert config.tool_namespace == "flat"
        assert config.server_name == "custom-server"
        assert config.session_ttl == 7200
    
    def test_default_denylist(self):
        """Test default tool denylist is populated."""
        from praisonai.mcp_server.recipe_adapter import RecipeMCPConfig
        
        config = RecipeMCPConfig(recipe_name="test")
        
        assert config.tool_denylist is not None
        assert len(config.tool_denylist) > 0
        assert "shell.exec" in config.tool_denylist


class TestRecipeMCPAdapter:
    """Tests for RecipeMCPAdapter class."""
    
    def test_init(self):
        """Test adapter initialization."""
        from praisonai.mcp_server.recipe_adapter import RecipeMCPAdapter
        
        adapter = RecipeMCPAdapter("test-recipe")
        
        assert adapter.recipe_name == "test-recipe"
        assert adapter.config is not None
        assert adapter._loaded is False
    
    def test_init_with_config(self):
        """Test adapter initialization with custom config."""
        from praisonai.mcp_server.recipe_adapter import RecipeMCPAdapter, RecipeMCPConfig
        
        config = RecipeMCPConfig(
            recipe_name="test-recipe",
            safe_mode=False,
        )
        adapter = RecipeMCPAdapter("test-recipe", config)
        
        assert adapter.config.safe_mode is False
    
    def test_sanitize_name(self):
        """Test name sanitization."""
        from praisonai.mcp_server.recipe_adapter import RecipeMCPAdapter
        
        adapter = RecipeMCPAdapter("test")
        
        assert adapter._sanitize_name("Test Name") == "test-name"
        assert adapter._sanitize_name("test_name") == "test-name"
        assert adapter._sanitize_name("TEST") == "test"
        assert adapter._sanitize_name("test@#$name") == "testname"
    
    def test_namespace_tool_prefixed(self):
        """Test tool namespacing with prefixed mode."""
        from praisonai.mcp_server.recipe_adapter import RecipeMCPAdapter, RecipeMCPConfig
        
        config = RecipeMCPConfig(recipe_name="my-recipe", tool_namespace="prefixed")
        adapter = RecipeMCPAdapter("my-recipe", config)
        
        result = adapter._namespace_tool("my-recipe", "agent1", "search")
        assert result == "my-recipe.agent1.search"
        
        result = adapter._namespace_tool("my-recipe", None, "run")
        assert result == "my-recipe.run"
    
    def test_namespace_tool_flat(self):
        """Test tool namespacing with flat mode."""
        from praisonai.mcp_server.recipe_adapter import RecipeMCPAdapter, RecipeMCPConfig
        
        config = RecipeMCPConfig(recipe_name="my-recipe", tool_namespace="flat")
        adapter = RecipeMCPAdapter("my-recipe", config)
        
        result = adapter._namespace_tool("my-recipe", "agent1", "search")
        assert result == "search"
    
    def test_namespace_tool_nested(self):
        """Test tool namespacing with nested mode."""
        from praisonai.mcp_server.recipe_adapter import RecipeMCPAdapter, RecipeMCPConfig
        
        config = RecipeMCPConfig(recipe_name="my-recipe", tool_namespace="nested")
        adapter = RecipeMCPAdapter("my-recipe", config)
        
        result = adapter._namespace_tool("my-recipe", "agent1", "search")
        assert result == "my-recipe/agent1/search"
    
    def test_is_tool_allowed_safe_mode(self):
        """Test tool allowlist in safe mode."""
        from praisonai.mcp_server.recipe_adapter import RecipeMCPAdapter, RecipeMCPConfig
        
        config = RecipeMCPConfig(recipe_name="test", safe_mode=True)
        adapter = RecipeMCPAdapter("test", config)
        
        assert adapter._is_tool_allowed("search") is True
        assert adapter._is_tool_allowed("shell.exec") is False
        assert adapter._is_tool_allowed("shell_tool") is False
    
    def test_is_tool_allowed_unsafe_mode(self):
        """Test all tools allowed in unsafe mode."""
        from praisonai.mcp_server.recipe_adapter import RecipeMCPAdapter, RecipeMCPConfig
        
        config = RecipeMCPConfig(recipe_name="test", safe_mode=False)
        adapter = RecipeMCPAdapter("test", config)
        
        assert adapter._is_tool_allowed("shell.exec") is True
        assert adapter._is_tool_allowed("anything") is True
    
    def test_is_tool_allowed_explicit_allowlist(self):
        """Test explicit tool allowlist."""
        from praisonai.mcp_server.recipe_adapter import RecipeMCPAdapter, RecipeMCPConfig
        
        config = RecipeMCPConfig(
            recipe_name="test",
            safe_mode=True,
            tool_allowlist=["search", "read"],
        )
        adapter = RecipeMCPAdapter("test", config)
        
        assert adapter._is_tool_allowed("search") is True
        assert adapter._is_tool_allowed("read") is True
        assert adapter._is_tool_allowed("write") is False
    
    def test_get_registries(self):
        """Test getting registries."""
        from praisonai.mcp_server.recipe_adapter import RecipeMCPAdapter
        from praisonai.mcp_server.registry import MCPToolRegistry, MCPResourceRegistry, MCPPromptRegistry
        
        adapter = RecipeMCPAdapter("test")
        
        assert isinstance(adapter.get_tool_registry(), MCPToolRegistry)
        assert isinstance(adapter.get_resource_registry(), MCPResourceRegistry)
        assert isinstance(adapter.get_prompt_registry(), MCPPromptRegistry)


class TestRecipeToolWrapper:
    """Tests for RecipeToolWrapper dataclass."""
    
    def test_tool_wrapper(self):
        """Test tool wrapper creation."""
        from praisonai.mcp_server.recipe_adapter import RecipeToolWrapper
        
        wrapper = RecipeToolWrapper(
            name="test-tool",
            description="A test tool",
            handler=lambda: None,
            input_schema={"type": "object"},
        )
        
        assert wrapper.name == "test-tool"
        assert wrapper.description == "A test tool"
        assert wrapper.input_schema == {"type": "object"}
    
    def test_tool_wrapper_with_annotations(self):
        """Test tool wrapper with annotations."""
        from praisonai.mcp_server.recipe_adapter import RecipeToolWrapper
        
        wrapper = RecipeToolWrapper(
            name="test-tool",
            description="A test tool",
            handler=lambda: None,
            input_schema={"type": "object"},
            annotations={"recipe": "test", "type": "agent_tool"},
            agent_name="agent1",
            original_name="original_tool",
        )
        
        assert wrapper.annotations["recipe"] == "test"
        assert wrapper.agent_name == "agent1"
        assert wrapper.original_name == "original_tool"


class TestCreateRecipeMCPServer:
    """Tests for create_recipe_mcp_server function."""
    
    @patch('praisonai.mcp_server.recipe_adapter.RecipeMCPAdapter')
    def test_create_server(self, mock_adapter_class):
        """Test creating MCP server from recipe."""
        from praisonai.mcp_server.recipe_adapter import create_recipe_mcp_server
        
        mock_adapter = MagicMock()
        mock_server = MagicMock()
        mock_adapter.to_mcp_server.return_value = mock_server
        mock_adapter_class.return_value = mock_adapter
        
        result = create_recipe_mcp_server("test-recipe")
        
        mock_adapter_class.assert_called_once()
        mock_adapter.load.assert_called_once()
        mock_adapter.to_mcp_server.assert_called_once()
        assert result == mock_server
