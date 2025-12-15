"""
PlanStorage for persisting plans and todo lists.

Provides storage functionality similar to:
- Cursor .cursor/plans/
- Windsurf ~/.codeium/windsurf/brain/
- Codex ~/.codex/sessions/

Features:
- Save/load plans as markdown files
- Save/load todo lists as JSON
- Auto-discovery of existing plans
- Plan versioning
"""

import os
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any

from .plan import Plan
from .todo import TodoList

logger = logging.getLogger(__name__)


class PlanStorage:
    """
    Storage manager for plans and todo lists.
    
    Attributes:
        base_path: Base directory for storage
        plans_dir: Directory for plan files
        todos_dir: Directory for todo files
    """
    
    DEFAULT_BASE_PATH = ".praison"
    
    def __init__(self, base_path: Optional[str] = None):
        """
        Initialize PlanStorage.
        
        Args:
            base_path: Base directory for storage. Defaults to .praison/
        """
        self.base_path = base_path or self.DEFAULT_BASE_PATH
        self.plans_dir = os.path.join(self.base_path, "plans")
        self.todos_dir = os.path.join(self.base_path, "todos")
        
        # Create directories if they don't exist
        self._ensure_directories()
        
    def _ensure_directories(self) -> None:
        """Create storage directories if they don't exist."""
        os.makedirs(self.plans_dir, exist_ok=True)
        os.makedirs(self.todos_dir, exist_ok=True)
        
    def _get_plan_filename(self, plan: Plan) -> str:
        """
        Generate filename for a plan.
        
        Args:
            plan: Plan to generate filename for
            
        Returns:
            Filename string
        """
        date_str = plan.created_at.strftime("%Y-%m-%d") if plan.created_at else datetime.now().strftime("%Y-%m-%d")
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in plan.name[:30])
        return f"plan_{date_str}_{plan.id}_{safe_name}.md"
    
    def _get_plan_path(self, plan_id: str) -> Optional[str]:
        """
        Find the path for a plan by ID.
        
        Args:
            plan_id: ID of the plan to find
            
        Returns:
            Path to the plan file, or None if not found
        """
        for filename in os.listdir(self.plans_dir):
            if plan_id in filename and filename.endswith(".md"):
                return os.path.join(self.plans_dir, filename)
        return None
    
    def save_plan(self, plan: Plan, filename: Optional[str] = None) -> str:
        """
        Save a plan to storage.
        
        Args:
            plan: Plan to save
            filename: Optional custom filename
            
        Returns:
            Path to the saved file
        """
        if filename is None:
            filename = self._get_plan_filename(plan)
            
        path = os.path.join(self.plans_dir, filename)
        
        # Convert plan to markdown
        markdown = plan.to_markdown()
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(markdown)
            
        plan.file_path = path
        logger.debug(f"Saved plan to {path}")
        
        return path
    
    def load_plan(self, plan_id: str) -> Optional[Plan]:
        """
        Load a plan from storage.
        
        Args:
            plan_id: ID of the plan to load
            
        Returns:
            Plan instance, or None if not found
        """
        path = self._get_plan_path(plan_id)
        
        if path is None or not os.path.exists(path):
            logger.debug(f"Plan {plan_id} not found")
            return None
            
        with open(path, "r", encoding="utf-8") as f:
            markdown = f.read()
            
        plan = Plan.from_markdown(markdown)
        plan.file_path = path
        
        logger.debug(f"Loaded plan from {path}")
        return plan
    
    def load_plan_from_file(self, path: str) -> Optional[Plan]:
        """
        Load a plan from a specific file path.
        
        Args:
            path: Path to the plan file
            
        Returns:
            Plan instance, or None if file doesn't exist
        """
        if not os.path.exists(path):
            return None
            
        with open(path, "r", encoding="utf-8") as f:
            markdown = f.read()
            
        plan = Plan.from_markdown(markdown)
        plan.file_path = path
        
        return plan
    
    def list_plans(self) -> List[Dict[str, Any]]:
        """
        List all saved plans.
        
        Returns:
            List of plan metadata dictionaries
        """
        plans = []
        
        for filename in os.listdir(self.plans_dir):
            if filename.endswith(".md"):
                path = os.path.join(self.plans_dir, filename)
                
                # Try to load and get metadata
                try:
                    plan = self.load_plan_from_file(path)
                    if plan:
                        plans.append({
                            "id": plan.id,
                            "name": plan.name,
                            "status": plan.status,
                            "created_at": plan.created_at.isoformat() if plan.created_at else None,
                            "file_path": path
                        })
                except Exception as e:
                    logger.warning(f"Failed to load plan from {path}: {e}")
                    
        # Sort by creation date (newest first)
        plans.sort(key=lambda p: p.get("created_at", ""), reverse=True)
        
        return plans
    
    def delete_plan(self, plan_id: str) -> bool:
        """
        Delete a plan from storage.
        
        Args:
            plan_id: ID of the plan to delete
            
        Returns:
            True if deleted, False if not found
        """
        path = self._get_plan_path(plan_id)
        
        if path and os.path.exists(path):
            os.remove(path)
            logger.debug(f"Deleted plan {plan_id}")
            return True
            
        return False
    
    def save_todo(self, todo: TodoList, name: str = "current") -> str:
        """
        Save a todo list to storage.
        
        Args:
            todo: TodoList to save
            name: Name for the todo file (without extension)
            
        Returns:
            Path to the saved file
        """
        filename = f"{name}.json"
        path = os.path.join(self.todos_dir, filename)
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(todo.to_json())
            
        logger.debug(f"Saved todo list to {path}")
        return path
    
    def load_todo(self, name: str = "current") -> Optional[TodoList]:
        """
        Load a todo list from storage.
        
        Args:
            name: Name of the todo file (without extension)
            
        Returns:
            TodoList instance, or None if not found
        """
        filename = f"{name}.json"
        path = os.path.join(self.todos_dir, filename)
        
        if not os.path.exists(path):
            return None
            
        with open(path, "r", encoding="utf-8") as f:
            json_str = f.read()
            
        logger.debug(f"Loaded todo list from {path}")
        return TodoList.from_json(json_str)
    
    def list_todos(self) -> List[str]:
        """
        List all saved todo lists.
        
        Returns:
            List of todo list names
        """
        todos = []
        
        for filename in os.listdir(self.todos_dir):
            if filename.endswith(".json"):
                name = filename[:-5]  # Remove .json extension
                todos.append(name)
                
        return todos
    
    def delete_todo(self, name: str) -> bool:
        """
        Delete a todo list from storage.
        
        Args:
            name: Name of the todo file (without extension)
            
        Returns:
            True if deleted, False if not found
        """
        filename = f"{name}.json"
        path = os.path.join(self.todos_dir, filename)
        
        if os.path.exists(path):
            os.remove(path)
            logger.debug(f"Deleted todo list {name}")
            return True
            
        return False
    
    def get_latest_plan(self) -> Optional[Plan]:
        """
        Get the most recently created plan.
        
        Returns:
            Most recent Plan, or None if no plans exist
        """
        plans = self.list_plans()
        
        if not plans:
            return None
            
        return self.load_plan(plans[0]["id"])
    
    def cleanup_old_plans(self, keep_count: int = 10) -> int:
        """
        Remove old plans, keeping only the most recent ones.
        
        Args:
            keep_count: Number of plans to keep
            
        Returns:
            Number of plans deleted
        """
        plans = self.list_plans()
        
        if len(plans) <= keep_count:
            return 0
            
        deleted = 0
        for plan in plans[keep_count:]:
            if self.delete_plan(plan["id"]):
                deleted += 1
                
        return deleted
