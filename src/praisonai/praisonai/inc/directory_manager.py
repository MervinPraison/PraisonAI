"""
Directory Manager for PraisonAI

This module handles the directory management improvements requested in issue #130.
It ensures that configuration files like chainlit.md, .chainlit directory, and 
public folder are organized in ~/.praison/ instead of cluttering the root directory.
"""

import os
import shutil
import logging
from pathlib import Path
from typing import Optional, Dict, Any
import tempfile


class DirectoryManager:
    """Manages PraisonAI directory structure and file organization."""
    
    def __init__(self, config_dir: Optional[str] = None):
        """
        Initialize the directory manager.
        
        Args:
            config_dir: Custom configuration directory path. 
                       Defaults to ~/.praison/
        """
        self.config_dir = Path(config_dir or os.path.expanduser("~/.praison"))
        self.logger = logging.getLogger(__name__)
        self._ensure_config_directory()
    
    def _ensure_config_directory(self) -> None:
        """Create the main configuration directory if it doesn't exist."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Configuration directory ensured: {self.config_dir}")
        except Exception as e:
            self.logger.error(f"Failed to create config directory: {e}")
            raise
    
    def get_config_path(self, filename: str) -> Path:
        """
        Get the full path for a configuration file.
        
        Args:
            filename: Name of the configuration file
            
        Returns:
            Full path to the configuration file in the config directory
        """
        return self.config_dir / filename
    
    def setup_chainlit_config(self) -> Dict[str, Path]:
        """
        Setup Chainlit configuration in the managed directory.
        
        Returns:
            Dictionary containing paths to Chainlit configuration files
        """
        chainlit_paths = {
            'config_file': self.get_config_path('chainlit.md'),
            'config_dir': self.get_config_path('.chainlit'),
            'database': self.get_config_path('database.sqlite'),
            'logs': self.get_config_path('logs')
        }
        
        # Create Chainlit subdirectories
        chainlit_paths['config_dir'].mkdir(exist_ok=True)
        chainlit_paths['logs'].mkdir(exist_ok=True)
        
        # Create default chainlit.md if it doesn't exist
        if not chainlit_paths['config_file'].exists():
            self._create_default_chainlit_config(chainlit_paths['config_file'])
        
        self.logger.info("Chainlit configuration setup completed")
        return chainlit_paths
    
    def _create_default_chainlit_config(self, config_path: Path) -> None:
        """Create a default chainlit.md configuration file."""
        default_config = """# Welcome to PraisonAI! 🤖

PraisonAI is a powerful multi-agent framework that combines the best of AI agents, 
AutoGen, and CrewAI into a unified platform.

## Features
- 🧠 Multi-agent collaboration
- 🔧 Self-reflection capabilities  
- 🚀 Low-code solution
- 🎯 Human-agent collaboration
- 📊 Rich analytics and monitoring

## Getting Started
To get started with PraisonAI:

1. Set your API keys in the environment
2. Create your first agent
3. Start collaborating!

Visit our [documentation](https://docs.praison.ai) for more information.
"""
        try:
            config_path.write_text(default_config)
            self.logger.info(f"Created default Chainlit config: {config_path}")
        except Exception as e:
            self.logger.error(f"Failed to create Chainlit config: {e}")
    
    def setup_public_assets(self) -> Path:
        """
        Setup public assets directory in the managed location.
        
        Returns:
            Path to the public assets directory
        """
        public_dir = self.get_config_path('public')
        public_dir.mkdir(exist_ok=True)
        
        # Copy default assets if they exist in the package
        self._copy_default_assets(public_dir)
        
        self.logger.info(f"Public assets directory setup: {public_dir}")
        return public_dir
    
    def _copy_default_assets(self, public_dir: Path) -> None:
        """Copy default public assets to the managed directory."""
        try:
            # Try to find assets in the package
            from praisonai.ui import public as ui_public_module
            ui_public_path = Path(ui_public_module.__file__).parent
            
            if ui_public_path.exists():
                for asset_file in ui_public_path.glob('*'):
                    if asset_file.is_file():
                        target_file = public_dir / asset_file.name
                        if not target_file.exists():
                            shutil.copy2(asset_file, target_file)
                            self.logger.debug(f"Copied asset: {asset_file.name}")
        except (ImportError, AttributeError):
            self.logger.debug("No default assets found to copy")
        except Exception as e:
            self.logger.warning(f"Error copying default assets: {e}")
    
    def migrate_existing_files(self, source_dir: Optional[Path] = None) -> None:
        """
        Migrate existing configuration files from the root directory.
        
        Args:
            source_dir: Source directory to migrate from. Defaults to current working directory.
        """
        source_dir = source_dir or Path.cwd()
        
        files_to_migrate = [
            'chainlit.md',
            '.chainlit',
            'database.sqlite',
            'public'
        ]
        
        for item_name in files_to_migrate:
            source_path = source_dir / item_name
            if source_path.exists():
                self._migrate_file_or_directory(source_path, item_name)
    
    def _migrate_file_or_directory(self, source_path: Path, item_name: str) -> None:
        """Migrate a single file or directory to the managed location."""
        target_path = self.get_config_path(item_name)
        
        try:
            if source_path.is_file():
                # Backup existing file in target location
                if target_path.exists():
                    backup_path = target_path.with_suffix(f"{target_path.suffix}.backup")
                    shutil.move(str(target_path), str(backup_path))
                    self.logger.info(f"Backed up existing file: {backup_path}")
                
                shutil.move(str(source_path), str(target_path))
                self.logger.info(f"Migrated file: {item_name}")
                
            elif source_path.is_dir():
                # Merge directories
                if target_path.exists():
                    # Move contents rather than replacing the directory
                    for item in source_path.rglob('*'):
                        if item.is_file():
                            relative_path = item.relative_to(source_path)
                            target_item = target_path / relative_path
                            target_item.parent.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(item), str(target_item))
                    
                    # Remove empty source directory
                    try:
                        source_path.rmdir()
                    except OSError:
                        self.logger.warning(f"Could not remove source directory: {source_path}")
                else:
                    shutil.move(str(source_path), str(target_path))
                
                self.logger.info(f"Migrated directory: {item_name}")
                
        except Exception as e:
            self.logger.error(f"Failed to migrate {item_name}: {e}")
    
    def get_environment_variables(self) -> Dict[str, str]:
        """
        Get environment variables for proper directory configuration.
        
        Returns:
            Dictionary of environment variables to set
        """
        return {
            'PRAISON_CONFIG_DIR': str(self.config_dir),
            'CHAINLIT_CONFIG_DIR': str(self.config_dir),
            'CHAINLIT_DB_DIR': str(self.config_dir),
            'CHAINLIT_CONFIG_FILE': str(self.get_config_path('chainlit.md')),
            'DATABASE_URL': f"sqlite:///{self.get_config_path('database.sqlite')}"
        }
    
    def apply_environment_variables(self) -> None:
        """Apply the environment variables to the current process."""
        env_vars = self.get_environment_variables()
        for key, value in env_vars.items():
            os.environ[key] = value
            self.logger.debug(f"Set environment variable: {key}={value}")
    
    def cleanup_root_directory(self, root_dir: Optional[Path] = None) -> None:
        """
        Clean up PraisonAI files from the root directory after migration.
        
        Args:
            root_dir: Root directory to clean. Defaults to current working directory.
        """
        root_dir = root_dir or Path.cwd()
        
        files_to_remove = [
            'chainlit.md',
            '.chainlit',
            'database.sqlite'
        ]
        
        for filename in files_to_remove:
            file_path = root_dir / filename
            if file_path.exists():
                try:
                    if file_path.is_file():
                        file_path.unlink()
                    elif file_path.is_dir():
                        shutil.rmtree(file_path)
                    self.logger.info(f"Cleaned up: {filename}")
                except Exception as e:
                    self.logger.warning(f"Could not remove {filename}: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of directory management.
        
        Returns:
            Dictionary containing status information
        """
        return {
            'config_dir': str(self.config_dir),
            'config_dir_exists': self.config_dir.exists(),
            'chainlit_config_exists': self.get_config_path('chainlit.md').exists(),
            'chainlit_dir_exists': self.get_config_path('.chainlit').exists(),
            'database_exists': self.get_config_path('database.sqlite').exists(),
            'public_dir_exists': self.get_config_path('public').exists(),
            'disk_usage_mb': self._get_disk_usage(),
            'file_count': len(list(self.config_dir.rglob('*'))),
            'environment_variables': self.get_environment_variables()
        }
    
    def _get_disk_usage(self) -> float:
        """Get disk usage of the config directory in MB."""
        try:
            if not self.config_dir.exists():
                return 0.0
            
            total_size = 0
            for file_path in self.config_dir.rglob('*'):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
            
            return round(total_size / (1024 * 1024), 2)
        except Exception:
            return 0.0


# Global instance for easy access
default_directory_manager = DirectoryManager()


def initialize_directories(config_dir: Optional[str] = None, migrate: bool = True) -> DirectoryManager:
    """
    Initialize PraisonAI directory management.
    
    Args:
        config_dir: Custom configuration directory path
        migrate: Whether to migrate existing files from root directory
        
    Returns:
        Configured DirectoryManager instance
    """
    manager = DirectoryManager(config_dir)
    
    # Setup core directories
    manager.setup_chainlit_config()
    manager.setup_public_assets()
    
    # Migrate existing files if requested
    if migrate:
        manager.migrate_existing_files()
    
    # Apply environment variables
    manager.apply_environment_variables()
    
    return manager


def get_config_path(filename: str) -> Path:
    """
    Convenience function to get a configuration file path.
    
    Args:
        filename: Name of the configuration file
        
    Returns:
        Full path to the configuration file
    """
    return default_directory_manager.get_config_path(filename)


def get_status() -> Dict[str, Any]:
    """
    Get the current directory management status.
    
    Returns:
        Status information dictionary
    """
    return default_directory_manager.get_status()