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
    # Invocation
    "render_skill_body",
    "render_shell_blocks",
    "load_skill",
    # Protocols
    "SkillSourceProtocol",
    "SkillInvocationPolicyProtocol",
    "SkillMutatorProtocol",
    "SkillActivationProtocol",
    # Events
    "SkillDiscoveredEvent",
    "SkillActivatedEvent",
    # Budget
    "SkillPromptBudget",
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

    if name == "render_skill_body":
        from .substitution import render_skill_body
        return render_skill_body

    if name == "render_shell_blocks":
        from .shell_render import render_shell_blocks
        return render_shell_blocks

    if name in ("SkillSourceProtocol", "SkillInvocationPolicyProtocol", "SkillMutatorProtocol"):
        from .protocols import SkillSourceProtocol, SkillInvocationPolicyProtocol, SkillMutatorProtocol
        return locals()[name]

    if name == "SkillActivationProtocol":
        from .activation import SkillActivationProtocol
        return SkillActivationProtocol

    if name in ("SkillDiscoveredEvent", "SkillActivatedEvent"):
        from .events import SkillDiscoveredEvent, SkillActivatedEvent
        return locals()[name]

    if name == "SkillPromptBudget":
        from .budget import SkillPromptBudget
        return SkillPromptBudget

    if name == "load_skill":
        # Fixes G12: praisonai.capabilities.skills.skill_load import target.
        # Returns a LoadedSkill (metadata + activated instructions) by name,
        # searching provided or default skill directories.
        from .discovery import discover_skills
        from .loader import SkillLoader

        def load_skill(skill_name: str, skill_dirs=None):
            props_list = discover_skills(skill_dirs, include_defaults=True)
            for props in props_list:
                if props.name == skill_name and props.path is not None:
                    loader = SkillLoader()
                    loaded = loader.load_metadata(str(props.path))
                    if loaded is not None:
                        loader.activate(loaded)
                    return loaded
            return None

        return load_skill

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
