"""
PraisonAI CLI Configuration Module.

Provides configuration management with TOML support and precedence handling.
"""

from .loader import ConfigLoader, get_config, load_config
from .schema import ConfigSchema
from .paths import (
    LEGACY_PROJECT_DATA_DIRNAME,
    get_config_paths,
    get_project_data_dir,
    get_project_data_path,
    resolve_project_data_path,
    get_user_config_path,
    get_project_config_path,
    get_project_config_dir,
    find_project_root,
)

__all__ = [
    'ConfigLoader',
    'ConfigSchema',
    'get_config',
    'load_config',
    'LEGACY_PROJECT_DATA_DIRNAME',
    'PROJECT_DATA_DIRNAME',
    'get_config_paths',
    'get_project_data_dir',
    'get_project_data_path',
    'resolve_project_data_path',
    'get_user_config_path',
    'get_project_config_path',
    'get_project_config_dir',
    'find_project_root',
]


def __getattr__(name):
    # Lazy so importing the configuration package does not import the core SDK.
    if name == "PROJECT_DATA_DIRNAME":
        from . import paths
        return paths.PROJECT_DATA_DIRNAME
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
