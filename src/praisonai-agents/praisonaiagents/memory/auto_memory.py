"""
Auto-Generated Memory System for PraisonAI Agents.

Provides automatic memory generation similar to Windsurf's Cascade,
where the AI automatically decides what context is worth remembering.

Features:
- Automatic extraction of important facts from conversations
- Entity recognition and storage
- Preference detection
- Lazy evaluation to avoid performance impact
- Configurable importance thresholds

This module is designed to be lightweight and only activates
when explicitly enabled to avoid impacting performance.
"""

import re
import logging
from typing import Any, Dict, List, Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .file_memory import FileMemory

logger = logging.getLogger(__name__)


class AutoMemoryExtractor:
    """
    Automatically extracts memorable content from conversations.
    
    Uses pattern matching for fast extraction without LLM calls,
    with optional LLM enhancement for better accuracy.
    
    Example:
        ```python
        extractor = AutoMemoryExtractor()
        
        # Extract from conversation
        memories = extractor.extract(
            "My name is John and I prefer Python for backend work."
        )
        # Returns: [
        #   {"type": "entity", "name": "John", "entity_type": "person"},
        #   {"type": "preference", "content": "prefers Python for backend work"}
        # ]
        ```
    """
    
    # Patterns for fast extraction (no LLM needed)
    PATTERNS = {
        # Name patterns
        "name": [
            r"(?:my name is|i'm|i am|call me)\s+([A-Z][a-z]+)",
            r"(?:name|Name):\s*([A-Z][a-z]+)",
        ],
        # Preference patterns
        "preference": [
            r"i (?:prefer|like|love|enjoy|use)\s+(.+?)(?:\.|$)",
            r"(?:my favorite|i always use)\s+(.+?)(?:\.|$)",
        ],
        # Role/job patterns
        "role": [
            r"i (?:am|work as|'m)\s+(?:a|an)\s+([a-z\s]+?)(?:\.|,|$)",
            r"(?:my job|my role|i do)\s+(?:is|as)?\s*(.+?)(?:\.|$)",
        ],
        # Location patterns
        "location": [
            r"i (?:live|work|am based|am located)\s+(?:in|at)\s+([A-Z][a-z\s]+)",
            r"(?:from|based in)\s+([A-Z][a-z\s,]+)",
        ],
        # Project/task patterns
        "project": [
            r"(?:working on|building|developing|creating)\s+(?:a|an|the)?\s*(.+?)(?:\.|$)",
            r"(?:my project|the project)\s+(?:is|called)?\s*(.+?)(?:\.|$)",
        ],
        # Technology preferences
        "technology": [
            r"(?:using|use|prefer)\s+(Python|JavaScript|TypeScript|Go|Rust|Java|C\+\+|Ruby|PHP)",
            r"(?:framework|library|tool)(?:s)?\s+(?:like|such as|including)\s+(.+?)(?:\.|$)",
        ],
    }
    
    # Importance scores by type
    IMPORTANCE_SCORES = {
        "name": 0.95,
        "preference": 0.7,
        "role": 0.85,
        "location": 0.6,
        "project": 0.75,
        "technology": 0.7,
    }
    
    def __init__(
        self,
        min_importance: float = 0.5,
        use_llm: bool = False,
        llm_func: Optional[Callable[[str], str]] = None,
        verbose: int = 0
    ):
        """
        Initialize AutoMemoryExtractor.
        
        Args:
            min_importance: Minimum importance score to extract (0.0-1.0)
            use_llm: Whether to use LLM for enhanced extraction
            llm_func: LLM function for extraction (if use_llm=True)
            verbose: Verbosity level
        """
        self.min_importance = min_importance
        self.use_llm = use_llm
        self.llm_func = llm_func
        self.verbose = verbose
        
        # Compile patterns for performance
        self._compiled_patterns = {}
        for category, patterns in self.PATTERNS.items():
            self._compiled_patterns[category] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]
    
    def extract(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract memorable content from text.
        
        Args:
            text: Text to extract from (conversation, message, etc.)
            
        Returns:
            List of extracted memories with type, content, and importance
        """
        memories = []
        
        # Fast pattern-based extraction
        for category, patterns in self._compiled_patterns.items():
            importance = self.IMPORTANCE_SCORES.get(category, 0.5)
            
            if importance < self.min_importance:
                continue
            
            for pattern in patterns:
                matches = pattern.findall(text)
                for match in matches:
                    if isinstance(match, tuple):
                        match = match[0]
                    
                    match = match.strip()
                    if len(match) < 2 or len(match) > 200:
                        continue
                    
                    memory = {
                        "type": category,
                        "content": match,
                        "importance": importance,
                        "source": "pattern"
                    }
                    
                    # Avoid duplicates
                    if not any(m["content"].lower() == match.lower() for m in memories):
                        memories.append(memory)
        
        # Optional LLM enhancement
        if self.use_llm and self.llm_func and len(text) > 50:
            llm_memories = self._extract_with_llm(text)
            for mem in llm_memories:
                if mem.get("importance", 0) >= self.min_importance:
                    if not any(m["content"].lower() == mem["content"].lower() for m in memories):
                        memories.append(mem)
        
        return memories
    
    def _extract_with_llm(self, text: str) -> List[Dict[str, Any]]:
        """Extract memories using LLM for better accuracy."""
        if not self.llm_func:
            return []
        
        prompt = f"""Extract important facts from this text that should be remembered.
Return a JSON array of objects with: type (name/preference/role/location/project/technology), content, importance (0.0-1.0).
Only extract clear, specific facts. Be concise.

Text: {text[:1500]}

JSON array (no markdown, just the array):"""

        try:
            response = self.llm_func(prompt)
            
            # Parse JSON from response
            import json
            # Find JSON array in response
            start = response.find("[")
            end = response.rfind("]") + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except Exception as e:
            if self.verbose:
                logger.warning(f"LLM extraction failed: {e}")
        
        return []
    
    def should_remember(self, text: str) -> bool:
        """
        Quick check if text likely contains memorable content.
        
        Useful for filtering before full extraction.
        
        Args:
            text: Text to check
            
        Returns:
            True if text likely contains memorable content
        """
        # Quick keyword check
        keywords = [
            "my name", "i am", "i'm", "i prefer", "i like", "i use",
            "i work", "i live", "working on", "building", "my project",
            "favorite", "always use"
        ]
        
        text_lower = text.lower()
        return any(kw in text_lower for kw in keywords)


class AutoMemory:
    """
    Wrapper that adds auto-generation capabilities to FileMemory.
    
    Intercepts interactions and automatically extracts/stores memories.
    Designed to be lightweight - only processes when enabled.
    
    Example:
        ```python
        from praisonaiagents.memory import FileMemory
        
        base_memory = FileMemory(user_id="user123")
        auto_memory = AutoMemory(base_memory, enabled=True)
        
        # Process conversation and auto-store memories
        auto_memory.process_interaction(
            user_message="My name is John and I prefer Python",
            assistant_response="Nice to meet you, John!"
        )
        ```
    """
    
    def __init__(
        self,
        memory: "FileMemory",
        enabled: bool = True,
        extractor: Optional[AutoMemoryExtractor] = None,
        min_importance: float = 0.6,
        verbose: int = 0
    ):
        """
        Initialize AutoMemory wrapper.
        
        Args:
            memory: Base FileMemory instance
            enabled: Whether auto-generation is enabled
            extractor: Custom extractor (or use default)
            min_importance: Minimum importance to auto-store
            verbose: Verbosity level
        """
        self.memory = memory
        self.enabled = enabled
        self.min_importance = min_importance
        self.verbose = verbose
        
        self.extractor = extractor or AutoMemoryExtractor(
            min_importance=min_importance,
            verbose=verbose
        )
        
        # Track what we've already processed to avoid duplicates
        self._processed_hashes: set = set()
    
    def process_interaction(
        self,
        user_message: str,
        assistant_response: Optional[str] = None,
        store: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Process an interaction and extract memories.
        
        Args:
            user_message: User's message
            assistant_response: Optional assistant response
            store: Whether to store extracted memories
            
        Returns:
            List of extracted memories
        """
        if not self.enabled:
            return []
        
        # Combine messages for extraction
        text = user_message
        if assistant_response:
            text += "\n" + assistant_response
        
        # Check if already processed
        import hashlib
        text_hash = hashlib.md5(text.encode()).hexdigest()[:16]
        if text_hash in self._processed_hashes:
            return []
        self._processed_hashes.add(text_hash)
        
        # Quick filter
        if not self.extractor.should_remember(text):
            return []
        
        # Extract memories
        memories = self.extractor.extract(text)
        
        if store and memories:
            self._store_memories(memories)
        
        return memories
    
    def _store_memories(self, memories: List[Dict[str, Any]]):
        """Store extracted memories in the base memory."""
        for mem in memories:
            mem_type = mem.get("type", "")
            content = mem.get("content", "")
            importance = mem.get("importance", 0.5)
            
            if not content:
                continue
            
            # Store based on type
            if mem_type == "name":
                # Store as entity
                self.memory.add_entity(
                    name=content,
                    entity_type="person",
                    attributes={"relationship": "user"}
                )
            elif mem_type in ("role", "location"):
                # Store as entity attribute
                self.memory.add_long_term(
                    f"User's {mem_type}: {content}",
                    importance=importance
                )
            else:
                # Store as long-term memory
                self.memory.add_long_term(content, importance=importance)
            
            if self.verbose:
                logger.info(f"Auto-stored memory: {mem_type} - {content[:50]}...")
    
    def enable(self):
        """Enable auto-generation."""
        self.enabled = True
    
    def disable(self):
        """Disable auto-generation."""
        self.enabled = False
    
    def set_llm(self, llm_func: Callable[[str], str]):
        """Set LLM function for enhanced extraction."""
        self.extractor.use_llm = True
        self.extractor.llm_func = llm_func


def create_auto_memory(
    memory: "FileMemory",
    enabled: bool = True,
    **kwargs
) -> AutoMemory:
    """
    Create an AutoMemory wrapper.
    
    Args:
        memory: Base FileMemory instance
        enabled: Whether auto-generation is enabled
        **kwargs: Additional configuration
        
    Returns:
        AutoMemory instance
    """
    return AutoMemory(memory, enabled=enabled, **kwargs)
