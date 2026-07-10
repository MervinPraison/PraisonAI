"""
Configuration for Goal Engineering.

Follows the PraisonAI ``XConfig`` convention: ``False=disabled, True=defaults,
Config=custom``.
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class GoalConfig:
    """
    Configuration for the GoalEngineer.

    Attributes:
        model: LLM model used for decomposition/verification.
        max_criteria: Maximum number of success criteria to generate.
        threshold: Score (0-10) at/above which a goal is considered achieved.
        auto_decompose: Whether to auto-generate criteria via the LLM.
        verbose: Enable verbose logging.
    """

    model: Optional[str] = None
    max_criteria: int = 5
    threshold: float = 8.0
    auto_decompose: bool = True
    verbose: bool = False

    def __post_init__(self):
        if self.model is None:
            self.model = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
