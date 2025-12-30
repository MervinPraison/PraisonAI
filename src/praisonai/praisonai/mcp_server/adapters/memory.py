"""
Memory Adapter

Maps PraisonAI memory operations to MCP tools.
"""

import logging
from typing import Optional

from ..registry import register_tool

logger = logging.getLogger(__name__)


def register_memory_tools() -> None:
    """Register memory-related MCP tools."""
    
    @register_tool("praisonai.memory.show")
    def memory_show(session_id: Optional[str] = None) -> str:
        """Show memory contents for a session."""
        try:
            from praisonaiagents.memory import Memory
            
            memory = Memory()
            if session_id:
                data = memory.get_session(session_id)
            else:
                data = memory.get_all()
            return str(data)
        except ImportError:
            return "Error: Memory module not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.memory.add")
    def memory_add(
        content: str,
        session_id: Optional[str] = None,
        metadata: Optional[str] = None,
    ) -> str:
        """Add content to memory."""
        try:
            from praisonaiagents.memory import Memory
            import json
            
            memory = Memory()
            meta = json.loads(metadata) if metadata else {}
            memory.add(content, session_id=session_id, metadata=meta)
            return "Memory added successfully"
        except ImportError:
            return "Error: Memory module not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.memory.search")
    def memory_search(
        query: str,
        limit: int = 10,
    ) -> str:
        """Search memory for relevant content."""
        try:
            from praisonaiagents.memory import Memory
            
            memory = Memory()
            results = memory.search(query, limit=limit)
            return str(results)
        except ImportError:
            return "Error: Memory module not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.memory.clear")
    def memory_clear(session_id: Optional[str] = None) -> str:
        """Clear memory contents."""
        try:
            from praisonaiagents.memory import Memory
            
            memory = Memory()
            if session_id:
                memory.clear_session(session_id)
                return f"Session {session_id} cleared"
            else:
                memory.clear_all()
                return "All memory cleared"
        except ImportError:
            return "Error: Memory module not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.memory.sessions")
    def memory_sessions() -> str:
        """List all memory sessions."""
        try:
            from praisonaiagents.memory import Memory
            
            memory = Memory()
            sessions = memory.list_sessions()
            return str(sessions)
        except ImportError:
            return "Error: Memory module not available"
        except Exception as e:
            return f"Error: {e}"
    
    logger.info("Registered memory MCP tools")
