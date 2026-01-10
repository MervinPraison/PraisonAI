"""
UI Backend system for PraisonAI CLI.

Provides multiple rendering backends for interactive mode:
- PlainBackend: No dependencies, works everywhere
- RichBackend: Rich-based rendering (current default)
- MiddleGroundBackend: Enhanced Rich + prompt_toolkit (new default when deps available)

All backends implement the UIBackend protocol and are selected automatically
based on environment, or explicitly via --ui flag.
"""

import os
import sys
from typing import Optional

__all__ = [
    'UIConfig',
    'UIEventType',
    'select_backend',
    'PlainBackend',
    'RichBackend',
    'MiddleGroundBackend',
]

_lazy_cache = {}


def __getattr__(name: str):
    """Lazy load UI components."""
    if name in _lazy_cache:
        return _lazy_cache[name]
    
    if name == 'UIConfig':
        from .config import UIConfig
        _lazy_cache[name] = UIConfig
        return UIConfig
    
    if name == 'UIEventType':
        from .events import UIEventType
        _lazy_cache[name] = UIEventType
        return UIEventType
    
    if name == 'PlainBackend':
        from .plain import PlainBackend
        _lazy_cache[name] = PlainBackend
        return PlainBackend
    
    if name == 'RichBackend':
        from .rich_backend import RichBackend
        _lazy_cache[name] = RichBackend
        return RichBackend
    
    if name == 'MiddleGroundBackend':
        from .mg_backend import MiddleGroundBackend
        _lazy_cache[name] = MiddleGroundBackend
        return MiddleGroundBackend
    
    if name == 'select_backend':
        from .selector import select_backend
        _lazy_cache[name] = select_backend
        return select_backend
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def select_backend(config: Optional['UIConfig'] = None):
    """
    Select the appropriate UI backend based on config and environment.
    
    Selection priority:
    1. Explicit config.ui_backend override
    2. PRAISONAI_UI_SAFE=1 → PlainBackend
    3. config.json_output=True → PlainBackend
    4. Non-TTY stdout → PlainBackend
    5. Auto-detect based on available deps:
       - MiddleGroundBackend if rich + prompt_toolkit available
       - RichBackend if rich available
       - PlainBackend otherwise
    
    Args:
        config: UIConfig instance with settings
        
    Returns:
        UIBackend instance
    """
    from .config import UIConfig
    from .plain import PlainBackend
    
    if config is None:
        config = UIConfig()
    
    # Explicit override
    if config.ui_backend and config.ui_backend != 'auto':
        return _get_backend_by_name(config.ui_backend, config)
    
    # Environment override for safe mode
    if os.environ.get('PRAISONAI_UI_SAFE') == '1':
        return PlainBackend(config)
    
    # JSON output forces plain
    if config.json_output:
        return PlainBackend(config)
    
    # Non-TTY forces plain
    if not sys.stdout.isatty():
        return PlainBackend(config)
    
    # Auto-detect based on available deps
    return _auto_select_backend(config)


def _get_backend_by_name(name: str, config: 'UIConfig'):
    """Get backend by name."""
    from .plain import PlainBackend
    
    if name == 'plain':
        return PlainBackend(config)
    
    if name == 'rich':
        try:
            from .rich_backend import RichBackend
            return RichBackend(config)
        except ImportError:
            return PlainBackend(config)
    
    if name == 'mg':
        try:
            from .mg_backend import MiddleGroundBackend
            return MiddleGroundBackend(config)
        except ImportError:
            # Fallback to rich, then plain
            try:
                from .rich_backend import RichBackend
                return RichBackend(config)
            except ImportError:
                return PlainBackend(config)
    
    # Unknown backend, use plain
    return PlainBackend(config)


def _auto_select_backend(config: 'UIConfig'):
    """Auto-select best available backend."""
    from .plain import PlainBackend
    
    # Try MiddleGroundBackend first (requires rich + prompt_toolkit)
    try:
        from .mg_backend import MiddleGroundBackend
        return MiddleGroundBackend(config)
    except ImportError:
        pass
    
    # Try RichBackend (requires rich)
    try:
        from .rich_backend import RichBackend
        return RichBackend(config)
    except ImportError:
        pass
    
    # Fallback to PlainBackend
    return PlainBackend(config)
