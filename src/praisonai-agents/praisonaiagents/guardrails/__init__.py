"""
Guardrails module for PraisonAI Agents.

This module provides validation and safety mechanisms for task outputs,
including both function-based and LLM-based guardrails.
"""

from .guardrail_result import GuardrailResult
from .llm_guardrail import LLMGuardrail
from .protocols import (
    GuardrailProtocol,
    StructuralGuardrailProtocol,
    PolicyGuardrailProtocol,
    is_guardrail_object,
)
from .chain import GuardrailChain
from .retry import GuardrailRetry
from .tool_guardrails import (
    ToolInputGuardrail,
    ToolOutputGuardrail,
    ToolGuardrailChain,
    build_tool_guardrails,
    get_tool_guardrail_chain,
)

__all__ = [
    "GuardrailResult", 
    "LLMGuardrail", 
    "GuardrailProtocol", 
    "StructuralGuardrailProtocol", 
    "PolicyGuardrailProtocol", 
    "GuardrailChain",
    "GuardrailRetry",
    "is_guardrail_object",
    # Per-tool guardrails (declared via @tool(input_guardrails=/output_guardrails=))
    "ToolInputGuardrail",
    "ToolOutputGuardrail",
    "ToolGuardrailChain",
    "build_tool_guardrails",
    "get_tool_guardrail_chain",
]