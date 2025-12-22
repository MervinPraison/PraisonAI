"""XML prompt generation for Agent Skills."""

from pathlib import Path
from typing import List
import html

from .models import SkillMetadata
from .parser import read_properties


def format_skill_for_prompt(skill: SkillMetadata) -> str:
    """Format a single skill as XML for system prompt.

    Args:
        skill: SkillMetadata instance

    Returns:
        XML string for the skill
    """
    name = html.escape(skill.name)
    description = html.escape(skill.description)
    location = html.escape(skill.location)

    return f"""  <skill>
    <name>{name}</name>
    <description>{description}</description>
    <location>{location}</location>
  </skill>"""


def generate_skills_xml(skills: List[SkillMetadata]) -> str:
    """Generate XML block for available skills.

    Args:
        skills: List of SkillMetadata instances

    Returns:
        XML string with <available_skills> block
    """
    if not skills:
        return "<available_skills>\n</available_skills>"

    skill_entries = "\n".join(format_skill_for_prompt(s) for s in skills)
    return f"<available_skills>\n{skill_entries}\n</available_skills>"


def to_prompt(skill_dirs: List[Path]) -> str:
    """Generate prompt XML from skill directories.

    This is the main entry point for generating the <available_skills>
    block to inject into agent system prompts.

    Args:
        skill_dirs: List of paths to skill directories

    Returns:
        XML string with <available_skills> block
    """
    skills = []

    for skill_dir in skill_dirs:
        skill_dir = Path(skill_dir)
        if not skill_dir.exists() or not skill_dir.is_dir():
            continue

        try:
            props = read_properties(skill_dir)
            meta = SkillMetadata.from_properties(props)
            skills.append(meta)
        except Exception:
            # Skip invalid skills silently
            continue

    return generate_skills_xml(skills)
