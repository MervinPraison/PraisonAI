"""SkillManager for Agent Skills integration."""

from typing import List, Optional, Dict

from .models import SkillMetadata
from .discovery import discover_skills
from .loader import SkillLoader, LoadedSkill
from .prompt import generate_skills_xml


class SkillManager:
    """Manager for discovering, loading, and using Agent Skills.

    This is the main entry point for Agent Skills integration.
    Supports progressive disclosure and zero performance impact
    when skills are not used.

    Usage:
        manager = SkillManager()

        # Discover skills from directories
        manager.discover(["./skills", "~/.praison/skills"])

        # Get XML for system prompt
        prompt_xml = manager.to_prompt()

        # Activate a specific skill
        skill = manager.get_skill("pdf-processing")
        manager.activate(skill)
    """

    def __init__(self):
        """Initialize the SkillManager."""
        self._skills: Dict[str, LoadedSkill] = {}
        self._loader = SkillLoader()
        self._discovered = False

    @property
    def skills(self) -> List[LoadedSkill]:
        """Get all loaded skills."""
        return list(self._skills.values())

    @property
    def skill_names(self) -> List[str]:
        """Get names of all loaded skills."""
        return list(self._skills.keys())

    def discover(
        self,
        skill_dirs: Optional[List[str]] = None,
        include_defaults: bool = True,
    ) -> int:
        """Discover skills from directories.

        Args:
            skill_dirs: List of directory paths to scan
            include_defaults: Whether to include default skill directories

        Returns:
            Number of skills discovered
        """
        props_list = discover_skills(skill_dirs, include_defaults)

        for props in props_list:
            if props.name not in self._skills:
                self._skills[props.name] = LoadedSkill(properties=props)

        self._discovered = True
        return len(props_list)

    def add_skill(self, skill_path: str) -> Optional[LoadedSkill]:
        """Add a single skill from a directory path.

        Args:
            skill_path: Path to skill directory

        Returns:
            LoadedSkill if successful, None otherwise
        """
        skill = self._loader.load_metadata(skill_path)
        if skill:
            self._skills[skill.properties.name] = skill
        return skill

    def get_skill(self, name: str) -> Optional[LoadedSkill]:
        """Get a skill by name.

        Args:
            name: Skill name

        Returns:
            LoadedSkill or None if not found
        """
        return self._skills.get(name)

    def activate(self, skill: LoadedSkill) -> bool:
        """Activate a skill (load its instructions).

        Args:
            skill: LoadedSkill to activate

        Returns:
            True if activation succeeded
        """
        return self._loader.activate(skill)

    def activate_by_name(self, name: str) -> bool:
        """Activate a skill by name.

        Args:
            name: Skill name

        Returns:
            True if activation succeeded
        """
        skill = self.get_skill(name)
        if skill is None:
            return False
        return self.activate(skill)

    def get_available_skills(self) -> List[SkillMetadata]:
        """Get metadata for all available skills.

        This is used for system prompt injection.

        Returns:
            List of SkillMetadata instances
        """
        return [skill.metadata for skill in self._skills.values()]

    def to_prompt(self) -> str:
        """Generate XML prompt for available skills.

        Returns:
            XML string with <available_skills> block
        """
        metadata_list = self.get_available_skills()
        return generate_skills_xml(metadata_list)

    def get_instructions(self, name: str) -> Optional[str]:
        """Get instructions for a skill, activating if needed.

        Args:
            name: Skill name

        Returns:
            Skill instructions or None if not found
        """
        skill = self.get_skill(name)
        if skill is None:
            return None

        if not skill.is_activated:
            self.activate(skill)

        return skill.instructions

    def load_resources(self, name: str) -> bool:
        """Load all resources for a skill.

        Args:
            name: Skill name

        Returns:
            True if resources loaded successfully
        """
        skill = self.get_skill(name)
        if skill is None:
            return False

        self._loader.load_all_resources(skill)
        return True

    def clear(self) -> None:
        """Clear all loaded skills."""
        self._skills.clear()
        self._discovered = False

    def __len__(self) -> int:
        """Get number of loaded skills."""
        return len(self._skills)

    def __contains__(self, name: str) -> bool:
        """Check if a skill is loaded."""
        return name in self._skills

    def __iter__(self):
        """Iterate over loaded skills."""
        return iter(self._skills.values())
