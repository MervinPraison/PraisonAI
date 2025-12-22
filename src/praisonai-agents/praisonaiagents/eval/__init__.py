"""
PraisonAI Agents Evaluation Framework.

Provides comprehensive evaluation capabilities for AI agents with zero performance
impact when not in use through lazy loading.

Evaluator Types:
    - AccuracyEvaluator: Compare output against expected output using LLM-as-judge
    - PerformanceEvaluator: Measure runtime and memory usage
    - ReliabilityEvaluator: Verify expected tool calls are made
    - CriteriaEvaluator: Evaluate against custom criteria

Example:
    >>> from praisonaiagents.eval import AccuracyEvaluator
    >>> evaluator = AccuracyEvaluator(
    ...     agent=my_agent,
    ...     input_text="What is 2+2?",
    ...     expected_output="4"
    ... )
    >>> result = evaluator.run(print_summary=True)
"""

__all__ = [
    "BaseEvaluator",
    "AccuracyEvaluator",
    "PerformanceEvaluator",
    "ReliabilityEvaluator",
    "CriteriaEvaluator",
    "AccuracyResult",
    "PerformanceResult",
    "ReliabilityResult",
    "CriteriaResult",
    "EvaluationScore",
    "PerformanceMetrics",
    "ToolCallResult",
    "CriteriaScore",
]

_LAZY_IMPORTS = {
    "BaseEvaluator": ("base", "BaseEvaluator"),
    "AccuracyEvaluator": ("accuracy", "AccuracyEvaluator"),
    "PerformanceEvaluator": ("performance", "PerformanceEvaluator"),
    "ReliabilityEvaluator": ("reliability", "ReliabilityEvaluator"),
    "CriteriaEvaluator": ("criteria", "CriteriaEvaluator"),
    "AccuracyResult": ("results", "AccuracyResult"),
    "PerformanceResult": ("results", "PerformanceResult"),
    "ReliabilityResult": ("results", "ReliabilityResult"),
    "CriteriaResult": ("results", "CriteriaResult"),
    "EvaluationScore": ("results", "EvaluationScore"),
    "PerformanceMetrics": ("results", "PerformanceMetrics"),
    "ToolCallResult": ("results", "ToolCallResult"),
    "CriteriaScore": ("results", "CriteriaScore"),
}


def __getattr__(name: str):
    """Lazy import mechanism for zero-cost imports when not used."""
    if name in _LAZY_IMPORTS:
        module_name, attr_name = _LAZY_IMPORTS[name]
        import importlib
        module = importlib.import_module(f".{module_name}", __name__)
        return getattr(module, attr_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    """Return list of available attributes for tab completion."""
    return __all__
