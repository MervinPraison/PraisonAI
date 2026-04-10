"""
LLM-based guardrail implementation for PraisonAI Agents.

This module provides LLM-powered guardrails that can validate task outputs
using natural language descriptions, similar to CrewAI's implementation.
"""

import logging
from praisonaiagents._logging import get_logger
from typing import Any, Tuple, Union, Optional, Dict
from pydantic import BaseModel
from ..output.models import TaskOutput
from .protocols import GuardrailProtocol

class LLMGuardrail:
    """
    An LLM-powered guardrail that validates task outputs using natural language.
    
    Implements GuardrailProtocol to provide input, output, and tool call validation
    using LLM reasoning. Defaults to fail-closed behavior for production safety.
    """
    
    def __init__(self, description: str, llm: Any = None):
        """Initialize the LLM guardrail.
        
        Args:
            description: Natural language description of what to validate
            llm: The LLM instance to use for validation (can be string or LLM instance)
        """
        self.description = description
        self.llm = self._initialize_llm(llm)
        self.logger = get_logger(__name__)
    
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
    
    def __call__(self, task_output) -> Tuple[bool, Union[str, "TaskOutput"]]:
        """Validate the task output using the LLM.
        
        Args:
            task_output: The task output to validate (TaskOutput or plain str)
            
        Returns:
            Tuple of (success, result) where result is the output or error message
        """
        try:
            # Accept plain str for convenience (e.g. chat-input screening)
            if isinstance(task_output, str):
                raw_text = task_output
            else:
                raw_text = task_output.raw

            if not self.llm:
                self.logger.warning("No LLM provided for guardrail validation")
                return True, task_output
            
            # Create validation prompt
            validation_prompt = f"""
You are a quality assurance validator. Your task is to evaluate the following output against specific criteria.

Validation Criteria: {self.description}

Output to Validate:
{raw_text}

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
            # Fail-closed: On error, block the output for safety
            return False, f"Guardrail validation error: {str(e)}"
    
    # GuardrailProtocol implementation methods
    
    def validate_input(self, content: str, **kwargs) -> Tuple[bool, str]:
        """
        Validate input content using LLM reasoning.
        
        Args:
            content: Input text to validate
            **kwargs: Additional context
            
        Returns:
            Tuple of (is_valid: bool, processed_content: str)
        """
        # Adapt the description for input validation
        input_description = f"Validate this input: {self.description}"
        return self._llm_validate(content, input_description)
    
    def validate_output(self, content: str, **kwargs) -> Tuple[bool, str]:
        """
        Validate output content using LLM reasoning.
        
        This is the main validation method, reusing existing logic.
        """
        return self._llm_validate(content, self.description)
    
    def validate_tool_call(self, tool_name: str, arguments: Dict[str, Any], **kwargs) -> Tuple[bool, Dict[str, Any]]:
        """
        Validate tool call arguments using LLM reasoning.
        
        Args:
            tool_name: Name of the tool being called
            arguments: Tool arguments to validate
            **kwargs: Additional context
            
        Returns:
            Tuple of (is_valid: bool, processed_arguments: Dict[str, Any])
        """
        # Convert tool call to text for LLM validation
        tool_text = f"Tool: {tool_name}, Arguments: {arguments}"
        tool_description = f"Validate this tool call: {self.description}"
        
        is_valid, result = self._llm_validate(tool_text, tool_description)
        return is_valid, arguments  # Return original arguments (LLM doesn't modify them)
    
    def _llm_validate(self, content: str, description: str) -> Tuple[bool, str]:
        """
        Internal method to perform LLM validation with custom description.
        
        Args:
            content: Content to validate
            description: Validation description/prompt
            
        Returns:
            Tuple of (is_valid: bool, response: str)
        """
        try:
            if self.llm is None:
                self.logger.warning("No LLM configured for guardrail validation")
                return False, "No LLM available for validation"
            
            # Create validation prompt
            prompt = f"""
You are a content validator. Your task is to validate content based on the following criteria:

{description}

Content to validate:
{content}

Please respond with either:
- "PASS" if the content meets the criteria
- "FAIL: [reason]" if the content does not meet the criteria

Your response:"""

            # Get LLM response
            if hasattr(self.llm, 'complete'):
                response = self.llm.complete(prompt)
            elif hasattr(self.llm, 'invoke'):
                response = self.llm.invoke(prompt)
            elif hasattr(self.llm, '__call__'):
                response = self.llm(prompt)
            else:
                return False, "Invalid LLM instance"
            
            # Extract text from response
            if hasattr(response, 'content'):
                response_text = response.content
            elif hasattr(response, 'text'):
                response_text = response.text  
            elif isinstance(response, str):
                response_text = response
            else:
                response_text = str(response)
            
            response_text = response_text.strip()
            
            # Parse response
            if response_text.upper().startswith("PASS"):
                return True, content
            elif response_text.upper().startswith("FAIL"):
                reason = response_text[5:].strip(": ")
                return False, f"Validation failed: {reason}"
            else:
                self.logger.warning(f"Unclear guardrail response: {response_text}")
                # Fail-closed on unclear response for safety
                return False, f"Unclear validation response: {response_text}"
                
        except Exception as e:
            self.logger.error(f"Error in LLM validation: {str(e)}")
            return False, f"Validation error: {str(e)}"