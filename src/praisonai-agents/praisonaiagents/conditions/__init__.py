"""
Conditions Module - Unified condition evaluation for workflows.

This module provides a protocol-driven approach to condition evaluation,
enabling DRY condition handling across AgentFlow and AgentTeam.

Exports:
    - ConditionProtocol: Protocol interface for condition implementations
    - ExpressionCondition: String-based conditions like "{{score}} > 80"
    - DictCondition: Dict-based routing conditions
    - evaluate_condition: Standalone function for condition evaluation
"""
from .protocols import ConditionProtocol
from .evaluator import (
    ExpressionCondition,
    DictCondition,
    evaluate_condition,
)

__all__ = [
    'ConditionProtocol',
    'ExpressionCondition',
    'DictCondition',
    'evaluate_condition',
]
