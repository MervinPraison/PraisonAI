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
    "MediaEvaluator",
    "AccuracyResult",
    "PerformanceResult",
    "ReliabilityResult",
    "CriteriaResult",
    "MediaEvaluationResult",
    "EvaluationScore",
    "PerformanceMetrics",
    "ToolCallResult",
    "CriteriaScore",
    # DRY: Common grading base classes and protocols
    "BaseLLMGrader",
    "GradeResult",
    "GraderProtocol",
    "GradeResultProtocol",
    "ScoredResultProtocol",
    "AsyncGraderProtocol",
    "parse_score_reasoning",
    # Eval package types
    "EvalCase",
    "EvalResult",
    "EvalReport",
    "EvalPackage",
    "EvalRunnerProtocol",
    # Unified Judge API (follows add_X/get_X/list_X naming)
    "Judge",
    "JudgeConfig",
    "JudgeResult",
    "JudgeProtocol",
    "JudgeResultProtocol",
    "AccuracyJudge",
    "CriteriaJudge",
    "RecipeJudge",
    "add_judge",
    "get_judge",
    "list_judges",
    "remove_judge",
    # Dynamic judge configuration (domain-agnostic)
    "JudgeCriteriaConfig",
    "OptimizationRuleProtocol",
    "add_optimization_rule",
    "get_optimization_rule",
    "list_optimization_rules",
    "remove_optimization_rule",
    # Token utilities
    "estimate_tokens",
    "get_context_length",
    "count_tokens",
    "needs_chunking",
    "get_recommended_chunk_size",
]

_LAZY_IMPORTS = {
    "BaseEvaluator": ("base", "BaseEvaluator"),
    "AccuracyEvaluator": ("accuracy", "AccuracyEvaluator"),
    "PerformanceEvaluator": ("performance", "PerformanceEvaluator"),
    "ReliabilityEvaluator": ("reliability", "ReliabilityEvaluator"),
    "CriteriaEvaluator": ("criteria", "CriteriaEvaluator"),
    "MediaEvaluator": ("media", "MediaEvaluator"),
    "AccuracyResult": ("results", "AccuracyResult"),
    "PerformanceResult": ("results", "PerformanceResult"),
    "ReliabilityResult": ("results", "ReliabilityResult"),
    "CriteriaResult": ("results", "CriteriaResult"),
    "MediaEvaluationResult": ("media", "MediaEvaluationResult"),
    "EvaluationScore": ("results", "EvaluationScore"),
    "PerformanceMetrics": ("results", "PerformanceMetrics"),
    "ToolCallResult": ("results", "ToolCallResult"),
    "CriteriaScore": ("results", "CriteriaScore"),
    # DRY: Common grading base classes and protocols
    "BaseLLMGrader": ("grader", "BaseLLMGrader"),
    "GradeResult": ("grader", "GradeResult"),
    "GraderProtocol": ("protocols", "GraderProtocol"),
    "GradeResultProtocol": ("protocols", "GradeResultProtocol"),
    "ScoredResultProtocol": ("protocols", "ScoredResultProtocol"),
    "AsyncGraderProtocol": ("protocols", "AsyncGraderProtocol"),
    "parse_score_reasoning": ("grader", "parse_score_reasoning"),
    # Eval package types
    "EvalCase": ("package", "EvalCase"),
    "EvalResult": ("package", "EvalResult"),
    "EvalReport": ("package", "EvalReport"),
    "EvalPackage": ("package", "EvalPackage"),
    "EvalRunnerProtocol": ("package", "EvalRunnerProtocol"),
    # Unified Judge API (follows add_X/get_X/list_X naming)
    "Judge": ("judge", "Judge"),
    "JudgeConfig": ("judge", "JudgeConfig"),
    "JudgeResult": ("results", "JudgeResult"),
    "JudgeProtocol": ("protocols", "JudgeProtocol"),
    "JudgeResultProtocol": ("protocols", "JudgeResultProtocol"),
    "AccuracyJudge": ("judge", "AccuracyJudge"),
    "CriteriaJudge": ("judge", "CriteriaJudge"),
    "RecipeJudge": ("judge", "RecipeJudge"),
    "add_judge": ("judge", "add_judge"),
    "get_judge": ("judge", "get_judge"),
    "list_judges": ("judge", "list_judges"),
    "remove_judge": ("judge", "remove_judge"),
    # Dynamic judge configuration (domain-agnostic)
    "JudgeCriteriaConfig": ("judge", "JudgeCriteriaConfig"),
    "OptimizationRuleProtocol": ("protocols", "OptimizationRuleProtocol"),
    "add_optimization_rule": ("judge", "add_optimization_rule"),
    "get_optimization_rule": ("judge", "get_optimization_rule"),
    "list_optimization_rules": ("judge", "list_optimization_rules"),
    "remove_optimization_rule": ("judge", "remove_optimization_rule"),
    # Token utilities
    "estimate_tokens": ("tokens", "estimate_tokens"),
    "get_context_length": ("tokens", "get_context_length"),
    "count_tokens": ("tokens", "count_tokens"),
    "needs_chunking": ("tokens", "needs_chunking"),
    "get_recommended_chunk_size": ("tokens", "get_recommended_chunk_size"),
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
