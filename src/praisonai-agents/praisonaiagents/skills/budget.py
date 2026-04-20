"""Agent Skills prompt budget management.

Controls how many skills and how much content gets included in 
the system prompt to prevent unbounded growth with large skill libraries.
"""

import html
from dataclasses import dataclass
from typing import Literal, List
from .models import SkillMetadata

# Maximum description chars before truncation (from prompt.py)
MAX_COMBINED_DESCRIPTION_CHARS = 1536


def _truncate(text: str, limit: int) -> str:
    """Truncate text to limit (same logic as prompt.py)."""
    if text is None:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "\u2026"


def _estimate_skill_xml_chars(skill: SkillMetadata) -> int:
    """Estimate the rendered XML character count for a skill."""
    name = html.escape(skill.name)
    description = html.escape(_truncate(skill.description, MAX_COMBINED_DESCRIPTION_CHARS))
    location = html.escape(skill.location or "")
    
    # Exact XML format from format_skill_for_prompt
    xml_content = f"""  <skill>
    <name>{name}</name>
    <description>{description}</description>
    <location>{location}</location>
  </skill>"""
    
    return len(xml_content)


@dataclass(frozen=True)
class SkillPromptBudget:
    """Budget constraints for skills included in system prompts.
    
    Prevents unbounded system prompt growth when agents have access
    to large skill libraries.
    """
    max_chars: int = 4096
    max_skills: int = 50
    strategy: Literal["priority", "fifo", "alpha"] = "fifo"


def apply_budget(skills: List[SkillMetadata], budget: SkillPromptBudget) -> tuple[List[SkillMetadata], bool]:
    """Apply budget constraints to a list of skills.
    
    Args:
        skills: List of skill metadata to potentially include
        budget: Budget constraints to apply
        
    Returns:
        Tuple of (filtered_skills, was_truncated)
    """
    if not skills:
        return skills, False
        
    # Apply ordering strategy first, before selecting the bounded subset
    if budget.strategy == "alpha":
        ordered_skills = sorted(skills, key=lambda s: s.name)
    elif budget.strategy == "fifo":
        ordered_skills = skills
    else:
        # priority strategy would require skill metadata to include priority field;
        # for now, treat as fifo
        ordered_skills = skills

    # Apply skill count limit after ordering
    limited_skills = ordered_skills[:budget.max_skills]
    skill_count_truncated = len(limited_skills) < len(skills)
    
    total_chars = 0
    filtered_skills = []
    char_truncated = False
    
    for skill in limited_skills:
        skill_chars = _estimate_skill_xml_chars(skill)
        if total_chars + skill_chars > budget.max_chars:
            char_truncated = True
            break
        filtered_skills.append(skill)
        total_chars += skill_chars
    
    was_truncated = skill_count_truncated or char_truncated
    return filtered_skills, was_truncated