"""Agent Skills module for PraisonAI Agents.

This module provides support for the open Agent Skills standard (agentskills.io),
enabling agents to load and use modular capabilities through SKILL.md files.

Zero Performance Impact:
- All imports are lazy loaded via __getattr__
- Skills only loaded when explicitly enabled
- No auto-discovery at import time

Usage:
    from praisonaiagents.skills import SkillManager, SkillProperties
    
    manager = SkillManager()
    manager.discover(["./skills"])
    prompt_xml = manager.to_prompt()
"""

__all__ = [
    # Models
    "SkillProperties",
    "SkillMetadata",
    "ParseError",
    "ValidationError",
    # Parser
    "parse_frontmatter",
    "find_skill_md",
    "read_properties",
    # Validator
    "validate",
    "validate_metadata",
    # Prompt
    "to_prompt",
    "generate_skills_xml",
    "format_skill_for_prompt",
    # Discovery
    "discover_skills",
    "get_default_skill_dirs",
    # Loader
    "SkillLoader",
    # Manager
    "SkillManager",
]


def __getattr__(name: str):
    """Lazy load module components to avoid import overhead."""
    if name in ("SkillProperties", "SkillMetadata", "ParseError", "ValidationError"):
        from .models import SkillProperties, SkillMetadata, ParseError, ValidationError
        return locals()[name]
    
    if name in ("parse_frontmatter", "find_skill_md", "read_properties"):
        from .parser import parse_frontmatter, find_skill_md, read_properties
        return locals()[name]
    
    if name in ("validate", "validate_metadata", "_validate_name", "_validate_description", "_validate_compatibility"):
        from .validator import validate, validate_metadata, _validate_name, _validate_description, _validate_compatibility
        return locals()[name]
    
    if name in ("to_prompt", "generate_skills_xml", "format_skill_for_prompt"):
        from .prompt import to_prompt, generate_skills_xml, format_skill_for_prompt
        return locals()[name]
    
    if name in ("discover_skills", "get_default_skill_dirs"):
        from .discovery import discover_skills, get_default_skill_dirs
        return locals()[name]
    
    if name == "SkillLoader":
        from .loader import SkillLoader
        return SkillLoader
    
    if name == "SkillManager":
        from .manager import SkillManager
        return SkillManager
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
