"""
LLM-based guardrail implementation for PraisonAI Agents.

This module provides LLM-powered guardrails that can validate task outputs
using natural language descriptions, similar to CrewAI's implementation.
"""

import logging
from typing import Any, Tuple, Union, Optional
from pydantic import BaseModel
from ..main import TaskOutput


class LLMGuardrail:
    """An LLM-powered guardrail that validates task outputs using natural language."""
    
    def __init__(self, description: str, llm: Any = None):
        """Initialize the LLM guardrail.
        
        Args:
            description: Natural language description of what to validate
            llm: The LLM instance to use for validation
        """
        self.description = description
        self.llm = llm
        self.logger = logging.getLogger(__name__)
    
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