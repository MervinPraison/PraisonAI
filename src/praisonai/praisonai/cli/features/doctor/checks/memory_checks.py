"""
Memory checks for the Doctor CLI module.

Validates memory/session storage and integrity.
"""

import os
from pathlib import Path

from ..models import (
    CheckCategory,
    CheckResult,
    CheckStatus,
    CheckSeverity,
    DoctorConfig,
)
from ..registry import register_check


def _find_memory_dirs() -> list:
    """Find memory storage directories."""
    locations = [
        Path.cwd() / ".praison" / "memory",
        Path.cwd() / ".praison" / "sessions",
        Path.home() / ".praison" / "memory",
        Path.home() / ".praison" / "sessions",
        Path.home() / ".config" / "praison" / "memory",
    ]
    
    found = []
    for loc in locations:
        if loc.exists() and loc.is_dir():
            found.append(str(loc))
    
    return found


@register_check(
    id="memory_dirs",
    title="Memory Directories",
    description="Check memory storage directories",
    category=CheckCategory.MEMORY,
    severity=CheckSeverity.INFO,
)
def check_memory_dirs(config: DoctorConfig) -> CheckResult:
    """Check memory storage directories."""
    dirs = _find_memory_dirs()
    
    if dirs:
        return CheckResult(
            id="memory_dirs",
            title="Memory Directories",
            category=CheckCategory.MEMORY,
            status=CheckStatus.PASS,
            message=f"Found {len(dirs)} memory directory(ies)",
            details=", ".join(dirs),
            metadata={"directories": dirs},
        )
    else:
        return CheckResult(
            id="memory_dirs",
            title="Memory Directories",
            category=CheckCategory.MEMORY,
            status=CheckStatus.SKIP,
            message="No memory directories found (will be created on first use)",
        )


@register_check(
    id="memory_files",
    title="Memory Files",
    description="Check memory file integrity",
    category=CheckCategory.MEMORY,
    severity=CheckSeverity.MEDIUM,
    dependencies=["memory_dirs"],
)
def check_memory_files(config: DoctorConfig) -> CheckResult:
    """Check memory file integrity."""
    dirs = _find_memory_dirs()
    
    if not dirs:
        return CheckResult(
            id="memory_files",
            title="Memory Files",
            category=CheckCategory.MEMORY,
            status=CheckStatus.SKIP,
            message="No memory directories to check",
        )
    
    valid_files = 0
    corrupt_files = []
    total_size = 0
    
    for dir_path in dirs:
        memory_dir = Path(dir_path)
        for file_path in memory_dir.rglob("*.json"):
            try:
                import json
                with open(file_path) as f:
                    json.load(f)
                valid_files += 1
                total_size += file_path.stat().st_size
            except json.JSONDecodeError:
                corrupt_files.append(str(file_path))
            except Exception:
                pass
    
    if corrupt_files:
        return CheckResult(
            id="memory_files",
            title="Memory Files",
            category=CheckCategory.MEMORY,
            status=CheckStatus.WARN,
            message=f"{len(corrupt_files)} corrupt file(s) found",
            details="; ".join(corrupt_files[:3]) + ("..." if len(corrupt_files) > 3 else ""),
            remediation="Remove or repair corrupt memory files",
            metadata={"valid": valid_files, "corrupt": corrupt_files},
        )
    elif valid_files > 0:
        size_kb = total_size / 1024
        return CheckResult(
            id="memory_files",
            title="Memory Files",
            category=CheckCategory.MEMORY,
            status=CheckStatus.PASS,
            message=f"{valid_files} valid memory file(s) ({size_kb:.1f} KB)",
            metadata={"valid_count": valid_files, "total_size_bytes": total_size},
        )
    else:
        return CheckResult(
            id="memory_files",
            title="Memory Files",
            category=CheckCategory.MEMORY,
            status=CheckStatus.SKIP,
            message="No memory files found",
        )


@register_check(
    id="memory_sessions",
    title="Session Storage",
    description="Check session storage",
    category=CheckCategory.MEMORY,
    severity=CheckSeverity.INFO,
)
def check_memory_sessions(config: DoctorConfig) -> CheckResult:
    """Check session storage."""
    session_dirs = [
        Path.cwd() / ".praison" / "sessions",
        Path.home() / ".praison" / "sessions",
    ]
    
    sessions = []
    for dir_path in session_dirs:
        if dir_path.exists():
            for item in dir_path.iterdir():
                if item.is_dir() or item.suffix == ".json":
                    sessions.append(item.name)
    
    if sessions:
        return CheckResult(
            id="memory_sessions",
            title="Session Storage",
            category=CheckCategory.MEMORY,
            status=CheckStatus.PASS,
            message=f"Found {len(sessions)} saved session(s)",
            metadata={"sessions": sessions[:10]},
        )
    else:
        return CheckResult(
            id="memory_sessions",
            title="Session Storage",
            category=CheckCategory.MEMORY,
            status=CheckStatus.SKIP,
            message="No saved sessions found",
        )


@register_check(
    id="memory_chromadb",
    title="ChromaDB Memory",
    description="Check ChromaDB vector memory",
    category=CheckCategory.MEMORY,
    severity=CheckSeverity.LOW,
)
def check_memory_chromadb(config: DoctorConfig) -> CheckResult:
    """Check ChromaDB vector memory."""
    chroma_dirs = [
        Path.cwd() / ".praison" / "chroma",
        Path.cwd() / "chroma_db",
        Path.home() / ".praison" / "chroma",
    ]
    
    found = None
    for dir_path in chroma_dirs:
        if dir_path.exists():
            found = dir_path
            break
    
    if found:
        try:
            import chromadb
            # Try to open the database
            client = chromadb.PersistentClient(path=str(found))
            collections = client.list_collections()
            return CheckResult(
                id="memory_chromadb",
                title="ChromaDB Memory",
                category=CheckCategory.MEMORY,
                status=CheckStatus.PASS,
                message=f"ChromaDB found with {len(collections)} collection(s)",
                metadata={"path": str(found), "collections": len(collections)},
            )
        except ImportError:
            return CheckResult(
                id="memory_chromadb",
                title="ChromaDB Memory",
                category=CheckCategory.MEMORY,
                status=CheckStatus.WARN,
                message="ChromaDB directory found but chromadb not installed",
                remediation="Install with: pip install chromadb",
            )
        except Exception as e:
            return CheckResult(
                id="memory_chromadb",
                title="ChromaDB Memory",
                category=CheckCategory.MEMORY,
                status=CheckStatus.WARN,
                message=f"ChromaDB found but cannot open: {type(e).__name__}",
                details=str(e)[:200],
            )
    else:
        return CheckResult(
            id="memory_chromadb",
            title="ChromaDB Memory",
            category=CheckCategory.MEMORY,
            status=CheckStatus.SKIP,
            message="No ChromaDB storage found (optional)",
        )


@register_check(
    id="memory_praisonai_module",
    title="PraisonAI Memory Module",
    description="Check PraisonAI memory module",
    category=CheckCategory.MEMORY,
    severity=CheckSeverity.LOW,
)
def check_memory_praisonai_module(config: DoctorConfig) -> CheckResult:
    """Check PraisonAI memory module."""
    try:
        from praisonaiagents.memory import FileMemory, Memory
        return CheckResult(
            id="memory_praisonai_module",
            title="PraisonAI Memory Module",
            category=CheckCategory.MEMORY,
            status=CheckStatus.PASS,
            message="Memory modules available (FileMemory, Memory)",
        )
    except ImportError as e:
        return CheckResult(
            id="memory_praisonai_module",
            title="PraisonAI Memory Module",
            category=CheckCategory.MEMORY,
            status=CheckStatus.WARN,
            message="Memory module import failed",
            details=str(e),
        )
