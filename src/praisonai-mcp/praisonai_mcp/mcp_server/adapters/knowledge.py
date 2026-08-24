"""
Knowledge Adapter

Maps PraisonAI knowledge operations to MCP tools.

Rebound to the real ``praisonaiagents.knowledge.Knowledge`` API
(``add``/``search``/``get_all``/``get_corpus_stats``/``reset``). The previous
bindings (``query``/``list_sources``/``stats``/``clear`` and ``add(source_type=)``)
never existed on core and every call fell into the ``except`` branch returning
an ``"Error: …"`` string.
"""

import logging

from ..registry import register_tool

logger = logging.getLogger(__name__)


def register_knowledge_tools() -> None:
    """Register knowledge-related MCP tools."""

    @register_tool("praisonai.knowledge.add")
    def knowledge_add(
        source: str,
    ) -> str:
        """Add a knowledge source (file path, URL, or raw text)."""
        try:
            from praisonaiagents.knowledge import Knowledge

            knowledge = Knowledge()
            knowledge.add(source)
            return f"Knowledge added from {source}"
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
            results = knowledge.search(query)
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
            sources = knowledge.get_all()
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
            knowledge.reset()
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
            stats = knowledge.get_corpus_stats()
            return str(stats)
        except ImportError:
            return "Error: Knowledge module not available"
        except Exception as e:
            return f"Error: {e}"

    logger.info("Registered knowledge MCP tools")
