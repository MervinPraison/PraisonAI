"""Path utilities for kanban data storage."""
import os
from pathlib import Path
from typing import Optional


def get_praisonai_home() -> Path:
    """Get PraisonAI home directory."""
    return Path.home() / ".praisonai"


def get_kanban_db_path(board: Optional[str] = None) -> Path:
    """Get kanban database path.
    
    Args:
        board: Board slug for multi-board support. None for default board.
        
    Returns:
        Path to SQLite database file.
    """
    home = get_praisonai_home()
    
    # Read from environment variable for override
    if board is None:
        board = os.environ.get('PRAISONAI_KANBAN_BOARD')
        if not board:
            # Try to read from persisted config file
            try:
                import json
                config_file = home / "kanban_config.json"
                if config_file.exists():
                    with open(config_file) as f:
                        config = json.load(f)
                        board = config.get('active_board', 'default')
                else:
                    board = 'default'
            except Exception:
                board = 'default'
    
    # Legacy override for single DB file
    if db_override := os.environ.get('PRAISONAI_KANBAN_DB'):
        return Path(db_override)
    
    # Default board at root
    if board == 'default':
        return home / "kanban.db"
    
    # Multi-board at boards/<slug>/
    boards_dir = home / "kanban" / "boards" / board
    boards_dir.mkdir(parents=True, exist_ok=True)
    return boards_dir / "kanban.db"


def get_kanban_boards_dir() -> Path:
    """Get kanban boards directory."""
    return get_praisonai_home() / "kanban" / "boards"


def list_available_boards() -> list[str]:
    """List all available board slugs."""
    boards_dir = get_kanban_boards_dir()
    if not boards_dir.exists():
        return ["default"]
    
    boards = ["default"]  # Always include default
    
    for board_dir in boards_dir.iterdir():
        if board_dir.is_dir() and (board_dir / "kanban.db").exists():
            boards.append(board_dir.name)
    
    return sorted(set(boards))