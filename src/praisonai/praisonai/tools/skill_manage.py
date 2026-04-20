"""
Skill management tool for agents to create, edit, and manage their own skills.

Provides the basic skill_manage tool that agents can use to persist knowledge
as skills. Implements SkillMutatorProtocol with safe-by-default behavior
(propose mode).
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

from praisonaiagents.skills import SkillMutatorProtocol
from praisonaiagents.tools import tool


class BasicSkillMutator(SkillMutatorProtocol):
    """
    Basic implementation of SkillMutatorProtocol.
    
    Writes to ~/.praisonai/skills/pending/ by default.
    Skills are promoted to ~/.praisonai/skills/ only after approval.
    """
    
    def __init__(self, skills_dir: Optional[str] = None):
        """Initialize the skill mutator.
        
        Args:
            skills_dir: Base skills directory (defaults to ~/.praisonai/skills)
        """
        if skills_dir is None:
            home = Path.home()
            skills_dir = home / ".praisonai" / "skills"
        
        self.skills_dir = Path(skills_dir)
        self.pending_dir = self.skills_dir / "pending"
        
        # Ensure directories exist
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.pending_dir.mkdir(parents=True, exist_ok=True)
    
    def create(self, name: str, content: str, category: Optional[str] = None,
               propose: bool = True) -> str:
        """Create a new skill."""
        if not self._is_valid_name(name):
            return f"❌ Invalid skill name '{name}'. Must be alphanumeric with hyphens/underscores."
        
        target_dir = self.pending_dir if propose else self.skills_dir
        skill_path = target_dir / name
        
        if skill_path.exists():
            return f"❌ Skill '{name}' already exists."
        
        try:
            skill_path.mkdir(parents=True, exist_ok=True)
            skill_md = skill_path / "SKILL.md"
            
            # Write skill content with minimal frontmatter
            frontmatter = f"""---
name: {name}
description: Auto-generated skill
version: 1.0.0
"""
            if category:
                frontmatter += f"category: {category}\n"
            frontmatter += "---\n\n"
            
            skill_md.write_text(frontmatter + content)
            
            # Log the creation
            self._log_action("create", name, propose)
            
            status = "pending approval" if propose else "created"
            return f"✅ Skill '{name}' {status} at {skill_path}"
            
        except Exception as e:
            return f"❌ Failed to create skill '{name}': {e}"
    
    def patch(self, name: str, old_string: str, new_string: str,
              file_path: Optional[str] = None, replace_all: bool = False,
              propose: bool = True) -> str:
        """Patch an existing skill using find-replace."""
        skill_path = self._find_skill(name)
        if not skill_path:
            return f"❌ Skill '{name}' not found."
        
        file_to_edit = skill_path / (file_path or "SKILL.md")
        if not file_to_edit.exists():
            return f"❌ File '{file_path or 'SKILL.md'}' not found in skill '{name}'."
        
        try:
            content = file_to_edit.read_text()
            
            if old_string not in content:
                return f"❌ String '{old_string[:50]}...' not found in {file_to_edit.name}."
            
            if replace_all:
                new_content = content.replace(old_string, new_string)
                occurrences = content.count(old_string)
            else:
                new_content = content.replace(old_string, new_string, 1)
                occurrences = 1
            
            if propose:
                # For propose mode, create a patch proposal
                patch_info = {
                    "action": "patch",
                    "skill": name,
                    "file": file_path or "SKILL.md",
                    "old_string": old_string,
                    "new_string": new_string,
                    "replace_all": replace_all,
                    "timestamp": datetime.now().isoformat()
                }
                self._save_proposal(name, "patch", patch_info)
                return f"✅ Patch for '{name}' staged for approval (affects {occurrences} occurrence(s))."
            else:
                file_to_edit.write_text(new_content)
                self._log_action("patch", name, False)
                return f"✅ Patched {occurrences} occurrence(s) in '{name}'."
                
        except Exception as e:
            return f"❌ Failed to patch skill '{name}': {e}"
    
    def edit(self, name: str, content: str, propose: bool = True) -> str:
        """Replace entire skill content."""
        if propose:
            return self.create(name + "_edit", content, propose=True)
        else:
            skill_path = self._find_skill(name)
            if not skill_path:
                return f"❌ Skill '{name}' not found."
            
            try:
                skill_md = skill_path / "SKILL.md"
                skill_md.write_text(content)
                self._log_action("edit", name, False)
                return f"✅ Skill '{name}' content updated."
            except Exception as e:
                return f"❌ Failed to edit skill '{name}': {e}"
    
    def delete(self, name: str, propose: bool = True) -> str:
        """Delete a skill entirely."""
        skill_path = self._find_skill(name)
        if not skill_path:
            return f"❌ Skill '{name}' not found."
        
        if propose:
            delete_info = {
                "action": "delete",
                "skill": name,
                "timestamp": datetime.now().isoformat()
            }
            self._save_proposal(name, "delete", delete_info)
            return f"✅ Deletion of '{name}' staged for approval."
        else:
            try:
                import shutil
                shutil.rmtree(skill_path)
                self._log_action("delete", name, False)
                return f"✅ Skill '{name}' deleted."
            except Exception as e:
                return f"❌ Failed to delete skill '{name}': {e}"
    
    def write_file(self, name: str, file_path: str, file_content: str,
                   propose: bool = True) -> str:
        """Write a file within a skill directory."""
        skill_path = self._find_skill(name)
        if not skill_path:
            return f"❌ Skill '{name}' not found."
        
        target_file = skill_path / file_path
        
        if propose:
            file_info = {
                "action": "write_file", 
                "skill": name,
                "file_path": file_path,
                "content": file_content,
                "timestamp": datetime.now().isoformat()
            }
            self._save_proposal(name, "write_file", file_info)
            return f"✅ File write for '{name}/{file_path}' staged for approval."
        else:
            try:
                target_file.parent.mkdir(parents=True, exist_ok=True)
                target_file.write_text(file_content)
                self._log_action("write_file", name, False)
                return f"✅ File '{file_path}' written to skill '{name}'."
            except Exception as e:
                return f"❌ Failed to write file to skill '{name}': {e}"
    
    def remove_file(self, name: str, file_path: str, propose: bool = True) -> str:
        """Remove a file from a skill directory."""
        skill_path = self._find_skill(name)
        if not skill_path:
            return f"❌ Skill '{name}' not found."
        
        target_file = skill_path / file_path
        if not target_file.exists():
            return f"❌ File '{file_path}' not found in skill '{name}'."
        
        if propose:
            remove_info = {
                "action": "remove_file",
                "skill": name, 
                "file_path": file_path,
                "timestamp": datetime.now().isoformat()
            }
            self._save_proposal(name, "remove_file", remove_info)
            return f"✅ File removal for '{name}/{file_path}' staged for approval."
        else:
            try:
                target_file.unlink()
                self._log_action("remove_file", name, False)
                return f"✅ File '{file_path}' removed from skill '{name}'."
            except Exception as e:
                return f"❌ Failed to remove file from skill '{name}': {e}"
    
    def list_pending(self) -> List[Dict]:
        """List all pending skill mutations awaiting approval."""
        pending = []
        
        # Check pending directory for proposals
        if self.pending_dir.exists():
            for skill_dir in self.pending_dir.iterdir():
                if skill_dir.is_dir():
                    proposal_file = skill_dir / ".proposal.json"
                    if proposal_file.exists():
                        try:
                            proposal = json.loads(proposal_file.read_text())
                            pending.append({
                                "name": skill_dir.name,
                                "action": proposal.get("action", "create"),
                                "status": "pending",
                                "created_at": proposal.get("timestamp", "unknown")
                            })
                        except Exception:
                            # Handle skills without proposal metadata
                            pending.append({
                                "name": skill_dir.name,
                                "action": "create",
                                "status": "pending",
                                "created_at": "unknown"
                            })
        
        return pending
    
    def approve(self, name: str) -> str:
        """Approve a pending skill mutation."""
        pending_path = self.pending_dir / name
        if not pending_path.exists():
            return f"❌ No pending proposal found for '{name}'."
        
        try:
            # Move from pending to active skills
            active_path = self.skills_dir / name
            if active_path.exists():
                import shutil
                shutil.rmtree(active_path)  # Remove existing version
            
            pending_path.rename(active_path)
            
            # Clean up proposal metadata
            proposal_file = active_path / ".proposal.json"
            if proposal_file.exists():
                proposal_file.unlink()
            
            self._log_action("approve", name, False)
            return f"✅ Skill '{name}' approved and activated."
            
        except Exception as e:
            return f"❌ Failed to approve skill '{name}': {e}"
    
    def reject(self, name: str) -> str:
        """Reject a pending skill mutation."""
        pending_path = self.pending_dir / name
        if not pending_path.exists():
            return f"❌ No pending proposal found for '{name}'."
        
        try:
            import shutil
            shutil.rmtree(pending_path)
            self._log_action("reject", name, False)
            return f"✅ Skill '{name}' rejected and removed."
        except Exception as e:
            return f"❌ Failed to reject skill '{name}': {e}"
    
    # Helper methods
    
    def _is_valid_name(self, name: str) -> bool:
        """Check if skill name is valid (alphanumeric, hyphens, underscores)."""
        if not name:
            return False
        return name.replace("-", "").replace("_", "").isalnum()
    
    def _find_skill(self, name: str) -> Optional[Path]:
        """Find skill in active or pending directories."""
        active_path = self.skills_dir / name
        if active_path.exists():
            return active_path
        
        pending_path = self.pending_dir / name
        if pending_path.exists():
            return pending_path
        
        return None
    
    def _save_proposal(self, name: str, action: str, info: Dict):
        """Save proposal metadata for later approval."""
        pending_path = self.pending_dir / name
        pending_path.mkdir(parents=True, exist_ok=True)
        
        proposal_file = pending_path / ".proposal.json"
        proposal_file.write_text(json.dumps(info, indent=2))
    
    def _log_action(self, action: str, name: str, proposed: bool):
        """Log skill mutation actions."""
        log_file = self.skills_dir / ".skill_log"
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "skill": name,
            "proposed": proposed
        }
        
        # Append to log
        try:
            if log_file.exists():
                existing_log = json.loads(log_file.read_text())
            else:
                existing_log = []
            
            existing_log.append(log_entry)
            log_file.write_text(json.dumps(existing_log, indent=2))
        except Exception:
            # Ignore logging failures
            pass


# Create default global mutator instance
_default_mutator = BasicSkillMutator()


@tool
def skill_manage(
    action: str,
    name: str,
    content: str = "",
    old_string: str = "",
    new_string: str = "",
    file_path: str = "",
    category: str = "",
    replace_all: bool = False
) -> str:
    """Manage agent skills - create, edit, and organize reusable knowledge.
    
    This tool allows agents to persist procedures and knowledge as skills
    that can be reused across sessions.
    
    Args:
        action: Action to perform (create, patch, edit, delete, write_file, remove_file, list, approve, reject)
        name: Skill name (required for most actions)
        content: Full skill content (for create/edit actions)
        old_string: String to find (for patch action)
        new_string: Replacement string (for patch action)
        file_path: File path within skill (for write_file/remove_file/patch)
        category: Skill category (for create action)
        replace_all: Replace all occurrences (for patch action)
    
    Returns:
        Status message describing the result
    
    Examples:
        # Create a new skill
        skill_manage("create", "python-debugging", "# Python Debugging\\n\\nStep 1: Check syntax...")
        
        # Patch an existing skill
        skill_manage("patch", "python-debugging", "Step 1", "Step 1: First,", replace_all=False)
        
        # List pending skills
        skill_manage("list", "")
        
        # Approve a pending skill
        skill_manage("approve", "python-debugging")
    """
    action = action.lower()
    
    if action == "create":
        return _default_mutator.create(name, content, category or None)
    
    elif action == "patch":
        return _default_mutator.patch(name, old_string, new_string, 
                                     file_path or None, replace_all)
    
    elif action == "edit":
        return _default_mutator.edit(name, content)
    
    elif action == "delete":
        return _default_mutator.delete(name)
    
    elif action == "write_file":
        return _default_mutator.write_file(name, file_path, content)
    
    elif action == "remove_file":
        return _default_mutator.remove_file(name, file_path)
    
    elif action in ("list", "list_pending"):
        pending = _default_mutator.list_pending()
        if not pending:
            return "📝 No pending skill proposals."
        
        result = "📝 Pending skill proposals:\\n"
        for p in pending:
            result += f"  • {p['name']} ({p['action']}) - {p['created_at']}\\n"
        result += f"\\nUse skill_manage('approve', '<name>') to activate a skill."
        return result
    
    elif action == "approve":
        return _default_mutator.approve(name)
    
    elif action == "reject":
        return _default_mutator.reject(name)
    
    else:
        return f"❌ Unknown action '{action}'. Available: create, patch, edit, delete, write_file, remove_file, list, approve, reject"