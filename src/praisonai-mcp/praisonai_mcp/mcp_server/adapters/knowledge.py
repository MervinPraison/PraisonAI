"""
Knowledge Adapter

Maps PraisonAI knowledge operations to MCP tools.
"""

import logging

from ..registry import register_tool

logger = logging.getLogger(__name__)


def register_knowledge_tools() -> None:
    """Register knowledge-related MCP tools."""
    
    @register_tool("praisonai.knowledge.add")
    def knowledge_add(
        source: str,
        source_type: str = "text",
    ) -> str:
        """Add a knowledge source (text, file, or URL)."""
        try:
            from praisonaiagents.knowledge import Knowledge
            
            knowledge = Knowledge()
            knowledge.add(source, source_type=source_type)
            return f"Knowledge added from {source_type}"
        except ImportError:
            return "Error: Knowledge module not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.knowledge.query")
    def knowledge_query(
        query: str,
        limit: int = 5,
    ) -> str:
        """Query the knowledge base."""
        try:
            from praisonaiagents.knowledge import Knowledge
            
            knowledge = Knowledge()
            results = knowledge.query(query, limit=limit)
            return str(results)
        except ImportError:
            return "Error: Knowledge module not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.knowledge.list")
    def knowledge_list() -> str:
        """List all knowledge sources."""
        try:
            from praisonaiagents.knowledge import Knowledge
            
            knowledge = Knowledge()
            sources = knowledge.list_sources()
            return str(sources)
        except ImportError:
            return "Error: Knowledge module not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.knowledge.clear")
    def knowledge_clear() -> str:
        """Clear all knowledge."""
        try:
            from praisonaiagents.knowledge import Knowledge
            
            knowledge = Knowledge()
            knowledge.clear()
            return "Knowledge cleared"
        except ImportError:
            return "Error: Knowledge module not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.knowledge.stats")
    def knowledge_stats() -> str:
        """Get knowledge base statistics."""
        try:
            from praisonaiagents.knowledge import Knowledge
            
            knowledge = Knowledge()
            stats = knowledge.stats()
            return str(stats)
        except ImportError:
            return "Error: Knowledge module not available"
        except Exception as e:
            return f"Error: {e}"
    
    logger.info("Registered knowledge MCP tools")
