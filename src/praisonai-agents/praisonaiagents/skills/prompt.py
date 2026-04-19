"""XML prompt generation for Agent Skills."""

from pathlib import Path
from typing import List
import html

from .models import SkillMetadata
from .parser import read_properties


# G22: Claude Code-equivalent cap on combined description + when_to_use.
MAX_COMBINED_DESCRIPTION_CHARS = 1536


def _truncate(text: str, limit: int) -> str:
    if text is None:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "\u2026"


def format_skill_for_prompt(skill: SkillMetadata) -> str:
    """Format a single skill as XML for system prompt.

    The ``description`` is truncated at 1,536 characters (G22) to keep the
    system-prompt listing bounded even with large skill libraries.
    """
    name = html.escape(skill.name)
    description = html.escape(_truncate(skill.description, MAX_COMBINED_DESCRIPTION_CHARS))
    location = html.escape(skill.location)

    return f"""  <skill>
    <name>{name}</name>
    <description>{description}</description>
    <location>{location}</location>
  </skill>"""


def generate_skills_xml(skills: List[SkillMetadata], working_directory: str = None) -> str:
    """Generate XML block for available skills.

    Args:
        skills: List of SkillMetadata instances
        working_directory: Current working directory for path resolution

    Returns:
        XML string with <available_skills> block
    """
    import os
    cwd = working_directory or os.getcwd()
    
    if not skills:
        return f"""<available_skills>
  <working_directory>{html.escape(cwd)}</working_directory>
  <note>When using run_skill_script, pass file paths relative to the working directory or as absolute paths. The tool will resolve relative paths automatically.</note>
</available_skills>"""

    skill_entries = "\n".join(format_skill_for_prompt(s) for s in skills)
    return f"""<available_skills>
  <working_directory>{html.escape(cwd)}</working_directory>
  <note>When using run_skill_script, pass file paths relative to the working directory or as absolute paths. The tool will resolve relative paths automatically.</note>
{skill_entries}
</available_skills>"""


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
