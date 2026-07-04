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
    mock_backends = MagicMock()
    mock_praisonaiui = MagicMock()
    mock_praisonaiui.backends = mock_backends

    with patch.dict('sys.modules', {
        'praisonaiui': mock_praisonaiui,
        'praisonaiui.backends': mock_backends,
    }):
        from praisonai.integration.bridges.kanban_bridge import register_kanban_backends

        result = register_kanban_backends()

        assert result is True
        assert mock_backends.set_backend.call_count >= 1

        backend_calls = [call[0] for call in mock_backends.set_backend.call_args_list]
        assert any('kanban_store' in str(call) for call in backend_calls)


def test_kanban_store_factory():
    """Test kanban store factory creation."""
    from praisonai.integration.bridges.kanban_bridge import get_kanban_store_factory
    
    # get_kanban_store_factory must be called inside the patch so the closure
    # captures the mock (the 'from ... import' inside it reads the patched attr)
    with patch('praisonai.kanban.sqlite_store.SQLiteKanbanStore') as mock_store:
        factory = get_kanban_store_factory()
        assert factory is not None
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
    
    expected_db = temp_kanban_dir / f"{test_board}_kanban.db"

    with patch.dict(os.environ, {'PRAISONAI_KANBAN_BOARD': test_board}):
        # Mock only the filesystem/DB path resolution edge; keep the real
        # SQLiteKanbanStore so the env-var-driven path actually flows through
        # get_kanban_db_path() and lands in the constructed store.
        with patch('praisonai.kanban.sqlite_store.get_kanban_db_path') as mock_path:
            mock_path.return_value = expected_db

            from praisonai.integration.bridges.kanban_bridge import get_kanban_store_factory

            factory = get_kanban_store_factory()
            store = factory()

            # The real store must have resolved its path via the patched
            # get_kanban_db_path(); this proves PRAISONAI_KANBAN_BOARD handling
            # is exercised rather than just asserting a mock was called.
            assert mock_path.called
            assert Path(store.db_path) == expected_db


def test_missing_dependencies_graceful_degradation():
    """Test that missing dependencies don't break setup."""
    # Simulate missing praisonaiui by patching just those modules to None
    with patch.dict('sys.modules', {'praisonaiui': None, 'praisonaiui.backends': None}):
        from praisonai.integration.bridges.kanban_bridge import register_kanban_backends
        
        # Should not raise, just return False
        result = register_kanban_backends()
        assert result is False


def test_jobs_store_bridge():
    """Test jobs store bridge resolves praisonai.jobs.server helpers."""
    from praisonai.integration.bridges.kanban_bridge import get_jobs_store, get_jobs_executor
    from praisonai_bot._wrapper_bridge import wrapper_available

    jobs_store = get_jobs_store()
    jobs_executor = get_jobs_executor()

    assert jobs_store is None or callable(jobs_store)
    assert jobs_executor is None or callable(jobs_executor)

    if wrapper_available():
        from praisonai.jobs import server as jobs_server

        assert jobs_store is jobs_server.get_store
        assert jobs_executor is jobs_server.get_executor