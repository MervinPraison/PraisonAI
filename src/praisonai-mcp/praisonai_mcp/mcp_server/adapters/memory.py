"""
Memory Adapter

Maps PraisonAI memory operations to MCP tools.

Rebound to the real ``praisonaiagents.memory.Memory`` API
(``store_short_term``/``search``/``get_all_memories``/``reset_all``). The
previous bindings (``get_session``/``get_all``/``clear_session``/``clear_all``/
``list_sessions``/``add``) never existed on core and every call fell into the
``except`` branch returning an ``"Error: …"`` string.
"""

import logging
from typing import Optional

from ..registry import register_tool

logger = logging.getLogger(__name__)


def register_memory_tools() -> None:
    """Register memory-related MCP tools."""

    @register_tool("praisonai.memory.show")
    def memory_show(user_id: Optional[str] = None) -> str:
        """Show stored memories; SQLite displays up to 1000 per tier."""
        try:
            from praisonaiagents.memory import Memory

            memory = Memory()
            adapter = getattr(memory, "memory_adapter", None)
            if getattr(memory, "provider", None) == "sqlite" and adapter is not None:
                # Display retains its previous bounded window. Full enumeration
                # is a separate API and must not load the whole store here.
                data = []
                for tier in ("short", "long"):
                    for record in getattr(adapter, f"search_{tier}_term")("", limit=1000, user_id=user_id):
                        data.append({
                            **record, "memory_type": f"{tier}_term", "type": f"{tier}_term",
                        })
            else:
                data = memory.get_all_memories()
            if user_id:
                data = [
                    m for m in data
                    if str((m.get("metadata") or {}).get("user_id")) == str(user_id)
                ]
            return str(data)
        except ImportError:
            return "Error: Memory module not available"
        except Exception as e:
            return f"Error: {e}"

    @register_tool("praisonai.memory.add")
    def memory_add(
        content: str,
        metadata: Optional[str] = None,
    ) -> str:
        """Add content to short-term memory."""
        try:
            from praisonaiagents.memory import Memory
            import json

            memory = Memory()
            meta = json.loads(metadata) if metadata else {}
            memory.store_short_term(content, metadata=meta)
            return "Memory added successfully"
        except ImportError:
            return "Error: Memory module not available"
        except Exception as e:
            return f"Error: {e}"

    @register_tool("praisonai.memory.search")
    def memory_search(
        query: str,
        limit: int = 10,
        user_id: Optional[str] = None,
    ) -> str:
        """Search memory for relevant content."""
        try:
            from praisonaiagents.memory import Memory

            memory = Memory()
            results = memory.search(query, user_id=user_id, limit=limit)
            return str(results)
        except ImportError:
            return "Error: Memory module not available"
        except Exception as e:
            return f"Error: {e}"

    @register_tool("praisonai.memory.clear")
    def memory_clear() -> str:
        """Clear all memory contents (short-term and long-term)."""
        try:
            from praisonaiagents.memory import Memory

            memory = Memory()
            memory.reset_all()
            return "All memory cleared"
        except ImportError:
            return "Error: Memory module not available"
        except Exception as e:
            return f"Error: {e}"

    logger.info("Registered memory MCP tools")
