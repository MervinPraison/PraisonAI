"""Progressive skill loading for Agent Skills."""

from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

from .parser import find_skill_md, read_properties, parse_frontmatter
from .models import SkillProperties, SkillMetadata


@dataclass
class LoadedSkill:
    """A fully or partially loaded skill.

    Supports progressive disclosure:
    - Level 1: metadata only (name, description, location)
    - Level 2: full instructions (SKILL.md body)
    - Level 3: resources (scripts, references, assets)
    """

    properties: SkillProperties
    instructions: Optional[str] = None
    resources_loaded: bool = False
    _scripts: dict = field(default_factory=dict)
    _references: dict = field(default_factory=dict)
    _assets: dict = field(default_factory=dict)

    @property
    def metadata(self) -> SkillMetadata:
        """Get lightweight metadata for system prompt."""
        return SkillMetadata.from_properties(self.properties)

    @property
    def is_activated(self) -> bool:
        """Check if skill has been activated (instructions loaded)."""
        return self.instructions is not None

    def get_scripts(self) -> dict:
        """Get loaded scripts."""
        return self._scripts

    def get_references(self) -> dict:
        """Get loaded references."""
        return self._references

    def get_assets(self) -> dict:
        """Get loaded assets."""
        return self._assets


class SkillLoader:
    """Loader for Agent Skills with progressive disclosure support.

    Usage:
        loader = SkillLoader()

        # Level 1: Load metadata only
        skill = loader.load_metadata("/path/to/skill")

        # Level 2: Activate skill (load instructions)
        loader.activate(skill)

        # Level 3: Load specific resources
        loader.load_scripts(skill)
        loader.load_references(skill)
    """

    def load_metadata(self, skill_path: str) -> Optional[LoadedSkill]:
        """Load skill metadata only (Level 1).

        This is the minimal load for system prompt injection.
        Only reads the YAML frontmatter, not the full SKILL.md body.

        Args:
            skill_path: Path to skill directory

        Returns:
            LoadedSkill with metadata only, or None if invalid
        """
        path = Path(skill_path).expanduser().resolve()

        if not path.exists() or not path.is_dir():
            return None

        try:
            props = read_properties(path)
            return LoadedSkill(properties=props)
        except Exception:
            return None

    def activate(self, skill: LoadedSkill) -> bool:
        """Activate a skill by loading its full instructions (Level 2).

        Args:
            skill: LoadedSkill instance to activate

        Returns:
            True if activation succeeded
        """
        if skill.is_activated:
            return True

        if skill.properties.path is None:
            return False

        skill_md = find_skill_md(skill.properties.path)
        if skill_md is None:
            return False

        try:
            content = skill_md.read_text()
            _, body = parse_frontmatter(content)
            skill.instructions = body
            return True
        except Exception:
            return False

    def load_scripts(self, skill: LoadedSkill) -> dict:
        """Load scripts from skill's scripts/ directory (Level 3).

        Args:
            skill: LoadedSkill instance

        Returns:
            Dict mapping script names to their contents
        """
        if skill.properties.path is None:
            return {}

        scripts_dir = skill.properties.path / "scripts"
        if not scripts_dir.exists() or not scripts_dir.is_dir():
            return {}

        scripts = {}
        try:
            for script_file in scripts_dir.iterdir():
                if script_file.is_file():
                    try:
                        scripts[script_file.name] = script_file.read_text()
                    except Exception:
                        continue
        except PermissionError:
            pass

        skill._scripts = scripts
        return scripts

    def load_references(self, skill: LoadedSkill) -> dict:
        """Load references from skill's references/ directory (Level 3).

        Args:
            skill: LoadedSkill instance

        Returns:
            Dict mapping reference names to their contents
        """
        if skill.properties.path is None:
            return {}

        refs_dir = skill.properties.path / "references"
        if not refs_dir.exists() or not refs_dir.is_dir():
            return {}

        refs = {}
        try:
            for ref_file in refs_dir.iterdir():
                if ref_file.is_file():
                    try:
                        refs[ref_file.name] = ref_file.read_text()
                    except Exception:
                        continue
        except PermissionError:
            pass

        skill._references = refs
        return refs

    def load_assets(self, skill: LoadedSkill) -> dict:
        """Load asset paths from skill's assets/ directory (Level 3).

        Note: For binary assets, only paths are returned, not contents.

        Args:
            skill: LoadedSkill instance

        Returns:
            Dict mapping asset names to their paths
        """
        if skill.properties.path is None:
            return {}

        assets_dir = skill.properties.path / "assets"
        if not assets_dir.exists() or not assets_dir.is_dir():
            return {}

        assets = {}
        try:
            for asset_file in assets_dir.iterdir():
                if asset_file.is_file():
                    assets[asset_file.name] = str(asset_file)
        except PermissionError:
            pass

        skill._assets = assets
        skill.resources_loaded = True
        return assets

    def load_all_resources(self, skill: LoadedSkill) -> None:
        """Load all resources for a skill (Level 3 complete).

        Args:
            skill: LoadedSkill instance
        """
        self.load_scripts(skill)
        self.load_references(skill)
        self.load_assets(skill)
        skill.resources_loaded = True

    @classmethod
    def load(cls, skill_path: str, activate: bool = False) -> Optional[LoadedSkill]:
        """Convenience method to load a skill.

        Args:
            skill_path: Path to skill directory
            activate: Whether to also load instructions

        Returns:
            LoadedSkill or None if invalid
        """
        loader = cls()
        skill = loader.load_metadata(skill_path)

        if skill and activate:
            loader.activate(skill)

        return skill
