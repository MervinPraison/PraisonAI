"""
LLM-based guardrail implementation for PraisonAI Agents.

This module provides LLM-powered guardrails that can validate task outputs
using natural language descriptions, similar to CrewAI's implementation.
"""

import logging
from typing import Any, Tuple, Union, Optional
from pydantic import BaseModel
from ..output.models import TaskOutput


class LLMGuardrail:
    """An LLM-powered guardrail that validates task outputs using natural language."""
    
    def __init__(self, description: str, llm: Any = None):
        """Initialize the LLM guardrail.
        
        Args:
            description: Natural language description of what to validate
            llm: The LLM instance to use for validation (can be string or LLM instance)
        """
        self.description = description
        self.llm = self._initialize_llm(llm)
        self.logger = logging.getLogger(__name__)
    
    def _initialize_llm(self, llm: Any) -> Any:
        """Initialize the LLM instance from string identifier or existing instance.
        
        Args:
            llm: String identifier, LLM instance, or None
            
        Returns:
            LLM instance or None
        """
        # Local import to avoid circular dependencies
        def _get_llm_class():
            from ..llm.llm import LLM
            return LLM
            
        if llm is None:
            return None
            
        # If it's already an LLM instance, return as-is
        if hasattr(llm, 'chat') or hasattr(llm, 'get_response') or callable(llm):
            return llm
            
        # If it's a string, convert to LLM instance
        if isinstance(llm, str):
            try:
                # Handle string identifiers (both provider/model and simple names)
                return _get_llm_class()(model=llm)
            except Exception as e:
                self.logger.error(f"Failed to initialize LLM from string '{llm}': {str(e)}")
                return None
        
        # If it's a dict, pass parameters to LLM
        if isinstance(llm, dict) and "model" in llm:
            try:
                return _get_llm_class()(**llm)
            except Exception as e:
                self.logger.error(f"Failed to initialize LLM from dict: {str(e)}")
                return None
        
        # Unknown type
        self.logger.warning(f"Unknown LLM type: {type(llm)}, treating as-is")
        return llm
    
    def __call__(self, task_output: TaskOutput) -> Tuple[bool, Union[str, TaskOutput]]:
        """Validate the task output using the LLM.
        
        Args:
            task_output: The task output to validate
            
        Returns:
            Tuple of (success, result) where result is the output or error message
        """
        try:
            if not self.llm:
                self.logger.warning("No LLM provided for guardrail validation")
                return True, task_output
            
            # Create validation prompt
            validation_prompt = f"""
You are a quality assurance validator. Your task is to evaluate the following output against specific criteria.

Validation Criteria: {self.description}

Output to Validate:
{task_output.raw}

Please evaluate if this output meets the criteria. Respond with:
1. "PASS" if the output meets all criteria
2. "FAIL: [specific reason]" if the output does not meet criteria

Your response:"""

            # Get LLM response
            if hasattr(self.llm, 'chat'):
                # For Agent's LLM interface
                response = self.llm.chat(validation_prompt, temperature=0.1)
            elif hasattr(self.llm, 'get_response'):
                # For custom LLM instances
                response = self.llm.get_response(validation_prompt, temperature=0.1)
            elif callable(self.llm):
                # For simple callable LLMs
                response = self.llm(validation_prompt)
            else:
                self.logger.error(f"Unsupported LLM type: {type(self.llm)}")
                return True, task_output
            
            # Parse response
            response = str(response).strip()
            
            if response.upper().startswith("PASS"):
                return True, task_output
            elif response.upper().startswith("FAIL"):
                # Extract the reason
                reason = response[5:].strip(": ")
                return False, f"Guardrail validation failed: {reason}"
            else:
                # Unclear response, log and pass through
                self.logger.warning(f"Unclear guardrail response: {response}")
                return True, task_output
                
        except Exception as e:
            self.logger.error(f"Error in LLM guardrail validation: {str(e)}")
            # On error, pass through the original output
            return True, task_output