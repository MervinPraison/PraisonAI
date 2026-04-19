"""Skill discovery and directory scanning."""

import logging
from pathlib import Path
from typing import List, Optional

from .parser import find_skill_md, read_properties
from .models import SkillProperties
from ..paths import get_skills_dir, get_project_data_dir

logger = logging.getLogger(__name__)


def get_default_skill_dirs() -> List[Path]:
    """Get default skill directory locations.

    Uses centralized paths.py for consistent path management.
    Returns directories in precedence order (high to low):
    1. Project: ./.praisonai/skills/ or ./.claude/skills/
    2. User: ~/.praisonai/skills/
    3. System: /etc/praison/skills/ (admin-managed)

    Returns:
        List of existing skill directories
    """
    dirs = []
    cwd = Path.cwd()

    # Project-level directories (use centralized path)
    project_data_dir = get_project_data_dir()
    project_skills = project_data_dir / "skills"
    if project_skills.exists() and project_skills.is_dir():
        dirs.append(project_skills)
    
    # Also check .claude/skills for compatibility
    claude_skills = cwd / ".claude" / "skills"
    if claude_skills.exists() and claude_skills.is_dir():
        dirs.append(claude_skills)

    # G10: Walk ancestor directories for nested `.claude/skills` or
    # `.praisonai/skills` so monorepo packages pick up workspace skills.
    for parent in cwd.parents:
        for sub in (".praisonai/skills", ".claude/skills"):
            p = parent / sub
            if p.exists() and p.is_dir() and p not in dirs:
                dirs.append(p)

    # User-level directory (use centralized path)
    user_skills = get_skills_dir()
    if user_skills.exists() and user_skills.is_dir():
        dirs.append(user_skills)

    # System-level directory (Unix-like systems)
    system_dir = Path("/etc/praison/skills")
    if system_dir.exists() and system_dir.is_dir():
        dirs.append(system_dir)

    return dirs


def discover_skills(
    skill_dirs: Optional[List[str]] = None,
    include_defaults: bool = True,
) -> List[SkillProperties]:
    """Discover all valid skills in the given directories.

    Args:
        skill_dirs: List of directory paths to scan for skills.
            Each directory should contain skill subdirectories.
        include_defaults: Whether to include default skill directories

    Returns:
        List of SkillProperties for all valid skills found
    """
    all_dirs = []

    # Add explicit directories
    if skill_dirs:
        for d in skill_dirs:
            path = Path(d).expanduser().resolve()
            if path.exists() and path.is_dir():
                all_dirs.append(path)

    # Add default directories
    if include_defaults:
        all_dirs.extend(get_default_skill_dirs())

    # Remove duplicates while preserving order
    seen = set()
    unique_dirs = []
    for d in all_dirs:
        if d not in seen:
            seen.add(d)
            unique_dirs.append(d)

    skills = []

    for parent_dir in unique_dirs:
        # Each subdirectory in parent_dir might be a skill
        try:
            for item in parent_dir.iterdir():
                if not item.is_dir():
                    continue

                # Check if this directory contains a SKILL.md
                skill_md = find_skill_md(item)
                if skill_md is None:
                    continue

                try:
                    props = read_properties(item)
                except Exception as exc:
                    logger.warning(
                        "Skipping invalid skill %s: %s", item, exc,
                    )
                    continue

                # G9: log collisions so users can see which skill won
                if any(p.name == props.name for p in skills):
                    logger.info(
                        "Skill '%s' at %s shadowed by earlier entry (precedence).",
                        props.name, item,
                    )
                    continue
                skills.append(props)
        except PermissionError as exc:
            logger.warning("Cannot read skills directory %s: %s", parent_dir, exc)
            continue

    return skills


def discover_skill(skill_path: str) -> Optional[SkillProperties]:
    """Discover a single skill from a directory path.

    Args:
        skill_path: Path to a skill directory

    Returns:
        SkillProperties if valid, None otherwise
    """
    path = Path(skill_path).expanduser().resolve()

    if not path.exists() or not path.is_dir():
        return None

    skill_md = find_skill_md(path)
    if skill_md is None:
        return None

    try:
        return read_properties(path)
    except Exception:
        return None
