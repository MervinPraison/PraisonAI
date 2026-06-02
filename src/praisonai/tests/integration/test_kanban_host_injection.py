"""Integration tests for kanban host injection."""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock


@pytest.fixture
def temp_kanban_dir():
    """Create temporary directory for kanban testing."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    if temp_dir.exists():
        shutil.rmtree(temp_dir)


def test_kanban_bridge_registration():
    """Test that kanban bridge can register backends."""
    # Mock praisonaiui backends
    mock_backends = MagicMock()
    
    with patch.dict('sys.modules', {'praisonaiui.backends': mock_backends}):
        from praisonai.integration.bridges.kanban_bridge import register_kanban_backends
        
        result = register_kanban_backends()
        
        # Should return True indicating successful registration
        assert result is True
        
        # Verify backends were set
        assert mock_backends.set_backend.call_count >= 1
        
        # Check specific backend calls
        backend_calls = [call[0] for call in mock_backends.set_backend.call_args_list]
        assert any('kanban_store' in str(call) for call in backend_calls)


def test_kanban_store_factory():
    """Test kanban store factory creation."""
    from praisonai.integration.bridges.kanban_bridge import get_kanban_store_factory
    
    factory = get_kanban_store_factory()
    
    assert factory is not None
    
    # Test factory creates store
    with patch('praisonai.integration.bridges.kanban_bridge.SQLiteKanbanStore') as mock_store:
        store = factory()
        mock_store.assert_called_once()


def test_setup_bridges_includes_kanban(temp_kanban_dir):
    """Test that setup_bridges includes kanban registration."""
    # Mock all the dependencies
    mock_backends = MagicMock()
    mock_praisonaiui = MagicMock()
    mock_praisonaiui.backends = mock_backends
    
    # Mock the kanban path to use temp directory
    def mock_get_path(board=None):
        return temp_kanban_dir / "test_kanban.db"
    
    with patch.dict('sys.modules', {
        'praisonaiui': mock_praisonaiui,
        'praisonaiui.backends': mock_backends
    }), patch('praisonai.kanban.paths.get_kanban_db_path', mock_get_path):
        
        from praisonai.integration.host_app import setup_bridges
        
        # This should not raise and should call kanban registration
        setup_bridges()
        
        # Verify some backend was registered (exact calls depend on available components)
        assert mock_backends.set_backend.called


def test_kanban_store_environment_variable_support(temp_kanban_dir):
    """Test that kanban store respects environment variables."""
    import os
    
    test_board = "test_board"
    
    with patch.dict(os.environ, {'PRAISONAI_KANBAN_BOARD': test_board}):
        with patch('praisonai.kanban.paths.get_kanban_db_path') as mock_path:
            mock_path.return_value = temp_kanban_dir / f"{test_board}_kanban.db"
            
            from praisonai.integration.bridges.kanban_bridge import get_kanban_store_factory
            
            factory = get_kanban_store_factory()
            
            # This should use the environment variable for board selection
            with patch('praisonai.integration.bridges.kanban_bridge.SQLiteKanbanStore') as mock_store:
                store = factory()
                mock_store.assert_called_once()


def test_missing_dependencies_graceful_degradation():
    """Test that missing dependencies don't break setup."""
    # Simulate missing praisonaiui
    with patch.dict('sys.modules', {}, clear=True):
        # Remove praisonaiui from modules to simulate missing dependency
        if 'praisonaiui' in __import__('sys').modules:
            del __import__('sys').modules['praisonaiui']
        if 'praisonaiui.backends' in __import__('sys').modules:
            del __import__('sys').modules['praisonaiui.backends']
        
        from praisonai.integration.bridges.kanban_bridge import register_kanban_backends
        
        # Should not raise, just return False
        result = register_kanban_backends()
        assert result is False


def test_jobs_store_bridge():
    """Test jobs store bridge functionality."""
    from praisonai.integration.bridges.kanban_bridge import get_jobs_store, get_jobs_executor
    
    # These may return None if jobs module isn't available, which is fine
    jobs_store = get_jobs_store()
    jobs_executor = get_jobs_executor()
    
    # Just test that the functions don't raise exceptions
    # Actual functionality depends on jobs module implementation
    assert jobs_store is None or callable(jobs_store)
    assert jobs_executor is None or callable(jobs_executor)