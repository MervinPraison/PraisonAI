"""
Migration manager for PraisonAI persistence schema versioning.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
from packaging import version as pkg_version

logger = logging.getLogger(__name__)


@dataclass
class SchemaVersion:
    """Represents a schema version."""
    version: str
    description: str = ""
    applied_at: Optional[float] = None
    
    def __lt__(self, other: "SchemaVersion") -> bool:
        return pkg_version.parse(self.version) < pkg_version.parse(other.version)
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SchemaVersion):
            return False
        return self.version == other.version


@dataclass
class Migration:
    """Represents a single migration."""
    version: str
    description: str
    up: Callable[[Any], None]
    down: Optional[Callable[[Any], None]] = None


class MigrationManager:
    """
    Manages database schema versions and migrations.
    
    Example:
        manager = MigrationManager(db_adapter)
        manager.register_migration(
            version="1.0.0",
            description="Initial schema",
            up=lambda db: db.execute("CREATE TABLE ..."),
            down=lambda db: db.execute("DROP TABLE ...")
        )
        manager.migrate_up()  # Apply all pending migrations
    """
    
    # Current schema version
    CURRENT_VERSION = "1.0.0"
    
    def __init__(self, db_adapter: Any = None):
        """
        Initialize migration manager.
        
        Args:
            db_adapter: Database adapter (PraisonDB or similar)
        """
        self._db = db_adapter
        self._migrations: List[Migration] = []
        self._versions_table = "praison_schema_versions"
        
        # Register built-in migrations
        self._register_builtin_migrations()
    
    def _register_builtin_migrations(self):
        """Register built-in migrations."""
        self.register_migration(
            version="1.0.0",
            description="Initial schema with sessions, messages, runs",
            up=self._migrate_1_0_0_up,
            down=self._migrate_1_0_0_down
        )
    
    def register_migration(
        self,
        version: str,
        description: str,
        up: Callable[[Any], None],
        down: Optional[Callable[[Any], None]] = None
    ):
        """
        Register a new migration.
        
        Args:
            version: Version string (e.g., "1.0.0")
            description: Human-readable description
            up: Function to apply migration
            down: Optional function to rollback migration
        """
        migration = Migration(
            version=version,
            description=description,
            up=up,
            down=down
        )
        self._migrations.append(migration)
        self._migrations.sort(key=lambda m: pkg_version.parse(m.version))
    
    def get_current_version(self) -> Optional[str]:
        """Get the current schema version from database."""
        if not self._db:
            return None
        
        try:
            # Try to get version from state store
            if hasattr(self._db, '_state_store') and self._db._state_store:
                self._db._init_stores()
                version_data = self._db._state_store.get(f"{self._versions_table}:current")
                if version_data:
                    return version_data.get("version")
        except Exception as e:
            logger.warning(f"Failed to get schema version: {e}")
        
        return None
    
    def set_current_version(self, version: str):
        """Set the current schema version in database."""
        if not self._db:
            return
        
        try:
            if hasattr(self._db, '_state_store') and self._db._state_store:
                self._db._init_stores()
                import time
                self._db._state_store.set(f"{self._versions_table}:current", {
                    "version": version,
                    "applied_at": time.time()
                })
        except Exception as e:
            logger.warning(f"Failed to set schema version: {e}")
    
    def get_pending_migrations(self) -> List[Migration]:
        """Get list of migrations that haven't been applied."""
        current = self.get_current_version()
        if not current:
            return self._migrations.copy()
        
        current_ver = pkg_version.parse(current)
        return [
            m for m in self._migrations
            if pkg_version.parse(m.version) > current_ver
        ]
    
    def migrate_up(self, target_version: Optional[str] = None) -> List[str]:
        """
        Apply pending migrations up to target version.
        
        Args:
            target_version: Optional target version (default: latest)
            
        Returns:
            List of applied migration versions
        """
        pending = self.get_pending_migrations()
        if not pending:
            logger.info("No pending migrations")
            return []
        
        target = pkg_version.parse(target_version) if target_version else None
        applied = []
        
        for migration in pending:
            if target and pkg_version.parse(migration.version) > target:
                break
            
            logger.info(f"Applying migration {migration.version}: {migration.description}")
            try:
                migration.up(self._db)
                self.set_current_version(migration.version)
                applied.append(migration.version)
                logger.info(f"Successfully applied migration {migration.version}")
            except Exception as e:
                logger.error(f"Failed to apply migration {migration.version}: {e}")
                raise
        
        return applied
    
    def migrate_down(self, target_version: str) -> List[str]:
        """
        Rollback migrations down to target version.
        
        Args:
            target_version: Target version to rollback to
            
        Returns:
            List of rolled back migration versions
        """
        current = self.get_current_version()
        if not current:
            logger.info("No migrations to rollback")
            return []
        
        current_ver = pkg_version.parse(current)
        target_ver = pkg_version.parse(target_version)
        
        if target_ver >= current_ver:
            logger.info("Target version is not lower than current")
            return []
        
        # Get migrations to rollback (in reverse order)
        to_rollback = [
            m for m in reversed(self._migrations)
            if pkg_version.parse(m.version) > target_ver and pkg_version.parse(m.version) <= current_ver
        ]
        
        rolled_back = []
        for migration in to_rollback:
            if not migration.down:
                logger.warning(f"Migration {migration.version} has no down function, skipping")
                continue
            
            logger.info(f"Rolling back migration {migration.version}")
            try:
                migration.down(self._db)
                rolled_back.append(migration.version)
                logger.info(f"Successfully rolled back migration {migration.version}")
            except Exception as e:
                logger.error(f"Failed to rollback migration {migration.version}: {e}")
                raise
        
        self.set_current_version(target_version)
        return rolled_back
    
    def get_migration_status(self) -> Dict[str, Any]:
        """Get current migration status."""
        current = self.get_current_version()
        pending = self.get_pending_migrations()
        
        return {
            "current_version": current,
            "latest_version": self._migrations[-1].version if self._migrations else None,
            "pending_count": len(pending),
            "pending_versions": [m.version for m in pending],
            "all_versions": [m.version for m in self._migrations]
        }
    
    # --- Built-in Migrations ---
    
    def _migrate_1_0_0_up(self, db: Any):
        """Initial schema migration."""
        # This is a no-op since tables are created on first use
        logger.info("Initial schema (1.0.0) - tables created on first use")
    
    def _migrate_1_0_0_down(self, db: Any):
        """Rollback initial schema."""
        logger.info("Rolling back initial schema (1.0.0)")
