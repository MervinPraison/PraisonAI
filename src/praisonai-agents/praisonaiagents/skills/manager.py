"""SkillManager for Agent Skills integration."""

import logging
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)

from .models import SkillMetadata
from .discovery import discover_skills
from .loader import SkillLoader, LoadedSkill
from .prompt import generate_skills_xml
from .substitution import render_skill_body
from .shell_render import render_shell_blocks


class SkillManager:
    """Manager for discovering, loading, and using Agent Skills.

    This is the main entry point for Agent Skills integration.
    Supports progressive disclosure and zero performance impact
    when skills are not used.

    Usage:
        manager = SkillManager()

        # Discover skills from directories
        manager.discover(["./skills", "~/.praisonai/skills"])

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

        This is used for system prompt injection. Skills with
        ``disable-model-invocation: true`` are omitted so the LLM never
        sees them and cannot auto-trigger them.
        """
        return [
            skill.metadata
            for skill in self._skills.values()
            if not getattr(skill.properties, "disable_model_invocation", False)
        ]

    def get_user_invocable_skills(self) -> List[LoadedSkill]:
        """Return skills the *user* may invoke via slash-commands.

        Skills with ``user-invocable: false`` are excluded.
        """
        return [
            s for s in self._skills.values()
            if getattr(s.properties, "user_invocable", True)
        ]

    def get_allowed_tools(self, name: str) -> List[str]:
        """Return the ``allowed-tools`` list for a skill as a list of names.

        Accepts either a YAML list or a whitespace-separated string (Claude
        Code accepts both forms). Unknown skill -> ``[]``.
        """
        skill = self.get_skill(name)
        if skill is None:
            return []
        raw = getattr(skill.properties, "allowed_tools", None)
        if raw is None:
            return []
        if isinstance(raw, (list, tuple)):
            return [str(x) for x in raw]
        if isinstance(raw, str):
            return raw.split()
        return []

    def invoke(
        self,
        name: str,
        raw_args: str = "",
        session_id: Optional[str] = None,
        shell_exec: bool = False,
    ) -> Optional[str]:
        """Render a skill body into a ready-to-send prompt.

        Substitutes ``$ARGUMENTS``, ``$N``, ``${PRAISON_SKILL_DIR}`` and
        optionally runs ``!`cmd` `` inline shell blocks when ``shell_exec``
        is True.

        Returns:
            Rendered body, or None if the skill does not exist or is not
            user-invocable.
        """
        skill = self.get_skill(name)
        if skill is None:
            return None
        if not getattr(skill.properties, "user_invocable", True):
            return None
        if not skill.is_activated:
            self.activate(skill)
        if skill.instructions is None:
            return None
        skill_dir = str(skill.properties.path) if skill.properties.path else None
        body = render_skill_body(
            skill.instructions,
            raw_args=raw_args,
            skill_dir=skill_dir,
            session_id=session_id,
        )
        shell = getattr(skill.properties, "shell", None) or "bash"
        body = render_shell_blocks(
            body, enabled=shell_exec, shell=shell, cwd=skill_dir,
        )
        return body

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

    def create_skill(self, name: str, content: str, category: str = None) -> dict:
        """Create a new skill with the given content.
        
        Args:
            name: Skill name (must be valid identifier)
            content: Skill instructions/content for SKILL.md
            category: Optional skill category
            
        Returns:
            Dict with success status and skill info
        """
        try:
            # Validate name
            if not self._validate_skill_name(name):
                return {"success": False, "error": f"Invalid skill name: {name}"}
            
            # Check if skill already exists
            if name in self._skills:
                return {"success": False, "error": f"Skill '{name}' already exists"}
            
            # Validate content size
            if len(content) > 100_000:
                return {"success": False, "error": "Skill content exceeds maximum size (100KB)"}
            
            # Create skill directory
            from .discovery import get_default_skill_directories
            skill_dirs = get_default_skill_directories()
            base_dir = skill_dirs[0] if skill_dirs else "~/.praisonai/skills"
            
            import os
            from pathlib import Path
            base_path = Path(base_dir).expanduser()
            base_path.mkdir(parents=True, exist_ok=True)
            
            skill_path = base_path / name
            skill_path.mkdir(exist_ok=True)
            
            # Write SKILL.md with frontmatter
            skill_content = f"""---
name: {name}
version: 1.0.0
"""
            if category:
                skill_content += f"category: {category}\n"
            skill_content += f"""description: Generated skill
author: agent
---

{content}
"""
            
            skill_file = skill_path / "SKILL.md"
            self._write_skill_atomically(skill_file, skill_content)
            
            # Load the new skill
            skill = self.add_skill(str(skill_path))
            if skill:
                return {"success": True, "skill": skill.properties.name, "path": str(skill_path)}
            else:
                return {"success": False, "error": "Failed to load created skill"}
                
        except Exception as e:
            return {"success": False, "error": f"Error creating skill: {str(e)}"}
    
    def edit_skill(self, name: str, content: str) -> dict:
        """Edit an existing skill's content (full rewrite).
        
        Args:
            name: Skill name to edit
            content: New skill content
            
        Returns:
            Dict with success status
        """
        try:
            skill = self.get_skill(name)
            if not skill:
                return {"success": False, "error": f"Skill '{name}' not found"}
            
            if not skill.properties.path:
                return {"success": False, "error": f"Cannot edit skill '{name}' - no path available"}
            
            # Validate content size
            if len(content) > 100_000:
                return {"success": False, "error": "Skill content exceeds maximum size (100KB)"}
            
            # Read existing frontmatter
            skill_file = skill.properties.path / "SKILL.md"
            if not skill_file.exists():
                return {"success": False, "error": f"Skill file not found: {skill_file}"}
            
            with open(skill_file, 'r', encoding='utf-8') as f:
                existing_content = f.read()
            
            # Extract frontmatter (preserve verbatim, only strip leading fence)
            frontmatter = ""
            if existing_content.startswith('---\n'):
                parts = existing_content.split('\n---\n', 1)
                if len(parts) == 2:
                    fm_body = parts[0].removeprefix('---\n')
                    frontmatter = f"---\n{fm_body}\n---\n\n"
            
            # Write updated content
            new_content = frontmatter + content
            self._write_skill_atomically(skill_file, new_content)
            
            # Reload the skill
            skill.instructions = None  # Clear cached content
            self.activate(skill)
            
            return {"success": True, "skill": name}
            
        except Exception as e:
            return {"success": False, "error": f"Error editing skill: {str(e)}"}
    
    def patch_skill(self, name: str, old_string: str, new_string: str, 
                   file_path: str = None, replace_all: bool = False) -> dict:
        """Apply a patch to a skill using fuzzy find-and-replace.
        
        Args:
            name: Skill name to patch
            old_string: String to find and replace
            new_string: Replacement string
            file_path: Optional relative path within skill (defaults to SKILL.md)
            replace_all: Replace all occurrences
            
        Returns:
            Dict with success status
        """
        try:
            skill = self.get_skill(name)
            if not skill:
                return {"success": False, "error": f"Skill '{name}' not found"}
            
            if not skill.properties.path:
                return {"success": False, "error": f"Cannot patch skill '{name}' - no path available"}
            
            # Determine target file
            if file_path:
                from pathlib import Path
                relative_path = Path(file_path)
                if relative_path.is_absolute() or ".." in relative_path.parts:
                    return {"success": False, "error": f"Path traversal detected: {file_path}"}
                target_file = (skill.properties.path / relative_path).resolve()
                try:
                    target_file.relative_to(skill.properties.path.resolve())
                except ValueError:
                    return {"success": False, "error": f"Path traversal detected: {file_path}"}
            else:
                target_file = skill.properties.path / "SKILL.md"
            
            if not target_file.exists():
                return {"success": False, "error": f"File not found: {target_file}"}
            
            # Perform fuzzy find and replace
            with open(target_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Simple string replacement
            if old_string in content:
                if replace_all:
                    new_content = content.replace(old_string, new_string)
                else:
                    # Replace only first occurrence
                    new_content = content.replace(old_string, new_string, 1)
                
                self._write_skill_atomically(target_file, new_content)
                
                # Clear cached content if SKILL.md was modified
                if file_path is None or file_path == "SKILL.md":
                    skill.instructions = None
                    self.activate(skill)
                
                return {"success": True, "skill": name, "replacements": 1}
            else:
                return {"success": False, "error": f"String not found: '{old_string[:50]}...'"}
                
        except Exception as e:
            return {"success": False, "error": f"Error patching skill: {str(e)}"}
    
    def delete_skill(self, name: str) -> dict:
        """Delete a skill and its directory.
        
        Args:
            name: Skill name to delete
            
        Returns:
            Dict with success status
        """
        try:
            skill = self.get_skill(name)
            if not skill:
                return {"success": False, "error": f"Skill '{name}' not found"}
            
            if not skill.properties.path:
                return {"success": False, "error": f"Cannot delete skill '{name}' - no path available"}
            
            # Remove directory first, then update in-memory index.
            import shutil
            shutil.rmtree(skill.properties.path)
            self._skills.pop(name, None)
            
            return {"success": True, "skill": name, "path": str(skill.properties.path)}
            
        except Exception as e:
            return {"success": False, "error": f"Error deleting skill: {str(e)}"}
    
    def write_skill_file(self, name: str, file_path: str, file_content: str) -> dict:
        """Write a file within a skill's directory.
        
        Args:
            name: Skill name
            file_path: Relative path within skill (must be under allowed subdirs)
            file_content: File content to write
            
        Returns:
            Dict with success status
        """
        try:
            skill = self.get_skill(name)
            if not skill:
                return {"success": False, "error": f"Skill '{name}' not found"}
            
            if not skill.properties.path:
                return {"success": False, "error": f"Cannot write to skill '{name}' - no path available"}
            
            # Validate file path is in allowed subdirectories
            from pathlib import Path
            allowed_subdirs = ['references', 'templates', 'scripts', 'assets']
            relative_path = Path(file_path)
            path_parts = relative_path.parts
            if relative_path.is_absolute() or ".." in path_parts:
                return {"success": False, "error": f"Path traversal detected: {file_path}"}
            if not path_parts or path_parts[0] not in allowed_subdirs:
                return {"success": False, "error": f"File path must be under: {allowed_subdirs}"}
            
            # Validate file size
            if len(file_content) > 1_048_576:  # 1 MB
                return {"success": False, "error": "File content exceeds maximum size (1MB)"}
            
            # Create target file
            target_file = (skill.properties.path / relative_path).resolve()
            try:
                target_file.relative_to(skill.properties.path.resolve())
            except ValueError:
                return {"success": False, "error": f"Path traversal detected: {file_path}"}
            target_file.parent.mkdir(parents=True, exist_ok=True)
            
            self._write_skill_atomically(target_file, file_content)
            
            return {"success": True, "skill": name, "file": file_path}
            
        except Exception as e:
            return {"success": False, "error": f"Error writing skill file: {str(e)}"}
    
    def remove_skill_file(self, name: str, file_path: str) -> dict:
        """Remove a file from a skill's directory.
        
        Args:
            name: Skill name
            file_path: Relative path within skill to remove
            
        Returns:
            Dict with success status
        """
        try:
            skill = self.get_skill(name)
            if not skill:
                return {"success": False, "error": f"Skill '{name}' not found"}
            
            if not skill.properties.path:
                return {"success": False, "error": f"Cannot remove from skill '{name}' - no path available"}
            
            target_file = skill.properties.path / file_path
            if not target_file.exists():
                return {"success": False, "error": f"File not found: {file_path}"}
            
            # Security check - file must be within skill directory
            try:
                target_file.resolve().relative_to(skill.properties.path.resolve())
            except ValueError:
                return {"success": False, "error": f"Path traversal detected: {file_path}"}
            
            target_file.unlink()
            
            return {"success": True, "skill": name, "file": file_path}
            
        except Exception as e:
            return {"success": False, "error": f"Error removing skill file: {str(e)}"}
    
    def _validate_skill_name(self, name: str) -> bool:
        """Validate skill name according to security constraints."""
        import re
        if len(name) > 64:
            return False
        # Allow letters, numbers, dots, underscores, hyphens
        return bool(re.match(r'^[a-z0-9][a-z0-9._-]*$', name))
    
    def _write_skill_atomically(self, file_path, content: str) -> None:
        """Write file content atomically using temp file + rename."""
        import tempfile
        import os
        
        # Create temp file in same directory
        temp_fd, temp_path = tempfile.mkstemp(
            dir=file_path.parent, 
            prefix=f".{file_path.name}.",
            suffix=".tmp"
        )
        
        try:
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                f.write(content)
            os.replace(temp_path, file_path)
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                logger.debug("Failed to clean up temp file %s", temp_path, exc_info=True)
            raise

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
