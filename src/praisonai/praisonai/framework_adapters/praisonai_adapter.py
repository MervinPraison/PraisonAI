"""
PraisonAI agents framework adapter.

Provides lazy-loaded integration with the PraisonAI agents framework.
"""

import logging
from typing import Dict, List, Any
from .base import BaseFrameworkAdapter

logger = logging.getLogger(__name__)


class PraisonAIAdapter(BaseFrameworkAdapter):
    """Adapter for PraisonAI agents framework."""
    
    name = "praisonai"
    
    def is_available(self) -> bool:
        """Check if PraisonAI agents is available for import."""
        try:
            from praisonaiagents import Agent, Task, AgentTeam  # noqa: F401
            return True
        except ImportError:
            return False
    
    def run(self, config: Dict[str, Any], llm_config: List[Dict], topic: str) -> str:
        """
        Run PraisonAI agents with given configuration.
        
        Args:
            config: PraisonAI configuration with agents and tasks
            llm_config: LLM configuration list
            topic: Topic for the tasks
            
        Returns:
            Execution result as string
        """
        if not self.is_available():
            raise ImportError("PraisonAI agents is not available. Install with: pip install praisonaiagents")
            
        logger.info("Starting PraisonAI execution...")
        # For now, return a proper error message instead of delegating  
        # TODO: Implement full PraisonAI adapter logic
        logger.warning("PraisonAI adapter is not yet fully implemented")
        return "### PraisonAI Output ###\nPraisonAI adapter is not yet fully implemented. Please use 'crewai' framework for similar functionality."
    
    def _format_template(self, template: str, **kwargs) -> str:
        """Safely format template string with given kwargs."""
        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Template formatting failed for key {e}, returning original template")
            return template
        except Exception as e:
            logger.warning(f"Template formatting error: {e}, returning original template")
            return template