"""
Goal Engineering Module for PraisonAI Agents.

Goal Engineering is the systematic practice of turning a vague objective into a
structured, measurable goal — a statement plus weighted success criteria and
constraints — then verifying agent output against it. It complements Context /
Harness / Loop (CHL) engineering by making the *goal* an explicit, testable
artifact.

Zero performance impact: all components are lazy loaded via ``__getattr__``.

Usage:
    from praisonaiagents.goal import GoalEngineer

    engineer = GoalEngineer()
    goal = engineer.engineer("Summarise the report in under 100 words")
    result = engineer.verify(goal, agent_output)
    print(result.score, result.achieved)
"""

__all__ = [
    # Core
    "GoalEngineer",
    "GoalConfig",
    # Models
    "Goal",
    "SuccessCriterion",
    "GoalVerificationResult",
    # Protocols
    "GoalDecomposerProtocol",
    "GoalVerifierProtocol",
    "GoalEngineerProtocol",
]

_LAZY_IMPORTS = {
    "GoalEngineer": ("engineer", "GoalEngineer"),
    "GoalConfig": ("config", "GoalConfig"),
    "Goal": ("models", "Goal"),
    "SuccessCriterion": ("models", "SuccessCriterion"),
    "GoalVerificationResult": ("models", "GoalVerificationResult"),
    "GoalDecomposerProtocol": ("protocols", "GoalDecomposerProtocol"),
    "GoalVerifierProtocol": ("protocols", "GoalVerifierProtocol"),
    "GoalEngineerProtocol": ("protocols", "GoalEngineerProtocol"),
}


def __getattr__(name: str):
    """Lazy load module components to avoid import overhead."""
    if name in _LAZY_IMPORTS:
        import importlib

        module_name, attr_name = _LAZY_IMPORTS[name]
        module = importlib.import_module(f".{module_name}", __name__)
        return getattr(module, attr_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return __all__
