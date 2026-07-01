"""
Todo Handler for CLI.

Provides todo list management.
Usage: praisonai todo list
       praisonai todo add "New task"
       praisonai "Plan project" --todo
"""

import os
import json
from typing import Any, Dict, List
from .base import CommandHandler, FlagHandler


class TodoHandler(CommandHandler, FlagHandler):
    """
    Handler for todo command and --todo flag.
    
    Manages todo lists for task planning.
    
    Example:
        praisonai todo list
        praisonai todo add "Implement feature X"
        praisonai todo complete 1
        praisonai "Plan project" --todo
    """
    
    def __init__(self, verbose: bool = False, workspace: str = None):
        CommandHandler.__init__(self, verbose)
        self.workspace = workspace or os.path.join(os.path.expanduser("~"), ".praison")
        self.todo_file = os.path.join(self.workspace, "todos.json")
        os.makedirs(self.workspace, exist_ok=True)
        self._todos = None
    
    @property
    def feature_name(self) -> str:
        return "todo"
    
    @property
    def flag_name(self) -> str:
        return "todo"
    
    @property
    def flag_help(self) -> str:
        return "Generate todo list from task"
    
    def get_actions(self) -> List[str]:
        return ["list", "add", "complete", "delete", "clear", "help"]
    
    def get_help_text(self) -> str:
        return """
Todo Commands:
  praisonai todo list                    - List all todos
  praisonai todo add <task>              - Add a new todo
  praisonai todo complete <id>           - Mark todo as complete
  praisonai todo delete <id>             - Delete a todo
  praisonai todo clear                   - Clear all todos

Flag Usage:
  praisonai "Plan project" --todo        - Generate todos from task
"""
    
    def _load_todos(self) -> List[Dict[str, Any]]:
        """Load todos from file."""
        if self._todos is not None:
            return self._todos
        
        if os.path.exists(self.todo_file):
            try:
                with open(self.todo_file, 'r') as f:
                    self._todos = json.load(f)
            except Exception:
                self._todos = []
        else:
            self._todos = []
        
        return self._todos
    
    def _save_todos(self):
        """Save todos to file."""
        try:
            with open(self.todo_file, 'w') as f:
                json.dump(self._todos or [], f, indent=2)
        except Exception as e:
            self.log(f"Failed to save todos: {e}", "error")
    
    def action_list(self, args: List[str], **kwargs) -> List[Dict[str, Any]]:
        """
        List all todos.
        
        Returns:
            List of todo items
        """
        todos = self._load_todos()
        
        if not todos:
            self.print_status("📋 No todos found", "info")
            return []
        
        self.print_status("\n📋 Todo List:", "info")
        self.print_status("-" * 50, "info")
        
        for i, todo in enumerate(todos, 1):
            status = "✅" if todo.get('completed') else "⬜"
            task = todo.get('task', 'Unknown')
            priority = todo.get('priority', 'medium')
            
            priority_color = {
                'high': '🔴',
                'medium': '🟡',
                'low': '🟢'
            }.get(priority, '⚪')
            
            self.print_status(f"  {i}. {status} {priority_color} {task}", "info")
        
        self.print_status("-" * 50, "info")
        completed = sum(1 for t in todos if t.get('completed'))
        self.print_status(f"  {completed}/{len(todos)} completed", "info")
        
        return todos
    
    def action_add(self, args: List[str], **kwargs) -> Dict[str, Any]:
        """
        Add a new todo.
        
        Args:
            args: List containing task description
            
        Returns:
            Created todo item
        """
        if not args:
            self.print_status("Usage: praisonai todo add <task>", "error")
            return {}
        
        task = ' '.join(args)
        priority = kwargs.get('priority', 'medium')
        
        todos = self._load_todos()
        
        todo = {
            'id': len(todos) + 1,
            'task': task,
            'completed': False,
            'priority': priority,
            'created_at': self._get_timestamp()
        }
        
        todos.append(todo)
        self._todos = todos
        self._save_todos()
        
        self.print_status(f"✅ Added: {task}", "success")
        return todo
    
    def action_complete(self, args: List[str], **kwargs) -> bool:
        """
        Mark a todo as complete.
        
        Args:
            args: List containing todo ID
            
        Returns:
            True if successful
        """
        if not args:
            self.print_status("Usage: praisonai todo complete <id>", "error")
            return False
        
        try:
            todo_id = int(args[0])
        except ValueError:
            self.print_status("Invalid todo ID", "error")
            return False
        
        todos = self._load_todos()
        
        if todo_id < 1 or todo_id > len(todos):
            self.print_status(f"Todo {todo_id} not found", "error")
            return False
        
        todos[todo_id - 1]['completed'] = True
        todos[todo_id - 1]['completed_at'] = self._get_timestamp()
        self._todos = todos
        self._save_todos()
        
        self.print_status(f"✅ Completed: {todos[todo_id - 1]['task']}", "success")
        return True
    
    def action_delete(self, args: List[str], **kwargs) -> bool:
        """
        Delete a todo.
        
        Args:
            args: List containing todo ID
            
        Returns:
            True if successful
        """
        if not args:
            self.print_status("Usage: praisonai todo delete <id>", "error")
            return False
        
        try:
            todo_id = int(args[0])
        except ValueError:
            self.print_status("Invalid todo ID", "error")
            return False
        
        todos = self._load_todos()
        
        if todo_id < 1 or todo_id > len(todos):
            self.print_status(f"Todo {todo_id} not found", "error")
            return False
        
        deleted = todos.pop(todo_id - 1)
        self._todos = todos
        self._save_todos()
        
        self.print_status(f"🗑️ Deleted: {deleted['task']}", "success")
        return True
    
    def action_clear(self, args: List[str], **kwargs) -> bool:
        """
        Clear all todos.
        
        Returns:
            True if successful
        """
        self._todos = []
        self._save_todos()
        self.print_status("🗑️ All todos cleared", "success")
        return True
    
    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime
        return datetime.now().isoformat()
    
    def apply_to_agent_config(self, config: Dict[str, Any], flag_value: Any) -> Dict[str, Any]:
        """
        Apply todo configuration.
        
        Args:
            config: Agent configuration dictionary
            flag_value: Boolean indicating todo generation
            
        Returns:
            Modified configuration
        """
        if flag_value:
            config['generate_todos'] = True
        return config
    
    def generate_todos_from_response(self, response: str) -> List[Dict[str, Any]]:
        """
        Extract todos from agent response.
        
        Args:
            response: Agent response text
            
        Returns:
            List of extracted todos
        """
        # Simple extraction - look for numbered lists or bullet points
        import re
        
        todos = []
        lines = response.split('\n')
        
        for line in lines:
            line = line.strip()
            # Match numbered lists (1. Task, 1) Task)
            match = re.match(r'^[\d]+[\.\)]\s*(.+)$', line)
            if match:
                task = match.group(1).strip()
                if task and len(task) > 3:
                    todos.append({
                        'task': task,
                        'completed': False,
                        'priority': 'medium'
                    })
            # Match bullet points (- Task, * Task, • Task)
            elif line.startswith(('-', '*', '•', '→')):
                task = line[1:].strip()
                if task and len(task) > 3:
                    todos.append({
                        'task': task,
                        'completed': False,
                        'priority': 'medium'
                    })
        
        return todos
    
    def post_process_result(self, result: Any, flag_value: Any) -> Any:
        """
        Post-process result to extract todos.
        
        Args:
            result: Agent output
            flag_value: Boolean indicating todo generation
            
        Returns:
            Original result (todos are saved)
        """
        if not flag_value:
            return result
        
        extracted = self.generate_todos_from_response(str(result))
        
        if extracted:
            todos = self._load_todos()
            for todo in extracted:
                todo['id'] = len(todos) + 1
                todo['created_at'] = self._get_timestamp()
                todos.append(todo)
            
            self._todos = todos
            self._save_todos()
            
            self.print_status(f"\n📋 Generated {len(extracted)} todos:", "success")
            for todo in extracted:
                self.print_status(f"  • {todo['task']}", "info")
        
        return result
    
    def execute(self, action: str = None, action_args: List[str] = None, **kwargs) -> Any:
        """Execute todo command action."""
        if action is None:
            action = "list"
        if action_args is None:
            action_args = []
        return CommandHandler.execute(self, action, action_args, **kwargs)
