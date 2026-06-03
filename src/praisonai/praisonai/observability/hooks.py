"""
Observability hooks for PraisonAI.

Centralizes observability initialization (AgentOps, etc.) so it can be 
used consistently across all entry points without duplicating logic.
"""

import os
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def init_observability(framework_tag: str, *, tags: Optional[List[str]] = None) -> None:
    """
    Initialize observability providers (AgentOps, etc.) if available.
    
    Args:
        framework_tag: Primary framework tag (e.g., "crewai", "autogen_v4")
        tags: Additional tags to include
    """
    # Try to initialize AgentOps if available
    _init_agentops(framework_tag, tags or [])
    
    # Future: Add other observability providers here
    # _init_langfuse(framework_tag, tags)
    # _init_wandb(framework_tag, tags)


def _init_agentops(framework_tag: str, additional_tags: List[str]) -> None:
    """Initialize AgentOps if available."""
    try:
        import agentops
        agentops_api_key = os.getenv("AGENTOPS_API_KEY")
        if agentops_api_key:
            all_tags = [framework_tag] + additional_tags
            agentops.init(agentops_api_key, default_tags=all_tags)
            logger.debug("Initialized AgentOps with tags: %s", all_tags)
    except ImportError:
        logger.debug("AgentOps not available, skipping initialization")
    except Exception as e:
        logger.warning("Failed to initialize AgentOps: %s", e)


# Constants for checking availability
try:
    import agentops
    AGENTOPS_AVAILABLE = True
except ImportError:
    AGENTOPS_AVAILABLE = False