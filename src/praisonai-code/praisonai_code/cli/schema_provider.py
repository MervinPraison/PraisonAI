"""
Schema provider selection for PraisonAI unified configuration.

Selects the appropriate schema provider based on available dependencies.
"""

try:
    from pydantic import BaseModel
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False

if PYDANTIC_AVAILABLE:
    # Use full Pydantic implementation
    from .unified_schema import RAGSchemaProvider
    rag_schema_provider = RAGSchemaProvider()
else:
    # Use basic fallback implementation  
    from .fallback_schema import basic_rag_schema_provider
    rag_schema_provider = basic_rag_schema_provider

# Export the selected provider
__all__ = ['rag_schema_provider']