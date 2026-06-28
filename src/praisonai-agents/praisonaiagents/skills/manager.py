"""SkillManager for Agent Skills integration."""

import logging
from typing import List, Optional, Dict, TYPE_CHECKING

logger = logging.getLogger(__name__)

from .models import SkillMetadata, SkillState

if TYPE_CHECKING:
    from .bundles import BundleManifest
from .discovery import discover_skills, get_default_skill_dirs
from .loader import SkillLoader, LoadedSkill
from .prompt import generate_skills_xml
from .substitution import render_skill_body
from .shell_render import render_shell_blocks
from .capability_validator import CapabilityValidator, EnforcementLevel, ValidationResult


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

    def __init__(self, enforcement_level: Optional[EnforcementLevel] = None,
                 write_approval: Optional[bool] = None):
        """Initialize the SkillManager.
        
        Args:
            enforcement_level: Capability enforcement level (defaults to environment-based)
            write_approval: When True, skill mutations are staged for human
                approval by default (``propose=True``). When None, resolved from
                the ``SKILL_WRITE_APPROVAL`` environment variable (default True
                for safe-by-default behaviour).
        """
        self._skills: Dict[str, LoadedSkill] = {}
        self._bundles: Dict[str, "BundleManifest"] = {}
        self._loader = SkillLoader()
        self._discovered = False
        self._validation_cache: Dict[str, ValidationResult] = {}
        
        # Initialize capability validator
        if enforcement_level is None:
            enforcement_level = self._get_default_enforcement_level()
        self._validator = CapabilityValidator(enforcement_level)

        # Resolve safe-by-default write-approval policy.
        if write_approval is None:
            write_approval = self._get_default_write_approval()
        self._write_approval = write_approval

        # Cap the pending-mutation store to bound resource use (configurable
        # via SKILL_MAX_PENDING; defaults to 100).
        import os
        try:
            self._max_pending = max(1, int(os.getenv('SKILL_MAX_PENDING', '100')))
        except (TypeError, ValueError):
            self._max_pending = 100

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

    # ── Bundles (composition over skills) ─────────────────────────────

    @property
    def bundles(self) -> List["BundleManifest"]:
        """Get all registered bundle manifests."""
        return list(self._bundles.values())

    @property
    def bundle_names(self) -> List[str]:
        """Get names of all registered bundles."""
        return list(self._bundles.keys())

    def add_bundle(self, manifest: "BundleManifest") -> None:
        """Register a bundle manifest.

        First registration wins; a later bundle of the same name is shadowed
        and logged (same precedence stance discovery already uses).
        """
        if manifest.name in self._bundles:
            logger.info(
                "Bundle '%s' already registered; ignoring duplicate (precedence).",
                manifest.name,
            )
            return
        self._bundles[manifest.name] = manifest

    def get_bundle(self, name: str) -> Optional["BundleManifest"]:
        """Get a bundle manifest by name (``@`` marker optional)."""
        from .bundles import strip_bundle_marker
        return self._bundles.get(strip_bundle_marker(name))

    def discover_bundles(
        self,
        skill_dirs: Optional[List[str]] = None,
        include_defaults: bool = True,
    ) -> int:
        """Discover bundle manifests from directories.

        Returns:
            Number of bundles registered.
        """
        from .bundles import discover_bundles as _discover_bundles
        manifests = _discover_bundles(skill_dirs, include_defaults)
        added = 0
        for manifest in manifests:
            if manifest.name not in self._bundles:
                self._bundles[manifest.name] = manifest
                added += 1
        return added

    def resolve(self, selectors: List[str]) -> List[str]:
        """Expand ``@bundle`` selectors into member skill names.

        Plain skill names/paths pass through unchanged. A ``@bundle`` selector
        expands to its member skill names (forgiving: a missing/unknown bundle
        is logged, not fatal). Duplicates are removed while preserving order.
        """
        from .bundles import is_bundle_selector, strip_bundle_marker

        resolved: List[str] = []
        seen = set()

        def _add(item: str) -> None:
            if item and item not in seen:
                seen.add(item)
                resolved.append(item)

        for selector in selectors or []:
            if is_bundle_selector(selector):
                name = strip_bundle_marker(selector)
                manifest = self._bundles.get(name)
                if manifest is None:
                    logger.warning(
                        "Unknown skill bundle '@%s'; skipping (no such bundle).",
                        name,
                    )
                    continue
                for member in manifest.skills:
                    _add(member)
            else:
                _add(selector)

        return resolved

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

    def add_skill_by_name(
        self,
        name: str,
        skill_dirs: Optional[List[str]] = None,
        include_defaults: bool = True,
    ) -> Optional[LoadedSkill]:
        """Add a single skill resolved by *name* (not path).

        Searches the given/default skill directories for a skill whose name
        matches and loads it. Used to materialise bundle members, which are
        referenced by name. Forgiving: returns None if no match is found.
        """
        if name in self._skills:
            return self._skills[name]
        props_list = discover_skills(skill_dirs, include_defaults)
        for props in props_list:
            if props.name == name and props.path is not None:
                return self.add_skill(str(props.path))
        return None

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

        This is used for system prompt injection. Skills are filtered by:
        1. disable-model-invocation: true (excluded)
        2. Capability enforcement (if strict mode, exclude UNAVAILABLE skills)
        """
        available = []
        for skill in self._skills.values():
            # Skip if explicitly disabled for model invocation
            if getattr(skill.properties, "disable_model_invocation", False):
                continue
                
            # Check capability requirements if enforcement is strict
            if self._validator.enforcement_level == EnforcementLevel.STRICT:
                try:
                    validation = self.validate_skill_capabilities(skill.properties.name)
                    if validation.state == SkillState.UNAVAILABLE:
                        continue  # Skip unavailable skills in strict mode
                except Exception as e:
                    logger.warning(f"Skipping skill '{skill.properties.name}' due to validation error: {e}")
                    continue
                    
            available.append(skill.metadata)
            
        return available

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
        self._record_use(skill)
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

        # Only count a genuinely usable skill: a skill that fails to activate
        # (instructions is None) must not accrue use telemetry, otherwise a
        # broken skill looks active to the lifecycle curator.
        if skill.instructions is None:
            return None

        self._record_use(skill)
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

    def create_skill(self, name: str, content: str, category: str = None,
                     agent_created: bool = True,
                     propose: Optional[bool] = None) -> dict:
        """Create a new skill with the given content.
        
        Args:
            name: Skill name (must be valid identifier)
            content: Skill instructions/content for SKILL.md
            category: Optional skill category
            agent_created: Provenance flag marking the skill as agent-authored.
                Defaults to True since skills created via this API originate
                from the agent's self-improvement loop. Lifecycle curator
                plugins only ever touch agent-created skills.
            propose: If True, stage the mutation for human approval instead of
                writing to disk. Defaults to the manager's ``write_approval``
                policy (safe-by-default). Pass ``propose=False`` to write
                directly in trusted/local contexts.
            
        Returns:
            Dict with success status and skill info
        """
        if self._should_propose(propose):
            return self._stage_pending(
                "create", name, content=content, category=category,
                agent_created=agent_created,
            )
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
            
            # Create skill directory (same base as the pending store target)
            base_path = self._skills_base_dir()
            
            skill_path = base_path / name
            skill_path.mkdir(exist_ok=True)
            
            # Write SKILL.md with frontmatter (incl. provenance + usage telemetry)
            created_at = self._now_iso()
            skill_content = f"""---
name: {name}
version: 1.0.0
"""
            if category:
                skill_content += f"category: {category}\n"
            skill_content += "description: Generated skill\n"
            skill_content += "author: agent\n"
            skill_content += f"agent-created: {str(bool(agent_created)).lower()}\n"
            skill_content += f'created-at: "{created_at}"\n'
            skill_content += "use-count: 0\n"
            skill_content += "patch-count: 0\n"
            skill_content += f"""---

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
    
    def edit_skill(self, name: str, content: str,
                   propose: Optional[bool] = None) -> dict:
        """Edit an existing skill's content (full rewrite).
        
        Args:
            name: Skill name to edit
            content: New skill content
            propose: If True, stage the mutation for human approval instead of
                writing to disk. Defaults to the manager's ``write_approval``
                policy. Pass ``propose=False`` to write directly.
            
        Returns:
            Dict with success status
        """
        if self._should_propose(propose):
            return self._stage_pending("edit", name, content=content)
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
            
            # Snapshot prior content so a broken mutation can be rolled back.
            self._save_backup(skill.properties.path, existing_content)
            
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
            self._record_patch(skill)
            
            return {"success": True, "skill": name}
            
        except Exception as e:
            return {"success": False, "error": f"Error editing skill: {str(e)}"}
    
    def patch_skill(self, name: str, old_string: str, new_string: str, 
                   file_path: str = None, replace_all: bool = False,
                   propose: Optional[bool] = None) -> dict:
        """Apply a patch to a skill using fuzzy find-and-replace.
        
        Args:
            name: Skill name to patch
            old_string: String to find and replace
            new_string: Replacement string
            file_path: Optional relative path within skill (defaults to SKILL.md)
            replace_all: Replace all occurrences
            propose: If True, stage the mutation for human approval instead of
                writing to disk. Defaults to the manager's ``write_approval``
                policy. Pass ``propose=False`` to apply directly.
            
        Returns:
            Dict with success status
        """
        if self._should_propose(propose):
            return self._stage_pending(
                "patch", name, old_string=old_string, new_string=new_string,
                file_path=file_path, replace_all=replace_all,
            )
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
                
                is_skill_md = file_path is None or file_path == "SKILL.md"
                # Snapshot the SKILL.md before mutating so it can be rolled back.
                if is_skill_md:
                    self._save_backup(skill.properties.path, content)
                
                self._write_skill_atomically(target_file, new_content)
                
                # Clear cached content if SKILL.md was modified
                if is_skill_md:
                    skill.instructions = None
                    self.activate(skill)
                    self._record_patch(skill)
                
                return {"success": True, "skill": name, "replacements": 1}
            else:
                return {"success": False, "error": f"String not found: '{old_string[:50]}...'"}
                
        except Exception as e:
            return {"success": False, "error": f"Error patching skill: {str(e)}"}
    
    def delete_skill(self, name: str, hard: bool = False,
                     propose: Optional[bool] = None) -> dict:
        """Remove a skill.

        By default this is a *recoverable* archive: the skill directory is
        moved aside into the archive store and can be restored later. This
        keeps the self-improvement loop safe — a skill is never lost. Pass
        ``hard=True`` to permanently delete the directory (legacy behaviour).
        
        Args:
            name: Skill name to delete
            hard: If True, permanently remove the directory (unrecoverable)
            propose: If True, stage the deletion for human approval instead of
                removing from disk. Defaults to the manager's ``write_approval``
                policy. Pass ``propose=False`` to delete directly.
            
        Returns:
            Dict with success status
        """
        if self._should_propose(propose):
            return self._stage_pending("delete", name, hard=hard)
        if not hard:
            return self.archive_skill(name)
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

    def archive_skill(self, name: str) -> dict:
        """Archive a skill (recoverable, never hard-deleted).

        Moves the skill directory into the archive store and drops it from
        the active in-memory index. Use :meth:`restore_skill` to recover it.
        Lifecycle curator plugins call this for agent-created skills that have
        gone stale.

        Args:
            name: Skill name to archive

        Returns:
            Dict with success status and archive path
        """
        try:
            skill = self.get_skill(name)
            if not skill:
                return {"success": False, "error": f"Skill '{name}' not found"}

            if not skill.properties.path:
                return {"success": False, "error": f"Cannot archive skill '{name}' - no path available"}

            import shutil
            from pathlib import Path

            archive_dir = self._archive_dir()
            archive_dir.mkdir(parents=True, exist_ok=True)
            dest = archive_dir / name
            # Avoid clobbering a previous archive of the same name.
            if dest.exists():
                from datetime import datetime, timezone
                stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                dest = archive_dir / f"{name}.{stamp}"

            shutil.move(str(skill.properties.path), str(dest))
            self._skills.pop(name, None)

            return {"success": True, "skill": name, "archive_path": str(dest)}

        except Exception as e:
            return {"success": False, "error": f"Error archiving skill: {str(e)}"}

    def restore_skill(self, name: str, skill_dir: Optional[str] = None) -> dict:
        """Restore a previously archived skill back to active use.

        Args:
            name: Archived skill name
            skill_dir: Optional destination directory (defaults to the first
                default skill dir)

        Returns:
            Dict with success status
        """
        try:
            import shutil
            from pathlib import Path

            archive_dir = self._archive_dir()
            src = archive_dir / name
            if not src.exists() or not src.is_dir():
                return {"success": False, "error": f"Archived skill '{name}' not found"}

            if skill_dir:
                base_path = Path(skill_dir).expanduser()
            else:
                skill_dirs = get_default_skill_dirs()
                base_dir = skill_dirs[0] if skill_dirs else "~/.praisonai/skills"
                base_path = Path(base_dir).expanduser()
            base_path.mkdir(parents=True, exist_ok=True)

            dest = base_path / name
            if dest.exists():
                return {"success": False, "error": f"Skill '{name}' already exists at destination"}

            shutil.move(str(src), str(dest))
            loaded = self.add_skill(str(dest))
            if loaded:
                return {"success": True, "skill": name, "path": str(dest)}
            return {"success": False, "error": "Failed to load restored skill"}

        except Exception as e:
            return {"success": False, "error": f"Error restoring skill: {str(e)}"}

    def list_archived_skills(self) -> List[str]:
        """List the names of skills currently in the archive store."""
        archive_dir = self._archive_dir()
        if not archive_dir.exists():
            return []
        try:
            return sorted(
                p.name for p in archive_dir.iterdir() if p.is_dir()
            )
        except OSError:
            return []

    def rollback_skill(self, name: str) -> dict:
        """Roll a skill's SKILL.md back to its content before the last mutation.

        Restores the snapshot saved by the most recent ``edit_skill`` or
        ``patch_skill`` call, undoing a mutation that broke a previously
        working skill.

        Note: this is a *single-step* undo. Only the most recent mutation is
        snapshotted; sequential ``edit``/``patch`` calls overwrite the prior
        snapshot, so rollback cannot step back more than one mutation.

        Args:
            name: Skill name to roll back

        Returns:
            Dict with success status
        """
        try:
            skill = self.get_skill(name)
            if not skill:
                return {"success": False, "error": f"Skill '{name}' not found"}

            if not skill.properties.path:
                return {"success": False, "error": f"Cannot roll back skill '{name}' - no path available"}

            backup_file = self._backup_path(skill.properties.path)
            if not backup_file.exists():
                return {"success": False, "error": f"No rollback snapshot for skill '{name}'"}

            previous = backup_file.read_text(encoding="utf-8")
            skill_file = skill.properties.path / "SKILL.md"
            self._write_skill_atomically(skill_file, previous)

            # Reload from the restored content.
            skill.instructions = None
            self.activate(skill)

            return {"success": True, "skill": name}

        except Exception as e:
            return {"success": False, "error": f"Error rolling back skill: {str(e)}"}
    
    def write_skill_file(self, name: str, file_path: str, file_content: str,
                         propose: Optional[bool] = None) -> dict:
        """Write a file within a skill's directory.
        
        Args:
            name: Skill name
            file_path: Relative path within skill (must be under allowed subdirs)
            file_content: File content to write
            propose: If True, stage the write for human approval instead of
                writing to disk. Defaults to the manager's ``write_approval``
                policy. Pass ``propose=False`` to write directly.
            
        Returns:
            Dict with success status
        """
        if self._should_propose(propose):
            return self._stage_pending(
                "write_file", name, file_path=file_path,
                file_content=file_content,
            )
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
    
    def remove_skill_file(self, name: str, file_path: str,
                          propose: Optional[bool] = None) -> dict:
        """Remove a file from a skill's directory.
        
        Args:
            name: Skill name
            file_path: Relative path within skill to remove
            propose: If True, stage the removal for human approval instead of
                removing from disk. Defaults to the manager's ``write_approval``
                policy. Pass ``propose=False`` to remove directly.
            
        Returns:
            Dict with success status
        """
        if self._should_propose(propose):
            return self._stage_pending("remove_file", name, file_path=file_path)
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
    
    @staticmethod
    def _now_iso() -> str:
        """Return the current UTC time as an ISO 8601 string."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    def _archive_dir(self):
        """Directory where archived skills are stored (recoverable)."""
        from pathlib import Path
        skill_dirs = get_default_skill_dirs()
        base_dir = skill_dirs[0] if skill_dirs else "~/.praisonai/skills"
        return Path(base_dir).expanduser().parent / "skills_archive"

    @staticmethod
    def _backup_path(skill_path):
        """Path to the rollback snapshot for a skill's SKILL.md."""
        return skill_path / ".skill.bak"

    def _save_backup(self, skill_path, content: str) -> None:
        """Persist a rollback snapshot of the current SKILL.md content."""
        try:
            self._write_skill_atomically(self._backup_path(skill_path), content)
        except Exception:
            logger.debug("Failed to save rollback snapshot for %s", skill_path, exc_info=True)

    def _record_use(self, skill) -> None:
        """Increment in-memory usage telemetry and persist to frontmatter."""
        try:
            props = skill.properties
            props.use_count = (props.use_count or 0) + 1
            props.last_used = self._now_iso()
            self._update_frontmatter_fields(
                props.path,
                {"use-count": props.use_count, "last-used": props.last_used},
            )
        except Exception:
            logger.debug("Failed to record skill use telemetry", exc_info=True)

    def _record_patch(self, skill) -> None:
        """Increment in-memory patch telemetry and persist to frontmatter."""
        try:
            props = skill.properties
            props.patch_count = (props.patch_count or 0) + 1
            self._update_frontmatter_fields(
                props.path, {"patch-count": props.patch_count}
            )
        except Exception:
            logger.debug("Failed to record skill patch telemetry", exc_info=True)

    def _update_frontmatter_fields(self, skill_path, fields: dict) -> None:
        """Update or insert simple scalar keys in a SKILL.md frontmatter block.

        Operates line-wise so existing (possibly hand-authored) frontmatter is
        preserved verbatim. No-op if there is no path or no frontmatter.
        """
        if skill_path is None or not fields:
            return
        from .parser import find_skill_md
        skill_md = find_skill_md(skill_path)
        if skill_md is None:
            return
        try:
            content = skill_md.read_text(encoding="utf-8")
        except OSError:
            return
        if not content.startswith("---"):
            return
        # Split only on a fence that sits on its own line so embedded "---"
        # sequences inside frontmatter values (e.g. "foo---bar") cannot
        # fragment the block and corrupt the file. The opening fence is the
        # leading "---"; the closing fence is the next "\n---\n".
        after_open = content[3:]
        fm_body, sep, body = after_open.partition("\n---\n")
        if not sep:
            return

        def _fmt(value):
            # Quote timestamp-like strings so YAML preserves them as strings
            # (e.g. the 'T' separator) rather than coercing to a datetime.
            if isinstance(value, str) and (":" in value or "-" in value):
                return f'"{value}"'
            return value

        fm_lines = fm_body.split("\n")
        remaining = dict(fields)
        new_lines = []
        for line in fm_lines:
            stripped = line.strip()
            replaced = False
            if stripped and ":" in stripped and not stripped.startswith("#"):
                key = stripped.split(":", 1)[0].strip()
                if key in remaining:
                    new_lines.append(f"{key}: {_fmt(remaining.pop(key))}")
                    replaced = True
            if not replaced:
                new_lines.append(line)

        # Insert any keys that were not already present, before the trailing
        # blank line that precedes the closing fence.
        for key, value in remaining.items():
            insert_at = len(new_lines)
            while insert_at > 0 and new_lines[insert_at - 1].strip() == "":
                insert_at -= 1
            new_lines.insert(insert_at, f"{key}: {_fmt(value)}")

        new_content = "---" + "\n".join(new_lines) + "\n---\n" + body
        try:
            self._write_skill_atomically(skill_md, new_content)
        except Exception:
            logger.debug("Failed to persist frontmatter telemetry for %s", skill_path, exc_info=True)

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

    def validate_skill_capabilities(self, skill_name: str, force_refresh: bool = False) -> ValidationResult:
        """Validate a skill's capability requirements.
        
        Args:
            skill_name: Name of the skill to validate
            force_refresh: If True, bypass cache and re-validate
            
        Returns:
            ValidationResult with capability status
            
        Raises:
            ValueError: If skill not found
        """
        skill = self.get_skill(skill_name)
        if skill is None:
            raise ValueError(f"Skill '{skill_name}' not found")
            
        # Check cache first
        if not force_refresh and skill_name in self._validation_cache:
            return self._validation_cache[skill_name]
            
        # Perform validation
        result = self._validator.validate_skill(skill.properties)
        self._validation_cache[skill_name] = result
        return result
    
    def get_available_skills_by_state(self, state: SkillState) -> List[LoadedSkill]:
        """Get skills filtered by their capability validation state.
        
        Args:
            state: Desired skill state
            
        Returns:
            List of skills in the specified state
        """
        matching = []
        for skill in self._skills.values():
            try:
                result = self.validate_skill_capabilities(skill.properties.name)
                if result.state == state:
                    matching.append(skill)
            except Exception as e:
                logger.warning(f"Failed to validate skill '{skill.properties.name}': {e}")
                continue
        return matching
    
    def get_skills_diagnostics(self) -> Dict[str, ValidationResult]:
        """Get capability diagnostics for all skills.
        
        Returns:
            Dict mapping skill names to their validation results
        """
        diagnostics = {}
        for skill_name in self.skill_names:
            try:
                diagnostics[skill_name] = self.validate_skill_capabilities(skill_name)
            except Exception as e:
                logger.error(f"Failed to validate skill '{skill_name}': {e}")
        return diagnostics
    
    def _get_default_enforcement_level(self) -> EnforcementLevel:
        """Get default enforcement level from environment."""
        import os
        level_str = os.getenv('SKILL_CAPABILITY_ENFORCEMENT', 'warn').lower()
        
        level_map = {
            'disabled': EnforcementLevel.DISABLED,
            'off': EnforcementLevel.DISABLED,
            'telemetry': EnforcementLevel.TELEMETRY,
            'log': EnforcementLevel.TELEMETRY,
            'warn': EnforcementLevel.WARN,
            'warning': EnforcementLevel.WARN,
            'strict': EnforcementLevel.STRICT,
            'hard': EnforcementLevel.STRICT,
            'fail': EnforcementLevel.STRICT,
        }
        
        return level_map.get(level_str, EnforcementLevel.WARN)

    def _get_default_write_approval(self) -> bool:
        """Resolve the default write-approval policy.

        Safe-by-default: skill mutations are staged for approval unless the
        ``SKILL_WRITE_APPROVAL`` environment variable explicitly disables it
        (e.g. ``0``/``false``/``off`` for trusted local contexts).
        """
        import os
        raw = os.getenv('SKILL_WRITE_APPROVAL')
        if raw is None:
            return True
        return raw.strip().lower() not in ('0', 'false', 'off', 'no', 'disabled')

    # ── Approval gate (SkillMutatorProtocol) ──────────────────────────

    def _should_propose(self, propose: Optional[bool]) -> bool:
        """Decide whether a mutation should be staged for approval."""
        if propose is None:
            return self._write_approval
        return bool(propose)

    def _skills_base_dir(self):
        """Return the base skills directory where mutations are written.

        Always targets the user-owned skills directory (honours
        ``PRAISONAI_HOME``). ``get_default_skill_dirs()`` is intentionally not
        used here because its first entry can be a project-scoped or
        admin-managed (e.g. ``/etc/praison/skills``) location that mutations
        must never write into.
        """
        from ..paths import get_skills_dir
        base = get_skills_dir()
        base.mkdir(parents=True, exist_ok=True)
        return base

    def _pending_store_path(self):
        """Return the path to the JSON-backed pending-mutation store."""
        return self._skills_base_dir() / ".pending_skills.json"

    def _audit_log_path(self):
        """Return the path to the append-only skill-mutation audit log."""
        return self._pending_store_path().parent / ".skill_audit.log"

    def _load_pending(self) -> Dict[str, dict]:
        """Load the pending-mutation store (id -> record)."""
        import json
        store = self._pending_store_path()
        if not store.exists():
            return {}
        try:
            with open(store, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read pending skills store: %s", e)
            return {}

    def _save_pending(self, pending: Dict[str, dict]) -> None:
        """Persist the pending-mutation store atomically."""
        import json
        self._write_skill_atomically(
            self._pending_store_path(), json.dumps(pending, indent=2)
        )

    def _audit(self, event: str, record: dict) -> None:
        """Append a single audit entry for a skill mutation decision."""
        import json
        import time
        try:
            entry = {
                "event": event,
                "timestamp": time.time(),
                "id": record.get("id"),
                "action": record.get("action"),
                "name": record.get("name"),
            }
            with open(self._audit_log_path(), 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry) + "\n")
        except OSError as e:
            logger.debug("Failed to write skill audit log: %s", e)

    def _stage_pending(self, action: str, name: str, **payload) -> dict:
        """Stage a skill mutation in the pending store instead of writing.

        Returns a dict with ``status='pending'`` and a short ``id`` for the
        human approval flow (``/skills approve <id>``).
        """
        import secrets
        import time

        # Validate the staged payload up front using the same checks as the
        # direct-write path, so invalid/oversized proposals never reach the
        # pending store or audit log.
        if action in ("create", "edit", "patch", "delete",
                      "write_file", "remove_file"):
            if not self._validate_skill_name(name):
                return {"success": False, "error": f"Invalid skill name: {name}"}
        if action in ("create", "edit") and len(payload.get("content") or "") > 100_000:
            return {"success": False, "error": "Skill content exceeds maximum size (100KB)"}
        if action == "write_file" and len(payload.get("file_content") or "") > 100_000:
            return {"success": False, "error": "File content exceeds maximum size (100KB)"}

        pending = self._load_pending()
        if len(pending) >= self._max_pending:
            return {
                "success": False,
                "error": (
                    f"Pending skill store is full ({self._max_pending} entries); "
                    "approve or reject existing proposals first."
                ),
            }
        request_id = f"skl-{secrets.token_hex(4)}"
        record = {
            "id": request_id,
            "action": action,
            "name": name,
            "status": "pending",
            "created_at": time.time(),
            "payload": {k: v for k, v in payload.items() if v is not None},
        }
        pending[request_id] = record
        self._save_pending(pending)
        self._audit("proposed", record)
        logger.info(
            "Skill mutation staged for approval: %s (action=%s, skill=%s)",
            request_id, action, name,
        )
        return {
            "success": True,
            "status": "pending",
            "id": request_id,
            "action": action,
            "skill": name,
        }

    def list_pending(self) -> List[dict]:
        """List all pending skill mutations awaiting approval.

        Returns:
            List of dicts with keys: id, action, name, status, created_at.
        """
        pending = self._load_pending()
        return [
            {
                "id": r.get("id"),
                "action": r.get("action"),
                "name": r.get("name"),
                "status": r.get("status", "pending"),
                "created_at": r.get("created_at"),
            }
            for r in pending.values()
        ]

    def _resolve_pending_id(self, identifier: str, pending: Dict[str, dict]):
        """Resolve a pending record by id, or by skill name as a fallback."""
        if identifier in pending:
            return identifier
        # Fall back to matching by skill name (most recent wins).
        matches = [
            r for r in pending.values() if r.get("name") == identifier
        ]
        if matches:
            matches.sort(key=lambda r: r.get("created_at", 0), reverse=True)
            return matches[0].get("id")
        return None

    def approve(self, identifier: str) -> dict:
        """Approve a pending skill mutation and apply it to disk.

        Args:
            identifier: The pending mutation id (preferred) or skill name.

        Returns:
            Dict with the result of applying the mutation.
        """
        pending = self._load_pending()
        request_id = self._resolve_pending_id(identifier, pending)
        if request_id is None:
            return {"success": False, "error": f"No pending mutation: {identifier}"}

        # Apply first; only remove + audit "approved" once the mutation
        # actually succeeds, so a failure neither loses the proposal nor
        # records a false approval.
        record = pending[request_id]
        result = self._apply_pending(record)
        result.setdefault("id", request_id)
        if result.get("success"):
            pending.pop(request_id, None)
            self._save_pending(pending)
            self._audit("approved", record)
        else:
            self._audit("approval_failed", record)
        return result

    def reject(self, identifier: str) -> dict:
        """Reject a pending skill mutation without applying it.

        Args:
            identifier: The pending mutation id (preferred) or skill name.

        Returns:
            Dict confirming the rejection.
        """
        pending = self._load_pending()
        request_id = self._resolve_pending_id(identifier, pending)
        if request_id is None:
            return {"success": False, "error": f"No pending mutation: {identifier}"}

        record = pending.pop(request_id)
        self._save_pending(pending)
        self._audit("rejected", record)
        return {
            "success": True,
            "status": "rejected",
            "id": request_id,
            "action": record.get("action"),
            "skill": record.get("name"),
        }

    def _apply_pending(self, record: dict) -> dict:
        """Apply an approved mutation directly (bypassing the approval gate)."""
        action = record.get("action")
        name = record.get("name")
        payload = record.get("payload", {})

        if action == "create":
            return self.create_skill(
                name, payload.get("content", ""),
                payload.get("category"),
                agent_created=payload.get("agent_created", True),
                propose=False,
            )
        if action == "edit":
            return self.edit_skill(name, payload.get("content", ""), propose=False)
        if action == "patch":
            return self.patch_skill(
                name, payload.get("old_string", ""),
                payload.get("new_string", ""),
                payload.get("file_path"),
                payload.get("replace_all", False),
                propose=False,
            )
        if action == "delete":
            return self.delete_skill(
                name, hard=payload.get("hard", False), propose=False,
            )
        if action == "write_file":
            return self.write_skill_file(
                name, payload.get("file_path", ""),
                payload.get("file_content", ""), propose=False,
            )
        if action == "remove_file":
            return self.remove_skill_file(
                name, payload.get("file_path", ""), propose=False,
            )
        return {"success": False, "error": f"Unknown action: {action}"}

    # ── SkillMutatorProtocol aliases ──────────────────────────────────

    def create(self, name: str, content: str, category: Optional[str] = None,
               propose: Optional[bool] = None) -> dict:
        """Protocol alias for :meth:`create_skill`."""
        return self.create_skill(name, content, category, propose=propose)

    def edit(self, name: str, content: str,
             propose: Optional[bool] = None) -> dict:
        """Protocol alias for :meth:`edit_skill`."""
        return self.edit_skill(name, content, propose=propose)

    def patch(self, name: str, old_string: str, new_string: str,
              file_path: Optional[str] = None, replace_all: bool = False,
              propose: Optional[bool] = None) -> dict:
        """Protocol alias for :meth:`patch_skill`."""
        return self.patch_skill(
            name, old_string, new_string, file_path, replace_all,
            propose=propose,
        )

    def delete(self, name: str, propose: Optional[bool] = None) -> dict:
        """Protocol alias for :meth:`delete_skill`."""
        return self.delete_skill(name, propose=propose)

    def write_file(self, name: str, file_path: str, file_content: str,
                   propose: Optional[bool] = None) -> dict:
        """Protocol alias for :meth:`write_skill_file`."""
        return self.write_skill_file(
            name, file_path, file_content, propose=propose,
        )

    def remove_file(self, name: str, file_path: str,
                    propose: Optional[bool] = None) -> dict:
        """Protocol alias for :meth:`remove_skill_file`."""
        return self.remove_skill_file(name, file_path, propose=propose)

    def clear(self) -> None:
        """Clear all loaded skills."""
        self._skills.clear()
        self._bundles.clear()
        self._validation_cache.clear()
        self._validator.clear_cache()
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
