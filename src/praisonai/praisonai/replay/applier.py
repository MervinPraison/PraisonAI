"""
Plan Applier Module for PraisonAI.

Applies fixes from a JudgePlan to YAML files.

Features:
- Comment-preserving YAML edits (using ruamel.yaml if available)
- Backup before modification
- Validation after modification
- Dry-run mode for preview

Usage:
    from praisonai.replay import PlanApplier, JudgePlan
    
    plan = JudgePlan.load("judge_plan.yaml")
    applier = PlanApplier(plan)
    
    # Preview changes
    applier.preview()
    
    # Apply with backup
    applier.apply(backup=True)
"""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .plan import JudgePlan, ActionableFix


class PlanApplier:
    """
    Applies fixes from a JudgePlan to YAML files.
    
    Supports:
    - replace_instruction: Replace agent instructions
    - add_expected_output: Add/modify expected_output
    - modify_context_config: Adjust context settings
    - add_goal: Add goal field to workflow
    """
    
    def __init__(self, plan: JudgePlan):
        """
        Initialize the applier.
        
        Args:
            plan: The JudgePlan containing fixes to apply
        """
        self.plan = plan
        self._yaml_content: Optional[Dict[str, Any]] = None
        self._original_text: Optional[str] = None
        self._use_ruamel = False
        
        # Try to use ruamel.yaml for comment preservation
        try:
            from ruamel.yaml import YAML
            self._yaml = YAML()
            self._yaml.preserve_quotes = True
            self._use_ruamel = True
        except ImportError:
            self._yaml = None
    
    def load_yaml(self) -> Dict[str, Any]:
        """Load the YAML file."""
        yaml_path = Path(self.plan.yaml_file)
        if not yaml_path.exists():
            raise FileNotFoundError(f"YAML file not found: {self.plan.yaml_file}")
        
        self._original_text = yaml_path.read_text()
        
        if self._use_ruamel:
            from io import StringIO
            self._yaml_content = self._yaml.load(StringIO(self._original_text))
        else:
            import yaml
            self._yaml_content = yaml.safe_load(self._original_text)
        
        return self._yaml_content
    
    def backup(self) -> str:
        """Create a backup of the original file."""
        yaml_path = Path(self.plan.yaml_file)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = yaml_path.with_suffix(f".backup_{timestamp}.yaml")
        shutil.copy2(yaml_path, backup_path)
        return str(backup_path)
    
    def _navigate_path(self, path: str) -> Tuple[Any, str]:
        """
        Navigate to the parent of the target path.
        
        Returns:
            Tuple of (parent_object, final_key)
        """
        parts = path.split(".")
        current = self._yaml_content
        
        for part in parts[:-1]:
            if part.isdigit():
                current = current[int(part)]
            else:
                if part not in current:
                    current[part] = {}
                current = current[part]
        
        return current, parts[-1]
    
    def _apply_fix(self, fix: ActionableFix) -> bool:
        """
        Apply a single fix.
        
        Returns:
            True if fix was applied successfully
        """
        try:
            if fix.fix_type == "add_goal":
                # Add goal at root level
                self._yaml_content["goal"] = fix.suggested_value
                return True
            
            elif fix.fix_type == "append_instruction":
                # Append to existing instruction/description instead of replacing
                parent, key = self._navigate_path(fix.target_path)
                
                if key.isdigit():
                    current = parent[int(key)] or ""
                    parent[int(key)] = current + fix.suggested_value
                else:
                    current = parent.get(key, "") or ""
                    parent[key] = current + fix.suggested_value
                return True
            
            elif fix.fix_type in ["replace_instruction", "add_expected_output", "modify_context_config", "modify_tool_config"]:
                parent, key = self._navigate_path(fix.target_path)
                
                if key.isdigit():
                    parent[int(key)] = fix.suggested_value
                else:
                    parent[key] = fix.suggested_value
                return True
            
            elif fix.fix_type == "add_retry_config":
                parent, key = self._navigate_path(fix.target_path)
                parent[key] = fix.suggested_value
                return True
            
            else:
                # Generic field replacement
                parent, key = self._navigate_path(fix.target_path)
                if key.isdigit():
                    parent[int(key)] = fix.suggested_value
                else:
                    parent[key] = fix.suggested_value
                return True
                
        except Exception as e:
            print(f"  ⚠️  Failed to apply fix {fix.fix_id}: {e}")
            return False
    
    def preview(self) -> str:
        """
        Preview the changes without applying.
        
        Returns:
            String showing what would be changed
        """
        lines = [
            "=" * 60,
            "  PREVIEW: Changes to be applied",
            "=" * 60,
            f"  File: {self.plan.yaml_file}",
            f"  Fixes: {len(self.plan.fixes)}",
            "",
        ]
        
        for fix in self.plan.fixes:
            lines.append(f"  [{fix.priority.upper()}] {fix.fix_id}")
            lines.append(f"    Agent: {fix.agent_name}")
            lines.append(f"    Type: {fix.fix_type}")
            lines.append(f"    Path: {fix.target_path}")
            if fix.current_value:
                current_preview = str(fix.current_value)[:50] + "..." if len(str(fix.current_value)) > 50 else str(fix.current_value)
                lines.append(f"    Current: {current_preview}")
            suggested_preview = str(fix.suggested_value)[:50] + "..." if len(str(fix.suggested_value)) > 50 else str(fix.suggested_value)
            lines.append(f"    New: {suggested_preview}")
            lines.append("")
        
        lines.append("=" * 60)
        return "\n".join(lines)
    
    def apply(self, backup: bool = True, fix_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Apply fixes to the YAML file.
        
        Args:
            backup: Whether to create a backup before modifying
            fix_ids: Optional list of specific fix IDs to apply (None = all)
            
        Returns:
            Dict with results: {"applied": [...], "failed": [...], "backup_path": ...}
        """
        result = {
            "applied": [],
            "failed": [],
            "backup_path": None,
            "yaml_file": self.plan.yaml_file,
        }
        
        # Load YAML
        self.load_yaml()
        
        # Create backup
        if backup:
            result["backup_path"] = self.backup()
            print(f"  📦 Backup created: {result['backup_path']}")
        
        # Filter fixes if specific IDs provided
        fixes_to_apply = self.plan.fixes
        if fix_ids:
            fixes_to_apply = [f for f in self.plan.fixes if f.fix_id in fix_ids]
        
        # Apply each fix
        for fix in fixes_to_apply:
            print(f"  🔧 Applying {fix.fix_id}: {fix.fix_type} on {fix.agent_name}...")
            if self._apply_fix(fix):
                result["applied"].append(fix.fix_id)
                print("    ✅ Applied")
            else:
                result["failed"].append(fix.fix_id)
                print("    ❌ Failed")
        
        # Save modified YAML
        yaml_path = Path(self.plan.yaml_file)
        if self._use_ruamel:
            from io import StringIO
            stream = StringIO()
            self._yaml.dump(self._yaml_content, stream)
            yaml_path.write_text(stream.getvalue())
        else:
            import yaml
            yaml_path.write_text(yaml.dump(self._yaml_content, default_flow_style=False, sort_keys=False, allow_unicode=True))
        
        print(f"\n  ✅ Applied {len(result['applied'])}/{len(fixes_to_apply)} fixes")
        if result["failed"]:
            print(f"  ⚠️  Failed: {result['failed']}")
        
        return result
    
    def validate(self) -> bool:
        """
        Validate the modified YAML file.
        
        Returns:
            True if valid
        """
        try:
            yaml_path = Path(self.plan.yaml_file)
            content = yaml_path.read_text()
            
            import yaml
            yaml.safe_load(content)
            return True
        except Exception as e:
            print(f"  ❌ Validation failed: {e}")
            return False
    
    def rollback(self, backup_path: str) -> bool:
        """
        Rollback to a backup.
        
        Args:
            backup_path: Path to the backup file
            
        Returns:
            True if rollback successful
        """
        try:
            shutil.copy2(backup_path, self.plan.yaml_file)
            print(f"  ↩️  Rolled back to: {backup_path}")
            return True
        except Exception as e:
            print(f"  ❌ Rollback failed: {e}")
            return False
