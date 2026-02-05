"""
Topic Normalizer for Documentation Parity Tracking.

Handles variations in topic names across different SDKs:
- Singular/plural: agents -> agent
- Case: Agent -> agent
- Hyphenation: agent-team, agentteam -> agent-team
- Suffixes: agent-cli -> agent-cli (kept separate)
"""

import re
from typing import Dict, Set

# Explicit topic aliases for known variations
TOPIC_ALIASES: Dict[str, str] = {
    # Plural to singular
    'agents': 'agent',
    'tasks': 'task',
    'tools': 'tool',
    'workflows': 'workflow',
    'guardrails': 'guardrail',
    'handoffs': 'handoff',
    'sessions': 'session',
    'hooks': 'hook',
    'skills': 'skill',
    'recipes': 'recipe',
    'callbacks': 'callback',
    'providers': 'provider',
    'embeddings': 'embedding',
    'databases': 'database',
    
    # Compound name variations
    'agentteam': 'agent-team',
    'agentos': 'agent-os',
    'agentflow': 'agent-flow',
    
    # Common abbreviations
    'js': 'javascript',
    'ts': 'typescript',
    
    # Index pages
    'index': 'overview',
}

# Topics that are language-specific and should be excluded from parity
LANGUAGE_SPECIFIC_TOPICS: Dict[str, Set[str]] = {
    'python': {
        'crewai',
        'autogen',
        'praisonaiagents',
    },
    'typescript': {
        'nodejs',
        'nextjs',
        'typescript-async',
    },
    'rust': {
        'cargo',
    },
}

# Topics that are CLI-specific (suffixed with -cli)
CLI_SUFFIX_PATTERN = re.compile(r'^(.+)-cli$')


def normalize_topic(name: str) -> str:
    """
    Normalize a topic name for comparison.
    
    Transformations applied:
    1. Convert to lowercase
    2. Replace underscores with hyphens
    3. Apply explicit aliases
    4. Keep CLI suffixes intact (agent-cli stays agent-cli)
    
    Args:
        name: Raw topic name (usually from filename)
        
    Returns:
        Normalized topic name
        
    Examples:
        >>> normalize_topic("Agents")
        'agent'
        >>> normalize_topic("agent_team")
        'agent-team'
        >>> normalize_topic("AgentTeam")
        'agent-team'
        >>> normalize_topic("agent-cli")
        'agent-cli'
    """
    # Step 1: Lowercase
    name = name.lower()
    
    # Step 2: Replace underscores with hyphens
    name = name.replace('_', '-')
    
    # Step 3: Handle camelCase by inserting hyphens
    # AgentTeam -> agent-team
    name = re.sub(r'([a-z])([A-Z])', r'\1-\2', name).lower()
    
    # Step 4: Apply explicit aliases
    if name in TOPIC_ALIASES:
        return TOPIC_ALIASES[name]
    
    # Step 5: Handle plural (only if not in aliases and not a CLI topic)
    if not CLI_SUFFIX_PATTERN.match(name):
        # Remove trailing 's' only for simple plurals
        if name.endswith('s') and not name.endswith('ss') and not name.endswith('os'):
            singular = name[:-1]
            # Check if singular form is a known alias
            if singular in TOPIC_ALIASES:
                return TOPIC_ALIASES[singular]
            # Only apply if it looks like a simple plural (not 'status', 'process', etc.)
            if len(singular) > 3:
                return singular
    
    return name


def is_cli_topic(name: str) -> bool:
    """Check if a topic is a CLI-specific topic (ends with -cli)."""
    return CLI_SUFFIX_PATTERN.match(name) is not None


def get_base_topic(name: str) -> str:
    """
    Get the base topic name, stripping CLI suffix if present.
    
    Examples:
        >>> get_base_topic("agent-cli")
        'agent'
        >>> get_base_topic("agent")
        'agent'
    """
    match = CLI_SUFFIX_PATTERN.match(name)
    if match:
        return normalize_topic(match.group(1))
    return normalize_topic(name)


def is_language_specific(topic: str, language: str) -> bool:
    """
    Check if a topic is specific to a language and shouldn't be in parity.
    
    Args:
        topic: Normalized topic name
        language: Target language ('python', 'typescript', 'rust')
        
    Returns:
        True if this topic is specific to another language
    """
    for lang, specific_topics in LANGUAGE_SPECIFIC_TOPICS.items():
        if lang != language and topic in specific_topics:
            return True
    return False


def topics_match(topic1: str, topic2: str) -> bool:
    """
    Check if two topics are equivalent after normalization.
    
    Args:
        topic1: First topic name
        topic2: Second topic name
        
    Returns:
        True if topics are considered equivalent
    """
    return normalize_topic(topic1) == normalize_topic(topic2)
