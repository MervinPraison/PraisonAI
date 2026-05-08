"""
Factory functions for creating store instances.

Provides lazy loading of backend implementations to avoid importing
unused dependencies. Uses registry pattern for extensibility.
"""

import logging
from typing import Any, Dict, Optional

from .config import PersistenceConfig
from .registry import CONVERSATION_STORES, KNOWLEDGE_STORES, STATE_STORES

logger = logging.getLogger(__name__)


def create_conversation_store(
    backend: str,
    url: Optional[str] = None,
    **options: Any
):
    """
    Create a ConversationStore instance using the registry pattern.
    
    Args:
        backend: Backend type (postgres, mysql, sqlite, etc.) 
        url: Connection URL
        **options: Backend-specific options
    
    Returns:
        ConversationStore instance
    
    Example:
        store = create_conversation_store(
            "postgres",
            url="postgresql://localhost:5432/praisonai"
        )
    """
    return CONVERSATION_STORES.create(backend, url=url, **options)


def create_knowledge_store(
    backend: str,
    url: Optional[str] = None,
    **options: Any
):
    """
    Create a KnowledgeStore instance using the registry pattern.
    
    Args:
        backend: Backend type (qdrant, pinecone, chroma, etc.)
        url: Connection URL
        **options: Backend-specific options
    
    Returns:
        KnowledgeStore instance
    
    Example:
        store = create_knowledge_store(
            "qdrant",
            url="http://localhost:6333"
        )
    """
    return KNOWLEDGE_STORES.create(backend, url=url, **options)


def create_state_store(
    backend: str,
    url: Optional[str] = None,
    **options: Any
):
    """
    Create a StateStore instance using the registry pattern.
    
    Args:
        backend: Backend type (redis, dynamodb, firestore, etc.)
        url: Connection URL
        **options: Backend-specific options
    
    Returns:
        StateStore instance
    
    Example:
        store = create_state_store(
            "redis",
            url="redis://localhost:6379"
        )
    """
    return STATE_STORES.create(backend, url=url, **options)


def create_stores_from_config(config: PersistenceConfig) -> Dict[str, Any]:
    """
    Create all configured stores from a PersistenceConfig.
    
    Returns:
        Dict with keys: conversation, knowledge, state (values may be None)
    """
    stores = {
        "conversation": None,
        "knowledge": None,
        "state": None,
    }
    
    if config.conversation_store:
        stores["conversation"] = create_conversation_store(
            config.conversation_store,
            url=config.conversation_url,
            **config.conversation_options
        )
    
    if config.knowledge_store:
        stores["knowledge"] = create_knowledge_store(
            config.knowledge_store,
            url=config.knowledge_url,
            **config.knowledge_options
        )
    
    if config.state_store:
        stores["state"] = create_state_store(
            config.state_store,
            url=config.state_url,
            **config.state_options
        )
    
    return stores
