"""Tests for unified CLI flags across interactive modes."""
import os
from argparse import Namespace


class TestContinueFlag:
    """Tests for --continue flag."""
    
    def test_config_from_args_continue(self):
        """Config correctly parses --continue flag."""
        from praisonai.cli.interactive.config import InteractiveConfig
        
        args = Namespace(
            model=None,
            session=None,
            continue_session=True,
            workspace=os.getcwd(),
            no_acp=False,
            no_lsp=False,
            verbose=False,
            memory=False,
            file=[]
        )
        
        config = InteractiveConfig.from_args(args)
        
        assert config.continue_session is True
    
    def test_config_from_args_continue_alias(self):
        """Config correctly parses --continue_ alias."""
        from praisonai.cli.interactive.config import InteractiveConfig
        
        args = Namespace(
            model=None,
            session=None,
            continue_=True,  # Typer uses continue_ due to reserved keyword
            workspace=os.getcwd(),
            no_acp=False,
            no_lsp=False,
            verbose=False,
            memory=False,
            file=[]
        )
        
        config = InteractiveConfig.from_args(args)
        
        assert config.continue_session is True


class TestFileFlag:
    """Tests for --file flag."""
    
    def test_config_from_args_single_file(self):
        """Config correctly parses single --file flag."""
        from praisonai.cli.interactive.config import InteractiveConfig
        
        args = Namespace(
            model=None,
            session=None,
            continue_session=False,
            workspace=os.getcwd(),
            no_acp=False,
            no_lsp=False,
            verbose=False,
            memory=False,
            file=["/tmp/test.py"]
        )
        
        config = InteractiveConfig.from_args(args)
        
        assert config.files == ["/tmp/test.py"]
    
    def test_config_from_args_multiple_files(self):
        """Config correctly parses multiple --file flags."""
        from praisonai.cli.interactive.config import InteractiveConfig
        
        args = Namespace(
            model=None,
            session=None,
            continue_session=False,
            workspace=os.getcwd(),
            no_acp=False,
            no_lsp=False,
            verbose=False,
            memory=False,
            file=["/tmp/a.py", "/tmp/b.py", "/tmp/c.py"]
        )
        
        config = InteractiveConfig.from_args(args)
        
        assert config.files == ["/tmp/a.py", "/tmp/b.py", "/tmp/c.py"]
    
    def test_config_files_default_empty(self):
        """Config files defaults to empty list."""
        from praisonai.cli.interactive.config import InteractiveConfig
        
        config = InteractiveConfig()
        
        assert config.files == []


class TestWorkspaceFlag:
    """Tests for --workspace flag."""
    
    def test_config_from_args_workspace(self):
        """Config correctly parses --workspace flag."""
        from praisonai.cli.interactive.config import InteractiveConfig
        
        args = Namespace(
            model=None,
            session=None,
            continue_session=False,
            workspace="/custom/workspace",
            no_acp=False,
            no_lsp=False,
            verbose=False,
            memory=False,
            file=[]
        )
        
        config = InteractiveConfig.from_args(args)
        
        assert config.workspace == "/custom/workspace"
    
    def test_config_workspace_defaults_to_cwd(self):
        """Config workspace defaults to current directory."""
        from praisonai.cli.interactive.config import InteractiveConfig
        
        config = InteractiveConfig()
        
        assert config.workspace == os.getcwd()


class TestToolFlags:
    """Tests for --no-acp and --no-lsp flags."""
    
    def test_config_from_args_no_acp(self):
        """Config correctly parses --no-acp flag."""
        from praisonai.cli.interactive.config import InteractiveConfig
        
        args = Namespace(
            model=None,
            session=None,
            continue_session=False,
            workspace=os.getcwd(),
            no_acp=True,
            no_lsp=False,
            verbose=False,
            memory=False,
            file=[]
        )
        
        config = InteractiveConfig.from_args(args)
        
        assert config.enable_acp is False
        assert config.enable_lsp is True
    
    def test_config_from_args_no_lsp(self):
        """Config correctly parses --no-lsp flag."""
        from praisonai.cli.interactive.config import InteractiveConfig
        
        args = Namespace(
            model=None,
            session=None,
            continue_session=False,
            workspace=os.getcwd(),
            no_acp=False,
            no_lsp=True,
            verbose=False,
            memory=False,
            file=[]
        )
        
        config = InteractiveConfig.from_args(args)
        
        assert config.enable_acp is True
        assert config.enable_lsp is False


class TestShareFlag:
    """Tests for --share flag."""
    
    def test_config_from_args_share(self):
        """Config correctly parses --share flag."""
        from praisonai.cli.interactive.config import InteractiveConfig
        
        args = Namespace(
            model=None,
            session=None,
            continue_session=False,
            workspace=os.getcwd(),
            no_acp=False,
            no_lsp=False,
            verbose=False,
            memory=False,
            file=[],
            share=True
        )
        
        config = InteractiveConfig.from_args(args)
        
        assert config.share is True
    
    def test_config_share_defaults_false(self):
        """Config share defaults to False."""
        from praisonai.cli.interactive.config import InteractiveConfig
        
        config = InteractiveConfig()
        
        assert config.share is False


class TestVariantFlag:
    """Tests for --variant flag."""
    
    def test_config_from_args_variant(self):
        """Config correctly parses --variant flag."""
        from praisonai.cli.interactive.config import InteractiveConfig
        
        args = Namespace(
            model=None,
            session=None,
            continue_session=False,
            workspace=os.getcwd(),
            no_acp=False,
            no_lsp=False,
            verbose=False,
            memory=False,
            file=[],
            variant="high"
        )
        
        config = InteractiveConfig.from_args(args)
        
        assert config.variant == "high"
    
    def test_config_variant_defaults_none(self):
        """Config variant defaults to None."""
        from praisonai.cli.interactive.config import InteractiveConfig
        
        config = InteractiveConfig()
        
        assert config.variant is None


class TestFlagParity:
    """Tests to ensure flag parity across modes."""
    
    def test_all_flags_in_config(self):
        """All expected flags are present in InteractiveConfig."""
        from praisonai.cli.interactive.config import InteractiveConfig
        
        # These flags should be available in all interactive modes
        expected_fields = [
            "model",
            "session_id",
            "continue_session",
            "workspace",
            "enable_acp",
            "enable_lsp",
            "verbose",
            "memory",
            "approval_mode",
            "files",
            "share",
            "variant",
        ]
        
        config = InteractiveConfig()
        
        for field in expected_fields:
            assert hasattr(config, field), f"Missing field: {field}"
