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

from .._lazy import create_lazy_getattr_with_groups

__all__ = [
    # Models
    "SkillProperties",
    "SkillMetadata", 
    "SkillRequirements",
    "SkillAutomation",
    "SkillState",
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
    # Learn-from-sources
    "build_learn_prompt",
    # Discovery
    "discover_skills",
    "get_default_skill_dirs",
    # Bundles
    "BundleManifest",
    "discover_bundles",
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
    "RemoteSkillSourceProtocol",
    "SkillInvocationPolicyProtocol",
    "SkillMutatorProtocol",
    "SkillActivationProtocol",
    "SkillReviewProtocol",
    "DefaultSkillReviewPolicy",
    # Remote sources
    "GitRemoteSkillSource",
    "fetch_remote_skill_dirs",
    # Events
    "SkillDiscoveredEvent",
    "SkillActivatedEvent",
    # Budget
    "SkillPromptBudget",
    # Capability validation
    "CapabilityValidator",
    "EnforcementLevel",
    "ValidationResult",
]


_LAZY_GROUPS = {
    'models': {
        'SkillProperties': ('praisonaiagents.skills.models', 'SkillProperties'),
        'SkillMetadata': ('praisonaiagents.skills.models', 'SkillMetadata'),
        'SkillRequirements': ('praisonaiagents.skills.models', 'SkillRequirements'),
        'SkillAutomation': ('praisonaiagents.skills.models', 'SkillAutomation'),
        'SkillState': ('praisonaiagents.skills.models', 'SkillState'),
        'ParseError': ('praisonaiagents.skills.models', 'ParseError'),
        'ValidationError': ('praisonaiagents.skills.models', 'ValidationError'),
    },
    'parser': {
        'parse_frontmatter': ('praisonaiagents.skills.parser', 'parse_frontmatter'),
        'find_skill_md': ('praisonaiagents.skills.parser', 'find_skill_md'),
        'read_properties': ('praisonaiagents.skills.parser', 'read_properties'),
    },
    'validator': {
        'validate': ('praisonaiagents.skills.validator', 'validate'),
        'validate_metadata': ('praisonaiagents.skills.validator', 'validate_metadata'),
        '_validate_name': ('praisonaiagents.skills.validator', '_validate_name'),
        '_validate_description': ('praisonaiagents.skills.validator', '_validate_description'),
        '_validate_compatibility': ('praisonaiagents.skills.validator', '_validate_compatibility'),
    },
    'prompt': {
        'to_prompt': ('praisonaiagents.skills.prompt', 'to_prompt'),
        'generate_skills_xml': ('praisonaiagents.skills.prompt', 'generate_skills_xml'),
        'format_skill_for_prompt': ('praisonaiagents.skills.prompt', 'format_skill_for_prompt'),
    },
    'learn': {
        'build_learn_prompt': ('praisonaiagents.skills.learn', 'build_learn_prompt'),
    },
    'discovery': {
        'discover_skills': ('praisonaiagents.skills.discovery', 'discover_skills'),
        'get_default_skill_dirs': ('praisonaiagents.skills.discovery', 'get_default_skill_dirs'),
    },
    'bundles': {
        'BundleManifest': ('praisonaiagents.skills.bundles', 'BundleManifest'),
        'discover_bundles': ('praisonaiagents.skills.bundles', 'discover_bundles'),
    },
    'loader': {
        'SkillLoader': ('praisonaiagents.skills.loader', 'SkillLoader'),
    },
    'manager': {
        'SkillManager': ('praisonaiagents.skills.manager', 'SkillManager'),
    },
    'substitution': {
        'render_skill_body': ('praisonaiagents.skills.substitution', 'render_skill_body'),
    },
    'shell_render': {
        'render_shell_blocks': ('praisonaiagents.skills.shell_render', 'render_shell_blocks'),
    },
    'protocols_sources': {
        'SkillSourceProtocol': ('praisonaiagents.skills.protocols', 'SkillSourceProtocol'),
        'RemoteSkillSourceProtocol': ('praisonaiagents.skills.protocols', 'RemoteSkillSourceProtocol'),
        'SkillInvocationPolicyProtocol': ('praisonaiagents.skills.protocols', 'SkillInvocationPolicyProtocol'),
        'SkillMutatorProtocol': ('praisonaiagents.skills.protocols', 'SkillMutatorProtocol'),
    },
    'remote': {
        'GitRemoteSkillSource': ('praisonaiagents.skills.remote', 'GitRemoteSkillSource'),
        'fetch_remote_skill_dirs': ('praisonaiagents.skills.remote', 'fetch_remote_skill_dirs'),
    },
    'protocols_review': {
        'SkillReviewProtocol': ('praisonaiagents.skills.protocols', 'SkillReviewProtocol'),
        'DefaultSkillReviewPolicy': ('praisonaiagents.skills.protocols', 'DefaultSkillReviewPolicy'),
    },
    'activation': {
        'SkillActivationProtocol': ('praisonaiagents.skills.activation', 'SkillActivationProtocol'),
    },
    'events': {
        'SkillDiscoveredEvent': ('praisonaiagents.skills.events', 'SkillDiscoveredEvent'),
        'SkillActivatedEvent': ('praisonaiagents.skills.events', 'SkillActivatedEvent'),
    },
    'budget': {
        'SkillPromptBudget': ('praisonaiagents.skills.budget', 'SkillPromptBudget'),
    },
    'capability_validator': {
        'CapabilityValidator': ('praisonaiagents.skills.capability_validator', 'CapabilityValidator'),
        'EnforcementLevel': ('praisonaiagents.skills.capability_validator', 'EnforcementLevel'),
        'ValidationResult': ('praisonaiagents.skills.capability_validator', 'ValidationResult'),
    },
}

_lazy_getattr = create_lazy_getattr_with_groups(_LAZY_GROUPS, __name__)


def __getattr__(name: str):
    """Lazy load module components to avoid import overhead."""
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

    return _lazy_getattr(name)
