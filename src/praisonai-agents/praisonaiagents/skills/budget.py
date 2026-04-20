"""Agent Skills prompt budget management.

Controls how many skills and how much content gets included in 
the system prompt to prevent unbounded growth with large skill libraries.
"""

from dataclasses import dataclass
from typing import Literal, List
from .models import SkillMetadata


@dataclass(frozen=True)
class SkillPromptBudget:
    """Budget constraints for skills included in system prompts.
    
    Prevents unbounded system prompt growth when agents have access
    to large skill libraries.
    """
    max_chars: int = 4096
    max_skills: int = 50
    strategy: Literal["priority", "fifo", "alpha"] = "priority"


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
        
    # Apply skill count limit first
    limited_skills = skills[:budget.max_skills] if len(skills) > budget.max_skills else skills
    skill_count_truncated = len(limited_skills) < len(skills)
    
    # Apply character budget
    if budget.strategy == "alpha":
        limited_skills = sorted(limited_skills, key=lambda s: s.name)
    elif budget.strategy == "fifo":
        # Keep original order (first discovered wins)
        pass
    # priority strategy would require skill metadata to include priority field
    # for now, treat as fifo
    
    total_chars = 0
    filtered_skills = []
    char_truncated = False
    
    for skill in limited_skills:
        skill_chars = len(skill.name) + len(skill.description) + 50  # XML overhead
        if total_chars + skill_chars > budget.max_chars:
            char_truncated = True
            break
        filtered_skills.append(skill)
        total_chars += skill_chars
    
    was_truncated = skill_count_truncated or char_truncated
    return filtered_skills, was_truncated