"""
Skills Capabilities Module

Provides agent skills functionality.
"""

from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List


@dataclass
class SkillResult:
    """Result from skill operations."""
    name: str
    description: Optional[str] = None
    path: Optional[str] = None
    instructions: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def skill_list(
    skill_dirs: Optional[List[str]] = None,
    include_defaults: bool = True,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> List[SkillResult]:
    """
    List available skills.
    
    Args:
        skill_dirs: Optional list of directories to scan
        include_defaults: Whether to include default skill directories
        metadata: Optional metadata for tracing
        
    Returns:
        List of SkillResult objects
        
    Example:
        >>> skills = skill_list()
        >>> for skill in skills:
        ...     print(skill.name)
    """
    try:
        from praisonaiagents.skills import discover_skills
        
        skills = discover_skills(skill_dirs, include_defaults)
        
        results = []
        for skill in skills:
            results.append(SkillResult(
                name=skill.name,
                description=skill.description,
                path=str(skill.path) if skill.path else None,
                metadata=metadata or {},
            ))
        
        return results
    except ImportError:
        return []


async def askill_list(
    skill_dirs: Optional[List[str]] = None,
    include_defaults: bool = True,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> List[SkillResult]:
    """
    Async: List available skills.
    
    See skill_list() for full documentation.
    """
    return skill_list(
        skill_dirs=skill_dirs,
        include_defaults=include_defaults,
        metadata=metadata,
        **kwargs
    )


def skill_load(
    skill_name: str,
    skill_dirs: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> Optional[SkillResult]:
    """
    Load a skill by name.
    
    Args:
        skill_name: Name of the skill to load
        skill_dirs: Optional list of directories to scan
        metadata: Optional metadata for tracing
        
    Returns:
        SkillResult with skill details or None if not found
    """
    try:
        from praisonaiagents.skills import load_skill
        
        skill = load_skill(skill_name, skill_dirs)
        
        if skill:
            return SkillResult(
                name=skill.name,
                description=skill.description,
                path=str(skill.path) if skill.path else None,
                instructions=skill.instructions if hasattr(skill, 'instructions') else None,
                metadata=metadata or {},
            )
        
        return None
    except ImportError:
        return None


async def askill_load(
    skill_name: str,
    skill_dirs: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> Optional[SkillResult]:
    """
    Async: Load a skill by name.
    
    See skill_load() for full documentation.
    """
    return skill_load(
        skill_name=skill_name,
        skill_dirs=skill_dirs,
        metadata=metadata,
        **kwargs
    )
