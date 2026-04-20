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

        loaded = load_skill(skill_name, skill_dirs)

        if loaded is None:
            return None

        props = loaded.properties
        return SkillResult(
            name=props.name,
            description=props.description,
            path=str(props.path) if props.path else None,
            instructions=loaded.instructions,
            metadata=metadata or {},
        )
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


def tool_from_skill(path: str):
    """Convert a skill to a tool function for direct tool registry integration.
    
    This adapter allows users who prefer "skill = tool" ergonomics to
    drop a SKILL.md into an existing tool registry without refactoring.
    
    Args:
        path: Path to the skill directory containing SKILL.md
        
    Returns:
        A function decorated with @tool that renders the skill body
        
    Example:
        # Convert a skill to a tool
        pdf_tool = tool_from_skill("./skills/pdf-processing")
        
        # Add to existing tool registry
        agent = Agent(tools=[pdf_tool, other_tools])
    """
    from pathlib import Path
    try:
        from praisonaiagents.skills import load_skill, render_skill_body
        from praisonaiagents.tools import tool
        
        # Load the skill
        skill_name = Path(path).name
        skill_dirs = [str(Path(path).parent)]
        loaded = load_skill(skill_name, skill_dirs)
        
        if loaded is None:
            raise ValueError(f"Skill not found at path: {path}")
        
        # Create the tool function with proper metadata and argument handling
        def _skill_tool(arguments: str = "") -> str:
            """Execute skill with provided arguments."""
            if loaded.instructions is None:
                return f"Skill '{skill_name}' has no instructions"
            
            # Return the skill instructions with argument substitution
            return render_skill_body(loaded.instructions, arguments)
        
        # Create tool with proper metadata during decoration
        safe_name = skill_name.replace('-', '_').replace(' ', '_')
        return tool(
            name=f"skill_{safe_name}",
            description=loaded.properties.description or f"Execute {skill_name} skill",
        )(_skill_tool)
        
    except ImportError:
        def _dummy_tool(arguments: str = "") -> str:
            return "Skills not available (praisonaiagents not installed)"
        return _dummy_tool
