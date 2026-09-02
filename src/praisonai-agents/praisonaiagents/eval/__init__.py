"""
PraisonAI Agents Evaluation Framework.

Provides comprehensive evaluation capabilities for AI agents with zero performance
impact when not in use through lazy loading.

Evaluator Types:
    - AccuracyEvaluator: Compare output against expected output using LLM-as-judge
    - PerformanceEvaluator: Measure runtime and memory usage
    - ReliabilityEvaluator: Verify expected tool calls are made
    - CriteriaEvaluator: Evaluate against custom criteria
    - ContextEvaluator: Score context budget compliance and multi-agent handoff fidelity
    - ComparisonEval: Side-by-side comparison of two agent outputs
    - SafetyEval: Detect harmful, biased, or inappropriate outputs
    - LoopEvaluator: Score loop health (convergence, wasted iterations, doom-loop guards)
    - EvalSuite: Orchestrator for running multiple evaluations

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
    "ContextEvaluator",
    "MediaEvaluator",
    "ComparisonEval",
    "SafetyEval",
    "HarnessEvaluator",
    "harness_row_to_eval_case",
    "HarnessResult",
    "EvalSuite",
    "AccuracyResult",
    "PerformanceResult",
    "ReliabilityResult",
    "CriteriaResult",
    "ContextHandoffResult",
    "BudgetComplianceResult",
    "ContextEvalResult",
    "MediaEvaluationResult",
    "ComparisonResult",
    "SafetyResult",
    "EvalSuiteResult",
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
    # EvalPort adapter (framework-neutral interop; dependency-free)
    "to_evalport",
    "from_evalport",
    "report_to_evalport",
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
    # EvaluationLoop (iterative improvement)
    "EvaluationLoop",
    "EvaluationLoopConfig",
    "IterationResult",
    "EvaluationLoopResult",
    "EvaluationLoopProtocol",
    "EvaluationLoopResultProtocol",
    # LoopEvaluator (loop health: convergence, waste, doom-loop guards)
    "LoopEvaluator",
    "LoopHealthResult",
    # PromptOptimizer (optimise agent.instructions against an eval, keep best)
    "PromptOptimizer",
    "OptimizeResult",
    # Trials engine (K isolated attempts per case, pass-rate + frontier)
    "run_trials",
    "arun_trials",
    "TrialScore",
    "TrialAttempt",
    "TrialReport",
]

from .._lazy import create_lazy_getattr

_LAZY_IMPORTS = {
    "BaseEvaluator": ("praisonaiagents.eval.base", "BaseEvaluator"),
    "AccuracyEvaluator": ("praisonaiagents.eval.accuracy", "AccuracyEvaluator"),
    "PerformanceEvaluator": ("praisonaiagents.eval.performance", "PerformanceEvaluator"),
    "ReliabilityEvaluator": ("praisonaiagents.eval.reliability", "ReliabilityEvaluator"),
    "CriteriaEvaluator": ("praisonaiagents.eval.criteria", "CriteriaEvaluator"),
    "ContextEvaluator": ("praisonaiagents.eval.context_eval", "ContextEvaluator"),
    "MediaEvaluator": ("praisonaiagents.eval.media", "MediaEvaluator"),
    "ComparisonEval": ("praisonaiagents.eval.comparison", "ComparisonEval"),
    "SafetyEval": ("praisonaiagents.eval.safety", "SafetyEval"),
    "HarnessEvaluator": ("praisonaiagents.eval.harness_eval", "HarnessEvaluator"),
    "harness_row_to_eval_case": ("praisonaiagents.eval.harness_eval", "harness_row_to_eval_case"),
    "HarnessResult": ("praisonaiagents.eval.results", "HarnessResult"),
    "EvalSuite": ("praisonaiagents.eval.suite", "EvalSuite"),
    "AccuracyResult": ("praisonaiagents.eval.results", "AccuracyResult"),
    "PerformanceResult": ("praisonaiagents.eval.results", "PerformanceResult"),
    "ReliabilityResult": ("praisonaiagents.eval.results", "ReliabilityResult"),
    "CriteriaResult": ("praisonaiagents.eval.results", "CriteriaResult"),
    "ContextHandoffResult": ("praisonaiagents.eval.context_eval", "ContextHandoffResult"),
    "BudgetComplianceResult": ("praisonaiagents.eval.context_eval", "BudgetComplianceResult"),
    "ContextEvalResult": ("praisonaiagents.eval.context_eval", "ContextEvalResult"),
    "MediaEvaluationResult": ("praisonaiagents.eval.media", "MediaEvaluationResult"),
    "ComparisonResult": ("praisonaiagents.eval.comparison", "ComparisonResult"),
    "SafetyResult": ("praisonaiagents.eval.safety", "SafetyResult"),
    "EvalSuiteResult": ("praisonaiagents.eval.suite", "EvalSuiteResult"),
    "EvaluationScore": ("praisonaiagents.eval.results", "EvaluationScore"),
    "PerformanceMetrics": ("praisonaiagents.eval.results", "PerformanceMetrics"),
    "ToolCallResult": ("praisonaiagents.eval.results", "ToolCallResult"),
    "CriteriaScore": ("praisonaiagents.eval.results", "CriteriaScore"),
    # DRY: Common grading base classes and protocols
    "BaseLLMGrader": ("praisonaiagents.eval.grader", "BaseLLMGrader"),
    "GradeResult": ("praisonaiagents.eval.grader", "GradeResult"),
    "GraderProtocol": ("praisonaiagents.eval.protocols", "GraderProtocol"),
    "GradeResultProtocol": ("praisonaiagents.eval.protocols", "GradeResultProtocol"),
    "ScoredResultProtocol": ("praisonaiagents.eval.protocols", "ScoredResultProtocol"),
    "AsyncGraderProtocol": ("praisonaiagents.eval.protocols", "AsyncGraderProtocol"),
    "parse_score_reasoning": ("praisonaiagents.eval.grader", "parse_score_reasoning"),
    # Eval package types
    "EvalCase": ("praisonaiagents.eval.package", "EvalCase"),
    "EvalResult": ("praisonaiagents.eval.package", "EvalResult"),
    "EvalReport": ("praisonaiagents.eval.package", "EvalReport"),
    "EvalPackage": ("praisonaiagents.eval.package", "EvalPackage"),
    "EvalRunnerProtocol": ("praisonaiagents.eval.package", "EvalRunnerProtocol"),
    # EvalPort adapter (framework-neutral interop; dependency-free)
    "to_evalport": ("praisonaiagents.eval.evalport", "to_evalport"),
    "from_evalport": ("praisonaiagents.eval.evalport", "from_evalport"),
    "report_to_evalport": ("praisonaiagents.eval.evalport", "report_to_evalport"),
    # Unified Judge API (follows add_X/get_X/list_X naming)
    "Judge": ("praisonaiagents.eval.judge", "Judge"),
    "JudgeConfig": ("praisonaiagents.eval.judge", "JudgeConfig"),
    "JudgeResult": ("praisonaiagents.eval.results", "JudgeResult"),
    "JudgeProtocol": ("praisonaiagents.eval.protocols", "JudgeProtocol"),
    "JudgeResultProtocol": ("praisonaiagents.eval.protocols", "JudgeResultProtocol"),
    "AccuracyJudge": ("praisonaiagents.eval.judge", "AccuracyJudge"),
    "CriteriaJudge": ("praisonaiagents.eval.judge", "CriteriaJudge"),
    "RecipeJudge": ("praisonaiagents.eval.judge", "RecipeJudge"),
    "add_judge": ("praisonaiagents.eval.judge", "add_judge"),
    "get_judge": ("praisonaiagents.eval.judge", "get_judge"),
    "list_judges": ("praisonaiagents.eval.judge", "list_judges"),
    "remove_judge": ("praisonaiagents.eval.judge", "remove_judge"),
    # Dynamic judge configuration (domain-agnostic)
    "JudgeCriteriaConfig": ("praisonaiagents.eval.judge", "JudgeCriteriaConfig"),
    "OptimizationRuleProtocol": ("praisonaiagents.eval.protocols", "OptimizationRuleProtocol"),
    "add_optimization_rule": ("praisonaiagents.eval.judge", "add_optimization_rule"),
    "get_optimization_rule": ("praisonaiagents.eval.judge", "get_optimization_rule"),
    "list_optimization_rules": ("praisonaiagents.eval.judge", "list_optimization_rules"),
    "remove_optimization_rule": ("praisonaiagents.eval.judge", "remove_optimization_rule"),
    # Token utilities
    "estimate_tokens": ("praisonaiagents.eval.tokens", "estimate_tokens"),
    "get_context_length": ("praisonaiagents.eval.tokens", "get_context_length"),
    "count_tokens": ("praisonaiagents.eval.tokens", "count_tokens"),
    "needs_chunking": ("praisonaiagents.eval.tokens", "needs_chunking"),
    "get_recommended_chunk_size": ("praisonaiagents.eval.tokens", "get_recommended_chunk_size"),
    # EvaluationLoop (iterative improvement)
    "EvaluationLoop": ("praisonaiagents.eval.loop", "EvaluationLoop"),
    "EvaluationLoopConfig": ("praisonaiagents.eval.loop", "EvaluationLoopConfig"),
    "IterationResult": ("praisonaiagents.eval.results", "IterationResult"),
    "EvaluationLoopResult": ("praisonaiagents.eval.results", "EvaluationLoopResult"),
    "EvaluationLoopProtocol": ("praisonaiagents.eval.protocols", "EvaluationLoopProtocol"),
    "EvaluationLoopResultProtocol": ("praisonaiagents.eval.protocols", "EvaluationLoopResultProtocol"),
    # LoopEvaluator (loop health: convergence, waste, doom-loop guards)
    "LoopEvaluator": ("praisonaiagents.eval.loop_eval", "LoopEvaluator"),
    "LoopHealthResult": ("praisonaiagents.eval.loop_eval", "LoopHealthResult"),
    # PromptOptimizer (optimise agent.instructions against an eval, keep best)
    "PromptOptimizer": ("praisonaiagents.eval.prompt_optimizer", "PromptOptimizer"),
    "OptimizeResult": ("praisonaiagents.eval.prompt_optimizer", "OptimizeResult"),
    # Trials engine (K isolated attempts per case, pass-rate + frontier)
    "run_trials": ("praisonaiagents.eval.trials", "run_trials"),
    "arun_trials": ("praisonaiagents.eval.trials", "arun_trials"),
    "TrialScore": ("praisonaiagents.eval.trials", "TrialScore"),
    "TrialAttempt": ("praisonaiagents.eval.trials", "TrialAttempt"),
    "TrialReport": ("praisonaiagents.eval.trials", "TrialReport"),
}

__getattr__ = create_lazy_getattr(_LAZY_IMPORTS, __name__)


def __dir__():
    """Return list of available attributes for tab completion."""
    return __all__
