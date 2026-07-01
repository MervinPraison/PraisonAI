"""
Auto Memory Handler for CLI.

Provides automatic memory extraction and storage.
Usage: praisonai "Learn about user preferences" --auto-memory
"""

from typing import Any, Dict, Tuple
from .base import FlagHandler


class AutoMemoryHandler(FlagHandler):
    """
    Handler for --auto-memory flag.
    
    Automatically extracts and stores important information from conversations.
    
    Example:
        praisonai "Learn about user preferences" --auto-memory
        praisonai "Remember this context" --auto-memory --user-id myuser
    """
    
    @property
    def feature_name(self) -> str:
        return "auto_memory"
    
    @property
    def flag_name(self) -> str:
        return "auto-memory"
    
    @property
    def flag_help(self) -> str:
        return "Enable automatic memory extraction and storage"
    
    def check_dependencies(self) -> Tuple[bool, str]:
        """Check if AutoMemory is available."""
        try:
            import importlib.util
            if importlib.util.find_spec("praisonaiagents") is not None:
                return True, ""
            return False, "praisonaiagents not installed"
        except ImportError:
            return False, "praisonaiagents not installed. Install with: pip install praisonaiagents"
    
    def _get_auto_memory(self, user_id: str = None):
        """Get AutoMemory instance lazily."""
        try:
            from praisonaiagents.memory import AutoMemory, FileMemory
            # AutoMemory requires a FileMemory instance
            memory = FileMemory(user_id=user_id or "default")
            return AutoMemory(memory=memory)
        except ImportError:
            self.print_status(
                "AutoMemory requires praisonaiagents. Install with: pip install praisonaiagents",
                "error"
            )
            return None
    
    def apply_to_agent_config(self, config: Dict[str, Any], flag_value: Any) -> Dict[str, Any]:
        """
        Apply auto memory configuration.
        
        Args:
            config: Agent configuration dictionary
            flag_value: Boolean or dict with user_id
            
        Returns:
            Modified configuration
        """
        if flag_value:
            config['auto_memory'] = True
            if isinstance(flag_value, dict):
                config['auto_memory_user_id'] = flag_value.get('user_id', 'default')
        return config
    
    def extract_memories(self, text: str, user_id: str = None, user_message: str = None) -> list:
        """
        Extract and store memories from text.
        
        Args:
            text: Assistant response text to extract memories from
            user_id: User ID for memory isolation
            user_message: Original user message (for context)
            
        Returns:
            List of extracted memories
        """
        auto_memory = self._get_auto_memory(user_id)
        if not auto_memory:
            return []
        
        try:
            # Use process_interaction which extracts AND stores memories
            memories = auto_memory.process_interaction(
                user_message=user_message or text,
                assistant_response=text if user_message else None,
                store=True  # Store the memories
            )
            if memories:
                self.print_status(f"🧠 Extracted and stored {len(memories)} memories", "success")
            return memories
        except Exception as e:
            self.log(f"Memory extraction failed: {e}", "error")
        
        return []
    
    def store_memory(self, content: str, user_id: str = None, importance: float = 0.5) -> bool:
        """
        Store a memory.
        
        Args:
            content: Memory content
            user_id: User ID for memory isolation
            importance: Importance score (0-1)
            
        Returns:
            True if successful
        """
        auto_memory = self._get_auto_memory(user_id)
        if not auto_memory:
            return False
        
        try:
            if hasattr(auto_memory, 'store'):
                auto_memory.store(content, importance=importance)
            elif hasattr(auto_memory, 'add'):
                auto_memory.add(content, importance=importance)
            
            self.print_status("✅ Memory stored", "success")
            return True
        except Exception as e:
            self.log(f"Memory storage failed: {e}", "error")
            return False
    
    def post_process_result(self, result: Any, flag_value: Any, user_message: str = None) -> Any:
        """
        Post-process result to extract and store memories.
        
        Args:
            result: Agent output
            flag_value: Boolean or dict with configuration
            user_message: Original user message for context
            
        Returns:
            Original result (memories are stored)
        """
        if not flag_value:
            return result
        
        user_id = None
        if isinstance(flag_value, dict):
            user_id = flag_value.get('user_id')
            user_message = flag_value.get('user_message', user_message)
        
        # Extract and store memories from result
        text = str(result)
        memories = self.extract_memories(text, user_id, user_message=user_message)
        
        if memories:
            self.print_status("\n🧠 Auto-extracted Memories:", "info")
            for mem in memories:
                mem_type = mem.get('type', 'unknown')
                content = mem.get('content', str(mem))[:50]
                self.print_status(f"  • {mem_type}: {content}...", "info")
        
        return result
    
    def execute(self, text: str = None, user_id: str = None, **kwargs) -> Dict[str, Any]:
        """
        Execute auto memory extraction.
        
        Args:
            text: Text to process
            user_id: User ID for memory isolation
            
        Returns:
            Dictionary of extracted memories
        """
        if not text:
            return {}
        
        return self.extract_memories(text, user_id)
