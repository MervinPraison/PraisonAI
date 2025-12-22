"""Skill discovery and directory scanning."""

from pathlib import Path
from typing import List, Optional

from .parser import find_skill_md, read_properties
from .models import SkillProperties


def get_default_skill_dirs() -> List[Path]:
    """Get default skill directory locations.

    Returns directories in precedence order (high to low):
    1. Project: ./.praison/skills/ or ./.claude/skills/
    2. User: ~/.praison/skills/
    3. System: /etc/praison/skills/ (admin-managed)

    Returns:
        List of existing skill directories
    """
    dirs = []
    cwd = Path.cwd()

    # Project-level directories
    project_dirs = [
        cwd / ".praison" / "skills",
        cwd / ".claude" / "skills",
    ]
    for d in project_dirs:
        if d.exists() and d.is_dir():
            dirs.append(d)

    # User-level directory
    user_dir = Path.home() / ".praison" / "skills"
    if user_dir.exists() and user_dir.is_dir():
        dirs.append(user_dir)

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
                    skills.append(props)
                except Exception:
                    # Skip invalid skills
                    continue
        except PermissionError:
            # Skip directories we can't read
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
