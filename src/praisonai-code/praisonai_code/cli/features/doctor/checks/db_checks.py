"""
Database checks for the Doctor CLI module.

Validates database connectivity and configuration.
"""

import os

from ..models import (
    CheckCategory,
    CheckResult,
    CheckStatus,
    CheckSeverity,
    DoctorConfig,
)
from ..registry import register_check


def _parse_dsn(dsn: str) -> dict:
    """Parse a database DSN into components."""
    result = {"type": "unknown", "host": "", "port": "", "database": ""}
    
    if dsn.startswith("postgresql://") or dsn.startswith("postgres://"):
        result["type"] = "postgresql"
    elif dsn.startswith("sqlite://"):
        result["type"] = "sqlite"
    elif dsn.startswith("redis://"):
        result["type"] = "redis"
    elif dsn.startswith("mongodb://") or dsn.startswith("mongodb+srv://"):
        result["type"] = "mongodb"
    
    return result


@register_check(
    id="db_config",
    title="Database Configuration",
    description="Check database configuration from environment",
    category=CheckCategory.DATABASE,
    severity=CheckSeverity.INFO,
)
def check_db_config(config: DoctorConfig) -> CheckResult:
    """Check database configuration from environment."""
    dsn = config.dsn or os.environ.get("DATABASE_URL") or os.environ.get("PRAISONAI_DATABASE_URL")
    
    if dsn:
        parsed = _parse_dsn(dsn)
        return CheckResult(
            id="db_config",
            title="Database Configuration",
            category=CheckCategory.DATABASE,
            status=CheckStatus.PASS,
            message=f"Database configured: {parsed['type']}",
            metadata={"type": parsed["type"]},
        )
    else:
        return CheckResult(
            id="db_config",
            title="Database Configuration",
            category=CheckCategory.DATABASE,
            status=CheckStatus.SKIP,
            message="No database DSN configured (using file-based storage)",
            details="Set DATABASE_URL to enable database persistence",
        )


@register_check(
    id="db_driver_postgresql",
    title="PostgreSQL Driver",
    description="Check PostgreSQL driver availability",
    category=CheckCategory.DATABASE,
    severity=CheckSeverity.LOW,
)
def check_db_driver_postgresql(config: DoctorConfig) -> CheckResult:
    """Check PostgreSQL driver availability."""
    try:
        import psycopg2
        version = getattr(psycopg2, "__version__", "unknown")
        return CheckResult(
            id="db_driver_postgresql",
            title="PostgreSQL Driver",
            category=CheckCategory.DATABASE,
            status=CheckStatus.PASS,
            message=f"psycopg2 {version} available",
        )
    except ImportError:
        try:
            import asyncpg
            version = getattr(asyncpg, "__version__", "unknown")
            return CheckResult(
                id="db_driver_postgresql",
                title="PostgreSQL Driver",
                category=CheckCategory.DATABASE,
                status=CheckStatus.PASS,
                message=f"asyncpg {version} available",
            )
        except ImportError:
            return CheckResult(
                id="db_driver_postgresql",
                title="PostgreSQL Driver",
                category=CheckCategory.DATABASE,
                status=CheckStatus.SKIP,
                message="PostgreSQL driver not installed (optional)",
                remediation="Install with: pip install psycopg2-binary or pip install asyncpg",
            )


@register_check(
    id="db_driver_sqlite",
    title="SQLite Driver",
    description="Check SQLite driver availability",
    category=CheckCategory.DATABASE,
    severity=CheckSeverity.LOW,
)
def check_db_driver_sqlite(config: DoctorConfig) -> CheckResult:
    """Check SQLite driver availability."""
    try:
        import sqlite3
        version = sqlite3.sqlite_version
        return CheckResult(
            id="db_driver_sqlite",
            title="SQLite Driver",
            category=CheckCategory.DATABASE,
            status=CheckStatus.PASS,
            message=f"SQLite {version} available (built-in)",
        )
    except ImportError:
        return CheckResult(
            id="db_driver_sqlite",
            title="SQLite Driver",
            category=CheckCategory.DATABASE,
            status=CheckStatus.FAIL,
            message="SQLite not available",
            severity=CheckSeverity.HIGH,
        )


@register_check(
    id="db_driver_redis",
    title="Redis Driver",
    description="Check Redis driver availability",
    category=CheckCategory.DATABASE,
    severity=CheckSeverity.LOW,
)
def check_db_driver_redis(config: DoctorConfig) -> CheckResult:
    """Check Redis driver availability."""
    try:
        import redis
        version = getattr(redis, "__version__", "unknown")
        return CheckResult(
            id="db_driver_redis",
            title="Redis Driver",
            category=CheckCategory.DATABASE,
            status=CheckStatus.PASS,
            message=f"redis-py {version} available",
        )
    except ImportError:
        return CheckResult(
            id="db_driver_redis",
            title="Redis Driver",
            category=CheckCategory.DATABASE,
            status=CheckStatus.SKIP,
            message="Redis driver not installed (optional)",
            remediation="Install with: pip install redis",
        )


@register_check(
    id="db_driver_mongodb",
    title="MongoDB Driver",
    description="Check MongoDB driver availability",
    category=CheckCategory.DATABASE,
    severity=CheckSeverity.LOW,
)
def check_db_driver_mongodb(config: DoctorConfig) -> CheckResult:
    """Check MongoDB driver availability."""
    try:
        import pymongo
        version = getattr(pymongo, "__version__", "unknown")
        return CheckResult(
            id="db_driver_mongodb",
            title="MongoDB Driver",
            category=CheckCategory.DATABASE,
            status=CheckStatus.PASS,
            message=f"pymongo {version} available",
        )
    except ImportError:
        return CheckResult(
            id="db_driver_mongodb",
            title="MongoDB Driver",
            category=CheckCategory.DATABASE,
            status=CheckStatus.SKIP,
            message="MongoDB driver not installed (optional)",
            remediation="Install with: pip install pymongo",
        )


@register_check(
    id="db_connectivity",
    title="Database Connectivity",
    description="Test database connection",
    category=CheckCategory.DATABASE,
    severity=CheckSeverity.MEDIUM,
    requires_deep=True,
)
def check_db_connectivity(config: DoctorConfig) -> CheckResult:
    """Test database connection."""
    dsn = config.dsn or os.environ.get("DATABASE_URL") or os.environ.get("PRAISONAI_DATABASE_URL")
    
    if not dsn:
        return CheckResult(
            id="db_connectivity",
            title="Database Connectivity",
            category=CheckCategory.DATABASE,
            status=CheckStatus.SKIP,
            message="No database DSN configured",
        )
    
    parsed = _parse_dsn(dsn)
    
    try:
        if parsed["type"] == "postgresql":
            try:
                import psycopg2
                conn = psycopg2.connect(dsn, connect_timeout=5)
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.close()
                conn.close()
                return CheckResult(
                    id="db_connectivity",
                    title="Database Connectivity",
                    category=CheckCategory.DATABASE,
                    status=CheckStatus.PASS,
                    message="PostgreSQL connection successful",
                )
            except ImportError:
                return CheckResult(
                    id="db_connectivity",
                    title="Database Connectivity",
                    category=CheckCategory.DATABASE,
                    status=CheckStatus.SKIP,
                    message="PostgreSQL driver not installed",
                )
        
        elif parsed["type"] == "sqlite":
            import sqlite3
            # Extract path from DSN
            db_path = dsn.replace("sqlite:///", "").replace("sqlite://", "")
            if db_path == ":memory:" or os.path.exists(db_path) or db_path == "":
                conn = sqlite3.connect(db_path if db_path else ":memory:")
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.close()
                conn.close()
                return CheckResult(
                    id="db_connectivity",
                    title="Database Connectivity",
                    category=CheckCategory.DATABASE,
                    status=CheckStatus.PASS,
                    message="SQLite connection successful",
                )
            else:
                return CheckResult(
                    id="db_connectivity",
                    title="Database Connectivity",
                    category=CheckCategory.DATABASE,
                    status=CheckStatus.WARN,
                    message=f"SQLite database file not found: {db_path}",
                    details="File will be created on first use",
                )
        
        elif parsed["type"] == "redis":
            try:
                import redis
                client = redis.from_url(dsn, socket_timeout=5)
                client.ping()
                client.close()
                return CheckResult(
                    id="db_connectivity",
                    title="Database Connectivity",
                    category=CheckCategory.DATABASE,
                    status=CheckStatus.PASS,
                    message="Redis connection successful",
                )
            except ImportError:
                return CheckResult(
                    id="db_connectivity",
                    title="Database Connectivity",
                    category=CheckCategory.DATABASE,
                    status=CheckStatus.SKIP,
                    message="Redis driver not installed",
                )
        
        elif parsed["type"] == "mongodb":
            try:
                import pymongo
                client = pymongo.MongoClient(dsn, serverSelectionTimeoutMS=5000)
                client.admin.command("ping")
                client.close()
                return CheckResult(
                    id="db_connectivity",
                    title="Database Connectivity",
                    category=CheckCategory.DATABASE,
                    status=CheckStatus.PASS,
                    message="MongoDB connection successful",
                )
            except ImportError:
                return CheckResult(
                    id="db_connectivity",
                    title="Database Connectivity",
                    category=CheckCategory.DATABASE,
                    status=CheckStatus.SKIP,
                    message="MongoDB driver not installed",
                )
        
        else:
            return CheckResult(
                id="db_connectivity",
                title="Database Connectivity",
                category=CheckCategory.DATABASE,
                status=CheckStatus.SKIP,
                message=f"Unknown database type: {parsed['type']}",
            )
    
    except Exception as e:
        return CheckResult(
            id="db_connectivity",
            title="Database Connectivity",
            category=CheckCategory.DATABASE,
            status=CheckStatus.FAIL,
            message=f"Connection failed: {type(e).__name__}",
            details=str(e)[:200],
            remediation="Check database server is running and DSN is correct",
            severity=CheckSeverity.HIGH,
        )


@register_check(
    id="db_chromadb",
    title="ChromaDB (Vector Store)",
    description="Check ChromaDB availability for RAG",
    category=CheckCategory.DATABASE,
    severity=CheckSeverity.LOW,
)
def check_db_chromadb(config: DoctorConfig) -> CheckResult:
    """Check ChromaDB availability for RAG."""
    try:
        import chromadb
        version = getattr(chromadb, "__version__", "unknown")
        return CheckResult(
            id="db_chromadb",
            title="ChromaDB (Vector Store)",
            category=CheckCategory.DATABASE,
            status=CheckStatus.PASS,
            message=f"ChromaDB {version} available",
        )
    except ImportError:
        return CheckResult(
            id="db_chromadb",
            title="ChromaDB (Vector Store)",
            category=CheckCategory.DATABASE,
            status=CheckStatus.SKIP,
            message="ChromaDB not installed (required for Knowledge/RAG features)",
            remediation="Install with: pip install chromadb",
        )
