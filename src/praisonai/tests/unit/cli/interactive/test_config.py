"""Tests for InteractiveCore config module."""
import os
import tempfile


class TestInteractiveConfig:
    """Tests for InteractiveConfig dataclass."""
    
    def test_config_defaults(self):
        """Config should have sensible defaults."""
        from praisonai.cli.interactive.config import InteractiveConfig
        
        config = InteractiveConfig()
        
        assert config.model is None  # Use default from env/settings
        assert config.session_id is None  # Auto-generate
        assert config.continue_session is False
        assert config.workspace == os.getcwd()
        assert config.enable_acp is True
        assert config.enable_lsp is True
        assert config.verbose is False
        assert config.memory is False
        assert config.approval_mode == "prompt"  # Default: ask user
        assert config.files == []
    
    def test_config_with_values(self):
        """Config should accept all values."""
        from praisonai.cli.interactive.config import InteractiveConfig
        
        config = InteractiveConfig(
            model="gpt-4",
            session_id="test-session-123",
            continue_session=True,
            workspace="/tmp/workspace",
            enable_acp=False,
            enable_lsp=False,
            verbose=True,
            memory=True,
            approval_mode="auto",
            files=["/tmp/file1.py", "/tmp/file2.py"]
        )
        
        assert config.model == "gpt-4"
        assert config.session_id == "test-session-123"
        assert config.continue_session is True
        assert config.workspace == "/tmp/workspace"
        assert config.enable_acp is False
        assert config.enable_lsp is False
        assert config.verbose is True
        assert config.memory is True
        assert config.approval_mode == "auto"
        assert config.files == ["/tmp/file1.py", "/tmp/file2.py"]
    
    def test_config_from_env(self):
        """Config should be creatable from environment variables."""
        from praisonai.cli.interactive.config import InteractiveConfig
        
        # Set env vars
        os.environ["PRAISON_MODEL"] = "claude-3-opus"
        os.environ["PRAISON_WORKSPACE"] = "/custom/workspace"
        os.environ["PRAISON_APPROVAL_MODE"] = "auto"
        
        try:
            config = InteractiveConfig.from_env()
            
            assert config.model == "claude-3-opus"
            assert config.workspace == "/custom/workspace"
            assert config.approval_mode == "auto"
        finally:
            # Cleanup
            os.environ.pop("PRAISON_MODEL", None)
            os.environ.pop("PRAISON_WORKSPACE", None)
            os.environ.pop("PRAISON_APPROVAL_MODE", None)
    
    def test_config_from_cli_args(self):
        """Config should be creatable from CLI arguments namespace."""
        from praisonai.cli.interactive.config import InteractiveConfig
        from argparse import Namespace
        
        args = Namespace(
            model="gpt-4-turbo",
            session="my-session",
            continue_session=True,
            workspace="/project",
            no_acp=True,
            no_lsp=False,
            verbose=True,
            memory=True,
            file=["/tmp/a.py", "/tmp/b.py"]
        )
        
        config = InteractiveConfig.from_args(args)
        
        assert config.model == "gpt-4-turbo"
        assert config.session_id == "my-session"
        assert config.continue_session is True
        assert config.workspace == "/project"
        assert config.enable_acp is False  # no_acp=True means enable_acp=False
        assert config.enable_lsp is True
        assert config.verbose is True
        assert config.memory is True
        assert config.files == ["/tmp/a.py", "/tmp/b.py"]
    
    def test_config_merge(self):
        """Config should support merging with another config."""
        from praisonai.cli.interactive.config import InteractiveConfig
        
        base = InteractiveConfig(model="gpt-4", verbose=False)
        override = InteractiveConfig(verbose=True, memory=True)
        
        merged = base.merge(override)
        
        assert merged.model == "gpt-4"  # From base
        assert merged.verbose is True  # Overridden
        assert merged.memory is True  # From override
    
    def test_approval_modes(self):
        """Verify valid approval modes."""
        from praisonai.cli.interactive.config import InteractiveConfig, ApprovalMode
        
        assert ApprovalMode.PROMPT.value == "prompt"
        assert ApprovalMode.AUTO.value == "auto"
        assert ApprovalMode.REJECT.value == "reject"
        
        # Config should accept string or enum
        config1 = InteractiveConfig(approval_mode="auto")
        config2 = InteractiveConfig(approval_mode=ApprovalMode.AUTO)
        
        assert config1.approval_mode == "auto"
        assert config2.approval_mode == ApprovalMode.AUTO


class TestToolConfig:
    """Tests for ToolConfig (reused from interactive_tools)."""
    
    def test_tool_config_integration(self):
        """InteractiveConfig should integrate with ToolConfig."""
        from praisonai.cli.interactive.config import InteractiveConfig
        
        config = InteractiveConfig(
            workspace="/project",
            enable_acp=True,
            enable_lsp=False
        )
        
        tool_config = config.to_tool_config()
        
        assert tool_config.workspace == "/project"
        assert tool_config.enable_acp is True
        assert tool_config.enable_lsp is False
