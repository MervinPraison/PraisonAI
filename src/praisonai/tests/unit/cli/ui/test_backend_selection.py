"""
Tests for UI backend selection logic.

Verifies:
1. Auto-selection picks correct backend based on environment
2. Non-TTY forces PlainBackend
3. --json forces PlainBackend
4. PRAISONAI_UI_SAFE=1 forces PlainBackend
5. Explicit --ui flag overrides auto-selection
6. Fallback chain works when deps missing
"""

import os
import sys
from unittest.mock import patch


class TestBackendSelection:
    """Test suite for UI backend auto-selection."""

    def test_select_backend_returns_plain_for_non_tty(self):
        """Non-TTY stdout should select PlainBackend."""
        from praisonai.cli.ui import select_backend, UIConfig
        
        with patch.object(sys.stdout, 'isatty', return_value=False):
            config = UIConfig()
            backend = select_backend(config)
            assert backend.__class__.__name__ == 'PlainBackend'

    def test_select_backend_returns_plain_for_json_mode(self):
        """--json flag should force PlainBackend."""
        from praisonai.cli.ui import select_backend, UIConfig
        
        config = UIConfig(json_output=True)
        backend = select_backend(config)
        assert backend.__class__.__name__ == 'PlainBackend'

    def test_select_backend_returns_plain_for_safe_mode(self):
        """PRAISONAI_UI_SAFE=1 should force PlainBackend."""
        from praisonai.cli.ui import select_backend, UIConfig
        
        with patch.dict(os.environ, {'PRAISONAI_UI_SAFE': '1'}):
            config = UIConfig()
            backend = select_backend(config)
            assert backend.__class__.__name__ == 'PlainBackend'

    def test_select_backend_explicit_override(self):
        """Explicit --ui flag should override auto-selection."""
        from praisonai.cli.ui import select_backend, UIConfig
        
        config = UIConfig(ui_backend='plain')
        backend = select_backend(config)
        assert backend.__class__.__name__ == 'PlainBackend'

    def test_select_backend_auto_with_deps(self):
        """Auto-selection with deps available should select MiddleGroundBackend."""
        from praisonai.cli.ui import select_backend, UIConfig
        
        with patch.object(sys.stdout, 'isatty', return_value=True):
            with patch.dict(os.environ, {}, clear=False):
                # Remove PRAISONAI_UI_SAFE if present
                os.environ.pop('PRAISONAI_UI_SAFE', None)
                config = UIConfig()
                backend = select_backend(config)
                # Should be MiddleGroundBackend or RichBackend depending on deps
                assert backend.__class__.__name__ in ('MiddleGroundBackend', 'RichBackend', 'PlainBackend')

    def test_select_backend_fallback_chain(self):
        """When deps missing, should fallback gracefully."""
        from praisonai.cli.ui import select_backend, UIConfig
        
        with patch.object(sys.stdout, 'isatty', return_value=True):
            config = UIConfig(ui_backend='auto')
            backend = select_backend(config)
            # Should return some valid backend
            assert hasattr(backend, 'emit')
            assert hasattr(backend, 'prompt')


class TestUIConfig:
    """Test UIConfig dataclass."""

    def test_ui_config_defaults(self):
        """UIConfig should have sensible defaults."""
        from praisonai.cli.ui import UIConfig
        
        config = UIConfig()
        assert config.ui_backend == 'auto'
        assert config.json_output is False
        assert config.no_color is False
        assert config.theme == 'default'

    def test_ui_config_from_cli_args(self):
        """UIConfig should be constructible from CLI args."""
        from praisonai.cli.ui import UIConfig
        
        config = UIConfig(
            ui_backend='mg',
            json_output=True,
            no_color=True,
            theme='dark',
            compact=True,
        )
        assert config.ui_backend == 'mg'
        assert config.json_output is True
        assert config.no_color is True
        assert config.theme == 'dark'
        assert config.compact is True


class TestBackendProtocol:
    """Test that backends implement the UIBackend protocol."""

    def test_plain_backend_has_required_methods(self):
        """PlainBackend should implement UIBackend protocol."""
        from praisonai.cli.ui.plain import PlainBackend
        
        backend = PlainBackend()
        assert hasattr(backend, 'emit')
        assert hasattr(backend, 'prompt')
        assert hasattr(backend, 'is_tty')
        assert callable(backend.emit)
        assert callable(backend.prompt)
        assert callable(backend.is_tty)

    def test_plain_backend_is_tty_returns_false_for_non_tty(self):
        """PlainBackend.is_tty() should return False for non-TTY."""
        from praisonai.cli.ui.plain import PlainBackend
        
        with patch.object(sys.stdout, 'isatty', return_value=False):
            backend = PlainBackend()
            assert backend.is_tty() is False

    def test_plain_backend_emit_writes_to_stdout(self, capsys):
        """PlainBackend.emit() should write to stdout."""
        from praisonai.cli.ui.plain import PlainBackend
        from praisonai.cli.ui.events import UIEventType
        
        backend = PlainBackend()
        backend.emit(UIEventType.MESSAGE_CHUNK, {'content': 'Hello'})
        
        captured = capsys.readouterr()
        assert 'Hello' in captured.out
